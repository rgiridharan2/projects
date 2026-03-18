"""
High-Performance Limit Order Book Implementation
Order book reconstruction and signal generation for HFT research
"""

import time
import numba
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Dict, List, Tuple, Optional
from matplotlib.animation import FuncAnimation
from enum import IntEnum
from numba import jit
from scipy import stats as sp_stats
from scipy.linalg import solve_discrete_are
import warnings
warnings.filterwarnings('ignore')

# Data Structures 
class Side(IntEnum):
    BID = 1
    ASK = -1

class EventType(IntEnum):
    NEW_LIMIT = 1
    CANCELLATION = 2
    DELETION = 3
    EXECUTION_VISIBLE = 4
    EXECUTION_HIDDEN = 5
    CROSS_TRADE = 6
    TRADING_HALT = 7

@dataclass
class Level:
    price: float
    size: int
    def __repr__(self):
        return f"({self.price:.2f}@{self.size})"

@dataclass
class BookSnapshot:
    """Point-in-time order book snapshot"""
    timestamp: float
    bids: List[Level]  # Sorted in descending order
    asks: List[Level]  # Sorted in ascending order

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
        bp, ap = self.bids[0].price, self.asks[0].price
        bs, az = self.bids[0].size, self.asks[0].size
        return (bp * az + ap * bs) / (bs + az) if (bs + az) > 0 else self.mid_price

    def get_imbalance(self, levels: int = 1) -> float:
        """Order flow imbalance at top N levels"""
        bid_vol = sum(b.size for b in self.bids[:levels])
        ask_vol = sum(a.size for a in self.asks[:levels])
        total = bid_vol + ask_vol
        return (bid_vol - ask_vol) / total if total > 0 else 0.0
# Order Book Engine

class OrderBook:
    """High-performance limit order book with O(1) updates. Target of >10,000 msg/s."""

    def __init__(self, tick_size: float = 0.01, num_levels: int = 10):
        self.tick_size = tick_size
        self.num_levels = num_levels
        self.bids: Dict[float, int] = {}
        self.asks: Dict[float, int] = {}
        self.bid_prices: List[float] = []
        self.ask_prices: List[float] = []
        self.message_count = 0
        self.last_update_time = 0.0
        self.trade_events: List[Dict] = []
        self.book_events: List[Dict] = []

    def _get_side(self, side: Side):
        """Return (book_dict, price_list) for the given side."""
        if side == Side.ASK:
            return self.asks, self.ask_prices
        return self.bids, self.bid_prices

    def process_lobster_message(self, timestamp: float, event_type: int,
                                order_id: int, size: int, price: float,
                                direction: int) -> None:
        """Process LOBSTER format message. direction: 1=sell(ask), -1=buy(bid)."""
        self.last_update_time = timestamp
        self.message_count += 1
        side = Side.ASK if direction == 1 else Side.BID

        if event_type == EventType.NEW_LIMIT:
            self._add_order(side, price, size)
        elif event_type == EventType.CANCELLATION:
            self._cancel_order(side, price, size)
        elif event_type in (EventType.EXECUTION_VISIBLE, EventType.EXECUTION_HIDDEN):
            self._cancel_order(side, price, size)
            self.trade_events.append({
                'timestamp': timestamp, 'price': price, 'size': size,
                'side': 'buy' if side == Side.BID else 'sell'
            })
        elif event_type == EventType.DELETION:
            self._cancel_order(side, price, size)

        self._uncross_book()

    def _add_order(self, side: Side, price: float, size: int) -> None:
        book, prices = self._get_side(side)
        if price in book:
            book[price] += size
        else:
            book[price] = size
            idx = (np.searchsorted([-p for p in prices], -price) if side == Side.BID
                   else np.searchsorted(prices, price))
            prices.insert(idx, price)
        self._trim_book(side)

    def _cancel_order(self, side: Side, price: float, size: int) -> None:
        book, prices = self._get_side(side)
        if price in book:
            book[price] = max(0, book[price] - size)
            if book[price] == 0:
                del book[price]
                prices.remove(price)

    def _trim_book(self, side: Side) -> None:
        book, prices = self._get_side(side)
        if len(prices) > self.num_levels:
            for price in prices[self.num_levels:]:
                book.pop(price, None)
            if side == Side.BID:
                self.bid_prices = prices[:self.num_levels]
            else:
                self.ask_prices = prices[:self.num_levels]

    def _uncross_book(self) -> None:
        while (self.bid_prices and self.ask_prices and
               self.bid_prices[0] >= self.ask_prices[0]):
            self.bids.pop(self.bid_prices.pop(0), None)
            self.asks.pop(self.ask_prices.pop(0), None)

    @property
    def is_crossed(self) -> bool:
        return bool(self.bid_prices and self.ask_prices and self.bid_prices[0] >= self.ask_prices[0])

    def get_snapshot(self, num_levels: int = 5) -> BookSnapshot:
        bids = [Level(p, self.bids[p]) for p in self.bid_prices[:num_levels] if p in self.bids]
        asks = [Level(p, self.asks[p]) for p in self.ask_prices[:num_levels] if p in self.asks]
        return BookSnapshot(timestamp=self.last_update_time, bids=bids, asks=asks)

    def get_metrics(self) -> Dict:
        return {
            'messages_processed': self.message_count,
            'bid_levels': len(self.bid_prices),
            'ask_levels': len(self.ask_prices),
            'total_bid_volume': sum(self.bids.values()),
            'total_ask_volume': sum(self.asks.values()),
            'trades': len(self.trade_events)
        }

# signal processing
class KalmanFilter:
    """1D Kalman filter for signal denoising.
    State: x_t = x_{t-1} + w_t (Q), Obs: y_t = x_t + v_t (R).
    Q/R ratio controls responsiveness; use Q/R >= 0.01 for HFT signals."""

    def __init__(self, process_variance: float = 1e-3,
                 measurement_variance: float = 0.01):
        self.Q = process_variance
        self.R = measurement_variance
        self.x = 0.0
        self.P = 1.0
        self.initialized = False

    def update(self, measurement: float) -> float:
        if not self.initialized:
            self.x = measurement
            self.initialized = True
            return self.x
        x_pred = self.x
        P_pred = self.P + self.Q
        K = P_pred / (P_pred + self.R)
        self.x = x_pred + K * (measurement - x_pred)
        self.P = (1 - K) * P_pred
        return self.x

@jit(nopython=True)
def exponential_smooth(values: np.ndarray, alpha: float) -> np.ndarray:
    result = np.empty_like(values)
    result[0] = values[0]
    for i in range(1, len(values)):
        result[i] = alpha * values[i] + (1 - alpha) * result[i-1]
    return result

@jit(nopython=True)
def rolling_zscore(values: np.ndarray, window: int) -> np.ndarray:
    n = len(values)
    result = np.zeros(n)
    for i in range(window, n):
        window_data = values[i-window:i]
        mean = np.mean(window_data)
        std = np.std(window_data)
        if std > 1e-8:
            result[i] = (values[i] - mean) / std
    return result

# kalman convergence analysis 

