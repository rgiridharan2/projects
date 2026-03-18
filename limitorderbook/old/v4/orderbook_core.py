# orderbook_core.py
"""
High-Performance Limit Order Book Implementation
Author: [Your Name]
Purpose: Order book reconstruction and signal generation for HFT research
"""

import numpy as np
import pandas as pd
from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Dict, List, Tuple, Optional
import time
from enum import IntEnum
import numba
from numba import jit
from scipy import stats as sp_stats
from scipy.linalg import solve_discrete_are
import warnings
warnings.filterwarnings('ignore')

# ==================== DATA STRUCTURES ====================

class Side(IntEnum):
    """Order side enumeration"""
    BID = 1
    ASK = -1

class EventType(IntEnum):
    """LOBSTER message types"""
    NEW_LIMIT = 1
    CANCELLATION = 2
    DELETION = 3
    EXECUTION_VISIBLE = 4
    EXECUTION_HIDDEN = 5
    CROSS_TRADE = 6
    TRADING_HALT = 7

@dataclass
class Level:
    """Single price level in the order book"""
    price: float
    size: int
    
    def __repr__(self):
        return f"({self.price:.2f}@{self.size})"

@dataclass
class BookSnapshot:
    """Point-in-time order book snapshot"""
    timestamp: float
    bids: List[Level]  # Sorted descending
    asks: List[Level]  # Sorted ascending
    
    @property
    def best_bid(self) -> Optional[float]:
        return self.bids[0].price if self.bids else None
    
    @property
    def best_ask(self) -> Optional[float]:
        return self.asks[0].price if self.asks else None
    
    @property
    def mid_price(self) -> Optional[float]:
        if self.best_bid and self.best_ask:
            return (self.best_bid + self.best_ask) / 2
        return None
    
    @property
    def spread(self) -> Optional[float]:
        if self.best_bid and self.best_ask:
            return self.best_ask - self.best_bid
        return None
    
    @property
    def microprice(self) -> Optional[float]:
        """Volume-weighted microprice"""
        if not self.bids or not self.asks:
            return None
        
        bid_price = self.bids[0].price
        ask_price = self.asks[0].price
        bid_size = self.bids[0].size
        ask_size = self.asks[0].size
        
        if bid_size + ask_size == 0:
            return self.mid_price
        
        return (bid_price * ask_size + ask_price * bid_size) / (bid_size + ask_size)
    
    def get_imbalance(self, levels: int = 1) -> float:
        """Order flow imbalance at top N levels"""
        bid_vol = sum(b.size for b in self.bids[:levels])
        ask_vol = sum(a.size for a in self.asks[:levels])
        total = bid_vol + ask_vol
        
        if total == 0:
            return 0.0
        
        return (bid_vol - ask_vol) / total

# ==================== ORDER BOOK ENGINE ====================

class OrderBook:
    """
    High-performance limit order book with O(1) updates
    
    Performance target: >10,000 messages/second
    """
    
    def __init__(self, tick_size: float = 0.01, num_levels: int = 10):
        """
        Args:
            tick_size: Minimum price increment
            num_levels: Number of levels to track on each side
        """
        self.tick_size = tick_size
        self.num_levels = num_levels
        
        # Price -> Size mapping for fast lookups
        self.bids: Dict[float, int] = {}
        self.asks: Dict[float, int] = {}
        
        # Sorted price levels (maintained on updates)
        self.bid_prices: List[float] = []
        self.ask_prices: List[float] = []
        
        # Performance metrics
        self.message_count = 0
        self.last_update_time = 0.0
        
        # Event tracking
        self.trade_events: List[Dict] = []
        self.book_events: List[Dict] = []
        
    def process_lobster_message(self, timestamp: float, event_type: int, 
                                order_id: int, size: int, price: float, 
                                direction: int) -> None:
        """
        Process LOBSTER format message
        
        Args:
            timestamp: Event timestamp (seconds)
            event_type: EventType enum value
            order_id: Unique order identifier
            size: Order size (shares)
            price: Order price
            direction: 1 for sell limit order (ask), -1 for buy (bid)
        """
        self.last_update_time = timestamp
        self.message_count += 1
        
        # Convert direction to side
        side = Side.ASK if direction == 1 else Side.BID
        
        if event_type == EventType.NEW_LIMIT:
            self._add_order(side, price, size)
            
        elif event_type == EventType.CANCELLATION:
            self._cancel_order(side, price, size)
            
        elif event_type in [EventType.EXECUTION_VISIBLE, EventType.EXECUTION_HIDDEN]:
            self._execute_order(side, price, size, timestamp)
            
        elif event_type == EventType.DELETION:
            self._delete_order(side, price, size)
        
        # Prevent crossed book after every update
        self._uncross_book()
    
    def _add_order(self, side: Side, price: float, size: int) -> None:
        """Add new limit order"""
        book = self.asks if side == Side.ASK else self.bids
        prices = self.ask_prices if side == Side.ASK else self.bid_prices
        
        if price in book:
            book[price] += size
        else:
            book[price] = size
            # Insert price in sorted order
            self._insert_price(prices, price, side)
        
        # Trim to top N levels
        self._trim_book(side)
    
    def _cancel_order(self, side: Side, price: float, size: int) -> None:
        """Cancel existing order"""
        book = self.asks if side == Side.ASK else self.bids
        prices = self.ask_prices if side == Side.ASK else self.bid_prices
        
        if price in book:
            book[price] = max(0, book[price] - size)
            if book[price] == 0:
                del book[price]
                prices.remove(price)
    
    def _execute_order(self, side: Side, price: float, size: int, 
                      timestamp: float) -> None:
        """Execute order (reduces book size)"""
        self._cancel_order(side, price, size)
        
        # Track trade event
        self.trade_events.append({
            'timestamp': timestamp,
            'price': price,
            'size': size,
            'side': 'buy' if side == Side.BID else 'sell'
        })
    
    def _delete_order(self, side: Side, price: float, size: int) -> None:
        """Delete order completely"""
        self._cancel_order(side, price, size)
    
    def _insert_price(self, prices: List[float], price: float, side: Side) -> None:
        """Insert price maintaining sorted order"""
        if side == Side.BID:
            # Bids: descending order
            idx = np.searchsorted([-p for p in prices], -price)
        else:
            # Asks: ascending order
            idx = np.searchsorted(prices, price)
        prices.insert(idx, price)
    
    def _trim_book(self, side: Side) -> None:
        """Keep only top N levels"""
        prices = self.ask_prices if side == Side.ASK else self.bid_prices
        book = self.asks if side == Side.ASK else self.bids
        
        if len(prices) > self.num_levels:
            # Remove furthest prices
            for price in prices[self.num_levels:]:
                if price in book:
                    del book[price]
            
            if side == Side.BID:
                self.bid_prices = prices[:self.num_levels]
            else:
                self.ask_prices = prices[:self.num_levels]
    
    def _uncross_book(self) -> None:
        """
        Remove crossed levels where best_bid >= best_ask.
        This can happen with synthetic data or out-of-order messages.
        """
        while (self.bid_prices and self.ask_prices and 
               self.bid_prices[0] >= self.ask_prices[0]):
            crossed_bid = self.bid_prices[0]
            crossed_ask = self.ask_prices[0]
            if crossed_bid in self.bids:
                del self.bids[crossed_bid]
            self.bid_prices.pop(0)
            if crossed_ask in self.asks:
                del self.asks[crossed_ask]
            self.ask_prices.pop(0)
    
    @property
    def is_crossed(self) -> bool:
        """Check if book is in a crossed state"""
        if self.bid_prices and self.ask_prices:
            return self.bid_prices[0] >= self.ask_prices[0]
        return False
    
    def get_snapshot(self, num_levels: int = 5) -> BookSnapshot:
        """
        Get current book state
        
        Args:
            num_levels: Number of levels to include
            
        Returns:
            BookSnapshot object
        """
        bids = [Level(p, self.bids[p]) for p in self.bid_prices[:num_levels] if p in self.bids]
        asks = [Level(p, self.asks[p]) for p in self.ask_prices[:num_levels] if p in self.asks]
        
        return BookSnapshot(
            timestamp=self.last_update_time,
            bids=bids,
            asks=asks
        )
    
    def get_metrics(self) -> Dict:
        """Performance and state metrics"""
        return {
            'messages_processed': self.message_count,
            'bid_levels': len(self.bid_prices),
            'ask_levels': len(self.ask_prices),
            'total_bid_volume': sum(self.bids.values()),
            'total_ask_volume': sum(self.asks.values()),
            'trades': len(self.trade_events)
        }

# ==================== SIGNAL PROCESSING ====================

class KalmanFilter:
    """
    1D Kalman filter for signal denoising
    
    State space model:
        x_t = x_{t-1} + w_t    (process noise)
        y_t = x_t + v_t        (measurement noise)
    """
    
    def __init__(self, process_variance: float = 1e-3, 
                 measurement_variance: float = 0.01):
        """
        Args:
            process_variance: Q - how much we expect signal to change
            measurement_variance: R - measurement noise level
            
        Note: Q/R ratio controls responsiveness. For HFT signals that change
        rapidly, use Q/R >= 0.01. A value of 1e-5 is far too sticky.
        """
        self.Q = process_variance
        self.R = measurement_variance
        
        # State estimate and covariance
        self.x = 0.0  # State estimate
        self.P = 1.0  # Estimate covariance
        
        self.initialized = False
    
    def update(self, measurement: float) -> float:
        """
        Update filter with new measurement
        
        Args:
            measurement: New observed value
            
        Returns:
            Filtered estimate
        """
        if not self.initialized:
            self.x = measurement
            self.initialized = True
            return self.x
        
        # Prediction step
        x_pred = self.x
        P_pred = self.P + self.Q
        
        # Update step
        K = P_pred / (P_pred + self.R)  # Kalman gain
        self.x = x_pred + K * (measurement - x_pred)
        self.P = (1 - K) * P_pred
        
        return self.x

@jit(nopython=True)
def exponential_smooth(values: np.ndarray, alpha: float) -> np.ndarray:
    """
    Fast exponential smoothing using Numba
    
    Args:
        values: Input array
        alpha: Smoothing parameter (0 to 1)
        
    Returns:
        Smoothed array
    """
    result = np.empty_like(values)
    result[0] = values[0]
    
    for i in range(1, len(values)):
        result[i] = alpha * values[i] + (1 - alpha) * result[i-1]
    
    return result

@jit(nopython=True)
def rolling_zscore(values: np.ndarray, window: int) -> np.ndarray:
    """
    Fast rolling z-score computation
    
    Args:
        values: Input array
        window: Rolling window size
        
    Returns:
        Z-score normalized array
    """
    n = len(values)
    result = np.zeros(n)
    
    for i in range(window, n):
        window_data = values[i-window:i]
        mean = np.mean(window_data)
        std = np.std(window_data)
        
        if std > 1e-8:
            result[i] = (values[i] - mean) / std
        else:
            result[i] = 0.0
    
    return result

# ==================== KALMAN FILTER CONVERGENCE ANALYSIS ====================

