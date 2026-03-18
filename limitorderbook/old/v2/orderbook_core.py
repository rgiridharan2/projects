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
        We remove the offending levels from both sides until the book
        is no longer crossed.
        """
        while (self.bid_prices and self.ask_prices and 
               self.bid_prices[0] >= self.ask_prices[0]):
            # Remove the crossed levels from both sides
            crossed_bid = self.bid_prices[0]
            crossed_ask = self.ask_prices[0]
            
            # Remove the bid level
            if crossed_bid in self.bids:
                del self.bids[crossed_bid]
            self.bid_prices.pop(0)
            
            # Remove the ask level
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
        rapidly, use Q/R >= 0.01. Previous default of 1e-5 was far too sticky,
        causing the filter to ignore new observations.
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

class SignalGenerator:
    """
    Generate predictive signals from order book data
    """
    
    def __init__(self):
        self.ofi_filter = KalmanFilter(process_variance=1e-3, 
                                       measurement_variance=0.01)
        self.signals_history = defaultdict(list)
        
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
    
    def compute_all_signals(self, snapshot: BookSnapshot) -> Dict[str, float]:
        """Compute all signals for a snapshot"""
        return {
            'ofi': self.compute_ofi(snapshot),
            'microprice': self.compute_microprice(snapshot),
            'spread_pressure': self.compute_spread_pressure(snapshot),
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
        Create synthetic LOBSTER-format data for testing.
        
        Generates realistic order flow by tracking a live book state so that
        cancellations and executions always reference prices with existing
        liquidity, and new orders are placed around the current mid-price
        to prevent the book from crossing.
        
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
        
        # Track live book state for realistic cancel/execute targeting
        # price -> total_size for each side
        live_bids = {}  # price -> size
        live_asks = {}  # price -> size
        
        for i in range(num_messages):
            # Random time increment (0.1ms to 10ms)
            current_time += np.random.uniform(0.0001, 0.01)
            
            # Decide what we can do given current book state
            can_cancel_bid = len(live_bids) > 0
            can_cancel_ask = len(live_asks) > 0
            can_execute = can_cancel_bid or can_cancel_ask
            
            # Weighted event type selection, adapting to book state
            if can_cancel_bid or can_cancel_ask:
                event_type = np.random.choice(
                    [EventType.NEW_LIMIT, EventType.CANCELLATION, 
                     EventType.EXECUTION_VISIBLE],
                    p=[0.5, 0.3, 0.2]
                )
            else:
                # Book is empty — can only add new orders
                event_type = EventType.NEW_LIMIT
            
            if event_type == EventType.NEW_LIMIT:
                # Place new order around current mid-price
                direction = np.random.choice([1, -1])  # 1=ask, -1=bid
                
                if direction == 1:  # Ask — place above mid
                    offset = np.random.uniform(0.01, 0.10)
                    price = round(current_price + offset, 2)
                else:  # Bid — place below mid
                    offset = np.random.uniform(0.01, 0.10)
                    price = round(current_price - offset, 2)
                
                size = np.random.randint(1, 100) * 100
                
                # Update live book
                if direction == 1:
                    live_asks[price] = live_asks.get(price, 0) + size
                else:
                    live_bids[price] = live_bids.get(price, 0) + size
                    
            elif event_type == EventType.CANCELLATION:
                # Cancel from a price level that actually has liquidity
                if can_cancel_bid and can_cancel_ask:
                    direction = np.random.choice([1, -1])
                elif can_cancel_ask:
                    direction = 1
                else:
                    direction = -1
                
                if direction == 1:
                    price = np.random.choice(list(live_asks.keys()))
                    available = live_asks[price]
                    size = min(np.random.randint(1, 100) * 100, available)
                    live_asks[price] -= size
                    if live_asks[price] <= 0:
                        del live_asks[price]
                else:
                    price = np.random.choice(list(live_bids.keys()))
                    available = live_bids[price]
                    size = min(np.random.randint(1, 100) * 100, available)
                    live_bids[price] -= size
                    if live_bids[price] <= 0:
                        del live_bids[price]
                        
            elif event_type == EventType.EXECUTION_VISIBLE:
                # Execute against existing resting order (removes liquidity)
                # A buy execution hits a resting ask; a sell hits a resting bid
                if can_cancel_ask and can_cancel_bid:
                    direction = np.random.choice([1, -1])
                elif can_cancel_ask:
                    direction = 1
                else:
                    direction = -1
                
                if direction == 1:
                    # Execute against best (lowest) ask
                    price = min(live_asks.keys())
                    available = live_asks[price]
                    size = min(np.random.randint(1, 50) * 100, available)
                    live_asks[price] -= size
                    if live_asks[price] <= 0:
                        del live_asks[price]
                else:
                    # Execute against best (highest) bid
                    price = max(live_bids.keys())
                    available = live_bids[price]
                    size = min(np.random.randint(1, 50) * 100, available)
                    live_bids[price] -= size
                    if live_bids[price] <= 0:
                        del live_bids[price]
                
                # Nudge price toward execution side (market impact)
                if direction == 1:
                    current_price += np.random.uniform(0.0, 0.02)
                else:
                    current_price -= np.random.uniform(0.0, 0.02)
            
            messages.append({
                'timestamp': current_time,
                'event_type': event_type,
                'order_id': i,
                'size': size,
                'price': price,
                'direction': direction
            })
            
            # Slow random walk in mid-price (mean-reverting toward initial)
            if np.random.random() < 0.05:
                drift = -0.01 * (current_price - initial_price)  # Mean reversion
                current_price += drift + np.random.uniform(-0.02, 0.02)
            
            # Periodically prune stale levels far from mid
            if i % 500 == 0:
                stale_bids = [p for p in live_bids if p < current_price - 1.0]
                for p in stale_bids:
                    del live_bids[p]
                stale_asks = [p for p in live_asks if p > current_price + 1.0]
                for p in stale_asks:
                    del live_asks[p]
        
        return pd.DataFrame(messages)

# ==================== BACKTESTING FRAMEWORK ====================

class SignalBacktester:
    """
    Backtest signal-based trading strategies
    """
    
    def __init__(self, transaction_cost_bps: float = 1.0):
        """
        Args:
            transaction_cost_bps: Transaction cost in basis points
        """
        self.transaction_cost = transaction_cost_bps / 10000
        self.trades = []
        self.positions = []
        
    def run_strategy(self, signals_df: pd.DataFrame, 
                     signal_name: str = 'ofi',
                     entry_threshold: float = 1.0,
                     exit_threshold: float = 0.0,
                     holding_period_ms: int = 1000) -> pd.DataFrame:
        """
        Run simple threshold-based strategy
        
        Strategy:
        - Enter long when signal > entry_threshold
        - Exit when signal < exit_threshold or after holding_period
        
        Args:
            signals_df: DataFrame with signals and prices
            signal_name: Signal to trade on
            entry_threshold: Z-score threshold for entry
            exit_threshold: Z-score threshold for exit
            holding_period_ms: Maximum holding period
            
        Returns:
            DataFrame with trade results
        """
        df = signals_df.copy()
        
        # Normalize signal to z-scores
        signal_mean = df[signal_name].mean()
        signal_std = df[signal_name].std()
        df['signal_z'] = (df[signal_name] - signal_mean) / signal_std
        
        position = 0
        entry_price = 0
        entry_time = 0
        entry_idx = 0
        
        trades = []
        
        for idx, row in df.iterrows():
            current_price = row['price']
            current_time = row['timestamp']
            signal_z = row['signal_z']
            
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
                        'entry_signal': df.iloc[entry_idx]['signal_z']
                    })
                    
                    position = 0
            
            # Check entry conditions
            if position == 0:
                if signal_z > entry_threshold:
                    # Enter long
                    position = 1
                    entry_price = current_price
                    entry_time = current_time
                    entry_idx = idx
                    
                elif signal_z < -entry_threshold:
                    # Enter short
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
        sharpe_annualized = sharpe * np.sqrt(252 * 6.5 * 3600)  # Assuming second-level data
        
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
            'sharpe_annualized': sharpe_annualized,
            'max_drawdown': max_drawdown,
            'avg_holding_time_ms': trades_df['holding_time_ms'].mean()
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
            ax2.set_title('Predictive Power Decay')
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
        
        Sharpe Ratio:        {metrics['sharpe_ratio']:.3f}
        Sharpe (Annual):     {metrics['sharpe_annualized']:.3f}
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
                signals = signal_gen.compute_all_signals(snapshot)
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
            print("  ⚠ WARNING: Book is crossed! Check data integrity.")
        else:
            print("  ✓ Book is healthy (not crossed)")
    
    # ========== Step 3: Predictive Analysis ==========
    print("\n[3/6] Analyzing predictive power...")
    
    signals_df = pd.DataFrame(all_signals)
    signals_df['price'] = signals_df['mid_price']
    
    for signal_name in ['ofi', 'spread_pressure']:
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
    
    # ========== Step 5: Backtesting ==========
    print("\n[5/6] Running backtest...")
    
    backtester = SignalBacktester(transaction_cost_bps=1.0)
    
    # Test multiple threshold levels and signals
    thresholds = [0.5, 1.0, 1.5, 2.0]
    signal_candidates = ['ofi', 'spread_pressure']
    holding_periods = [1000, 2000, 5000]
    
    best_metrics = None
    best_threshold = None
    best_trades_df = None
    best_signal = None
    best_holding = None
    
    for signal_name in signal_candidates:
        if signal_name not in signals_df.columns:
            continue
        if signals_df[signal_name].isna().all():
            continue
            
        for holding_ms in holding_periods:
            print(f"\n  Signal: {signal_name.upper()}, Holding: {holding_ms}ms")
            print("  " + "-"*80)
            print(f"  {'Threshold':<12} {'Trades':<10} {'Win Rate':<12} {'Total PnL':<15} {'Sharpe':<12}")
            print("  " + "-"*80)
            
            for threshold in thresholds:
                trades_df = backtester.run_strategy(
                    signals_df,
                    signal_name=signal_name,
                    entry_threshold=threshold,
                    exit_threshold=0.0,
                    holding_period_ms=holding_ms
                )
                
                if len(trades_df) > 0:
                    metrics = backtester.compute_performance_metrics(trades_df)
                    
                    print(f"  {threshold:<12.1f} "
                          f"{metrics['num_trades']:<10} "
                          f"{metrics['win_rate']:<12.1%} "
                          f"${metrics['total_pnl']:<14.2f} "
                          f"{metrics['sharpe_ratio']:<12.3f}")
                    
                    if best_metrics is None or metrics['sharpe_ratio'] > best_metrics['sharpe_ratio']:
                        best_metrics = metrics
                        best_threshold = threshold
                        best_trades_df = trades_df
                        best_signal = signal_name
                        best_holding = holding_ms
            
            print("  " + "-"*80)
    
    if best_metrics:
        print(f"\n  Best Configuration:")
        print(f"    Signal:          {best_signal}")
        print(f"    Threshold:       {best_threshold}")
        print(f"    Holding Period:  {best_holding}ms")
        print(f"    Sharpe Ratio:    {best_metrics['sharpe_ratio']:.3f}")
        print(f"    Annual Sharpe:   {best_metrics['sharpe_annualized']:.3f}")
    
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
    print("  ✓ Add bid order")
    
    # Add ask
    book.process_lobster_message(0.1, EventType.NEW_LIMIT, 2, 100, 100.50, 1)
    snapshot = book.get_snapshot()
    assert snapshot.best_ask == 100.50, "Best ask incorrect"
    assert snapshot.spread == 1.0, "Spread incorrect"
    print("  ✓ Add ask order")
    
    # Cancel order
    book.process_lobster_message(0.2, EventType.CANCELLATION, 1, 50, 99.50, -1)
    snapshot = book.get_snapshot()
    assert snapshot.bids[0].size == 50, "Cancellation incorrect"
    print("  ✓ Cancel order")
    
    # Test 2: Signal generation
    print("\n[Test 2] Signal Generation")
    sig_gen = SignalGenerator()
    
    book = OrderBook()
    book.process_lobster_message(0.0, EventType.NEW_LIMIT, 1, 100, 99.50, -1)
    book.process_lobster_message(0.0, EventType.NEW_LIMIT, 2, 200, 100.50, 1)
    
    snapshot = book.get_snapshot()
    
    ofi = sig_gen.compute_ofi(snapshot)
    assert -1 <= ofi <= 1, "OFI out of range"
    print(f"  ✓ OFI computed: {ofi:.3f}")
    
    mp = sig_gen.compute_microprice(snapshot)
    assert mp is not None, "Microprice failed"
    assert 99.5 <= mp <= 100.5, "Microprice out of range"
    print(f"  ✓ Microprice computed: {mp:.2f}")
    
    # Test 3: Kalman filter
    print("\n[Test 3] Kalman Filter")
    kf = KalmanFilter()
    
    noisy_signal = [1.0, 1.1, 0.9, 1.2, 0.8, 1.0]
    filtered = [kf.update(x) for x in noisy_signal]
    
    # Filtered signal should be smoother
    filtered_std = np.std(filtered)
    raw_std = np.std(noisy_signal)
    assert filtered_std < raw_std, "Kalman filter not smoothing"
    print(f"  ✓ Noise reduction: {raw_std:.3f} -> {filtered_std:.3f}")
    
    print("\n" + "="*60)
    print("ALL TESTS PASSED")
    print("="*60)

# ==================== MAIN ENTRY POINT ====================

if __name__ == "__main__":
    import sys
    
    print("\n")
    print("╔" + "═"*58 + "╗")
    print("║" + " "*58 + "║")
    print("║" + "  LIMIT ORDER BOOK SIGNAL PROCESSOR  ".center(58) + "║")
    print("║" + "  High-Frequency Trading Research Platform  ".center(58) + "║")
    print("║" + " "*58 + "║")
    print("╚" + "═"*58 + "╝")
    
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
    print("  3. Predictive analysis")
    print("  4. Backtest results")
    print("  5. Visualization outputs")
    print("\nFiles created:")
    print("  - signal_analysis.png")
    print("  - backtest_results.png")
    print("  - orderbook_snapshot.png")
    print("\n" + "="*60)