class KalmanConvergenceAnalyzer:
    """Rigorous convergence analysis for the 1D Kalman filter.
    Solves the DARE: P^2 + QP - QR = 0 => P_inf = [-Q + sqrt(Q^2 + 4QR)] / 2.
    Verifies geometric convergence and innovation whiteness."""

    def __init__(self, Q: float, R: float):
        if Q <= 0 or R <= 0:
            raise ValueError("Q and R must be strictly positive")
        self.Q, self.R = Q, R

    def steady_state_covariance(self) -> float:
        """P_inf = [-Q + sqrt(Q^2 + 4QR)] / 2"""
        return (-self.Q + np.sqrt(self.Q**2 + 4 * self.Q * self.R)) / 2.0

    def steady_state_gain(self) -> float:
        """K_inf = (P_inf + Q) / (P_inf + Q + R), in (0,1)"""
        P_inf = self.steady_state_covariance()
        P_pred = P_inf + self.Q
        return P_pred / (P_pred + self.R)

    def convergence_rate(self) -> float:
        """Geometric contraction rate rho = (R / (P_inf + Q + R))^2"""
        P_inf = self.steady_state_covariance()
        return (self.R / (P_inf + self.Q + self.R)) ** 2

    def verify_convergence_numerically(self, P_0: float = 1.0,
                                        n_steps: int = 200,
                                        tol: float = 1e-12) -> Dict:
        """Iterate P_{t+1} = (P_t + Q)R / (P_t + Q + R) and verify convergence."""
        P_inf_analytical = self.steady_state_covariance()
        rho_theoretical = self.convergence_rate()

        P_trajectory = np.zeros(n_steps)
        P = P_0
        converged_step = n_steps

        for t in range(n_steps):
            P_pred = P + self.Q
            P = P_pred * self.R / (P_pred + self.R)
            P_trajectory[t] = P
            if abs(P - P_inf_analytical) < tol and converged_step == n_steps:
                converged_step = t + 1

        # Estimate empirical convergence rate
        errors = np.abs(P_trajectory - P_inf_analytical)
        valid = errors > 1e-14
        rho_empirical = np.nan
        if valid.sum() > 2:
            log_errors = np.log(errors[valid])
            steps_valid = np.where(valid)[0]
            if len(steps_valid) > 2:
                n_fit = min(50, len(steps_valid))
                slope, _, _, _, _ = sp_stats.linregress(steps_valid[:n_fit], log_errors[:n_fit])
                rho_empirical = np.exp(slope)

        return {
            'P_inf_analytical': P_inf_analytical, 'P_inf_numerical': P_trajectory[-1],
            'K_inf': self.steady_state_gain(), 'rho_theoretical': rho_theoretical,
            'rho_empirical': rho_empirical, 'converged_at_step': converged_step,
            'P_trajectory': P_trajectory,
            'agreement': abs(P_trajectory[-1] - P_inf_analytical) < 1e-10,
            'snr_db': 10 * np.log10(self.Q / self.R)
        }

    def innovation_consistency_test(self, measurements: np.ndarray,
                                     max_lag: int = 20) -> Dict:
        """Test innovation whiteness: zero-mean (t-test), Ljung-Box, and NIS consistency."""
        n = len(measurements)
        if n < max_lag + 10:
            return {'error': 'Insufficient data for innovation test'}

        # Run Kalman filter and collect innovations
        innovations = np.zeros(n)
        predicted_variances = np.zeros(n)
        x, P = 0.0, 1.0

        for t in range(n):
            if t == 0:
                innovations[t] = measurements[t]
                x = measurements[t]
                continue
            x_pred, P_pred = x, P + self.Q
            innovations[t] = measurements[t] - x_pred
            predicted_variances[t] = P_pred + self.R
            K = P_pred / (P_pred + self.R)
            x = x_pred + K * innovations[t]
            P = (1 - K) * P_pred

        burn_in = max(50, n // 10)
        innov = innovations[burn_in:]
        pred_var = predicted_variances[burn_in:]

        # Test 1: Zero-mean
        t_stat, t_pvalue = sp_stats.ttest_1samp(innov, 0.0)

        # Test 2: Ljung-Box whiteness
        n_innov = len(innov)
        autocorrs = np.array([
            np.corrcoef(innov[:-k], innov[k:])[0, 1] for k in range(1, max_lag + 1)
        ])
        Q_LB = n_innov * (n_innov + 2) * np.sum(
            autocorrs**2 / (n_innov - np.arange(1, max_lag + 1)))
        lb_pvalue = 1 - sp_stats.chi2.cdf(Q_LB, df=max_lag)

        # Test 3: Normalized innovation squared
        P_inf = self.steady_state_covariance()
        S_inf = P_inf + self.Q + self.R
        mean_nis = np.mean(innov**2 / S_inf)

        return {
            'zero_mean_t_stat': t_stat, 'zero_mean_p_value': t_pvalue,
            'zero_mean_pass': t_pvalue > 0.05,
            'ljung_box_Q': Q_LB, 'ljung_box_p_value': lb_pvalue,
            'whiteness_pass': lb_pvalue > 0.05,
            'mean_nis': mean_nis, 'nis_consistent': 0.5 < mean_nis < 2.0,
            'innovation_std': np.std(innov), 'predicted_std': np.sqrt(S_inf),
            'max_autocorr': np.max(np.abs(autocorrs)), 'autocorrelations': autocorrs
        }


class SignalGenerator:
    """Generate predictive signals: OFI, delta OFI, trade imbalance, spread pressure, composite."""

    def __init__(self, trade_window: int = 50):
        self.ofi_filter = KalmanFilter(process_variance=1e-3, measurement_variance=0.01)
        self.signals_history = defaultdict(list)
        self.prev_ofi = 0.0
        self.ofi_initialized = False
        self.recent_trades = deque(maxlen=trade_window)
        self.trade_window = trade_window

    def compute_ofi(self, snapshot: BookSnapshot, levels: int = 3) -> float:
        raw_ofi = snapshot.get_imbalance(levels)
        filtered_ofi = self.ofi_filter.update(raw_ofi)
        self.signals_history['ofi_raw'].append(raw_ofi)
        self.signals_history['ofi_filtered'].append(filtered_ofi)
        return filtered_ofi

    def compute_delta_ofi(self, snapshot: BookSnapshot, levels: int = 3) -> float:
        """Change in OFI — more predictive than level per microstructure theory."""
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
        """Net signed trade pressure from recent executions, in [-1, 1]."""
        new_trades = order_book.trade_events[len(self.recent_trades):]
        for t in new_trades:
            signed_size = t['size'] if t['side'] == 'sell' else -t['size']
            self.recent_trades.append(signed_size)
        if not self.recent_trades:
            return 0.0
        buy_vol = sum(s for s in self.recent_trades if s > 0)
        sell_vol = sum(abs(s) for s in self.recent_trades if s < 0)
        total = buy_vol + sell_vol
        imbalance = (buy_vol - sell_vol) / total if total > 0 else 0.0
        self.signals_history['trade_imbalance'].append(imbalance)
        return imbalance

    def compute_microprice(self, snapshot: BookSnapshot) -> Optional[float]:
        mp = snapshot.microprice
        if mp is not None:
            self.signals_history['microprice'].append(mp)
        return mp

    def compute_spread_pressure(self, snapshot: BookSnapshot, window: int = 100) -> float:
        """Normalized spread z-score relative to recent history."""
        spread = snapshot.spread
        if spread is None:
            return 0.0
        self.signals_history['spread'].append(spread)
        if len(self.signals_history['spread']) < window:
            return 0.0
        recent = self.signals_history['spread'][-window:]
        std_s = np.std(recent)
        if std_s < 1e-8:
            return 0.0
        pressure = (spread - np.mean(recent)) / std_s
        self.signals_history['spread_pressure'].append(pressure)
        return pressure

    def compute_composite(self, delta_ofi: float, trade_imbalance: float,
                          spread_pressure: float) -> float:
        """Heuristic weighted combination of alpha sources."""
        composite = 0.40 * delta_ofi + 0.40 * trade_imbalance + 0.20 * (-spread_pressure)
        self.signals_history['composite'].append(composite)
        return composite

    def compute_all_signals(self, snapshot: BookSnapshot,
                           order_book: 'OrderBook' = None) -> Dict[str, float]:
        ofi = self.compute_ofi(snapshot)
        delta_ofi = self.compute_delta_ofi(snapshot)
        sp = self.compute_spread_pressure(snapshot)
        trade_imb = self.compute_trade_imbalance(order_book) if order_book else 0.0
        composite = self.compute_composite(delta_ofi, trade_imb, sp)
        return {
            'ofi': ofi, 'delta_ofi': delta_ofi, 'trade_imbalance': trade_imb,
            'spread_pressure': sp, 'composite': composite,
            'microprice': self.compute_microprice(snapshot),
            'mid_price': snapshot.mid_price, 'spread': snapshot.spread,
            'timestamp': snapshot.timestamp
        }

# shared utility function

def compute_forward_returns_at_horizon(df: pd.DataFrame, horizon_sec: float) -> np.ndarray:
    """Compute forward returns for each row at a given horizon (in seconds)."""
    timestamps = df['timestamp'].values
    prices = df['price'].values
    fwd_ret = np.full(len(df), np.nan)
    for i in range(len(df)):
        target_time = timestamps[i] + horizon_sec
        mask = timestamps >= target_time
        if mask.any():
            j = np.argmax(mask)
            fwd_ret[i] = (prices[j] - prices[i]) / prices[i]
    return fwd_ret

# predictive analysis 

class PredictiveAnalyzer:
    """Analyze forecasting power of signals across horizons."""

    def __init__(self, horizons_ms: List[int] = [100, 500, 1000, 5000]):
        self.horizons_ms = horizons_ms
        self.signal_data = []

    def record_signal(self, signals: Dict[str, float], current_price: float) -> None:
        record = signals.copy()
        record['price'] = current_price
        self.signal_data.append(record)

    def compute_forward_returns(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        for h_ms in self.horizons_ms:
            df[f'fwd_ret_{h_ms}ms'] = compute_forward_returns_at_horizon(df, h_ms / 1000.0)
        return df

    def analyze_predictive_power(self, signal_name: str = 'ofi') -> pd.DataFrame:
        df = pd.DataFrame(self.signal_data)
        if signal_name not in df.columns:
            raise ValueError(f"Signal {signal_name} not found")
        df = self.compute_forward_returns(df)

        results = []
        for h_ms in self.horizons_ms:
            ret_col = f'fwd_ret_{h_ms}ms'
            if ret_col not in df.columns:
                continue
            valid = df[signal_name].notna() & df[ret_col].notna()
            sig_vals, returns = df.loc[valid, signal_name], df.loc[valid, ret_col]
            if len(sig_vals) < 10:
                continue

            correlation = sig_vals.corr(returns)
            hit_rate = (np.sign(sig_vals) == np.sign(returns)).mean()

            df_valid = df[valid].copy()
            try:
                df_valid['quintile'] = pd.qcut(df_valid[signal_name], 5,
                                               labels=['Q1','Q2','Q3','Q4','Q5'], duplicates='drop')
            except ValueError:
                df_valid['quintile'] = pd.qcut(df_valid[signal_name], 5, duplicates='drop')
            qr = df_valid.groupby('quintile')[ret_col].mean()

            results.append({
                'horizon_ms': h_ms, 'correlation': correlation, 'hit_rate': hit_rate,
                'mean_return': returns.mean(),
                'sharpe': returns.mean() / returns.std() if returns.std() > 0 else 0,
                'q1_return': qr.get('Q1', np.nan), 'q5_return': qr.get('Q5', np.nan),
                'q5_q1_spread': qr.get('Q5', 0) - qr.get('Q1', 0)
            })
        return pd.DataFrame(results)

    def signal_decay_analysis(self, signal_name: str = 'ofi',
                             max_horizon_ms: int = 10000,
                             step_ms: int = 100) -> pd.DataFrame:
        df = pd.DataFrame(self.signal_data)
        horizons = list(range(step_ms, max_horizon_ms + step_ms, step_ms))
        correlations = []
        for h_ms in horizons:
            fwd_ret = compute_forward_returns_at_horizon(df, h_ms / 1000.0)
            valid = df[signal_name].notna() & np.isfinite(fwd_ret)
            if valid.sum() > 10:
                correlations.append(df.loc[valid, signal_name].corr(pd.Series(fwd_ret[valid], index=df.index[valid])))
            else:
                correlations.append(np.nan)
        return pd.DataFrame({'horizon_ms': horizons, 'correlation': correlations})

# statistical significance testing 

class SignalSignificanceTester:
    """Rigorous tests for signal predictive power: Fisher z (Newey-West adjusted),
    block bootstrap, and BH/Bonferroni/Holm multiple testing correction."""

    @staticmethod
    def fisher_z_test(signal: np.ndarray, returns: np.ndarray,
                      newey_west_lags: int = None) -> Dict:
        """Fisher z-test for H0: rho=0 with autocorrelation-adjusted n_eff."""
        valid = np.isfinite(signal) & np.isfinite(returns)
        x, y = signal[valid], returns[valid]
        n = len(x)
        if n < 10:
            return {'error': 'Insufficient observations', 'n': n}

        r = np.corrcoef(x, y)[0, 1]
        if newey_west_lags is None:
            newey_west_lags = int(np.floor(4 * (n / 100) ** (2/9)))
        newey_west_lags = max(1, min(newey_west_lags, n // 4))

        x_dm, y_dm = x - np.mean(x), y - np.mean(y)
        sum_gamma = 0.0
        for k in range(1, newey_west_lags + 1):
            w_k = 1 - k / (newey_west_lags + 1)
            rho_x = np.corrcoef(x_dm[:-k], x_dm[k:])[0, 1]
            rho_y = np.corrcoef(y_dm[:-k], y_dm[k:])[0, 1]
            sum_gamma += w_k * rho_x * rho_y

        n_eff = max(10, n / max(1 + 2 * sum_gamma, 0.1))
        z = np.arctanh(r)
        se = 1.0 / np.sqrt(n_eff - 3)
        z_stat = z / se
        p_value = 2 * (1 - sp_stats.norm.cdf(abs(z_stat)))
        r_lower, r_upper = np.tanh(z - 1.96 * se), np.tanh(z + 1.96 * se)

        return {
            'correlation': r, 'fisher_z': z, 'z_statistic': z_stat,
            'p_value': p_value, 'significant_5pct': p_value < 0.05,
            'significant_1pct': p_value < 0.01, 'n_raw': n, 'n_effective': n_eff,
            'inflation_factor': 1 + 2 * sum_gamma,
            'ci_95_lower': r_lower, 'ci_95_upper': r_upper,
            'newey_west_lags': newey_west_lags
        }

    @staticmethod
    def block_bootstrap_test(signal: np.ndarray, returns: np.ndarray,
                              n_bootstrap: int = 5000, block_length: int = None) -> Dict:
        """Circular block bootstrap test for H0: rho=0 (Politis & Romano, 1992)."""
        valid = np.isfinite(signal) & np.isfinite(returns)
        x, y = signal[valid], returns[valid]
        n = len(x)
        if n < 30:
            return {'error': 'Insufficient data for block bootstrap', 'n': n}

        if block_length is None:
            block_length = max(2, int(np.ceil((3 * n) ** (1/3))))

        r_obs = np.corrcoef(x, y)[0, 1]
        n_blocks = int(np.ceil(n / block_length))
        bootstrap_corrs = np.zeros(n_bootstrap)
        rng = np.random.RandomState(42)

        for b in range(n_bootstrap):
            block_starts = rng.randint(0, n, size=n_blocks)
            resampled_idx = np.concatenate([
                np.arange(s, s + block_length) % n for s in block_starts
            ])[:n]
            bootstrap_corrs[b] = np.corrcoef(x[resampled_idx], y)[0, 1]

        p_value = np.mean(np.abs(bootstrap_corrs) >= np.abs(r_obs))
        return {
            'correlation': r_obs, 'bootstrap_p_value': p_value,
            'significant_5pct': p_value < 0.05,
            'bootstrap_mean': np.mean(bootstrap_corrs),
            'bootstrap_std': np.std(bootstrap_corrs),
            'ci_95_lower': np.percentile(bootstrap_corrs, 2.5),
            'ci_95_upper': np.percentile(bootstrap_corrs, 97.5),
            'block_length': block_length, 'n_bootstrap': n_bootstrap,
            'bootstrap_distribution': bootstrap_corrs
        }

    @staticmethod
    def multiple_testing_correction(p_values: Dict[str, float],
                                     method: str = 'bh') -> Dict[str, Dict]:
        """Adjust p-values: 'bonferroni', 'bh' (Benjamini-Hochberg), or 'holm'."""
        names = list(p_values.keys())
        raw_ps = np.array([p_values[name] for name in names])
        K = len(raw_ps)
        sorted_idx = np.argsort(raw_ps)

        if method == 'bonferroni':
            adjusted = np.minimum(raw_ps * K, 1.0)
        elif method == 'bh':
            adjusted = np.zeros(K)
            for rank, idx in enumerate(sorted_idx):
                adjusted[idx] = raw_ps[idx] * K / (rank + 1)
            for i in range(K - 2, -1, -1):
                adjusted[sorted_idx[i]] = min(adjusted[sorted_idx[i]], adjusted[sorted_idx[i + 1]])
            adjusted = np.minimum(adjusted, 1.0)
        elif method == 'holm':
            adjusted = np.zeros(K)
            for rank, idx in enumerate(sorted_idx):
                adjusted[idx] = raw_ps[idx] * (K - rank)
            for i in range(1, K):
                adjusted[sorted_idx[i]] = max(adjusted[sorted_idx[i]], adjusted[sorted_idx[i - 1]])
            adjusted = np.minimum(adjusted, 1.0)
        else:
            raise ValueError(f"Unknown method: {method}")

        return {name: {'raw_p': raw_ps[i], 'adjusted_p': adjusted[i],
                        'significant_5pct': adjusted[i] < 0.05,
                        'significant_1pct': adjusted[i] < 0.01}
                for i, name in enumerate(names)}

    @staticmethod
    def comprehensive_signal_test(signal_data: pd.DataFrame, signal_name: str,
                                   horizons_ms: List[int],
                                   n_bootstrap: int = 2000) -> pd.DataFrame:
        """Full battery: Fisher z + block bootstrap + BH correction across horizons."""
        df = signal_data.copy()
        all_results, raw_p_values = [], {}

        for h_ms in horizons_ms:
            fwd_ret = compute_forward_returns_at_horizon(df, h_ms / 1000.0)
            sig_vals = df[signal_name].values
            valid = np.isfinite(sig_vals) & np.isfinite(fwd_ret) & (sig_vals != 0)
            if valid.sum() < 30:
                continue

            sig_v, ret_v = sig_vals[valid], fwd_ret[valid]
            fisher = SignalSignificanceTester.fisher_z_test(sig_v, ret_v)
            bootstrap = SignalSignificanceTester.block_bootstrap_test(sig_v, ret_v, n_bootstrap=n_bootstrap)

            test_name = f'{signal_name}_{h_ms}ms'
            raw_p_values[test_name] = fisher.get('p_value', 1.0)
            all_results.append({
                'horizon_ms': h_ms, 'n_obs': valid.sum(),
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
        if raw_p_values:
            bh = SignalSignificanceTester.multiple_testing_correction(raw_p_values, 'bh')
            results_df['bh_adjusted_p'] = [
                bh.get(f'{signal_name}_{int(r["horizon_ms"])}ms', {}).get('adjusted_p', np.nan)
                for _, r in results_df.iterrows()]
            results_df['bh_significant_5pct'] = results_df['bh_adjusted_p'] < 0.05
        return results_df

# dataloader

class LOBSTERDataLoader:
    """Load and parse LOBSTER format data (message + orderbook files)."""

    @staticmethod
    def load_message_file(filepath: str, nrows: Optional[int] = None) -> pd.DataFrame:
        cols = ['timestamp', 'event_type', 'order_id', 'size', 'price', 'direction']
        df = pd.read_csv(filepath, header=None, names=cols, nrows=nrows)
        df['timestamp'] = df['timestamp'] / 1e9
        return df

    @staticmethod
    def load_orderbook_file(filepath: str, levels: int = 10,
                           nrows: Optional[int] = None) -> pd.DataFrame:
        columns = []
        for i in range(1, levels + 1):
            columns.extend([f'ask_price_{i}', f'ask_size_{i}', f'bid_price_{i}', f'bid_size_{i}'])
        return pd.read_csv(filepath, header=None, names=columns, nrows=nrows)

    @staticmethod
    def create_synthetic_data(num_messages: int = 10000,
                             initial_price: float = 100.0,
                             seed: int = 42) -> pd.DataFrame:
        """Create synthetic LOBSTER-format data with realistic microstructure:
        autocorrelated order flow, trade impact, informed trading episodes, mean-reverting spread."""
        np.random.seed(seed)
        messages = []
        current_time, current_price = 0.0, initial_price
        live_bids, live_asks = {}, {}
        order_flow_momentum, informed_direction, informed_countdown, trade_pressure = 0.0, 0, 0, 0.0

        for i in range(num_messages):
            current_time += np.random.uniform(0.0001, 0.01)

            # Informed trading episodes (~2% start probability)
            if informed_countdown <= 0 and np.random.random() < 0.02:
                informed_direction = np.random.choice([1, -1])
                informed_countdown = np.random.randint(20, 80)
            if informed_countdown > 0:
                informed_countdown -= 1
            else:
                informed_direction = 0

            # Order flow autocorrelation
            order_flow_momentum = np.clip(
                order_flow_momentum * 0.95 + (0.1 * informed_direction if informed_direction else 0),
                -0.8, 0.8)
            direction = 1 if np.random.random() < (0.5 + 0.5 * order_flow_momentum) else -1

            can_cancel_bid, can_cancel_ask = len(live_bids) > 0, len(live_asks) > 0

            # Event type selection
            if can_cancel_bid or can_cancel_ask:
                probs = [0.35, 0.25, 0.40] if informed_direction else [0.50, 0.30, 0.20]
                event_type = np.random.choice(
                    [EventType.NEW_LIMIT, EventType.CANCELLATION, EventType.EXECUTION_VISIBLE], p=probs)
            else:
                event_type = EventType.NEW_LIMIT

            price, size = current_price, 100  # defaults

            if event_type == EventType.NEW_LIMIT:
                offset = np.random.exponential(0.03) + 0.01
                size = np.random.randint(1, 100) * 100
                if direction == 1:
                    price = round(current_price + offset, 2)
                    live_asks[price] = live_asks.get(price, 0) + size
                else:
                    price = round(current_price - offset, 2)
                    live_bids[price] = live_bids.get(price, 0) + size

            elif event_type == EventType.CANCELLATION:
                # Informed traders cancel on the side they're about to hit
                if informed_direction == 1 and can_cancel_ask:
                    direction = 1
                elif informed_direction == -1 and can_cancel_bid:
                    direction = -1
                elif can_cancel_ask and not can_cancel_bid:
                    direction = 1
                elif can_cancel_bid and not can_cancel_ask:
                    direction = -1

                book = live_asks if direction == 1 and can_cancel_ask else (live_bids if can_cancel_bid else None)
                if book is None:
                    continue
                price = np.random.choice(list(book.keys()))
                size = min(np.random.randint(1, 80) * 100, book[price])
                book[price] -= size
                if book[price] <= 0:
                    del book[price]

            elif event_type == EventType.EXECUTION_VISIBLE:
                if informed_direction == 1 and can_cancel_ask:
                    direction = 1
                elif informed_direction == -1 and can_cancel_bid:
                    direction = -1
                elif not can_cancel_ask and not can_cancel_bid:
                    continue
                elif can_cancel_ask and not can_cancel_bid:
                    direction = 1
                elif can_cancel_bid and not can_cancel_ask:
                    direction = -1

                if direction == 1 and can_cancel_ask:
                    price = min(live_asks.keys())
                    size = min(np.random.randint(1, 50) * 100, live_asks[price])
                    live_asks[price] -= size
                    if live_asks[price] <= 0: del live_asks[price]
                    trade_pressure += size * 0.000001
                elif can_cancel_bid:
                    price = max(live_bids.keys())
                    size = min(np.random.randint(1, 50) * 100, live_bids[price])
                    live_bids[price] -= size
                    if live_bids[price] <= 0: del live_bids[price]
                    trade_pressure -= size * 0.000001
                else:
                    continue

            messages.append({
                'timestamp': current_time, 'event_type': event_type, 'order_id': i,
                'size': size, 'price': price, 'direction': direction
            })

            # Price evolution: lagged impact + mean reversion + noise
            current_price += trade_pressure * 0.3 - 0.005 * (current_price - initial_price) + np.random.normal(0, 0.002)
            trade_pressure *= 0.97
            current_price = round(current_price, 2)

            # Prune stale levels periodically
            if i % 200 == 0:
                for p in [p for p in live_bids if p < current_price - 0.50]: del live_bids[p]
                for p in [p for p in live_asks if p > current_price + 0.50]: del live_asks[p]

        return pd.DataFrame(messages)

# backtesting framework 

class SignalBacktester:
    """Backtest signal-based strategies with auto-inversion detection."""

    def __init__(self, transaction_cost_bps: float = 1.0):
        self.transaction_cost = transaction_cost_bps / 10000
        self.trades = []
        self.positions = []

    def _estimate_signal_direction(self, df: pd.DataFrame, signal_col: str) -> int:
        """Use first 30% as calibration. Returns +1 (direct) or -1 (invert)."""
        cal_df = df.iloc[:int(len(df) * 0.3)].copy()
        if len(cal_df) < 50:
            return 1
        prices = cal_df['price'].values
        lookahead = min(20, len(prices) // 5)
        fwd_returns = np.zeros(len(prices))
        for i in range(len(prices) - lookahead):
            fwd_returns[i] = (prices[i + lookahead] - prices[i]) / prices[i]
        sig = cal_df[signal_col].values[:len(prices) - lookahead]
        fwd = fwd_returns[:len(prices) - lookahead]
        valid = np.isfinite(sig) & np.isfinite(fwd) & (sig != 0)
        if valid.sum() < 20:
            return 1
        return -1 if np.corrcoef(sig[valid], fwd[valid])[0, 1] < -0.02 else 1

    def run_strategy(self, signals_df: pd.DataFrame, signal_name: str = 'ofi',
                     entry_threshold: float = 1.0, exit_threshold: float = 0.0,
                     holding_period_ms: int = 1000, auto_invert: bool = True) -> pd.DataFrame:
        """Threshold-based strategy with optional auto-inversion.
        Enter long/short when |signal_z| > entry_threshold, exit at exit_threshold or max hold."""
        df = signals_df.copy()
        if df[signal_name].isna().all() or (df[signal_name] == 0).all():
            return pd.DataFrame()

        signal_std = df[signal_name].std()
        if signal_std < 1e-10:
            return pd.DataFrame()
        df['signal_z'] = (df[signal_name] - df[signal_name].mean()) / signal_std

        signal_flip = 1
        if auto_invert:
            signal_flip = self._estimate_signal_direction(df, signal_name)
            df['signal_z'] *= signal_flip

        trade_start_idx = int(len(df) * 0.3) if auto_invert else 0
        position, entry_price, entry_time, entry_idx = 0, 0, 0, 0
        trades = []

        for idx, row in df.iloc[trade_start_idx:].iterrows():
            price, ts, sz = row['price'], row['timestamp'], row['signal_z']
            if np.isnan(sz) or np.isnan(price):
                continue

            if position != 0:
                hold_ms = (ts - entry_time) * 1000
                should_exit = ((position > 0 and sz < exit_threshold) or
                              (position < 0 and sz > -exit_threshold) or
                              hold_ms > holding_period_ms)
                if should_exit:
                    pnl = position * (price - entry_price)
                    pnl -= abs(position) * (entry_price + price) * self.transaction_cost
                    trades.append({
                        'entry_time': entry_time, 'exit_time': ts,
                        'entry_price': entry_price, 'exit_price': price,
                        'position': position, 'pnl': pnl,
                        'return': pnl / (abs(position) * entry_price),
                        'holding_time_ms': hold_ms,
                        'entry_signal': df.loc[entry_idx, 'signal_z'] if entry_idx in df.index else 0,
                        'signal_flipped': signal_flip == -1
                    })
                    position = 0

            if position == 0:
                if sz > entry_threshold:
                    position, entry_price, entry_time, entry_idx = 1, price, ts, idx
                elif sz < -entry_threshold:
                    position, entry_price, entry_time, entry_idx = -1, price, ts, idx

        return pd.DataFrame(trades)

    def compute_performance_metrics(self, trades_df: pd.DataFrame) -> Dict:
        if len(trades_df) == 0:
            return {'error': 'No trades executed'}
        pnls = trades_df['pnl'].values
        returns = trades_df['return'].values
        cumulative = np.cumsum(pnls)
        drawdown = np.maximum.accumulate(cumulative) - cumulative
        avg_win = pnls[pnls > 0].mean() if (pnls > 0).any() else 0
        avg_loss = pnls[pnls < 0].mean() if (pnls < 0).any() else 0
        return {
            'total_pnl': pnls.sum(), 'num_trades': len(trades_df),
            'win_rate': (pnls > 0).mean(), 'avg_win': avg_win, 'avg_loss': avg_loss,
            'profit_factor': abs(avg_win / avg_loss) if avg_loss != 0 else np.inf,
            'sharpe_ratio': returns.mean() / returns.std() if returns.std() > 0 else 0,
            'max_drawdown': drawdown.max(),
            'avg_holding_time_ms': trades_df['holding_time_ms'].mean()
        }

# almgren-chriss

class OptimalExecutionScheduler:
    """Almgren-Chriss (2001) optimal execution.
    Liquidate X shares over N periods with linear impact: g(v)=gamma*v, h(v)=eta*v.
    Minimize E[cost] + lambda*Var[cost].
    Solution: x_k = X * sinh(kappa*(T - k*tau)) / sinh(kappa*T), kappa = sqrt(lambda*sigma^2/eta)."""

    def __init__(self, total_shares: int, n_periods: int, total_time: float,
                 sigma: float, gamma: float, eta: float):
        self.X, self.N, self.T = total_shares, n_periods, total_time
        self.tau = total_time / n_periods
        self.sigma, self.gamma, self.eta = sigma, gamma, eta

    def optimal_trajectory(self, risk_aversion: float) -> Dict:
        X, N, T, tau = self.X, self.N, self.T, self.tau

        if risk_aversion <= 0:
            trade_list = np.full(N, X / N)
            trajectory = np.array([X - k * (X / N) for k in range(N + 1)])
        else:
            kappa = np.sqrt(risk_aversion * self.sigma**2 / self.eta)
            if kappa * T > 500:
                trade_list = np.zeros(N); trade_list[0] = X
                trajectory = np.zeros(N + 1); trajectory[0] = X
            else:
                trajectory = np.array([
                    X * np.sinh(kappa * (T - k * tau)) / np.sinh(kappa * T)
                    for k in range(N + 1)])
                trajectory[0], trajectory[-1] = X, 0
                trade_list = np.diff(-trajectory)

        expected_cost = 0.5 * self.gamma * X**2 + self.eta * np.sum(trade_list**2) / tau
        variance = self.sigma**2 * tau * np.sum(trajectory[1:]**2)

        return {
            'trajectory': trajectory, 'trade_list': trade_list,
            'time_grid': np.array([k * tau for k in range(N + 1)]),
            'trade_times': np.array([(k + 0.5) * tau for k in range(N)]),
            'expected_cost': expected_cost, 'variance': variance,
            'std_cost': np.sqrt(variance), 'risk_aversion': risk_aversion,
            'kappa': np.sqrt(risk_aversion * self.sigma**2 / self.eta) if risk_aversion > 0 else 0,
            'is_twap': risk_aversion <= 0
        }

    def efficient_frontier(self, n_points: int = 50) -> pd.DataFrame:
        lambdas = np.concatenate([[0], np.logspace(-6, 2, n_points - 1)])
        results = []
        for lam in lambdas:
            opt = self.optimal_trajectory(lam)
            results.append({
                'risk_aversion': lam, 'expected_cost': opt['expected_cost'],
                'std_cost': opt['std_cost'], 'variance': opt['variance'],
                'kappa': opt['kappa'], 'front_loaded_pct': opt['trade_list'][0] / self.X * 100
            })
        return pd.DataFrame(results)

    def compare_strategies(self, risk_aversion: float) -> Dict:
        """Compare optimal vs TWAP, immediate, and VWAP-proxy."""
        X, N, tau = self.X, self.N, self.tau
        opt = self.optimal_trajectory(risk_aversion)
        twap = self.optimal_trajectory(0)

        # Immediate
        imm_cost = 0.5 * self.gamma * X**2 + self.eta * X**2 / tau

        # VWAP-proxy (U-shape)
        weights = np.array([1.5 - abs(2 * k / (N - 1) - 1) for k in range(N)])
        weights /= weights.sum()
        vwap_trades = X * weights
        vwap_traj = np.concatenate([[X], X - np.cumsum(vwap_trades)])
        vwap_cost = 0.5 * self.gamma * X**2 + self.eta * np.sum(vwap_trades**2) / tau
        vwap_var = self.sigma**2 * tau * np.sum(vwap_traj[1:]**2)

        obj = lambda e, v: e + risk_aversion * v
        return {
            'optimal': {'expected_cost': opt['expected_cost'], 'std_cost': opt['std_cost'],
                        'objective': obj(opt['expected_cost'], opt['variance']),
                        'trajectory': opt['trajectory']},
            'twap': {'expected_cost': twap['expected_cost'], 'std_cost': twap['std_cost'],
                     'objective': obj(twap['expected_cost'], twap['variance']),
                     'cost_increase_pct': (twap['expected_cost'] - opt['expected_cost']) /
                                          opt['expected_cost'] * 100 if opt['expected_cost'] > 0 else 0},
            'immediate': {'expected_cost': imm_cost, 'std_cost': 0.0, 'objective': obj(imm_cost, 0)},
            'vwap_proxy': {'expected_cost': vwap_cost, 'std_cost': np.sqrt(vwap_var),
                           'objective': obj(vwap_cost, vwap_var)},
            'risk_aversion': risk_aversion
        }

# visualization 

class OrderBookVisualizer:

    @staticmethod
    def plot_orderbook_snapshot(snapshot: BookSnapshot, ax=None):
        if ax is None:
            fig, ax = plt.subplots(figsize=(10, 6))
        bid_p = [l.price for l in snapshot.bids]; bid_s = [l.size for l in snapshot.bids]
        ask_p = [l.price for l in snapshot.asks]; ask_s = [l.size for l in snapshot.asks]
        ax.barh(bid_p, bid_s, color='green', alpha=0.6, label='Bids')
        ax.barh(ask_p, ask_s, color='red', alpha=0.6, label='Asks')
        if snapshot.mid_price:
            ax.axhline(snapshot.mid_price, color='black', linestyle='--',
                      label=f'Mid: {snapshot.mid_price:.2f}')
        ax.set_xlabel('Size'); ax.set_ylabel('Price')
        ax.set_title(f'Order Book Snapshot @ {snapshot.timestamp:.3f}s')
        ax.legend(); ax.grid(True, alpha=0.3)
        return ax

    @staticmethod
    def plot_signal_analysis(analyzer: PredictiveAnalyzer, signal_name: str = 'ofi'):
        df = pd.DataFrame(analyzer.signal_data)
        fig = plt.figure(figsize=(16, 12))
        gs = gridspec.GridSpec(3, 2, figure=fig)

        ax1 = fig.add_subplot(gs[0, :])
        ax1.plot(df['timestamp'], df[signal_name], label=signal_name, alpha=0.7)
        ax1.set_xlabel('Time (s)'); ax1.set_ylabel('Signal Value')
        ax1.set_title(f'{signal_name.upper()} Signal Over Time')
        ax1.grid(True, alpha=0.3); ax1.legend()

        try:
            pred = analyzer.analyze_predictive_power(signal_name)
            ax2 = fig.add_subplot(gs[1, 0])
            ax2.plot(pred['horizon_ms'], pred['correlation'], marker='o', linewidth=2)
            ax2.set_xlabel('Horizon (ms)'); ax2.set_ylabel('Correlation')
            ax2.set_title('Predictive Power by Horizon'); ax2.grid(True, alpha=0.3)

            ax3 = fig.add_subplot(gs[1, 1])
            ax3.plot(pred['horizon_ms'], pred['hit_rate'], marker='o', linewidth=2, color='green')
            ax3.axhline(0.5, color='red', linestyle='--', label='Random')
            ax3.set_xlabel('Horizon (ms)'); ax3.set_ylabel('Hit Rate')
            ax3.set_title('Directional Accuracy'); ax3.legend(); ax3.grid(True, alpha=0.3)
        except Exception as e:
            print(f"Could not compute predictive power: {e}")

        ax4 = fig.add_subplot(gs[2, 0])
        ax4.hist(df[signal_name].dropna(), bins=50, alpha=0.7, edgecolor='black')
        ax4.set_xlabel('Signal Value'); ax4.set_ylabel('Frequency')
        ax4.set_title(f'{signal_name.upper()} Distribution'); ax4.grid(True, alpha=0.3)

        ax5 = fig.add_subplot(gs[2, 1])
        if 'price' in df.columns:
            sc = ax5.scatter(df[signal_name], df['price'], c=df['timestamp'],
                            cmap='viridis', alpha=0.5, s=10)
            ax5.set_xlabel(f'{signal_name.upper()}'); ax5.set_ylabel('Price')
            ax5.set_title('Signal vs Price (colored by time)')
            plt.colorbar(sc, ax=ax5, label='Time (s)'); ax5.grid(True, alpha=0.3)

        plt.tight_layout()
        return fig

    @staticmethod
    def plot_backtest_results(trades_df: pd.DataFrame, metrics: Dict):
        fig, axes = plt.subplots(2, 2, figsize=(14, 10))

        ax = axes[0, 0]
        ax.plot(trades_df['pnl'].cumsum().values, linewidth=2)
        ax.set_xlabel('Trade Number'); ax.set_ylabel('Cumulative PnL')
        ax.set_title(f'Cumulative PnL (Total: ${metrics["total_pnl"]:.2f})'); ax.grid(True, alpha=0.3)

        ax = axes[0, 1]
        ax.hist(trades_df['pnl'], bins=30, alpha=0.7, edgecolor='black')
        ax.axvline(0, color='red', linestyle='--', linewidth=2)
        ax.set_xlabel('PnL per Trade'); ax.set_ylabel('Frequency')
        ax.set_title(f'PnL Distribution (Win Rate: {metrics["win_rate"]:.1%})'); ax.grid(True, alpha=0.3)

        ax = axes[1, 0]
        sc = ax.scatter(trades_df['holding_time_ms'], trades_df['return']*10000,
                       c=trades_df['pnl'], cmap='RdYlGn', alpha=0.6, s=50)
        ax.set_xlabel('Holding Time (ms)'); ax.set_ylabel('Return (bps)')
        ax.set_title('Return vs Holding Time'); ax.axhline(0, color='black', linestyle='--', alpha=0.5)
        plt.colorbar(sc, ax=ax, label='PnL'); ax.grid(True, alpha=0.3)

        ax = axes[1, 1]; ax.axis('off')
        ax.text(0.1, 0.5, f"""
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
        """, fontfamily='monospace', fontsize=10, verticalalignment='center')

        plt.tight_layout()
        return fig

# regime detection

class RegimeDetector:

    @staticmethod
    def compute_volatility_regime(prices: np.ndarray, window: int = 100) -> np.ndarray:
        returns = np.diff(prices) / prices[:-1]
        vol = np.zeros(len(prices))
        for i in range(window, len(returns)):
            vol[i] = np.std(returns[i-window:i])
        q = np.percentile(vol[vol > 0], [33, 66])
        regime = np.zeros(len(vol))
        regime[(vol > q[0]) & (vol <= q[1])] = 1
        regime[vol > q[1]] = 2
        return regime

    @staticmethod
    def analyze_regime_performance(signals_df: pd.DataFrame,
                                   trades_df: pd.DataFrame) -> pd.DataFrame:
        prices = signals_df['price'].values
        regimes = RegimeDetector.compute_volatility_regime(prices)
        signals_df = signals_df.copy()
        signals_df['regime'] = regimes

        regime_map = dict(zip(signals_df['timestamp'], signals_df['regime']))
        trades_wr = trades_df.copy()
        trades_wr['regime'] = trades_wr['entry_time'].map(
            lambda t: min(regime_map.items(), key=lambda x: abs(x[0]-t))[1])

        results = []
        for r in [0, 1, 2]:
            rt = trades_wr[trades_wr['regime'] == r]
            if len(rt) > 0:
                pnls, rets = rt['pnl'].values, rt['return'].values
                results.append({
                    'regime': ['Low Vol', 'Medium Vol', 'High Vol'][r],
                    'num_trades': len(rt), 'win_rate': (pnls > 0).mean(),
                    'avg_pnl': pnls.mean(), 'total_pnl': pnls.sum(),
                    'sharpe': rets.mean() / rets.std() if rets.std() > 0 else 0
                })
        return pd.DataFrame(results)

# main execution 

def _print_section(title):
    print(f"\n{'='*60}\n{title}\n{'='*60}")

def _print_table_row(fmt, *args):
    print(f"  {fmt}" % args if '%' in fmt else f"  {fmt.format(*args)}")

def performance_benchmark():
    _print_section("PERFORMANCE BENCHMARK")
    for n in [1000, 5000, 10000, 50000]:
        df = LOBSTERDataLoader.create_synthetic_data(num_messages=n, seed=42)
        book = OrderBook()
        start = time.time()
        for _, row in df.iterrows():
            book.process_lobster_message(
                timestamp=row['timestamp'], event_type=row['event_type'],
                order_id=row['order_id'], size=row['size'],
                price=row['price'], direction=row['direction'])
        elapsed = time.time() - start
        print(f"\nMessages: {n:,}  Time: {elapsed:.3f}s  Throughput: {n/elapsed:,.0f} msg/s")

def run_comprehensive_analysis():
    """Complete end-to-end analysis demonstrating all components."""
    _print_section("LIMIT ORDER BOOK SIGNAL PROCESSOR")

    # Step 1: Generate Data
    print("\n[1/6] Loading data...")
    df_messages = LOBSTERDataLoader.create_synthetic_data(num_messages=50000, initial_price=100.0, seed=42)
    print(f"  Loaded {len(df_messages)} messages, time: {df_messages['timestamp'].min():.2f}s to {df_messages['timestamp'].max():.2f}s")

    # Step 2: Process Order Book
    print("\n[2/6] Processing order book...")
    order_book = OrderBook(tick_size=0.01, num_levels=10)
    signal_gen = SignalGenerator()
    analyzer = PredictiveAnalyzer(horizons_ms=[100, 500, 1000, 5000])
    all_signals, snapshots = [], []
    start_time = time.time()

    for idx, row in df_messages.iterrows():
        order_book.process_lobster_message(
            timestamp=row['timestamp'], event_type=row['event_type'],
            order_id=row['order_id'], size=row['size'],
            price=row['price'], direction=row['direction'])
        if idx % 10 == 0:
            snapshot = order_book.get_snapshot(num_levels=5)
            if snapshot.mid_price is not None:
                signals = signal_gen.compute_all_signals(snapshot, order_book)
                all_signals.append(signals)
                snapshots.append(snapshot)
                analyzer.record_signal(signals, snapshot.mid_price)

    elapsed = time.time() - start_time
    metrics = order_book.get_metrics()
    print(f"  {len(df_messages)} msgs in {elapsed:.2f}s ({len(df_messages)/elapsed:,.0f} msg/s), {len(all_signals)} snapshots")
    print(f"  Book: {metrics['bid_levels']} bids, {metrics['ask_levels']} asks, {metrics['trades']} trades")
    fs = order_book.get_snapshot()
    if fs.best_bid and fs.best_ask:
        print(f"  BBO: {fs.best_bid:.2f}/{fs.best_ask:.2f}, spread: {fs.spread:.4f}, {'CROSSED!' if order_book.is_crossed else 'healthy'}")

    # Step 3: Predictive Analysis
    print("\n[3/6] Analyzing predictive power...")
    signals_df = pd.DataFrame(all_signals)
    signals_df['price'] = signals_df['mid_price']

    for sn in ['ofi', 'delta_ofi', 'trade_imbalance', 'spread_pressure', 'composite']:
        if sn not in signals_df.columns or signals_df[sn].isna().all() or (signals_df[sn] == 0).all():
            continue
        print(f"\n  Signal: {sn.upper()}")
        try:
            pp = analyzer.analyze_predictive_power(sn)
            print(f"  {'Horizon':<12} {'Correlation':<15} {'Hit Rate':<15} {'Sharpe':<15}")
            print("  " + "-"*57)
            for _, r in pp.iterrows():
                print(f"  {r['horizon_ms']:<12} {r['correlation']:<15.4f} {r['hit_rate']:<15.2%} {r['sharpe']:<15.3f}")
        except Exception as e:
            print(f"  Error: {e}")

    # Step 3b: Statistical Significance
    _print_section("STATISTICAL SIGNIFICANCE TESTING")
    print("  Testing H0: signal has zero predictive power")

    for sn in ['ofi', 'composite']:
        if sn not in signals_df.columns or signals_df[sn].isna().all() or (signals_df[sn] == 0).all():
            continue
        print(f"\n  Signal: {sn.upper()}")
        try:
            sr = SignalSignificanceTester.comprehensive_signal_test(
                signals_df, sn, [100, 500, 1000, 5000], n_bootstrap=2000)
            if len(sr) > 0:
                print(f"  {'Hz':<8} {'Corr':<8} {'n_eff':<8} {'Fisher p':<10} {'Boot p':<10} {'BH p':<10} {'95% CI':<22} {'Sig?'}")
                print("  " + "-"*86)
                for _, r in sr.iterrows():
                    sig = "***" if r.get('bh_significant_5pct', False) else "   "
                    print(f"  {int(r['horizon_ms']):<8} {r['correlation']:<8.4f} {r['n_effective']:<8.0f} "
                          f"{r['fisher_p_value']:<10.4f} {r['bootstrap_p_value']:<10.4f} "
                          f"{r.get('bh_adjusted_p', np.nan):<10.4f} [{r['ci_95_lower']:.4f}, {r['ci_95_upper']:.4f}] {sig}")
        except Exception as e:
            print(f"  Error: {e}")

    # Step 4: Signal Decay
    print("\n[4/6] Analyzing signal decay...")
    try:
        decay = analyzer.signal_decay_analysis('ofi', max_horizon_ms=5000, step_ms=200)
        init_corr = decay['correlation'].iloc[0]
        hl_idx = (decay['correlation'] - init_corr * 0.5).abs().idxmin()
        print(f"  OFI Half-life: {decay.loc[hl_idx, 'horizon_ms']:.0f} ms")
    except Exception as e:
        print(f"  Error: {e}")

    # Step 4b: Kalman Convergence
    _print_section("KALMAN FILTER CONVERGENCE ANALYSIS")
    try:
        Q_val, R_val = signal_gen.ofi_filter.Q, signal_gen.ofi_filter.R
        kca = KalmanConvergenceAnalyzer(Q=Q_val, R=R_val)
        conv = kca.verify_convergence_numerically()
        print(f"  Q={Q_val}, R={R_val}, SNR={conv['snr_db']:.1f} dB")
        print(f"  P_inf: analytical={conv['P_inf_analytical']:.8f}, numerical={conv['P_inf_numerical']:.8f}, agree={'YES' if conv['agreement'] else 'NO'}")
        print(f"  K_inf={conv['K_inf']:.6f}, rho_theory={conv['rho_theoretical']:.6f}, rho_emp={conv['rho_empirical']:.6f}")
        print(f"  Converged in {conv['converged_at_step']} steps")

        ofi_vals = signals_df['ofi'].dropna().values
        if len(ofi_vals) > 100:
            it = kca.innovation_consistency_test(ofi_vals)
            if 'error' not in it:
                print(f"  Innovation tests: zero-mean p={it['zero_mean_p_value']:.4f} {'[PASS]' if it['zero_mean_pass'] else '[FAIL]'}, "
                      f"LB p={it['ljung_box_p_value']:.4f} {'[PASS]' if it['whiteness_pass'] else '[FAIL]'}, "
                      f"NIS={it['mean_nis']:.3f} {'[PASS]' if it['nis_consistent'] else '[FAIL]'}")
                if not it['whiteness_pass']:
                    print("  => Innovations autocorrelated: random-walk model misspecified. Consider AR(p) or higher Q.")
    except Exception as e:
        print(f"  Error: {e}")

    # Step 5: Backtesting
    print("\n[5/6] Running backtest...")
    backtester = SignalBacktester(transaction_cost_bps=1.0)
    best_metrics, best_trades_df, best_signal, best_threshold, best_holding = None, None, None, None, None

    for sn in ['ofi', 'delta_ofi', 'trade_imbalance', 'composite']:
        if sn not in signals_df.columns or signals_df[sn].isna().all() or (signals_df[sn] == 0).all():
            continue
        for hold_ms in [1000, 2000, 5000]:
            print(f"\n  {sn.upper()}, Hold={hold_ms}ms:")
            print(f"  {'Thresh':<8} {'Trades':<8} {'Win%':<8} {'PnL':<12} {'Sharpe':<8}")
            for thresh in [0.5, 1.0, 1.5, 2.0]:
                tdf = backtester.run_strategy(signals_df, sn, thresh, 0.0, hold_ms, True)
                if len(tdf) > 0:
                    m = backtester.compute_performance_metrics(tdf)
                    inv = " [INV]" if tdf.get('signal_flipped', pd.Series([False])).iloc[0] else ""
                    print(f"  {thresh:<8.1f} {m['num_trades']:<8} {m['win_rate']:<8.1%} ${m['total_pnl']:<11.2f} {m['sharpe_ratio']:<8.3f}{inv}")
                    if best_metrics is None or m['sharpe_ratio'] > best_metrics['sharpe_ratio']:
                        best_metrics, best_trades_df = m, tdf
                        best_signal, best_threshold, best_holding = sn, thresh, hold_ms

    if best_metrics:
        inv = best_trades_df.get('signal_flipped', pd.Series([False])).iloc[0]
        print(f"\n  Best: {best_signal}{' (inv)' if inv else ''}, thresh={best_threshold}, hold={best_holding}ms")
        print(f"  PnL=${best_metrics['total_pnl']:.2f}, Win={best_metrics['win_rate']:.1%}, Sharpe={best_metrics['sharpe_ratio']:.3f}")

    # Step 5b: Optimal Execution
    _print_section("OPTIMAL EXECUTION ANALYSIS (ALMGREN-CHRISS)")
    try:
        avg_spread = signals_df['spread'].mean() if 'spread' in signals_df.columns else 0.02
        snapshot_dt = np.diff(signals_df['timestamp'].values).mean()
        vol_est = signals_df['price'].diff().std() / np.sqrt(max(snapshot_dt, 1e-6))
        eta_est = avg_spread / (2 * 1000)
        gamma_est = eta_est * 0.1

        scheduler = OptimalExecutionScheduler(
            total_shares=10000, n_periods=20, total_time=1.0,
            sigma=max(vol_est, 0.01), gamma=max(gamma_est, 1e-6), eta=max(eta_est, 1e-5))

        print(f"  X={scheduler.X:,}, T={scheduler.T}s, sigma={scheduler.sigma:.6f}, gamma={scheduler.gamma:.2e}, eta={scheduler.eta:.2e}")
        print(f"  {'Lambda':<16} {'E[Cost]':<14} {'Std[Cost]':<14} {'Front%':<10} {'Obj':<14}")
        for lam in [0, 0.001, 0.01, 0.1, 1.0, 10.0]:
            o = scheduler.optimal_trajectory(lam)
            label = "TWAP" if lam == 0 else f"lam={lam}"
            print(f"  {label:<16} ${o['expected_cost']:<13.4f} ${o['std_cost']:<13.4f} "
                  f"{o['trade_list'][0]/scheduler.X*100:<9.1f}% ${o['expected_cost']+lam*o['variance']:<13.4f}")

        comp = scheduler.compare_strategies(0.1)
        print(f"\n  At lam=0.1: Optimal=${comp['optimal']['expected_cost']:.4f}, "
              f"TWAP=${comp['twap']['expected_cost']:.4f} (+{comp['twap'].get('cost_increase_pct',0):.1f}%), "
              f"Immediate=${comp['immediate']['expected_cost']:.4f}")
    except Exception as e:
        print(f"  Error: {e}")

    # Step 6: Visualization
    print("\n[6/6] Generating visualizations...")
    viz = OrderBookVisualizer()

    try:
        fig1 = viz.plot_signal_analysis(analyzer, signal_name='ofi')
        plt.savefig('signal_analysis.png', dpi=150, bbox_inches='tight'); print("  Saved: signal_analysis.png")
    except Exception as e:
        print(f"  Signal plot error: {e}")

    if best_trades_df is not None and len(best_trades_df) > 0:
        try:
            fig2 = viz.plot_backtest_results(best_trades_df, best_metrics)
            plt.savefig('backtest_results.png', dpi=150, bbox_inches='tight'); print("  Saved: backtest_results.png")
        except Exception as e:
            print(f"  Backtest plot error: {e}")

    if snapshots:
        try:
            fig3, ax = plt.subplots(figsize=(10, 6))
            viz.plot_orderbook_snapshot(snapshots[len(snapshots)//2], ax=ax)
            plt.savefig('orderbook_snapshot.png', dpi=150, bbox_inches='tight'); print("  Saved: orderbook_snapshot.png")
        except Exception as e:
            print(f"  Orderbook plot error: {e}")

    # Optimal execution plots
    try:
        fig4, axes4 = plt.subplots(1, 3, figsize=(18, 5))
        frontier = scheduler.efficient_frontier(n_points=40)
        axes4[0].plot(frontier['std_cost'], frontier['expected_cost'], 'b-o', markersize=3, linewidth=1.5)
        axes4[0].set_xlabel('Std[Cost] (Execution Risk)'); axes4[0].set_ylabel('E[Cost] (Expected Slippage)')
        axes4[0].set_title('Almgren-Chriss Efficient Frontier'); axes4[0].grid(True, alpha=0.3)
        twap_r = frontier.iloc[0]
        axes4[0].annotate('TWAP\n(risk-neutral)', xy=(twap_r['std_cost'], twap_r['expected_cost']),
                          fontsize=8, ha='left', arrowprops=dict(arrowstyle='->', color='red'),
                          textcoords='offset points', xytext=(15, -15))

        colors_exec = plt.cm.viridis(np.linspace(0, 1, 5))
        for i, lam in enumerate([0, 0.01, 0.1, 1.0, 10.0]):
            o = scheduler.optimal_trajectory(lam)
            label = 'TWAP' if lam == 0 else f'\u03bb={lam}'
            axes4[1].plot(o['time_grid'], o['trajectory']/scheduler.X, color=colors_exec[i], linewidth=2, label=label)
            axes4[2].bar(o['trade_times']+i*0.008, o['trade_list']/scheduler.X,
                        width=0.008, alpha=0.7, color=colors_exec[i], label=label)
        axes4[1].set_xlabel('Time'); axes4[1].set_ylabel('Remaining Position (fraction)')
        axes4[1].set_title('Optimal Liquidation Trajectories'); axes4[1].legend(fontsize=8); axes4[1].grid(True, alpha=0.3)
        axes4[2].set_xlabel('Time'); axes4[2].set_ylabel('Trade Size (fraction of total)')
        axes4[2].set_title('Execution Rate Schedules'); axes4[2].legend(fontsize=8); axes4[2].grid(True, alpha=0.3)
        plt.tight_layout()
        plt.savefig('optimal_execution.png', dpi=150, bbox_inches='tight'); print("  Saved: optimal_execution.png")
    except Exception as e:
        print(f"  Execution plot error: {e}")

    # Kalman convergence plots
    try:
        Q_val, R_val = signal_gen.ofi_filter.Q, signal_gen.ofi_filter.R
        kca = KalmanConvergenceAnalyzer(Q=Q_val, R=R_val)
        conv = kca.verify_convergence_numerically()
        fig5, axes5 = plt.subplots(1, 3, figsize=(18, 5))

        axes5[0].plot(conv['P_trajectory'][:50], 'b-', linewidth=2, label='P_t (numerical)')
        axes5[0].axhline(conv['P_inf_analytical'], color='red', linestyle='--', linewidth=2,
                        label=f'P_\u221e = {conv["P_inf_analytical"]:.6f}')
        axes5[0].set_xlabel('Iteration'); axes5[0].set_ylabel('Error Covariance P')
        axes5[0].set_title('Riccati Recursion Convergence'); axes5[0].legend(); axes5[0].grid(True, alpha=0.3)

        qr_ratios = np.logspace(-4, 2, 100)
        gains = [KalmanConvergenceAnalyzer(Q=qr*R_val, R=R_val).steady_state_gain() for qr in qr_ratios]
        axes5[1].semilogx(qr_ratios, gains, 'b-', linewidth=2)
        axes5[1].axvline(Q_val/R_val, color='red', linestyle='--', label=f'Current Q/R = {Q_val/R_val:.2f}')
        axes5[1].set_xlabel('Q/R Ratio (Signal-to-Noise)'); axes5[1].set_ylabel('Steady-State Gain K_\u221e')
        axes5[1].set_title('Kalman Gain Sensitivity'); axes5[1].legend(); axes5[1].grid(True, alpha=0.3)

        ofi_vals = signals_df['ofi'].dropna().values
        if len(ofi_vals) > 100:
            it = kca.innovation_consistency_test(ofi_vals)
            if 'autocorrelations' in it:
                lags = np.arange(1, len(it['autocorrelations'])+1)
                axes5[2].bar(lags, it['autocorrelations'], color='steelblue', alpha=0.7)
                ci = 1.96 / np.sqrt(len(ofi_vals))
                axes5[2].axhline(ci, color='red', linestyle='--', alpha=0.7, label='95% CI')
                axes5[2].axhline(-ci, color='red', linestyle='--', alpha=0.7)
                axes5[2].axhline(0, color='black', linewidth=0.5)
                axes5[2].set_xlabel('Lag'); axes5[2].set_ylabel('Autocorrelation')
                axes5[2].set_title('Innovation Autocorrelations'); axes5[2].legend(); axes5[2].grid(True, alpha=0.3)

        plt.tight_layout()
        plt.savefig('kalman_analysis.png', dpi=150, bbox_inches='tight'); print("  Saved: kalman_analysis.png")
    except Exception as e:
        print(f"  Kalman plot error: {e}")

    _print_section("ANALYSIS COMPLETE")
    return {
        'signals_df': signals_df, 'analyzer': analyzer,
        'best_metrics': best_metrics, 'best_trades': best_trades_df,
        'order_book': order_book
    }

# unit tests

def run_unit_tests():
    _print_section("UNIT TESTS")

    # Test 1: Order book ops
    print("\n[Test 1] Order Book Operations")
    book = OrderBook()
    book.process_lobster_message(0.0, EventType.NEW_LIMIT, 1, 100, 99.50, -1)
    s = book.get_snapshot()
    assert s.best_bid == 99.50, "Best bid incorrect"
    print("  Add bid order")

    book.process_lobster_message(0.1, EventType.NEW_LIMIT, 2, 100, 100.50, 1)
    s = book.get_snapshot()
    assert s.best_ask == 100.50 and s.spread == 1.0
    print("  Add ask order")

    book.process_lobster_message(0.2, EventType.CANCELLATION, 1, 50, 99.50, -1)
    assert book.get_snapshot().bids[0].size == 50
    print("  Cancel order")

    # Test 2: Signal generation
    print("\n[Test 2] Signal Generation")
    sig_gen = SignalGenerator()
    book = OrderBook()
    book.process_lobster_message(0.0, EventType.NEW_LIMIT, 1, 100, 99.50, -1)
    book.process_lobster_message(0.0, EventType.NEW_LIMIT, 2, 200, 100.50, 1)
    s = book.get_snapshot()
    ofi = sig_gen.compute_ofi(s); assert -1 <= ofi <= 1
    delta = sig_gen.compute_delta_ofi(s)
    mp = sig_gen.compute_microprice(s); assert mp and 99.5 <= mp <= 100.5
    signals = sig_gen.compute_all_signals(s, book)
    assert all(k in signals for k in ['composite', 'delta_ofi', 'trade_imbalance'])
    print(f"  OFI={ofi:.3f}, Delta={delta:.3f}, MP={mp:.2f}, {len(signals)} signals")

    # Test 3: Kalman filter
    print("\n[Test 3] Kalman Filter")
    kf = KalmanFilter()
    noisy = [1.0, 1.1, 0.9, 1.2, 0.8, 1.0]
    filtered = [kf.update(x) for x in noisy]
    assert np.std(filtered) < np.std(noisy)
    print(f"  Noise: {np.std(noisy):.3f} -> {np.std(filtered):.3f}")

    # Test 4: Kalman convergence
    print("\n[Test 4] Kalman Convergence Analysis")
    kca = KalmanConvergenceAnalyzer(Q=1e-3, R=0.01)
    P_inf = kca.steady_state_covariance()
    P_check = (P_inf + 1e-3) * 0.01 / (P_inf + 1e-3 + 0.01)
    assert abs(P_inf - P_check) < 1e-10
    K_inf = kca.steady_state_gain(); assert 0 < K_inf < 1
    conv = kca.verify_convergence_numerically(); assert conv['agreement']
    print(f"  P_inf={P_inf:.8f}, K_inf={K_inf:.6f}, rho={conv['rho_theoretical']:.6f}, steps={conv['converged_at_step']}")

    # Test 5: Statistical significance
    print("\n[Test 5] Statistical Significance Tests")
    np.random.seed(42)
    x_sig = np.random.randn(500)
    y_ret = 0.3 * x_sig + np.random.randn(500)
    fr = SignalSignificanceTester.fisher_z_test(x_sig, y_ret)
    assert fr['significant_5pct']
    x_null, y_null = np.random.randn(500), np.random.randn(500)
    fn = SignalSignificanceTester.fisher_z_test(x_null, y_null)
    print(f"  Correlated: r={fr['correlation']:.3f}, p={fr['p_value']:.4f} [sig]")
    print(f"  Null: r={fn['correlation']:.3f}, p={fn['p_value']:.4f}")

    p_vals = {'a': 0.01, 'b': 0.04, 'c': 0.06, 'd': 0.20}
    bh = SignalSignificanceTester.multiple_testing_correction(p_vals, 'bh')
    assert bh['a']['significant_5pct']
    print(f"  BH: {sum(1 for v in bh.values() if v['significant_5pct'])}/4 significant")

    # Test 6: Optimal execution
    print("\n[Test 6] Optimal Execution (Almgren-Chriss)")
    sched = OptimalExecutionScheduler(total_shares=10000, n_periods=20, total_time=1.0,
                                      sigma=0.01, gamma=1e-6, eta=1e-5)
    twap = sched.optimal_trajectory(0)
    assert abs(twap['trade_list'].std()) < 1e-10
    assert abs(twap['trajectory'][0] - 10000) < 1e-10 and abs(twap['trajectory'][-1]) < 1e-10
    agg = sched.optimal_trajectory(1.0)
    assert agg['trade_list'][0] > twap['trade_list'][0]
    frontier = sched.efficient_frontier(n_points=20)
    print(f"  TWAP: {twap['trade_list'][0]:.0f}/period, lam=1.0 first={agg['trade_list'][0]:.0f} ({agg['trade_list'][0]/10000*100:.1f}%)")
    print(f"  Frontier: {len(frontier)} points")

    _print_section("ALL TESTS PASSED")

# main

if __name__ == "__main__":
    print("\n")
    run_unit_tests()
    performance_benchmark()
    results = run_comprehensive_analysis()

    if results['best_trades'] is not None and len(results['best_trades']) > 0:
        _print_section("REGIME ANALYSIS")
        regime_perf = RegimeDetector.analyze_regime_performance(
            results['signals_df'], results['best_trades'])
        print("\nPerformance by Volatility Regime:")
        print(regime_perf.to_string(index=False))

    _print_section("EXECUTION COMPLETE")
    print("\nKey Deliverables: Order book engine, signal framework, predictive analysis,")
    print("  Kalman convergence (DARE), Almgren-Chriss execution, backtest, visualizations")
    print("\nFiles: signal_analysis.png, backtest_results.png, orderbook_snapshot.png,")
    print("  optimal_execution.png, kalman_analysis.png")
    print("=" * 60)