class KalmanConvergenceAnalyzer:
    """
    Rigorous analysis of the 1D Kalman filter's convergence properties.
    
    For our scalar state-space model:
        x_{t+1} = x_t + w_t,    w_t ~ N(0, Q)
        y_t     = x_t + v_t,    v_t ~ N(0, R)
    
    We prove and numerically verify:
    1. The error covariance P_t converges to a unique fixed point P_∞
       satisfying the Discrete Algebraic Riccati Equation (DARE).
    2. The steady-state Kalman gain K_∞ = P_∞ / (P_∞ + R).
    3. Convergence is geometric: |P_t - P_∞| ≤ C · ρ^t for ρ < 1.
    4. The innovation sequence ε_t = y_t - ŷ_t should be white noise
       under correct model specification (Ljung-Box test).
    
    Mathematical background:
        The DARE for the scalar case is:
            P = (P + Q) - (P + Q)^2 / (P + Q + R)
        which simplifies to the quadratic:
            P^2 + (Q - R)P - QR = 0
        with unique positive root:
            P_∞ = [-(Q - R) + sqrt((Q - R)^2 + 4QR)] / 2
                = [-(Q - R) + sqrt((Q + R)^2)] / 2
                = [-(Q - R) + (Q + R)] / 2    (since Q, R > 0)
                = R
        
        Wait — that's the degenerate case for F=1, H=1. More carefully:
        The Riccati recursion is P⁻ = P + Q, then P = P⁻ - P⁻²/(P⁻+R).
        At steady state P_∞ satisfies:
            P_∞ = (P_∞ + Q) · R / (P_∞ + Q + R)
        Rearranging: P_∞(P_∞ + Q + R) = (P_∞ + Q)R
            P_∞² + QP_∞ + RP_∞ = RP_∞ + QR
            P_∞² + QP_∞ - QR = 0
        Positive root: P_∞ = [-Q + sqrt(Q² + 4QR)] / 2
    """
    
    def __init__(self, Q: float, R: float):
        """
        Args:
            Q: Process noise variance
            R: Measurement noise variance
        """
        if Q <= 0 or R <= 0:
            raise ValueError("Q and R must be strictly positive")
        self.Q = Q
        self.R = R
    
    def steady_state_covariance(self) -> float:
        """
        Compute the steady-state error covariance P_∞ analytically.
        
        Solves P² + QP - QR = 0 via the quadratic formula.
        The unique positive root is:
            P_∞ = [-Q + √(Q² + 4QR)] / 2
        
        Returns:
            P_∞: Steady-state estimation error covariance
        """
        discriminant = self.Q**2 + 4 * self.Q * self.R
        P_inf = (-self.Q + np.sqrt(discriminant)) / 2.0
        return P_inf
    
    def steady_state_gain(self) -> float:
        """
        Compute the steady-state Kalman gain K_∞.
        
        K_∞ = (P_∞ + Q) / (P_∞ + Q + R)
        
        Properties:
        - K_∞ ∈ (0, 1) for all Q, R > 0
        - K_∞ → 1 as Q/R → ∞  (trust measurements)
        - K_∞ → 0 as Q/R → 0  (trust prediction)
        
        Returns:
            K_∞: Steady-state Kalman gain
        """
        P_inf = self.steady_state_covariance()
        P_pred = P_inf + self.Q
        return P_pred / (P_pred + self.R)
    
    def convergence_rate(self) -> float:
        """
        Compute the geometric convergence rate ρ of the Riccati recursion.
        
        For the scalar case, the contraction factor of the Riccati map
        T(P) = (P + Q)R / (P + Q + R) at the fixed point P_∞ is:
        
            ρ = |T'(P_∞)| = R² / (P_∞ + Q + R)²
        
        This gives |P_t - P_∞| ≤ |P_0 - P_∞| · ρ^t.
        
        Returns:
            ρ: Geometric convergence rate (smaller = faster convergence)
        """
        P_inf = self.steady_state_covariance()
        denom = P_inf + self.Q + self.R
        rho = (self.R / denom) ** 2
        return rho
    
    def verify_convergence_numerically(self, P_0: float = 1.0, 
                                        n_steps: int = 200,
                                        tol: float = 1e-12) -> Dict:
        """
        Numerically verify that the Riccati recursion converges to P_∞.
        
        Iterates the recursion P_{t+1} = (P_t + Q)R / (P_t + Q + R)
        from initial condition P_0 and checks:
        1. Convergence to the analytical P_∞
        2. Geometric convergence rate matches the theoretical bound
        3. Steps to convergence within tolerance
        
        Args:
            P_0: Initial error covariance
            n_steps: Maximum iterations
            tol: Convergence tolerance
            
        Returns:
            Dictionary with convergence diagnostics
        """
        P_inf_analytical = self.steady_state_covariance()
        rho_theoretical = self.convergence_rate()
        
        P_trajectory = np.zeros(n_steps)
        P = P_0
        converged_step = n_steps
        
        for t in range(n_steps):
            P_pred = P + self.Q
            P = P_pred * self.R / (P_pred + self.R)  # Riccati update
            P_trajectory[t] = P
            
            if abs(P - P_inf_analytical) < tol and converged_step == n_steps:
                converged_step = t + 1
        
        # Estimate empirical convergence rate from trajectory
        errors = np.abs(P_trajectory - P_inf_analytical)
        # Use log-ratio of successive errors (away from machine epsilon)
        valid = errors > 1e-14
        if valid.sum() > 2:
            log_errors = np.log(errors[valid])
            # Linear regression on log(error) vs step to get rate
            steps_valid = np.where(valid)[0]
            if len(steps_valid) > 2:
                slope, _, r_value, _, _ = sp_stats.linregress(
                    steps_valid[:min(50, len(steps_valid))], 
                    log_errors[:min(50, len(log_errors))]
                )
                rho_empirical = np.exp(slope)
            else:
                rho_empirical = np.nan
        else:
            rho_empirical = np.nan
        
        return {
            'P_inf_analytical': P_inf_analytical,
            'P_inf_numerical': P_trajectory[-1],
            'K_inf': self.steady_state_gain(),
            'rho_theoretical': rho_theoretical,
            'rho_empirical': rho_empirical,
            'converged_at_step': converged_step,
            'P_trajectory': P_trajectory,
            'agreement': abs(P_trajectory[-1] - P_inf_analytical) < 1e-10,
            'snr_db': 10 * np.log10(self.Q / self.R)  # Signal-to-noise ratio
        }
    
    def innovation_consistency_test(self, measurements: np.ndarray,
                                     max_lag: int = 20) -> Dict:
        """
        Test whether the Kalman filter's innovation sequence is white noise.
        
        Under correct model specification, the innovations
            ε_t = y_t - ŷ_{t|t-1}
        should be:
        1. Zero-mean (t-test)
        2. Uncorrelated (Ljung-Box test on autocorrelations)
        3. Homoscedastic (consistent with predicted variance P⁻_t + R)
        
        This is the standard diagnostic for filter consistency
        (Bar-Shalom, Li & Kirubarajan, "Estimation with Applications 
        to Tracking and Navigation", Ch. 5).
        
        Args:
            measurements: Observed signal values
            max_lag: Maximum lag for autocorrelation test
            
        Returns:
            Dictionary with test results and p-values
        """
        n = len(measurements)
        if n < max_lag + 10:
            return {'error': 'Insufficient data for innovation test'}
        
        # Run Kalman filter and collect innovations
        kf = KalmanFilter(process_variance=self.Q, measurement_variance=self.R)
        innovations = np.zeros(n)
        predicted_variances = np.zeros(n)
        
        x = 0.0
        P = 1.0
        
        for t in range(n):
            if t == 0:
                innovations[t] = measurements[t]  # No prior prediction
                x = measurements[t]
                continue
            
            # Prediction
            x_pred = x
            P_pred = P + self.Q
            
            # Innovation
            innovations[t] = measurements[t] - x_pred
            predicted_variances[t] = P_pred + self.R
            
            # Update
            K = P_pred / (P_pred + self.R)
            x = x_pred + K * innovations[t]
            P = (1 - K) * P_pred
        
        # Discard burn-in (first 10% or 50 samples)
        burn_in = max(50, n // 10)
        innov = innovations[burn_in:]
        pred_var = predicted_variances[burn_in:]
        
        # Test 1: Zero-mean (one-sample t-test)
        t_stat, t_pvalue = sp_stats.ttest_1samp(innov, 0.0)
        
        # Test 2: Whiteness (Ljung-Box)
        # Q_LB = n(n+2) Σ_{k=1}^{m} r_k² / (n-k)
        n_innov = len(innov)
        autocorrs = np.array([
            np.corrcoef(innov[:-k], innov[k:])[0, 1] 
            for k in range(1, max_lag + 1)
        ])
        
        Q_LB = n_innov * (n_innov + 2) * np.sum(
            autocorrs**2 / (n_innov - np.arange(1, max_lag + 1))
        )
        lb_pvalue = 1 - sp_stats.chi2.cdf(Q_LB, df=max_lag)
        
        # Test 3: Normalized innovations should have unit variance
        # NIS = ε_t² / S_t where S_t = P⁻_t + R (innovation covariance)
        valid_var = pred_var > 0
        nis = (innov[valid_var]**2) / pred_var[valid_var]
        # Simplified: just use the steady-state variance
        P_inf = self.steady_state_covariance()
        S_inf = P_inf + self.Q + self.R
        nis_simple = innov**2 / S_inf
        mean_nis = np.mean(nis_simple)
        # Under correct specification, E[NIS] = 1
        # Test with chi-squared: n * mean_nis ~ chi²(n)
        
        return {
            'zero_mean_t_stat': t_stat,
            'zero_mean_p_value': t_pvalue,
            'zero_mean_pass': t_pvalue > 0.05,
            'ljung_box_Q': Q_LB,
            'ljung_box_p_value': lb_pvalue,
            'whiteness_pass': lb_pvalue > 0.05,
            'mean_nis': mean_nis,
            'nis_consistent': 0.5 < mean_nis < 2.0,
            'innovation_std': np.std(innov),
            'predicted_std': np.sqrt(S_inf),
            'max_autocorr': np.max(np.abs(autocorrs)),
            'autocorrelations': autocorrs
        }


class SignalGenerator:
    """
    Generate predictive signals from order book data.
    
    Signals:
    - ofi: Raw order flow imbalance (Kalman-filtered)
    - delta_ofi: Change in OFI — typically more predictive than level
    - trade_imbalance: Net signed trade pressure from recent executions
    - spread_pressure: Spread compression/expansion z-score
    - composite: Weighted combination of above signals
    """
    
    def __init__(self, trade_window: int = 50):
        self.ofi_filter = KalmanFilter(process_variance=1e-3, 
                                       measurement_variance=0.01)
        self.signals_history = defaultdict(list)
        self.prev_ofi = 0.0
        self.ofi_initialized = False
        
        # Trade tracking for trade_imbalance signal
        self.recent_trades = deque(maxlen=trade_window)
        self.trade_window = trade_window
        
    def compute_ofi(self, snapshot: BookSnapshot, levels: int = 3) -> float:
        """
        Order Flow Imbalance
        
        Raw OFI = (Bid Volume - Ask Volume) / Total Volume
        """
        raw_ofi = snapshot.get_imbalance(levels)
        
        # Apply Kalman filter for denoising
        filtered_ofi = self.ofi_filter.update(raw_ofi)
        
        self.signals_history['ofi_raw'].append(raw_ofi)
        self.signals_history['ofi_filtered'].append(filtered_ofi)
        
        return filtered_ofi
    
    def compute_delta_ofi(self, snapshot: BookSnapshot, levels: int = 3) -> float:
        """
        Change in Order Flow Imbalance.
        
        In microstructure theory, the *change* in imbalance is more predictive
        than the level. A sudden shift toward bid-heavy imbalance suggests
        incoming buy pressure that hasn't yet been reflected in price.
        """
        current_ofi = snapshot.get_imbalance(levels)
        
        if not self.ofi_initialized:
            self.prev_ofi = current_ofi
            self.ofi_initialized = True
            delta = 0.0
        else:
            delta = current_ofi - self.prev_ofi
            self.prev_ofi = current_ofi
        
        self.signals_history['delta_ofi'].append(delta)
        return delta
    
    def compute_trade_imbalance(self, order_book: 'OrderBook') -> float:
        """
        Net signed trade pressure from recent executions.
        
        Tracks whether recent trades have been predominantly buyer- or
        seller-initiated. A burst of buy-side executions (hitting asks)
        suggests upward pressure.
        
        Returns value in [-1, 1] where positive = buy pressure.
        """
        # Grab new trades since last call
        new_trades = order_book.trade_events[len(self.recent_trades):]
        for t in new_trades:
            # In LOBSTER: execution removes from the resting side
            # If a bid order was executed (resting bid hit by incoming sell),
            # that's sell pressure. If ask executed, that's buy pressure.
            signed_size = t['size'] if t['side'] == 'sell' else -t['size']
            self.recent_trades.append(signed_size)
        
        if len(self.recent_trades) == 0:
            return 0.0
        
        buy_vol = sum(s for s in self.recent_trades if s > 0)
        sell_vol = sum(abs(s) for s in self.recent_trades if s < 0)
        total = buy_vol + sell_vol
        
        if total == 0:
            return 0.0
        
        imbalance = (buy_vol - sell_vol) / total
        self.signals_history['trade_imbalance'].append(imbalance)
        return imbalance
    
    def compute_microprice(self, snapshot: BookSnapshot) -> Optional[float]:
        """
        Volume-weighted microprice
        More responsive than mid-price
        """
        mp = snapshot.microprice
        if mp is not None:
            self.signals_history['microprice'].append(mp)
        return mp
    
    def compute_spread_pressure(self, snapshot: BookSnapshot, 
                                window: int = 100) -> float:
        """
        Normalized spread pressure
        
        Measures spread compression/expansion relative to recent history
        """
        spread = snapshot.spread
        if spread is None:
            return 0.0
        
        self.signals_history['spread'].append(spread)
        
        if len(self.signals_history['spread']) < window:
            return 0.0
        
        recent_spreads = self.signals_history['spread'][-window:]
        mean_spread = np.mean(recent_spreads)
        std_spread = np.std(recent_spreads)
        
        if std_spread < 1e-8:
            return 0.0
        
        pressure = (spread - mean_spread) / std_spread
        self.signals_history['spread_pressure'].append(pressure)
        
        return pressure
    
    def compute_composite(self, delta_ofi: float, trade_imbalance: float,
                          spread_pressure: float) -> float:
        """
        Composite signal combining multiple alpha sources.
        
        Weights are set heuristically. In production these would be
        fitted via regression or learned from data.
        """
        composite = (
            0.40 * delta_ofi +
            0.40 * trade_imbalance +
            0.20 * (-spread_pressure)  # Spread widening = negative pressure
        )
        self.signals_history['composite'].append(composite)
        return composite
    
    def compute_all_signals(self, snapshot: BookSnapshot, 
                           order_book: 'OrderBook' = None) -> Dict[str, float]:
        """Compute all signals for a snapshot"""
        ofi = self.compute_ofi(snapshot)
        delta_ofi = self.compute_delta_ofi(snapshot)
        sp = self.compute_spread_pressure(snapshot)
        
        trade_imb = 0.0
        if order_book is not None:
            trade_imb = self.compute_trade_imbalance(order_book)
        
        composite = self.compute_composite(delta_ofi, trade_imb, sp)
        
        return {
            'ofi': ofi,
            'delta_ofi': delta_ofi,
            'trade_imbalance': trade_imb,
            'spread_pressure': sp,
            'composite': composite,
            'microprice': self.compute_microprice(snapshot),
            'mid_price': snapshot.mid_price,
            'spread': snapshot.spread,
            'timestamp': snapshot.timestamp
        }

# ==================== PREDICTIVE ANALYSIS ====================

class PredictiveAnalyzer:
    """
    Analyze forecasting power of signals
    """
    
    def __init__(self, horizons_ms: List[int] = [100, 500, 1000, 5000]):
        """
        Args:
            horizons_ms: Prediction horizons in milliseconds
        """
        self.horizons_ms = horizons_ms
        self.signal_data = []
        self.price_returns = defaultdict(list)
        
    def record_signal(self, signals: Dict[str, float], 
                     current_price: float) -> None:
        """Record signal values and current price"""
        record = signals.copy()
        record['price'] = current_price
        self.signal_data.append(record)
    
    def compute_forward_returns(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Compute forward returns at multiple horizons
        
        Args:
            df: DataFrame with 'timestamp' and 'price' columns
            
        Returns:
            DataFrame with forward return columns
        """
        df = df.copy()
        
        for horizon_ms in self.horizons_ms:
            horizon_sec = horizon_ms / 1000.0
            col_name = f'fwd_ret_{horizon_ms}ms'
            
            # Find future price at each horizon
            future_prices = []
            for idx, row in df.iterrows():
                target_time = row['timestamp'] + horizon_sec
                
                # Find closest future timestamp
                future_mask = df['timestamp'] >= target_time
                if future_mask.any():
                    future_price = df.loc[future_mask, 'price'].iloc[0]
                    ret = (future_price - row['price']) / row['price']
                    future_prices.append(ret)
                else:
                    future_prices.append(np.nan)
            
            df[col_name] = future_prices
        
        return df
    
    def analyze_predictive_power(self, signal_name: str = 'ofi') -> pd.DataFrame:
        """
        Analyze signal's predictive power across horizons
        
        Args:
            signal_name: Name of signal to analyze
            
        Returns:
            DataFrame with correlation, hit rate, and profitability metrics
        """
        df = pd.DataFrame(self.signal_data)
        
        if signal_name not in df.columns:
            raise ValueError(f"Signal {signal_name} not found")
        
        # Compute forward returns
        df = self.compute_forward_returns(df)
        
        results = []
        
        for horizon_ms in self.horizons_ms:
            ret_col = f'fwd_ret_{horizon_ms}ms'
            
            if ret_col not in df.columns:
                continue
            
            # Remove NaN values
            valid_mask = df[signal_name].notna() & df[ret_col].notna()
            signal_vals = df.loc[valid_mask, signal_name]
            returns = df.loc[valid_mask, ret_col]
            
            if len(signal_vals) < 10:
                continue
            
            # Correlation
            correlation = signal_vals.corr(returns)
            
            # Directional accuracy
            signal_direction = np.sign(signal_vals)
            return_direction = np.sign(returns)
            hit_rate = (signal_direction == return_direction).mean()
            
            # Quintile analysis
            df_valid = df[valid_mask].copy()
            try:
                df_valid['quintile'] = pd.qcut(df_valid[signal_name], 5, 
                                               labels=['Q1', 'Q2', 'Q3', 'Q4', 'Q5'],
                                               duplicates='drop')
            except ValueError:
                # When duplicates='drop' reduces bin count, use auto labels
                df_valid['quintile'] = pd.qcut(df_valid[signal_name], 5, 
                                               duplicates='drop')
            
            quintile_returns = df_valid.groupby('quintile')[ret_col].mean()
            
            results.append({
                'horizon_ms': horizon_ms,
                'correlation': correlation,
                'hit_rate': hit_rate,
                'mean_return': returns.mean(),
                'sharpe': returns.mean() / returns.std() if returns.std() > 0 else 0,
                'q1_return': quintile_returns.get('Q1', np.nan),
                'q5_return': quintile_returns.get('Q5', np.nan),
                'q5_q1_spread': quintile_returns.get('Q5', 0) - quintile_returns.get('Q1', 0)
            })
        
        return pd.DataFrame(results)
    
    def signal_decay_analysis(self, signal_name: str = 'ofi', 
                             max_horizon_ms: int = 10000,
                             step_ms: int = 100) -> pd.DataFrame:
        """
        Analyze how quickly signal predictive power decays
        
        Args:
            signal_name: Signal to analyze
            max_horizon_ms: Maximum horizon to test
            step_ms: Step size for horizons
            
        Returns:
            DataFrame with decay curve
        """
        df = pd.DataFrame(self.signal_data)
        
        horizons = list(range(step_ms, max_horizon_ms + step_ms, step_ms))
        correlations = []
        
        for horizon_ms in horizons:
            horizon_sec = horizon_ms / 1000.0
            
            future_returns = []
            for idx, row in df.iterrows():
                target_time = row['timestamp'] + horizon_sec
                future_mask = df['timestamp'] >= target_time
                
                if future_mask.any():
                    future_price = df.loc[future_mask, 'price'].iloc[0]
                    ret = (future_price - row['price']) / row['price']
                    future_returns.append(ret)
                else:
                    future_returns.append(np.nan)
            
            df[f'ret_{horizon_ms}'] = future_returns
            
            valid_mask = df[signal_name].notna() & df[f'ret_{horizon_ms}'].notna()
            
            if valid_mask.sum() > 10:
                corr = df.loc[valid_mask, signal_name].corr(
                    df.loc[valid_mask, f'ret_{horizon_ms}']
                )
                correlations.append(corr)
            else:
                correlations.append(np.nan)
        
        return pd.DataFrame({
            'horizon_ms': horizons,
            'correlation': correlations
        })

# ==================== STATISTICAL SIGNIFICANCE TESTING ====================

class SignalSignificanceTester:
    """
    Rigorous statistical tests for whether signal predictive power is
    significantly different from zero.
    
    The naive approach (just report the correlation) is insufficient because:
    1. Autocorrelation in both signal and returns inflates the effective
       sample size, producing spurious significance under standard tests.
    2. Multiple testing across horizons/signals inflates family-wise error.
    3. Microstructure noise can create mechanical correlations.
    
    We implement:
    A) Fisher z-transformation with Newey-West effective sample size
    B) Block bootstrap permutation test (nonparametric, assumption-free)
    C) Benjamini-Hochberg FDR correction for multiple comparisons
    D) Hansen's Superior Predictive Ability (SPA) test concept
    
    References:
    - Fisher (1915), "Frequency distribution of the correlation coefficient"
    - Newey & West (1987), "A Simple, Positive Semi-definite, 
      Heteroskedasticity and Autocorrelation Consistent Covariance Matrix"
    - Romano & Wolf (2005), "Stepwise multiple testing as formalized 
      data snooping"
    """
    
    @staticmethod
    def fisher_z_test(signal: np.ndarray, returns: np.ndarray,
                      newey_west_lags: int = None) -> Dict:
        """
        Test H₀: ρ = 0 using Fisher's z-transformation with
        autocorrelation-adjusted effective sample size.
        
        The Fisher z-transform maps r → z = arctanh(r), which is
        approximately N(arctanh(ρ), 1/(n-3)) for large n.
        
        Under H₀: ρ = 0, this gives z = arctanh(r) ~ N(0, 1/(n_eff-3))
        where n_eff accounts for serial dependence.
        
        Effective sample size (Bartlett, 1935):
            n_eff = n / (1 + 2·Σ_{k=1}^{K} (1 - k/(K+1)) · γ_xy(k))
        where γ_xy(k) = corr(x_t, x_{t+k}) · corr(y_t, y_{t+k})
        is the product of marginal autocorrelations at lag k.
        
        Args:
            signal: Signal values (n,)
            returns: Forward returns (n,)
            newey_west_lags: Number of lags for autocorrelation adjustment.
                            If None, uses Newey-West automatic: floor(4(n/100)^{2/9})
        
        Returns:
            Dictionary with test statistic, p-value, effective sample size
        """
        # Remove NaN
        valid = np.isfinite(signal) & np.isfinite(returns)
        x, y = signal[valid], returns[valid]
        n = len(x)
        
        if n < 10:
            return {'error': 'Insufficient observations', 'n': n}
        
        # Sample correlation
        r = np.corrcoef(x, y)[0, 1]
        
        # Automatic lag selection (Newey-West rule of thumb)
        if newey_west_lags is None:
            newey_west_lags = int(np.floor(4 * (n / 100) ** (2/9)))
        newey_west_lags = max(1, min(newey_west_lags, n // 4))
        
        # Compute effective sample size via Bartlett's formula
        # Demean
        x_dm = x - np.mean(x)
        y_dm = y - np.mean(y)
        
        # Marginal autocorrelations with Bartlett kernel weights
        sum_gamma = 0.0
        for k in range(1, newey_west_lags + 1):
            # Bartlett kernel weight
            w_k = 1 - k / (newey_west_lags + 1)
            
            # Autocorrelation of x at lag k
            rho_x_k = np.corrcoef(x_dm[:-k], x_dm[k:])[0, 1]
            # Autocorrelation of y at lag k
            rho_y_k = np.corrcoef(y_dm[:-k], y_dm[k:])[0, 1]
            
            sum_gamma += w_k * rho_x_k * rho_y_k
        
        # Effective sample size
        inflation_factor = 1 + 2 * sum_gamma
        n_eff = max(10, n / max(inflation_factor, 0.1))
        
        # Fisher z-transformation
        z = np.arctanh(r)
        se = 1.0 / np.sqrt(n_eff - 3)
        z_stat = z / se
        
        # Two-sided p-value
        p_value = 2 * (1 - sp_stats.norm.cdf(abs(z_stat)))
        
        # Confidence interval for ρ (back-transform)
        z_lower = z - 1.96 * se
        z_upper = z + 1.96 * se
        r_lower = np.tanh(z_lower)
        r_upper = np.tanh(z_upper)
        
        return {
            'correlation': r,
            'fisher_z': z,
            'z_statistic': z_stat,
            'p_value': p_value,
            'significant_5pct': p_value < 0.05,
            'significant_1pct': p_value < 0.01,
            'n_raw': n,
            'n_effective': n_eff,
            'inflation_factor': inflation_factor,
            'ci_95_lower': r_lower,
            'ci_95_upper': r_upper,
            'newey_west_lags': newey_west_lags
        }
    
    @staticmethod
    def block_bootstrap_test(signal: np.ndarray, returns: np.ndarray,
                              n_bootstrap: int = 5000,
                              block_length: int = None) -> Dict:
        """
        Nonparametric block bootstrap test for H₀: ρ = 0.
        
        Standard permutation tests break temporal dependence. The circular
        block bootstrap (Politis & Romano, 1992) preserves autocorrelation
        structure by resampling contiguous blocks.
        
        Procedure:
        1. Compute observed correlation r_obs
        2. For b = 1, ..., B:
           a. Resample signal in circular blocks of length l
           b. Compute r_b = corr(signal_resampled, returns)
        3. p-value = proportion of |r_b| ≥ |r_obs|
        
        Block length selection follows Politis & White (2004) automatic
        rule: l = ⌈(3n)^{1/3}⌉ for stationary bootstrap.
        
        Args:
            signal: Signal values
            returns: Forward returns
            n_bootstrap: Number of bootstrap replications
            block_length: Block length (auto if None)
            
        Returns:
            Dictionary with bootstrap distribution and p-value
        """
        valid = np.isfinite(signal) & np.isfinite(returns)
        x, y = signal[valid], returns[valid]
        n = len(x)
        
        if n < 30:
            return {'error': 'Insufficient data for block bootstrap', 'n': n}
        
        # Automatic block length: Politis-White rule
        if block_length is None:
            block_length = max(2, int(np.ceil((3 * n) ** (1/3))))
        
        # Observed statistic
        r_obs = np.corrcoef(x, y)[0, 1]
        
        # Block bootstrap: resample signal only (break signal-return link)
        n_blocks = int(np.ceil(n / block_length))
        bootstrap_corrs = np.zeros(n_bootstrap)
        
        rng = np.random.RandomState(42)
        
        for b in range(n_bootstrap):
            # Circular block bootstrap on signal
            block_starts = rng.randint(0, n, size=n_blocks)
            resampled_idx = np.concatenate([
                np.arange(start, start + block_length) % n
                for start in block_starts
            ])[:n]
            
            x_boot = x[resampled_idx]
            bootstrap_corrs[b] = np.corrcoef(x_boot, y)[0, 1]
        
        # Two-sided p-value
        p_value = np.mean(np.abs(bootstrap_corrs) >= np.abs(r_obs))
        
        # Bootstrap confidence interval (percentile method)
        ci_lower = np.percentile(bootstrap_corrs, 2.5)
        ci_upper = np.percentile(bootstrap_corrs, 97.5)
        
        return {
            'correlation': r_obs,
            'bootstrap_p_value': p_value,
            'significant_5pct': p_value < 0.05,
            'bootstrap_mean': np.mean(bootstrap_corrs),
            'bootstrap_std': np.std(bootstrap_corrs),
            'ci_95_lower': ci_lower,
            'ci_95_upper': ci_upper,
            'block_length': block_length,
            'n_bootstrap': n_bootstrap,
            'bootstrap_distribution': bootstrap_corrs
        }
    
    @staticmethod
    def multiple_testing_correction(p_values: Dict[str, float],
                                     method: str = 'bh') -> Dict[str, Dict]:
        """
        Adjust p-values for multiple hypothesis testing.
        
        When testing K signal-horizon combinations, the probability of
        at least one false positive under the global null is:
            P(≥1 false positive) = 1 - (1-α)^K ≈ Kα  for small α
        
        Methods:
        - 'bonferroni': p_adj = min(K·p, 1). Controls FWER but conservative.
        - 'bh': Benjamini-Hochberg (1995). Controls FDR at level α.
                 Sort p_(1) ≤ ... ≤ p_(K), reject all p_(i) ≤ i·α/K.
        - 'holm': Holm (1979). Step-down Bonferroni. Less conservative than
                  Bonferroni while still controlling FWER.
        
        Args:
            p_values: Dict mapping test name -> raw p-value
            method: Correction method ('bonferroni', 'bh', 'holm')
            
        Returns:
            Dict mapping test name -> {raw_p, adjusted_p, significant}
        """
        names = list(p_values.keys())
        raw_ps = np.array([p_values[name] for name in names])
        K = len(raw_ps)
        
        if method == 'bonferroni':
            adjusted = np.minimum(raw_ps * K, 1.0)
            
        elif method == 'bh':
            # Benjamini-Hochberg
            sorted_idx = np.argsort(raw_ps)
            adjusted = np.zeros(K)
            for rank, idx in enumerate(sorted_idx):
                adjusted[idx] = raw_ps[idx] * K / (rank + 1)
            # Enforce monotonicity (step-up)
            for i in range(K - 2, -1, -1):
                rev_idx = sorted_idx[i]
                next_idx = sorted_idx[i + 1]
                adjusted[rev_idx] = min(adjusted[rev_idx], adjusted[next_idx])
            adjusted = np.minimum(adjusted, 1.0)
            
        elif method == 'holm':
            sorted_idx = np.argsort(raw_ps)
            adjusted = np.zeros(K)
            for rank, idx in enumerate(sorted_idx):
                adjusted[idx] = raw_ps[idx] * (K - rank)
            # Enforce monotonicity (step-down)
            for i in range(1, K):
                idx = sorted_idx[i]
                prev_idx = sorted_idx[i - 1]
                adjusted[idx] = max(adjusted[idx], adjusted[prev_idx])
            adjusted = np.minimum(adjusted, 1.0)
        else:
            raise ValueError(f"Unknown method: {method}")
        
        results = {}
        for i, name in enumerate(names):
            results[name] = {
                'raw_p': raw_ps[i],
                'adjusted_p': adjusted[i],
                'significant_5pct': adjusted[i] < 0.05,
                'significant_1pct': adjusted[i] < 0.01
            }
        
        return results
    
    @staticmethod
    def comprehensive_signal_test(signal_data: pd.DataFrame,
                                   signal_name: str,
                                   horizons_ms: List[int],
                                   n_bootstrap: int = 2000) -> pd.DataFrame:
        """
        Run the full battery of significance tests across all horizons.
        
        For each horizon:
        1. Fisher z-test (parametric, autocorrelation-adjusted)
        2. Block bootstrap (nonparametric, assumption-free)
        3. Benjamini-Hochberg correction across all horizons
        
        Args:
            signal_data: DataFrame with signal, timestamp, price columns
            signal_name: Column name of the signal to test
            horizons_ms: List of forecast horizons in milliseconds
            n_bootstrap: Bootstrap replications per horizon
            
        Returns:
            DataFrame with test results per horizon
        """
        df = signal_data.copy()
        all_results = []
        raw_p_values = {}
        
        for horizon_ms in horizons_ms:
            horizon_sec = horizon_ms / 1000.0
            
            # Compute forward returns at this horizon
            future_returns = []
            for idx, row in df.iterrows():
                target_time = row['timestamp'] + horizon_sec
                future_mask = df['timestamp'] >= target_time
                if future_mask.any():
                    future_price = df.loc[future_mask, 'price'].iloc[0]
                    ret = (future_price - row['price']) / row['price']
                    future_returns.append(ret)
                else:
                    future_returns.append(np.nan)
            
            fwd_ret = np.array(future_returns)
            sig_vals = df[signal_name].values
            
            # Filter valid
            valid = np.isfinite(sig_vals) & np.isfinite(fwd_ret) & (sig_vals != 0)
            if valid.sum() < 30:
                continue
            
            sig_v = sig_vals[valid]
            ret_v = fwd_ret[valid]
            
            # Fisher z-test
            fisher = SignalSignificanceTester.fisher_z_test(sig_v, ret_v)
            
            # Block bootstrap
            bootstrap = SignalSignificanceTester.block_bootstrap_test(
                sig_v, ret_v, n_bootstrap=n_bootstrap
            )
            
            # Collect for multiple testing correction
            test_name = f'{signal_name}_{horizon_ms}ms'
            raw_p_values[test_name] = fisher.get('p_value', 1.0)
            
            all_results.append({
                'horizon_ms': horizon_ms,
                'n_obs': valid.sum(),
                'correlation': fisher.get('correlation', np.nan),
                'fisher_z_stat': fisher.get('z_statistic', np.nan),
                'fisher_p_value': fisher.get('p_value', np.nan),
                'n_effective': fisher.get('n_effective', np.nan),
                'inflation_factor': fisher.get('inflation_factor', np.nan),
                'ci_95_lower': fisher.get('ci_95_lower', np.nan),
                'ci_95_upper': fisher.get('ci_95_upper', np.nan),
                'bootstrap_p_value': bootstrap.get('bootstrap_p_value', np.nan),
                'bootstrap_ci_lower': bootstrap.get('ci_95_lower', np.nan),
                'bootstrap_ci_upper': bootstrap.get('ci_95_upper', np.nan),
            })
        
        if not all_results:
            return pd.DataFrame()
        
        results_df = pd.DataFrame(all_results)
        
        # Apply BH correction
        if raw_p_values:
            bh_corrected = SignalSignificanceTester.multiple_testing_correction(
                raw_p_values, method='bh'
            )
            # Map back to results
            bh_p_values = []
            for _, row in results_df.iterrows():
                test_name = f'{signal_name}_{int(row["horizon_ms"])}ms'
                if test_name in bh_corrected:
                    bh_p_values.append(bh_corrected[test_name]['adjusted_p'])
                else:
                    bh_p_values.append(np.nan)
            results_df['bh_adjusted_p'] = bh_p_values
            results_df['bh_significant_5pct'] = results_df['bh_adjusted_p'] < 0.05
        
        return results_df

# ==================== DATA LOADER ====================

class LOBSTERDataLoader:
    """
    Load and parse LOBSTER format data
    
    LOBSTER provides two files:
    - message file: timestamp, event_type, order_id, size, price, direction
    - orderbook file: ask_price_1, ask_size_1, bid_price_1, bid_size_1, ...
    """
    
    @staticmethod
    def load_message_file(filepath: str, nrows: Optional[int] = None) -> pd.DataFrame:
        """
        Load LOBSTER message file
        
        Args:
            filepath: Path to message file
            nrows: Number of rows to load (None for all)
            
        Returns:
            DataFrame with parsed messages
        """
        column_names = ['timestamp', 'event_type', 'order_id', 'size', 
                       'price', 'direction']
        
        df = pd.read_csv(filepath, header=None, names=column_names, nrows=nrows)
        
        # Convert timestamp to seconds
        df['timestamp'] = df['timestamp'] / 1e9  # Nanoseconds to seconds
        
        return df
    
    @staticmethod
    def load_orderbook_file(filepath: str, levels: int = 10, 
                           nrows: Optional[int] = None) -> pd.DataFrame:
        """
        Load LOBSTER orderbook file
        
        Args:
            filepath: Path to orderbook file
            levels: Number of levels in file
            nrows: Number of rows to load
            
        Returns:
            DataFrame with order book snapshots
        """
        columns = []
        for i in range(1, levels + 1):
            columns.extend([f'ask_price_{i}', f'ask_size_{i}',
                          f'bid_price_{i}', f'bid_size_{i}'])
        
        df = pd.read_csv(filepath, header=None, names=columns, nrows=nrows)
        
        return df
    
    @staticmethod
    def create_synthetic_data(num_messages: int = 10000, 
                             initial_price: float = 100.0,
                             seed: int = 42) -> pd.DataFrame:
        """
        Create synthetic LOBSTER-format data with realistic microstructure.
        
        Embeds the following alpha-generating effects:
        1. Autocorrelated order flow — informed traders cluster on one side
        2. Trade impact — executions move price with a realistic lag
        3. Informed trading episodes — periodic bursts of directional pressure
        4. Mean-reverting spread — spread widens then compresses
        
        Args:
            num_messages: Number of messages to generate
            initial_price: Starting price
            seed: Random seed
            
        Returns:
            DataFrame with synthetic messages
        """
        np.random.seed(seed)
        
        messages = []
        current_time = 0.0
        current_price = initial_price
        
        # Track live book state for realistic targeting
        live_bids = {}  # price -> size
        live_asks = {}  # price -> size
        
        # Microstructure state
        order_flow_momentum = 0.0   # Autocorrelation in flow direction
        informed_direction = 0      # 0=no episode, 1=buy, -1=sell
        informed_countdown = 0      # Messages left in informed episode
        trade_pressure = 0.0        # Accumulated trade impact (lagged)
        
        for i in range(num_messages):
            # Random time increment (0.1ms to 10ms)
            current_time += np.random.uniform(0.0001, 0.01)
            
            # === Informed trading episodes ===
            # Start a new episode with ~2% probability
            if informed_countdown <= 0 and np.random.random() < 0.02:
                informed_direction = np.random.choice([1, -1])
                informed_countdown = np.random.randint(20, 80)  # 20-80 messages
            
            if informed_countdown > 0:
                informed_countdown -= 1
            else:
                informed_direction = 0
            
            # === Order flow autocorrelation ===
            # Momentum decays toward 0 but is nudged by informed traders
            order_flow_momentum *= 0.95  # Decay
            if informed_direction != 0:
                order_flow_momentum += 0.1 * informed_direction
            order_flow_momentum = np.clip(order_flow_momentum, -0.8, 0.8)
            
            # Direction choice influenced by momentum
            dir_prob = 0.5 + 0.5 * order_flow_momentum  # P(ask/sell-side)
            direction = 1 if np.random.random() < dir_prob else -1
            
            # Decide event type based on book state
            can_cancel_bid = len(live_bids) > 0
            can_cancel_ask = len(live_asks) > 0
            
            if can_cancel_bid or can_cancel_ask:
                # During informed episodes, increase execution rate
                if informed_direction != 0:
                    event_type = np.random.choice(
                        [EventType.NEW_LIMIT, EventType.CANCELLATION, 
                         EventType.EXECUTION_VISIBLE],
                        p=[0.35, 0.25, 0.40]  # More executions
                    )
                else:
                    event_type = np.random.choice(
                        [EventType.NEW_LIMIT, EventType.CANCELLATION, 
                         EventType.EXECUTION_VISIBLE],
                        p=[0.50, 0.30, 0.20]
                    )
            else:
                event_type = EventType.NEW_LIMIT
            
            if event_type == EventType.NEW_LIMIT:
                if direction == 1:  # Ask
                    offset = np.random.exponential(0.03) + 0.01
                    price = round(current_price + offset, 2)
                    size = np.random.randint(1, 100) * 100
                    live_asks[price] = live_asks.get(price, 0) + size
                else:  # Bid
                    offset = np.random.exponential(0.03) + 0.01
                    price = round(current_price - offset, 2)
                    size = np.random.randint(1, 100) * 100
                    live_bids[price] = live_bids.get(price, 0) + size
                    
            elif event_type == EventType.CANCELLATION:
                if can_cancel_bid and can_cancel_ask:
                    # Informed traders cancel on the side they're about to hit
                    if informed_direction == 1 and can_cancel_ask:
                        direction = 1  # Cancel asks (pull offers before buying)
                    elif informed_direction == -1 and can_cancel_bid:
                        direction = -1
                    # else keep random direction
                elif can_cancel_ask:
                    direction = 1
                else:
                    direction = -1
                
                if direction == 1 and can_cancel_ask:
                    price = np.random.choice(list(live_asks.keys()))
                    available = live_asks[price]
                    size = min(np.random.randint(1, 80) * 100, available)
                    live_asks[price] -= size
                    if live_asks[price] <= 0:
                        del live_asks[price]
                elif can_cancel_bid:
                    price = np.random.choice(list(live_bids.keys()))
                    available = live_bids[price]
                    size = min(np.random.randint(1, 80) * 100, available)
                    live_bids[price] -= size
                    if live_bids[price] <= 0:
                        del live_bids[price]
                else:
                    continue  # Skip this message
                        
            elif event_type == EventType.EXECUTION_VISIBLE:
                # Informed traders execute aggressively on their side
                if informed_direction == 1 and can_cancel_ask:
                    direction = 1  # Buy execution (lifts ask)
                elif informed_direction == -1 and can_cancel_bid:
                    direction = -1  # Sell execution (hits bid)
                elif can_cancel_ask and can_cancel_bid:
                    pass  # Keep random direction
                elif can_cancel_ask:
                    direction = 1
                elif can_cancel_bid:
                    direction = -1
                else:
                    continue
                
                if direction == 1 and can_cancel_ask:
                    price = min(live_asks.keys())  # Best ask
                    available = live_asks[price]
                    size = min(np.random.randint(1, 50) * 100, available)
                    live_asks[price] -= size
                    if live_asks[price] <= 0:
                        del live_asks[price]
                    # Buy execution → upward pressure
                    trade_pressure += size * 0.000001
                elif can_cancel_bid:
                    price = max(live_bids.keys())  # Best bid
                    available = live_bids[price]
                    size = min(np.random.randint(1, 50) * 100, available)
                    live_bids[price] -= size
                    if live_bids[price] <= 0:
                        del live_bids[price]
                    # Sell execution → downward pressure
                    trade_pressure -= size * 0.000001
                else:
                    continue
            
            messages.append({
                'timestamp': current_time,
                'event_type': event_type,
                'order_id': i,
                'size': size,
                'price': price,
                'direction': direction
            })
            
            # === Price evolution with lagged trade impact ===
            # Price moves toward accumulated trade pressure (market impact)
            price_impact = trade_pressure * 0.3  # Partial incorporation
            trade_pressure *= 0.97  # Decay remaining pressure
            
            # Add small noise + mean reversion to initial price
            mean_reversion = -0.005 * (current_price - initial_price)
            noise = np.random.normal(0, 0.002)
            
            current_price += price_impact + mean_reversion + noise
            current_price = round(current_price, 2)
            
            # Periodically prune stale levels far from mid
            if i % 200 == 0:
                stale_bids = [p for p in live_bids if p < current_price - 0.50]
                for p in stale_bids:
                    del live_bids[p]
                stale_asks = [p for p in live_asks if p > current_price + 0.50]
                for p in stale_asks:
                    del live_asks[p]
        
        return pd.DataFrame(messages)

# ==================== BACKTESTING FRAMEWORK ====================

class SignalBacktester:
    """
    Backtest signal-based trading strategies.
    
    Supports auto-inversion: if a signal has negative correlation with
    forward returns, the strategy automatically flips the signal direction
    rather than trading it wrong-way.
    """
    
    def __init__(self, transaction_cost_bps: float = 1.0):
        """
        Args:
            transaction_cost_bps: Transaction cost in basis points
        """
        self.transaction_cost = transaction_cost_bps / 10000
        self.trades = []
        self.positions = []
    
    def _estimate_signal_direction(self, df: pd.DataFrame, 
                                    signal_col: str) -> int:
        """
        Estimate whether signal positively or negatively predicts returns.
        Uses first 30% of data as calibration window.
        
        Returns:
            +1 if positive correlation (trade signal directly)
            -1 if negative correlation (invert signal)
        """
        calibration_end = int(len(df) * 0.3)
        cal_df = df.iloc[:calibration_end].copy()
        
        if len(cal_df) < 50:
            return 1  # Default to direct
        
        # Compute short-horizon forward returns
        prices = cal_df['price'].values
        fwd_returns = np.zeros(len(prices))
        lookahead = min(20, len(prices) // 5)
        for i in range(len(prices) - lookahead):
            fwd_returns[i] = (prices[i + lookahead] - prices[i]) / prices[i]
        
        signal_vals = cal_df[signal_col].values[:len(prices) - lookahead]
        fwd_rets = fwd_returns[:len(prices) - lookahead]
        
        # Remove NaN/zero
        valid = np.isfinite(signal_vals) & np.isfinite(fwd_rets) & (signal_vals != 0)
        if valid.sum() < 20:
            return 1
        
        corr = np.corrcoef(signal_vals[valid], fwd_rets[valid])[0, 1]
        return -1 if corr < -0.02 else 1
        
    def run_strategy(self, signals_df: pd.DataFrame, 
                     signal_name: str = 'ofi',
                     entry_threshold: float = 1.0,
                     exit_threshold: float = 0.0,
                     holding_period_ms: int = 1000,
                     auto_invert: bool = True) -> pd.DataFrame:
        """
        Run threshold-based strategy with optional auto-inversion.
        
        Strategy:
        - Calibrate signal direction on first 30% of data
        - Enter long when (adjusted) signal > entry_threshold
        - Enter short when (adjusted) signal < -entry_threshold
        - Exit when signal crosses exit_threshold or after holding_period
        
        Args:
            signals_df: DataFrame with signals and prices
            signal_name: Signal to trade on
            entry_threshold: Z-score threshold for entry
            exit_threshold: Z-score threshold for exit
            holding_period_ms: Maximum holding period
            auto_invert: If True, detect and invert anti-predictive signals
            
        Returns:
            DataFrame with trade results
        """
        df = signals_df.copy()
        
        # Remove rows where signal is NaN or zero
        if df[signal_name].isna().all() or (df[signal_name] == 0).all():
            return pd.DataFrame()
        
        # Normalize signal to z-scores
        signal_mean = df[signal_name].mean()
        signal_std = df[signal_name].std()
        if signal_std < 1e-10:
            return pd.DataFrame()
        df['signal_z'] = (df[signal_name] - signal_mean) / signal_std
        
        # Auto-inversion: detect if signal is anti-predictive
        signal_flip = 1
        if auto_invert:
            signal_flip = self._estimate_signal_direction(df, signal_name)
            df['signal_z'] = df['signal_z'] * signal_flip
        
        # Only trade on the out-of-sample portion (after calibration window)
        trade_start_idx = int(len(df) * 0.3) if auto_invert else 0
        
        position = 0
        entry_price = 0
        entry_time = 0
        entry_idx = 0
        
        trades = []
        
        for idx, row in df.iloc[trade_start_idx:].iterrows():
            current_price = row['price']
            current_time = row['timestamp']
            signal_z = row['signal_z']
            
            if np.isnan(signal_z) or np.isnan(current_price):
                continue
            
            # Check exit conditions
            if position != 0:
                holding_time_ms = (current_time - entry_time) * 1000
                
                should_exit = (
                    (position > 0 and signal_z < exit_threshold) or
                    (position < 0 and signal_z > -exit_threshold) or
                    holding_time_ms > holding_period_ms
                )
                
                if should_exit:
                    # Close position
                    pnl = position * (current_price - entry_price)
                    pnl -= abs(position) * entry_price * self.transaction_cost   # Entry cost
                    pnl -= abs(position) * current_price * self.transaction_cost  # Exit cost
                    
                    trades.append({
                        'entry_time': entry_time,
                        'exit_time': current_time,
                        'entry_price': entry_price,
                        'exit_price': current_price,
                        'position': position,
                        'pnl': pnl,
                        'return': pnl / (abs(position) * entry_price),
                        'holding_time_ms': holding_time_ms,
                        'entry_signal': df.loc[entry_idx, 'signal_z'] if entry_idx in df.index else 0,
                        'signal_flipped': signal_flip == -1
                    })
                    
                    position = 0
            
            # Check entry conditions
            if position == 0:
                if signal_z > entry_threshold:
                    position = 1
                    entry_price = current_price
                    entry_time = current_time
                    entry_idx = idx
                    
                elif signal_z < -entry_threshold:
                    position = -1
                    entry_price = current_price
                    entry_time = current_time
                    entry_idx = idx
        
        return pd.DataFrame(trades)
    
    def compute_performance_metrics(self, trades_df: pd.DataFrame) -> Dict:
        """
        Compute comprehensive performance metrics
        
        Args:
            trades_df: DataFrame from run_strategy
            
        Returns:
            Dictionary of performance metrics
        """
        if len(trades_df) == 0:
            return {'error': 'No trades executed'}
        
        returns = trades_df['return'].values
        pnls = trades_df['pnl'].values
        
        total_pnl = pnls.sum()
        num_trades = len(trades_df)
        win_rate = (pnls > 0).mean()
        
        avg_win = pnls[pnls > 0].mean() if (pnls > 0).any() else 0
        avg_loss = pnls[pnls < 0].mean() if (pnls < 0).any() else 0
        
        profit_factor = abs(avg_win / avg_loss) if avg_loss != 0 else np.inf
        
        sharpe = returns.mean() / returns.std() if returns.std() > 0 else 0
        
        # Maximum drawdown
        cumulative = np.cumsum(pnls)
        running_max = np.maximum.accumulate(cumulative)
        drawdown = running_max - cumulative
        max_drawdown = drawdown.max()
        
        return {
            'total_pnl': total_pnl,
            'num_trades': num_trades,
            'win_rate': win_rate,
            'avg_win': avg_win,
            'avg_loss': avg_loss,
            'profit_factor': profit_factor,
            'sharpe_ratio': sharpe,
            'max_drawdown': max_drawdown,
            'avg_holding_time_ms': trades_df['holding_time_ms'].mean()
        }

# ==================== OPTIMAL EXECUTION (ALMGREN-CHRISS) ====================

class OptimalExecutionScheduler:
    """
    Derive and compute the optimal execution schedule for liquidating a
    position, following the Almgren-Chriss (2001) framework.
    
    Model setup:
    ───────────
    We liquidate X shares over T periods (τ = T/N each).
    Let x_k = remaining shares after period k, with x_0 = X, x_N = 0.
    Trade list: n_k = x_{k-1} - x_k (shares traded in period k).
    
    Price dynamics:
        S_k = S_{k-1} - g(n_k/τ)·τ - σ·√τ·ε_k     (permanent + diffusion)
    
    Temporary impact on execution price:
        S̃_k = S_k - h(n_k/τ)                        (temporary slippage)
    
    With linear impact:
        g(v) = γ·v     (permanent, γ = impact coefficient)
        h(v) = η·v     (temporary, η = slippage coefficient)
    
    The trader minimizes:
        E[cost] + λ·Var[cost]
    
    where λ is the risk-aversion parameter.
    
    Closed-form solution:
    ────────────────────
    Define κ = √(λσ²/η) (urgency parameter).
    
    The optimal trajectory is:
        x_k = X · sinh(κ(T - t_k)) / sinh(κT)
    
    And the optimal trade list:
        n_k = X · 2sinh(κτ/2) · cosh(κ(T - t_{k-1/2})) / sinh(κT)
    
    where t_{k-1/2} = (k - 1/2)τ is the midpoint of interval k.
    
    Special cases:
    - λ → 0:  n_k = X/N  (TWAP, risk-neutral)
    - λ → ∞:  n_1 = X    (immediate liquidation, infinitely risk-averse)
    
    The efficient frontier traces out the (E[cost], Var[cost]) pairs
    as λ varies from 0 to ∞.
    
    Reference:
    Almgren, R. & Chriss, N. (2001). "Optimal Execution of Portfolio
    Transactions." Journal of Risk, 3(2), 5-39.
    """
    
    def __init__(self, total_shares: int, n_periods: int, 
                 total_time: float, sigma: float,
                 gamma: float, eta: float):
        """
        Args:
            total_shares: X - total shares to liquidate
            n_periods: N - number of trading intervals
            total_time: T - total time horizon (seconds)
            sigma: σ - price volatility (per √second)
            gamma: γ - permanent impact coefficient (price per share/sec)
            eta: η - temporary impact coefficient (price per share/sec)
        """
        self.X = total_shares
        self.N = n_periods
        self.T = total_time
        self.tau = total_time / n_periods  # Period length
        self.sigma = sigma
        self.gamma = gamma
        self.eta = eta
    
    def optimal_trajectory(self, risk_aversion: float) -> Dict:
        """
        Compute the optimal execution trajectory for a given risk aversion.
        
        The closed-form solution from Almgren-Chriss:
            κ = √(λσ²/η)
            x_k = X · sinh(κ(T - kτ)) / sinh(κT)
            n_k = x_{k-1} - x_k
        
        Args:
            risk_aversion: λ - Lagrange multiplier on variance
            
        Returns:
            Dictionary with trajectory, trade list, expected cost, and variance
        """
        X, N, T, tau = self.X, self.N, self.T, self.tau
        sigma, gamma, eta = self.sigma, self.gamma, self.eta
        
        if risk_aversion <= 0:
            # TWAP (risk-neutral)
            trade_list = np.full(N, X / N)
            trajectory = np.array([X - k * (X / N) for k in range(N + 1)])
        else:
            # Urgency parameter
            kappa = np.sqrt(risk_aversion * sigma**2 / eta)
            
            # Check for numerical overflow
            if kappa * T > 500:
                # Essentially immediate execution
                trade_list = np.zeros(N)
                trade_list[0] = X
                trajectory = np.zeros(N + 1)
                trajectory[0] = X
            else:
                # Optimal trajectory: x_k = X * sinh(κ(T - kτ)) / sinh(κT)
                trajectory = np.array([
                    X * np.sinh(kappa * (T - k * tau)) / np.sinh(kappa * T)
                    for k in range(N + 1)
                ])
                trajectory[0] = X   # Enforce boundary
                trajectory[-1] = 0  # Enforce boundary
                
                # Trade list
                trade_list = np.diff(-trajectory)  # n_k = x_{k-1} - x_k
        
        # Expected cost and variance (Almgren-Chriss Proposition 2)
        # E[cost] = (1/2)γX² + η·Σ(n_k²/τ)
        expected_cost = 0.5 * gamma * X**2 + eta * np.sum(trade_list**2) / tau
        
        # Var[cost] = σ²·τ·Σ_{k=1}^{N} x_k²
        # (variance comes from diffusion risk on remaining position)
        variance = sigma**2 * tau * np.sum(trajectory[1:]**2)
        
        # Time grid
        time_grid = np.array([k * tau for k in range(N + 1)])
        trade_times = np.array([(k + 0.5) * tau for k in range(N)])
        
        return {
            'trajectory': trajectory,
            'trade_list': trade_list,
            'time_grid': time_grid,
            'trade_times': trade_times,
            'expected_cost': expected_cost,
            'variance': variance,
            'std_cost': np.sqrt(variance),
            'risk_aversion': risk_aversion,
            'kappa': np.sqrt(risk_aversion * sigma**2 / eta) if risk_aversion > 0 else 0,
            'is_twap': risk_aversion <= 0
        }
    
    def efficient_frontier(self, n_points: int = 50) -> pd.DataFrame:
        """
        Compute the efficient frontier in (E[cost], Std[cost]) space.
        
        As λ increases from 0 to ∞:
        - E[cost] increases (more aggressive → more market impact)
        - Std[cost] decreases (faster execution → less volatility risk)
        
        The frontier is the set of Pareto-optimal strategies: no strategy
        can reduce both expected cost and cost variance simultaneously.
        
        The curve is parameterized by λ and is convex in (E, σ) space.
        
        Args:
            n_points: Number of points on the frontier
            
        Returns:
            DataFrame with expected_cost, std_cost, risk_aversion columns
        """
        # Logarithmically spaced risk aversion from ~0 to large
        lambdas = np.concatenate([
            [0],  # TWAP
            np.logspace(-6, 2, n_points - 1)
        ])
        
        results = []
        for lam in lambdas:
            opt = self.optimal_trajectory(lam)
            results.append({
                'risk_aversion': lam,
                'expected_cost': opt['expected_cost'],
                'std_cost': opt['std_cost'],
                'variance': opt['variance'],
                'kappa': opt['kappa'],
                'front_loaded_pct': opt['trade_list'][0] / self.X * 100
            })
        
        return pd.DataFrame(results)
    
    def compare_strategies(self, risk_aversion: float) -> Dict:
        """
        Compare optimal vs naive strategies quantitatively.
        
        Strategies compared:
        1. TWAP: n_k = X/N (equal splits)
        2. Optimal: Almgren-Chriss closed-form for given λ
        3. VWAP-proxy: Front-loaded U-shape heuristic
        4. Immediate: Liquidate everything in period 1
        
        Reports cost savings of optimal over each alternative.
        
        Args:
            risk_aversion: λ for optimal strategy
            
        Returns:
            Dictionary comparing all strategies
        """
        X, N, T, tau = self.X, self.N, self.T, self.tau
        sigma, gamma, eta = self.sigma, self.gamma, self.eta
        
        # Optimal
        opt = self.optimal_trajectory(risk_aversion)
        
        # TWAP
        twap = self.optimal_trajectory(0)
        
        # Immediate
        imm_trades = np.zeros(N)
        imm_trades[0] = X
        imm_traj = np.zeros(N + 1)
        imm_traj[0] = X
        imm_cost = 0.5 * gamma * X**2 + eta * X**2 / tau
        imm_var = 0.0  # No remaining position risk
        
        # VWAP-proxy (U-shape: heavier at start and end)
        weights = np.array([
            1.5 - abs(2 * k / (N - 1) - 1) for k in range(N)
        ])
        weights = weights / weights.sum()
        vwap_trades = X * weights
        vwap_traj = np.concatenate([[X], X - np.cumsum(vwap_trades)])
        vwap_cost = 0.5 * gamma * X**2 + eta * np.sum(vwap_trades**2) / tau
        vwap_var = sigma**2 * tau * np.sum(vwap_traj[1:]**2)
        
        # Objective: E[cost] + λ·Var[cost]
        def objective(e, v): return e + risk_aversion * v
        
        return {
            'optimal': {
                'expected_cost': opt['expected_cost'],
                'std_cost': opt['std_cost'],
                'objective': objective(opt['expected_cost'], opt['variance']),
                'trajectory': opt['trajectory']
            },
            'twap': {
                'expected_cost': twap['expected_cost'],
                'std_cost': twap['std_cost'],
                'objective': objective(twap['expected_cost'], twap['variance']),
                'cost_increase_pct': (twap['expected_cost'] - opt['expected_cost']) 
                                     / opt['expected_cost'] * 100 if opt['expected_cost'] > 0 else 0
            },
            'immediate': {
                'expected_cost': imm_cost,
                'std_cost': 0.0,
                'objective': objective(imm_cost, imm_var),
            },
            'vwap_proxy': {
                'expected_cost': vwap_cost,
                'std_cost': np.sqrt(vwap_var),
                'objective': objective(vwap_cost, vwap_var),
            },
            'risk_aversion': risk_aversion
        }

# ==================== VISUALIZATION ====================

import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
from matplotlib.animation import FuncAnimation

class OrderBookVisualizer:
    """
    Visualization tools for order book and signals
    """
    
    @staticmethod
    def plot_orderbook_snapshot(snapshot: BookSnapshot, ax=None):
        """Plot single order book snapshot"""
        if ax is None:
            fig, ax = plt.subplots(figsize=(10, 6))
        
        # Extract data
        bid_prices = [level.price for level in snapshot.bids]
        bid_sizes = [level.size for level in snapshot.bids]
        ask_prices = [level.price for level in snapshot.asks]
        ask_sizes = [level.size for level in snapshot.asks]
        
        # Plot
        ax.barh(bid_prices, bid_sizes, color='green', alpha=0.6, label='Bids')
        ax.barh(ask_prices, ask_sizes, color='red', alpha=0.6, label='Asks')
        
        # Mark mid-price
        if snapshot.mid_price:
            ax.axhline(snapshot.mid_price, color='black', 
                      linestyle='--', label=f'Mid: {snapshot.mid_price:.2f}')
        
        ax.set_xlabel('Size')
        ax.set_ylabel('Price')
        ax.set_title(f'Order Book Snapshot @ {snapshot.timestamp:.3f}s')
        ax.legend()
        ax.grid(True, alpha=0.3)
        
        return ax
    
    @staticmethod
    def plot_signal_analysis(analyzer: PredictiveAnalyzer, 
                           signal_name: str = 'ofi'):
        """
        Create comprehensive signal analysis dashboard
        
        Args:
            analyzer: PredictiveAnalyzer with recorded data
            signal_name: Signal to analyze
        """
        df = pd.DataFrame(analyzer.signal_data)
        
        fig = plt.figure(figsize=(16, 12))
        gs = gridspec.GridSpec(3, 2, figure=fig)
        
        # 1. Signal time series
        ax1 = fig.add_subplot(gs[0, :])
        ax1.plot(df['timestamp'], df[signal_name], label=signal_name, alpha=0.7)
        ax1.set_xlabel('Time (s)')
        ax1.set_ylabel('Signal Value')
        ax1.set_title(f'{signal_name.upper()} Signal Over Time')
        ax1.grid(True, alpha=0.3)
        ax1.legend()
        
        # 2. Predictive power by horizon
        try:
            pred_power = analyzer.analyze_predictive_power(signal_name)
            
            ax2 = fig.add_subplot(gs[1, 0])
            ax2.plot(pred_power['horizon_ms'], pred_power['correlation'], 
                    marker='o', linewidth=2)
            ax2.set_xlabel('Horizon (ms)')
            ax2.set_ylabel('Correlation')
            ax2.set_title('Predictive Power by Horizon')
            ax2.grid(True, alpha=0.3)
            
            ax3 = fig.add_subplot(gs[1, 1])
            ax3.plot(pred_power['horizon_ms'], pred_power['hit_rate'], 
                    marker='o', linewidth=2, color='green')
            ax3.axhline(0.5, color='red', linestyle='--', label='Random')
            ax3.set_xlabel('Horizon (ms)')
            ax3.set_ylabel('Hit Rate')
            ax3.set_title('Directional Accuracy')
            ax3.legend()
            ax3.grid(True, alpha=0.3)
            
        except Exception as e:
            print(f"Could not compute predictive power: {e}")
        
        # 3. Signal distribution
        ax4 = fig.add_subplot(gs[2, 0])
        ax4.hist(df[signal_name].dropna(), bins=50, alpha=0.7, edgecolor='black')
        ax4.set_xlabel('Signal Value')
        ax4.set_ylabel('Frequency')
        ax4.set_title(f'{signal_name.upper()} Distribution')
        ax4.grid(True, alpha=0.3)
        
        # 4. Price vs signal scatter
        ax5 = fig.add_subplot(gs[2, 1])
        if 'price' in df.columns:
            scatter = ax5.scatter(df[signal_name], df['price'], 
                                 c=df['timestamp'], cmap='viridis', 
                                 alpha=0.5, s=10)
            ax5.set_xlabel(f'{signal_name.upper()}')
            ax5.set_ylabel('Price')
            ax5.set_title('Signal vs Price (colored by time)')
            plt.colorbar(scatter, ax=ax5, label='Time (s)')
            ax5.grid(True, alpha=0.3)
        
        plt.tight_layout()
        return fig
    
    @staticmethod
    def plot_backtest_results(trades_df: pd.DataFrame, metrics: Dict):
        """
        Visualize backtest results
        
        Args:
            trades_df: DataFrame from SignalBacktester
            metrics: Performance metrics dictionary
        """
        fig, axes = plt.subplots(2, 2, figsize=(14, 10))
        
        # 1. Cumulative PnL
        ax = axes[0, 0]
        cumulative_pnl = trades_df['pnl'].cumsum()
        ax.plot(cumulative_pnl.values, linewidth=2)
        ax.set_xlabel('Trade Number')
        ax.set_ylabel('Cumulative PnL')
        ax.set_title(f'Cumulative PnL (Total: ${metrics["total_pnl"]:.2f})')
        ax.grid(True, alpha=0.3)
        
        # 2. PnL distribution
        ax = axes[0, 1]
        ax.hist(trades_df['pnl'], bins=30, alpha=0.7, edgecolor='black')
        ax.axvline(0, color='red', linestyle='--', linewidth=2)
        ax.set_xlabel('PnL per Trade')
        ax.set_ylabel('Frequency')
        ax.set_title(f'PnL Distribution (Win Rate: {metrics["win_rate"]:.1%})')
        ax.grid(True, alpha=0.3)
        
        # 3. Return vs holding time
        ax = axes[1, 0]
        scatter = ax.scatter(trades_df['holding_time_ms'], 
                           trades_df['return']*10000,  # bps
                           c=trades_df['pnl'], 
                           cmap='RdYlGn', alpha=0.6, s=50)
        ax.set_xlabel('Holding Time (ms)')
        ax.set_ylabel('Return (bps)')
        ax.set_title('Return vs Holding Time')
        ax.axhline(0, color='black', linestyle='--', alpha=0.5)
        plt.colorbar(scatter, ax=ax, label='PnL')
        ax.grid(True, alpha=0.3)
        
        # 4. Performance metrics table
        ax = axes[1, 1]
        ax.axis('off')
        
        metrics_text = f"""
        Performance Metrics
        {'='*40}
        Total PnL:           ${metrics['total_pnl']:,.2f}
        Number of Trades:    {metrics['num_trades']}
        Win Rate:            {metrics['win_rate']:.1%}
        
        Average Win:         ${metrics['avg_win']:.2f}
        Average Loss:        ${metrics['avg_loss']:.2f}
        Profit Factor:       {metrics['profit_factor']:.2f}
        
        Sharpe (per-trade):  {metrics['sharpe_ratio']:.3f}
        Max Drawdown:        ${metrics['max_drawdown']:.2f}
        
        Avg Hold Time:       {metrics['avg_holding_time_ms']:.0f} ms
        """
        
        ax.text(0.1, 0.5, metrics_text, 
               fontfamily='monospace', fontsize=10,
               verticalalignment='center')
        
        plt.tight_layout()
        return fig

# ==================== MAIN EXECUTION EXAMPLE ====================

def run_comprehensive_analysis():
    """
    Complete end-to-end analysis demonstrating all components
    """
    print("="*60)
    print("LIMIT ORDER BOOK SIGNAL PROCESSOR")
    print("High-Frequency Trading Signal Analysis")
    print("="*60)
    
    # ========== Step 1: Generate/Load Data ==========
    print("\n[1/6] Loading data...")
    
    # For demonstration, use synthetic data
    # In production, use: df_messages = LOBSTERDataLoader.load_message_file('path/to/file')
    df_messages = LOBSTERDataLoader.create_synthetic_data(
        num_messages=50000,
        initial_price=100.0,
        seed=42
    )
    
    print(f"  Loaded {len(df_messages)} messages")
    print(f"  Time range: {df_messages['timestamp'].min():.2f}s to {df_messages['timestamp'].max():.2f}s")
    
    # ========== Step 2: Process Order Book ==========
    print("\n[2/6] Processing order book...")
    
    order_book = OrderBook(tick_size=0.01, num_levels=10)
    signal_gen = SignalGenerator()
    analyzer = PredictiveAnalyzer(horizons_ms=[100, 500, 1000, 5000])
    
    all_signals = []
    snapshots = []
    
    start_time = time.time()
    
    for idx, row in df_messages.iterrows():
        # Update order book
        order_book.process_lobster_message(
            timestamp=row['timestamp'],
            event_type=row['event_type'],
            order_id=row['order_id'],
            size=row['size'],
            price=row['price'],
            direction=row['direction']
        )
        
        # Sample every 10th message to reduce computation
        if idx % 10 == 0:
            snapshot = order_book.get_snapshot(num_levels=5)
            
            if snapshot.mid_price is not None:
                signals = signal_gen.compute_all_signals(snapshot, order_book)
                all_signals.append(signals)
                snapshots.append(snapshot)
                
                # Record for predictive analysis
                analyzer.record_signal(signals, snapshot.mid_price)
    
    processing_time = time.time() - start_time
    messages_per_sec = len(df_messages) / processing_time
    
    print(f"  Processed {len(df_messages)} messages in {processing_time:.2f}s")
    print(f"  Throughput: {messages_per_sec:,.0f} messages/second")
    print(f"  Generated {len(all_signals)} signal snapshots")
    
    metrics = order_book.get_metrics()
    print(f"  Final book state: {metrics['bid_levels']} bid levels, {metrics['ask_levels']} ask levels")
    print(f"  Total trades: {metrics['trades']}")
    
    # Book health check
    final_snapshot = order_book.get_snapshot()
    if final_snapshot.best_bid and final_snapshot.best_ask:
        print(f"  Best bid: {final_snapshot.best_bid:.2f}, Best ask: {final_snapshot.best_ask:.2f}")
        print(f"  Spread: {final_snapshot.spread:.4f}")
        if order_book.is_crossed:
            print("  WARNING: Book is crossed!")
        else:
            print("  Book is healthy (not crossed)")
    
    # ========== Step 3: Predictive Analysis ==========
    print("\n[3/6] Analyzing predictive power...")
    
    signals_df = pd.DataFrame(all_signals)
    signals_df['price'] = signals_df['mid_price']
    
    for signal_name in ['ofi', 'delta_ofi', 'trade_imbalance', 'spread_pressure', 'composite']:
        if signal_name not in signals_df.columns:
            continue
        if signals_df[signal_name].isna().all() or (signals_df[signal_name] == 0).all():
            continue
            
        print(f"\n  Signal: {signal_name.upper()}")
        
        try:
            pred_power = analyzer.analyze_predictive_power(signal_name)
            
            print("\n  Predictive Power by Horizon:")
            print("  " + "-"*70)
            print(f"  {'Horizon':<12} {'Correlation':<15} {'Hit Rate':<15} {'Sharpe':<15}")
            print("  " + "-"*70)
            
            for _, row in pred_power.iterrows():
                print(f"  {row['horizon_ms']:<12} "
                      f"{row['correlation']:<15.4f} "
                      f"{row['hit_rate']:<15.2%} "
                      f"{row['sharpe']:<15.3f}")
            
            print("  " + "-"*70)
            
        except Exception as e:
            print(f"  Error in analysis: {e}")
    
    # ========== Step 3b: Statistical Significance Tests ==========
    print("\n" + "="*60)
    print("STATISTICAL SIGNIFICANCE TESTING")
    print("="*60)
    print("\n  Testing H_o: signal has zero predictive power")
    print("  Methods: Fisher z-test (autocorrelation-adjusted) + Block Bootstrap")
    print("  Multiple testing: Benjamini-Hochberg FDR correction")
    
    for signal_name in ['ofi', 'composite']:
        if signal_name not in signals_df.columns:
            continue
        if signals_df[signal_name].isna().all() or (signals_df[signal_name] == 0).all():
            continue
        
        print(f"\n  Signal: {signal_name.upper()}")
        
        try:
            sig_results = SignalSignificanceTester.comprehensive_signal_test(
                signal_data=signals_df,
                signal_name=signal_name,
                horizons_ms=[100, 500, 1000, 5000],
                n_bootstrap=2000
            )
            
            if len(sig_results) > 0:
                print("\n  " + "-"*95)
                print(f"  {'Horizon':<10} {'Corr':<8} {'n_eff':<8} {'Fisher p':<12} "
                      f"{'Boot p':<12} {'BH adj p':<12} {'95% CI':<20} {'Sig?'}")
                print("  " + "-"*95)
                
                for _, row in sig_results.iterrows():
                    ci_str = f"[{row['ci_95_lower']:.4f}, {row['ci_95_upper']:.4f}]"
                    sig_marker = "***" if row.get('bh_significant_5pct', False) else "   "
                    print(f"  {int(row['horizon_ms']):<10} "
                          f"{row['correlation']:<8.4f} "
                          f"{row['n_effective']:<8.0f} "
                          f"{row['fisher_p_value']:<12.4f} "
                          f"{row['bootstrap_p_value']:<12.4f} "
                          f"{row.get('bh_adjusted_p', np.nan):<12.4f} "
                          f"{ci_str:<20} {sig_marker}")
                
                print("  " + "-"*95)
                print("  *** = significant at 5% after BH correction")
                
        except Exception as e:
            print(f"  Error in significance testing: {e}")
    
    # ========== Step 4: Signal Decay Analysis ==========
    print("\n[4/6] Analyzing signal decay...")
    
    try:
        decay_df = analyzer.signal_decay_analysis(
            signal_name='ofi',
            max_horizon_ms=5000,
            step_ms=200
        )
        
        # Find half-life (where correlation drops to 50% of initial)
        initial_corr = decay_df['correlation'].iloc[0]
        half_corr = initial_corr * 0.5
        
        half_life_idx = (decay_df['correlation'] - half_corr).abs().idxmin()
        half_life_ms = decay_df.loc[half_life_idx, 'horizon_ms']
        
        print(f"  OFI Signal Half-life: {half_life_ms:.0f} ms")
        
    except Exception as e:
        print(f"  Error in decay analysis: {e}")
    
    # ========== Step 4b: Kalman Filter Convergence Analysis ==========
    print("\n" + "="*60)
    print("KALMAN FILTER CONVERGENCE ANALYSIS")
    print("="*60)
    
    try:
        Q_val = signal_gen.ofi_filter.Q
        R_val = signal_gen.ofi_filter.R
        kca = KalmanConvergenceAnalyzer(Q=Q_val, R=R_val)
        
        # Analytical results
        conv = kca.verify_convergence_numerically()
        
        print(f"\n  Filter Parameters: Q={Q_val}, R={R_val}")
        print(f"  SNR: {conv['snr_db']:.1f} dB")
        print(f"\n  Steady-State Results (DARE solution):")
        print(f"    P_inf (analytical):  {conv['P_inf_analytical']:.8f}")
        print(f"    P_inf (numerical):   {conv['P_inf_numerical']:.8f}")
        print(f"    Agreement:         {'YES' if conv['agreement'] else 'NO'}")
        print(f"    K_inf (steady gain): {conv['K_inf']:.6f}")
        print(f"\n  Convergence Properties:")
        print(f"    Theoretical rate rho:  {conv['rho_theoretical']:.6f}")
        print(f"    Empirical rate rho:      {conv['rho_empirical']:.6f}")
        print(f"    Converged at step:   {conv['converged_at_step']}")
        print(f"    Interpretation:      Filter reaches steady-state in "
              f"~{conv['converged_at_step']} updates")
        
        # Innovation consistency test on the OFI signal
        ofi_values = signals_df['ofi'].dropna().values
        if len(ofi_values) > 100:
            innov_test = kca.innovation_consistency_test(ofi_values)
            
            if 'error' not in innov_test:
                print(f"\n  Innovation Consistency Tests (model validation):")
                print(f"    Zero-mean test:    t={innov_test['zero_mean_t_stat']:.3f}, "
                      f"p={innov_test['zero_mean_p_value']:.4f} "
                      f"{'[PASS]' if innov_test['zero_mean_pass'] else '[FAIL]'}")
                print(f"    Whiteness (LB):    Q={innov_test['ljung_box_Q']:.2f}, "
                      f"p={innov_test['ljung_box_p_value']:.4f} "
                      f"{'[PASS]' if innov_test['whiteness_pass'] else '[FAIL]'}")
                print(f"    NIS consistency:   E[NIS]={innov_test['mean_nis']:.3f} "
                      f"(expect ~1.0) "
                      f"{'[PASS]' if innov_test['nis_consistent'] else '[FAIL]'}")
                print(f"    Max autocorr:      {innov_test['max_autocorr']:.4f}")
                
                if not innov_test['whiteness_pass']:
                    print(f"\n  Diagnostic: Innovations show significant autocorrelation")
                    print(f"    => Random-walk process model is misspecified for OFI.")
                    print(f"    => OFI has persistent dynamics that a simple Kalman")
                    print(f"       filter cannot capture. Consider AR(p) state model")
                    print(f"       or increasing Q to widen the filter bandwidth.")
        
    except Exception as e:
        print(f"  Error in Kalman analysis: {e}")
    
    # ========== Step 5: Backtesting ==========
    print("\n[5/6] Running backtest...")
    
    backtester = SignalBacktester(transaction_cost_bps=1.0)
    
    # Test multiple signals, thresholds, and holding periods
    thresholds = [0.5, 1.0, 1.5, 2.0]
    signal_candidates = ['ofi', 'delta_ofi', 'trade_imbalance', 'composite']
    holding_periods = [1000, 2000, 5000]
    
    best_metrics = None
    best_threshold = None
    best_trades_df = None
    best_signal = None
    best_holding = None
    
    for signal_name in signal_candidates:
        if signal_name not in signals_df.columns:
            continue
        if signals_df[signal_name].isna().all() or (signals_df[signal_name] == 0).all():
            continue
            
        for holding_ms in holding_periods:
            print(f"\n  Signal: {signal_name.upper()}, Holding: {holding_ms}ms (auto-invert)")
            print("  " + "-"*80)
            print(f"  {'Threshold':<12} {'Trades':<10} {'Win Rate':<12} {'Total PnL':<15} {'Sharpe':<12}")
            print("  " + "-"*80)
            
            for threshold in thresholds:
                trades_df = backtester.run_strategy(
                    signals_df,
                    signal_name=signal_name,
                    entry_threshold=threshold,
                    exit_threshold=0.0,
                    holding_period_ms=holding_ms,
                    auto_invert=True
                )
                
                if len(trades_df) > 0:
                    metrics = backtester.compute_performance_metrics(trades_df)
                    
                    inverted = trades_df['signal_flipped'].iloc[0] if 'signal_flipped' in trades_df.columns else False
                    inv_marker = " [INV]" if inverted else ""
                    
                    print(f"  {threshold:<12.1f} "
                          f"{metrics['num_trades']:<10} "
                          f"{metrics['win_rate']:<12.1%} "
                          f"${metrics['total_pnl']:<14.2f} "
                          f"{metrics['sharpe_ratio']:<12.3f}{inv_marker}")
                    
                    if best_metrics is None or metrics['sharpe_ratio'] > best_metrics['sharpe_ratio']:
                        best_metrics = metrics
                        best_threshold = threshold
                        best_trades_df = trades_df
                        best_signal = signal_name
                        best_holding = holding_ms
            
            print("  " + "-"*80)
    
    if best_metrics:
        was_inverted = best_trades_df['signal_flipped'].iloc[0] if 'signal_flipped' in best_trades_df.columns else False
        print(f"\n  Best Configuration:")
        print(f"    Signal:          {best_signal}{' (inverted)' if was_inverted else ''}")
        print(f"    Threshold:       {best_threshold}")
        print(f"    Holding Period:  {best_holding}ms")
        print(f"    Win Rate:        {best_metrics['win_rate']:.1%}")
        print(f"    Sharpe Ratio:    {best_metrics['sharpe_ratio']:.3f}")
        print(f"    (N={best_metrics['num_trades']} trades -- insufficient for annualization)")
    
    # ========== Step 5b: Optimal Execution Analysis ==========
    print("\n" + "="*60)
    print("OPTIMAL EXECUTION ANALYSIS (ALMGREN-CHRISS)")
    print("="*60)
    
    try:
        # Estimate impact parameters from the order book data
        # Use average trade size and observed price impact
        avg_trade_size = 1000  # shares
        book_metrics = order_book.get_metrics()
        avg_spread = signals_df['spread'].mean() if 'spread' in signals_df.columns else 0.02
        
        # Calibrate impact parameters from observed data
        # σ: price volatility per √second (convert from per-snapshot)
        snapshot_dt = np.diff(signals_df['timestamp'].values).mean()  # actual interval
        price_std = signals_df['price'].diff().std()                   # $/snapshot
        vol_estimate = price_std / np.sqrt(max(snapshot_dt, 1e-6))     # $/√s

        # η (temporary): half-spread cost per share (Kyle's lambda proxy)
        eta_estimate = avg_spread / (2 * avg_trade_size)
        # γ (permanent): typically ~10% of temporary
        gamma_estimate = eta_estimate * 0.1
        
        scheduler = OptimalExecutionScheduler(
            total_shares=10000,
            n_periods=20,
            total_time=1.0,  # 1 second execution horizon
            sigma=vol_estimate if vol_estimate > 0 else 0.01,
            gamma=gamma_estimate if gamma_estimate > 0 else 1e-6,
            eta=eta_estimate if eta_estimate > 0 else 1e-5
        )
        
        print(f"\n  Execution Problem:")
        print(f"    Shares to liquidate: {scheduler.X:,}")
        print(f"    Time horizon:        {scheduler.T:.1f}s ({scheduler.N} periods)")
        print(f"    Volatility (sigma):        {scheduler.sigma:.6f}")
        print(f"    Permanent impact (gamma):  {scheduler.gamma:.2e}")
        print(f"    Temporary impact (eta):  {scheduler.eta:.2e}")
        
        # Compare strategies at different risk aversion levels
        print(f"\n  Strategy Comparison:")
        print("  " + "-"*80)
        print(f"  {'lam (risk aversion)':<20} {'E[Cost]':<15} {'Std[Cost]':<15} "
              f"{'Front-loaded%':<15} {'Objective':<15}")
        print("  " + "-"*80)
        
        for lam in [0, 0.001, 0.01, 0.1, 1.0, 10.0]:
            opt = scheduler.optimal_trajectory(lam)
            obj = opt['expected_cost'] + lam * opt['variance']
            fl_pct = opt['trade_list'][0] / scheduler.X * 100
            label = "TWAP" if lam == 0 else f"lam={lam}"
            fl_str = f"{fl_pct:.1f}%"
            print(f"  {label:<20} "
                  f"${opt['expected_cost']:<14.4f} "
                  f"${opt['std_cost']:<14.4f} "
                  f"{fl_str:<14} "
                  f"${obj:<14.4f}")
        
        print("  " + "-"*80)
        
        # Compare optimal vs alternatives
        comparison = scheduler.compare_strategies(risk_aversion=0.1)
        print(f"\n  At lam=0.1 (moderate risk aversion):")
        print(f"    Optimal E[cost]:    ${comparison['optimal']['expected_cost']:.4f}")
        print(f"    TWAP E[cost]:       ${comparison['twap']['expected_cost']:.4f}"
              f"  (+{comparison['twap'].get('cost_increase_pct', 0):.1f}%)")
        print(f"    Immediate E[cost]:  ${comparison['immediate']['expected_cost']:.4f}")
        
    except Exception as e:
        print(f"  Error in optimal execution analysis: {e}")
    
    # ========== Step 6: Visualization ==========
    print("\n[6/6] Generating visualizations...")
    
    viz = OrderBookVisualizer()
    
    # Plot 1: Signal analysis
    try:
        fig1 = viz.plot_signal_analysis(analyzer, signal_name='ofi')
        plt.savefig('signal_analysis.png', dpi=150, bbox_inches='tight')
        print("  Saved: signal_analysis.png")
    except Exception as e:
        print(f"  Could not create signal analysis plot: {e}")
    
    # Plot 2: Backtest results
    if best_trades_df is not None and len(best_trades_df) > 0:
        try:
            fig2 = viz.plot_backtest_results(best_trades_df, best_metrics)
            plt.savefig('backtest_results.png', dpi=150, bbox_inches='tight')
            print("  Saved: backtest_results.png")
        except Exception as e:
            print(f"  Could not create backtest plot: {e}")
    
    # Plot 3: Sample order book snapshot
    if len(snapshots) > 0:
        try:
            fig3, ax = plt.subplots(figsize=(10, 6))
            viz.plot_orderbook_snapshot(snapshots[len(snapshots)//2], ax=ax)
            plt.savefig('orderbook_snapshot.png', dpi=150, bbox_inches='tight')
            print("  Saved: orderbook_snapshot.png")
        except Exception as e:
            print(f"  Could not create orderbook plot: {e}")
    
    # Plot 4: Optimal Execution Frontier & Trajectories
    try:
        fig4, axes4 = plt.subplots(1, 3, figsize=(18, 5))
        
        # 4a: Efficient frontier
        frontier = scheduler.efficient_frontier(n_points=40)
        ax = axes4[0]
        ax.plot(frontier['std_cost'], frontier['expected_cost'], 
                'b-o', markersize=3, linewidth=1.5)
        ax.set_xlabel('Std[Cost] (Execution Risk)')
        ax.set_ylabel('E[Cost] (Expected Slippage)')
        ax.set_title('Almgren-Chriss Efficient Frontier')
        ax.grid(True, alpha=0.3)
        
        # Mark key points
        twap_row = frontier.iloc[0]
        ax.annotate('TWAP\n(risk-neutral)', 
                    xy=(twap_row['std_cost'], twap_row['expected_cost']),
                    fontsize=8, ha='left',
                    arrowprops=dict(arrowstyle='->', color='red'),
                    textcoords='offset points', xytext=(15, -15))
        
        # 4b: Trajectories at different λ
        ax = axes4[1]
        colors_exec = plt.cm.viridis(np.linspace(0, 1, 5))
        for i, lam in enumerate([0, 0.01, 0.1, 1.0, 10.0]):
            opt = scheduler.optimal_trajectory(lam)
            label = 'TWAP' if lam == 0 else f'λ={lam}'
            ax.plot(opt['time_grid'], opt['trajectory'] / scheduler.X, 
                    color=colors_exec[i], linewidth=2, label=label)
        ax.set_xlabel('Time')
        ax.set_ylabel('Remaining Position (fraction)')
        ax.set_title('Optimal Liquidation Trajectories')
        ax.legend(fontsize=8)
        ax.grid(True, alpha=0.3)
        
        # 4c: Trade rate schedules
        ax = axes4[2]
        for i, lam in enumerate([0, 0.01, 0.1, 1.0, 10.0]):
            opt = scheduler.optimal_trajectory(lam)
            label = 'TWAP' if lam == 0 else f'λ={lam}'
            ax.bar(opt['trade_times'] + i*0.008, 
                   opt['trade_list'] / scheduler.X,
                   width=0.008, alpha=0.7, color=colors_exec[i], label=label)
        ax.set_xlabel('Time')
        ax.set_ylabel('Trade Size (fraction of total)')
        ax.set_title('Execution Rate Schedules')
        ax.legend(fontsize=8)
        ax.grid(True, alpha=0.3)
        
        plt.tight_layout()
        plt.savefig('optimal_execution.png', dpi=150, bbox_inches='tight')
        print("  Saved: optimal_execution.png")
    except Exception as e:
        print(f"  Could not create execution plot: {e}")
    
    # Plot 5: Kalman convergence & innovation diagnostics
    try:
        Q_val = signal_gen.ofi_filter.Q
        R_val = signal_gen.ofi_filter.R
        kca = KalmanConvergenceAnalyzer(Q=Q_val, R=R_val)
        conv = kca.verify_convergence_numerically()
        
        fig5, axes5 = plt.subplots(1, 3, figsize=(18, 5))
        
        # 5a: Riccati convergence
        ax = axes5[0]
        P_traj = conv['P_trajectory'][:50]
        ax.plot(P_traj, 'b-', linewidth=2, label='P_t (numerical)')
        ax.axhline(conv['P_inf_analytical'], color='red', linestyle='--', 
                   linewidth=2, label=f'P_∞ = {conv["P_inf_analytical"]:.6f}')
        ax.set_xlabel('Iteration')
        ax.set_ylabel('Error Covariance P')
        ax.set_title('Riccati Recursion Convergence')
        ax.legend()
        ax.grid(True, alpha=0.3)
        
        # 5b: Sensitivity of K_∞ to Q/R ratio
        ax = axes5[1]
        qr_ratios = np.logspace(-4, 2, 100)
        gains = []
        for qr in qr_ratios:
            kca_temp = KalmanConvergenceAnalyzer(Q=qr * R_val, R=R_val)
            gains.append(kca_temp.steady_state_gain())
        ax.semilogx(qr_ratios, gains, 'b-', linewidth=2)
        ax.axvline(Q_val / R_val, color='red', linestyle='--', 
                   label=f'Current Q/R = {Q_val/R_val:.2f}')
        ax.set_xlabel('Q/R Ratio (Signal-to-Noise)')
        ax.set_ylabel('Steady-State Gain K_∞')
        ax.set_title('Kalman Gain Sensitivity')
        ax.legend()
        ax.grid(True, alpha=0.3)
        
        # 5c: Innovation autocorrelations
        ofi_values = signals_df['ofi'].dropna().values
        if len(ofi_values) > 100:
            innov_test = kca.innovation_consistency_test(ofi_values)
            if 'autocorrelations' in innov_test:
                ax = axes5[2]
                lags = np.arange(1, len(innov_test['autocorrelations']) + 1)
                ax.bar(lags, innov_test['autocorrelations'], color='steelblue', alpha=0.7)
                # 95% confidence bands for white noise
                n_innov = len(ofi_values)
                ci = 1.96 / np.sqrt(n_innov)
                ax.axhline(ci, color='red', linestyle='--', alpha=0.7, label='95% CI')
                ax.axhline(-ci, color='red', linestyle='--', alpha=0.7)
                ax.axhline(0, color='black', linewidth=0.5)
                ax.set_xlabel('Lag')
                ax.set_ylabel('Autocorrelation')
                ax.set_title('Innovation Autocorrelations')
                ax.legend()
                ax.grid(True, alpha=0.3)
        
        plt.tight_layout()
        plt.savefig('kalman_analysis.png', dpi=150, bbox_inches='tight')
        print("  Saved: kalman_analysis.png")
    except Exception as e:
        print(f"  Could not create Kalman plot: {e}")
    
    print("\n" + "="*60)
    print("ANALYSIS COMPLETE")
    print("="*60)
    
    return {
        'signals_df': signals_df,
        'analyzer': analyzer,
        'best_metrics': best_metrics,
        'best_trades': best_trades_df,
        'order_book': order_book
    }

# ==================== REGIME DETECTION (BONUS) ====================

class RegimeDetector:
    """
    Detect market regimes where signals work vs fail
    """
    
    @staticmethod
    def compute_volatility_regime(prices: np.ndarray, window: int = 100) -> np.ndarray:
        """Compute rolling volatility regime"""
        returns = np.diff(prices) / prices[:-1]
        
        vol = np.zeros(len(prices))
        for i in range(window, len(returns)):
            vol[i] = np.std(returns[i-window:i])
        
        # Classify into low/medium/high
        vol_quantiles = np.percentile(vol[vol > 0], [33, 66])
        
        regime = np.zeros(len(vol))
        regime[vol <= vol_quantiles[0]] = 0  # Low vol
        regime[(vol > vol_quantiles[0]) & (vol <= vol_quantiles[1])] = 1  # Medium
        regime[vol > vol_quantiles[1]] = 2  # High vol
        
        return regime
    
    @staticmethod
    def analyze_regime_performance(signals_df: pd.DataFrame, 
                                   trades_df: pd.DataFrame) -> pd.DataFrame:
        """
        Analyze strategy performance by regime
        
        Args:
            signals_df: DataFrame with signals
            trades_df: DataFrame with trades
            
        Returns:
            Performance metrics by regime
        """
        # Compute regimes
        prices = signals_df['price'].values
        regimes = RegimeDetector.compute_volatility_regime(prices)
        
        # Add regime to signals
        signals_df['regime'] = regimes
        
        # Merge with trades
        trades_with_regime = trades_df.copy()
        
        # Map entry time to regime
        regime_map = dict(zip(signals_df['timestamp'], signals_df['regime']))
        
        trades_with_regime['regime'] = trades_with_regime['entry_time'].map(
            lambda t: min(regime_map.items(), key=lambda x: abs(x[0]-t))[1]
        )
        
        # Analyze by regime
        regime_results = []
        
        for regime in [0, 1, 2]:
            regime_trades = trades_with_regime[trades_with_regime['regime'] == regime]
            
            if len(regime_trades) > 0:
                pnls = regime_trades['pnl'].values
                returns = regime_trades['return'].values
                
                regime_results.append({
                    'regime': ['Low Vol', 'Medium Vol', 'High Vol'][regime],
                    'num_trades': len(regime_trades),
                    'win_rate': (pnls > 0).mean(),
                    'avg_pnl': pnls.mean(),
                    'total_pnl': pnls.sum(),
                    'sharpe': returns.mean() / returns.std() if returns.std() > 0 else 0
                })
        
        return pd.DataFrame(regime_results)

# ==================== PERFORMANCE TESTING ====================

def performance_benchmark():
    """
    Benchmark order book processing speed
    """
    print("\n" + "="*60)
    print("PERFORMANCE BENCHMARK")
    print("="*60)
    
    test_sizes = [1000, 5000, 10000, 50000]
    
    for n in test_sizes:
        df = LOBSTERDataLoader.create_synthetic_data(num_messages=n, seed=42)
        
        book = OrderBook()
        
        start = time.time()
        
        for _, row in df.iterrows():
            book.process_lobster_message(
                timestamp=row['timestamp'],
                event_type=row['event_type'],
                order_id=row['order_id'],
                size=row['size'],
                price=row['price'],
                direction=row['direction']
            )
        
        elapsed = time.time() - start
        throughput = n / elapsed
        
        print(f"\nMessages: {n:,}")
        print(f"Time: {elapsed:.3f}s")
        print(f"Throughput: {throughput:,.0f} msg/s")

# ==================== UNIT TESTS ====================

def run_unit_tests():
    """
    Basic unit tests for core functionality
    """
    print("\n" + "="*60)
    print("UNIT TESTS")
    print("="*60)
    
    # Test 1: Order book basic operations
    print("\n[Test 1] Order Book Operations")
    book = OrderBook()
    
    # Add bid
    book.process_lobster_message(0.0, EventType.NEW_LIMIT, 1, 100, 99.50, -1)
    snapshot = book.get_snapshot()
    assert snapshot.best_bid == 99.50, "Best bid incorrect"
    print("  Add bid order")
    
    # Add ask
    book.process_lobster_message(0.1, EventType.NEW_LIMIT, 2, 100, 100.50, 1)
    snapshot = book.get_snapshot()
    assert snapshot.best_ask == 100.50, "Best ask incorrect"
    assert snapshot.spread == 1.0, "Spread incorrect"
    print("  Add ask order")
    
    # Cancel order
    book.process_lobster_message(0.2, EventType.CANCELLATION, 1, 50, 99.50, -1)
    snapshot = book.get_snapshot()
    assert snapshot.bids[0].size == 50, "Cancellation incorrect"
    print("  Cancel order")
    
    # Test 2: Signal generation
    print("\n[Test 2] Signal Generation")
    sig_gen = SignalGenerator()
    
    book = OrderBook()
    book.process_lobster_message(0.0, EventType.NEW_LIMIT, 1, 100, 99.50, -1)
    book.process_lobster_message(0.0, EventType.NEW_LIMIT, 2, 200, 100.50, 1)
    
    snapshot = book.get_snapshot()
    
    ofi = sig_gen.compute_ofi(snapshot)
    assert -1 <= ofi <= 1, "OFI out of range"
    print(f"  OFI computed: {ofi:.3f}")
    
    delta = sig_gen.compute_delta_ofi(snapshot)
    print(f"  Delta OFI computed: {delta:.3f}")
    
    mp = sig_gen.compute_microprice(snapshot)
    assert mp is not None, "Microprice failed"
    assert 99.5 <= mp <= 100.5, "Microprice out of range"
    print(f"  Microprice computed: {mp:.2f}")
    
    # Test all signals together
    signals = sig_gen.compute_all_signals(snapshot, book)
    assert 'composite' in signals, "Composite signal missing"
    assert 'delta_ofi' in signals, "Delta OFI signal missing"
    assert 'trade_imbalance' in signals, "Trade imbalance signal missing"
    print(f"  All signals computed ({len(signals)} fields)")
    
    # Test 3: Kalman filter
    print("\n[Test 3] Kalman Filter")
    kf = KalmanFilter()
    
    noisy_signal = [1.0, 1.1, 0.9, 1.2, 0.8, 1.0]
    filtered = [kf.update(x) for x in noisy_signal]
    
    # Filtered signal should be smoother
    filtered_std = np.std(filtered)
    raw_std = np.std(noisy_signal)
    assert filtered_std < raw_std, "Kalman filter not smoothing"
    print(f"  Noise reduction: {raw_std:.3f} -> {filtered_std:.3f}")
    
    # Test 4: Kalman Convergence Analysis
    print("\n[Test 4] Kalman Convergence Analysis")
    kca = KalmanConvergenceAnalyzer(Q=1e-3, R=0.01)
    
    # Verify DARE solution
    P_inf = kca.steady_state_covariance()
    # Check it satisfies the fixed-point equation: P = (P+Q)R/(P+Q+R)
    P_check = (P_inf + 1e-3) * 0.01 / (P_inf + 1e-3 + 0.01)
    assert abs(P_inf - P_check) < 1e-10, f"DARE solution inconsistent: {P_inf} vs {P_check}"
    print(f"  P_inf = {P_inf:.8f} (DARE verified)")
    
    K_inf = kca.steady_state_gain()
    assert 0 < K_inf < 1, f"Steady-state gain out of (0,1): {K_inf}"
    print(f"  K_inf = {K_inf:.6f}")
    
    conv = kca.verify_convergence_numerically()
    assert conv['agreement'], "Numerical convergence disagrees with analytical"
    print(f"  Convergence rate rho = {conv['rho_theoretical']:.6f}")
    print(f"  Converged in {conv['converged_at_step']} iterations")
    
    # Test 5: Statistical Significance Testing
    print("\n[Test 5] Statistical Significance Tests")
    np.random.seed(42)
    n_test = 500
    
    # Case A: Signal with known correlation
    x_sig = np.random.randn(n_test)
    y_ret = 0.3 * x_sig + np.random.randn(n_test)  # True ρ ≈ 0.29
    
    fisher_result = SignalSignificanceTester.fisher_z_test(x_sig, y_ret)
    assert fisher_result['significant_5pct'], "Should detect ρ≈0.3 as significant"
    print(f"  Correlated signal: r={fisher_result['correlation']:.3f}, "
          f"p={fisher_result['p_value']:.4f} [correctly significant]")
    
    # Case B: Null signal (no relationship)
    x_null = np.random.randn(n_test)
    y_null = np.random.randn(n_test)
    
    fisher_null = SignalSignificanceTester.fisher_z_test(x_null, y_null)
    print(f"  Null signal: r={fisher_null['correlation']:.3f}, "
          f"p={fisher_null['p_value']:.4f} [expect non-significant]")
    
    # Multiple testing correction
    p_vals = {'test_a': 0.01, 'test_b': 0.04, 'test_c': 0.06, 'test_d': 0.20}
    bh_result = SignalSignificanceTester.multiple_testing_correction(p_vals, 'bh')
    assert bh_result['test_a']['significant_5pct'], "BH should keep p=0.01"
    print(f"  BH correction: 4 tests, {sum(1 for v in bh_result.values() if v['significant_5pct'])} significant")
    
    # Test 6: Optimal Execution Scheduler
    print("\n[Test 6] Optimal Execution (Almgren-Chriss)")
    scheduler = OptimalExecutionScheduler(
        total_shares=10000, n_periods=20, total_time=1.0,
        sigma=0.01, gamma=1e-6, eta=1e-5
    )
    
    # TWAP should split evenly
    twap = scheduler.optimal_trajectory(risk_aversion=0)
    assert abs(twap['trade_list'].std()) < 1e-10, "TWAP should have equal trades"
    assert abs(twap['trajectory'][0] - 10000) < 1e-10, "Should start at X"
    assert abs(twap['trajectory'][-1]) < 1e-10, "Should end at 0"
    print(f"  TWAP: {twap['trade_list'][0]:.0f} shares/period")
    
    # Higher λ should front-load trades
    aggressive = scheduler.optimal_trajectory(risk_aversion=1.0)
    assert aggressive['trade_list'][0] > twap['trade_list'][0], \
        "Higher lambda should front-load execution"
    print(f"  lambda=1.0: first trade = {aggressive['trade_list'][0]:.0f} "
          f"({aggressive['trade_list'][0]/10000*100:.1f}% of total)")
    
    # Efficient frontier should be monotone
    frontier = scheduler.efficient_frontier(n_points=20)
    assert frontier['expected_cost'].is_monotonic_increasing or \
           len(frontier) < 3, "Frontier E[cost] should increase with λ"
    print(f"  Efficient frontier: {len(frontier)} points computed")
    
    print("\n" + "="*60)
    print("ALL TESTS PASSED")
    print("="*60)

# ==================== MAIN ENTRY POINT ====================

if __name__ == "__main__":
    import sys
    
    print("\n")
    # print("╔" + "═"*58 + "╗")
    # print("║" + " "*58 + "║")
    # print("║" + "  LIMIT ORDER BOOK SIGNAL PROCESSOR  ".center(58) + "║")
    # print("║" + "  High-Frequency Trading Research Platform  ".center(58) + "║")
    # print("║" + " "*58 + "║")
    # print("╚" + "═"*58 + "╝")
    
    # Run tests first
    run_unit_tests()
    
    # Performance benchmark
    performance_benchmark()
    
    # Full analysis
    results = run_comprehensive_analysis()
    
    # Regime analysis (if trades exist)
    if results['best_trades'] is not None and len(results['best_trades']) > 0:
        print("\n" + "="*60)
        print("REGIME ANALYSIS")
        print("="*60)
        
        regime_perf = RegimeDetector.analyze_regime_performance(
            results['signals_df'],
            results['best_trades']
        )
        
        print("\nPerformance by Volatility Regime:")
        print(regime_perf.to_string(index=False))
    
    print("\n\n" + "="*60)
    print("EXECUTION COMPLETE")
    print("="*60)
    print("\nKey Deliverables Generated:")
    print("  1. Order book reconstruction engine")
    print("  2. Signal generation framework")
    print("  3. Predictive analysis with statistical significance testing")
    print("  4. Kalman filter convergence analysis (DARE, innovation tests)")
    print("  5. Almgren-Chriss optimal execution scheduler")
    print("  6. Backtest results")
    print("  7. Visualization outputs")
    print("\nFiles created:")
    print("  - signal_analysis.png")
    print("  - backtest_results.png")
    print("  - orderbook_snapshot.png")
    print("  - optimal_execution.png")
    print("  - kalman_analysis.png")
    print("\n" + "="*60)