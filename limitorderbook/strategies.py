"""
Trading strategy implementations.
Each strategy generates entry/exit signals based on technical indicators.
"""
import pandas as pd
import numpy as np
from abc import ABC, abstractmethod
from typing import Tuple


class BaseStrategy(ABC):
    """
    Abstract base class for trading strategies.
    
    All strategies must implement:
        - generate_signals(): Returns entry and exit signals
        - name property: Human-readable strategy name
    """
    
    def __init__(self, prices: pd.Series):
        """
        Args:
            prices: Close price series
        """
        self.prices = prices
        self._signals: pd.Series = None
        
    @property
    @abstractmethod
    def name(self) -> str:
        """Strategy name for display"""
        pass
    
    @abstractmethod
    def generate_signals(self) -> Tuple[pd.Series, pd.Series]:
        """
        Generate trading signals.
        
        Returns:
            Tuple of (entries, exits) as boolean Series
        """
        pass
    
    def get_positions(self) -> pd.Series:
        """
        Get position series (1 = long, 0 = flat).
        Useful for calculating strategy returns.
        """
        entries, exits = self.generate_signals()
        
        position = pd.Series(0, index=self.prices.index)
        in_position = False
        
        for i in range(len(position)):
            if entries.iloc[i] and not in_position:
                in_position = True
            elif exits.iloc[i] and in_position:
                in_position = False
            position.iloc[i] = 1 if in_position else 0
            
        return position


class MovingAverageCrossover(BaseStrategy):
    """
    Moving Average Crossover Strategy
    
    Logic:
        - ENTER LONG: When fast MA crosses above slow MA
        - EXIT: When fast MA crosses below slow MA
        
    This is a trend-following strategy that aims to capture
    sustained price movements.
    
    Parameters:
        fast_period: Lookback for fast moving average
        slow_period: Lookback for slow moving average
    """
    
    def __init__(self, prices: pd.Series, fast_period: int = 10, slow_period: int = 50):
        super().__init__(prices)
        self.fast_period = fast_period
        self.slow_period = slow_period
        
        if fast_period >= slow_period:
            raise ValueError("fast_period must be less than slow_period")
            
    @property
    def name(self) -> str:
        return f"MA_Crossover({self.fast_period}/{self.slow_period})"
    
    def generate_signals(self) -> Tuple[pd.Series, pd.Series]:
        # Calculate moving averages
        fast_ma = self.prices.rolling(window=self.fast_period).mean()
        slow_ma = self.prices.rolling(window=self.slow_period).mean()
        
        # Crossover signals
        fast_above = fast_ma > slow_ma
        
        # Entry: fast crosses above slow (was below, now above)
        entries = fast_above & (~fast_above.shift(1).fillna(False))
        
        # Exit: fast crosses below slow
        exits = (~fast_above) & (fast_above.shift(1).fillna(False))
        
        return entries, exits
    
    def get_indicator_data(self) -> pd.DataFrame:
        """Return indicator values for plotting"""
        return pd.DataFrame({
            'price': self.prices,
            'fast_ma': self.prices.rolling(self.fast_period).mean(),
            'slow_ma': self.prices.rolling(self.slow_period).mean()
        })


class BollingerBandsMeanReversion(BaseStrategy):
    """
    Bollinger Bands Mean Reversion Strategy
    
    Logic:
        - ENTER LONG: When price closes below lower band (oversold)
        - EXIT: When price crosses above middle band (mean reversion complete)
        
    This is a mean-reversion strategy that bets on price returning
    to its moving average after extreme moves.
    
    Parameters:
        period: Lookback period for moving average and std dev
        num_std: Number of standard deviations for bands
    """
    
    def __init__(self, prices: pd.Series, period: int = 20, num_std: float = 2.0):
        super().__init__(prices)
        self.period = period
        self.num_std = num_std
        
    @property
    def name(self) -> str:
        return f"BB_MeanRev({self.period}, {self.num_std}σ)"
    
    def generate_signals(self) -> Tuple[pd.Series, pd.Series]:
        # Calculate Bollinger Bands
        middle = self.prices.rolling(window=self.period).mean()
        std = self.prices.rolling(window=self.period).std()
        
        lower = middle - (std * self.num_std)
        upper = middle + (std * self.num_std)
        
        # Entry: price below lower band
        entries = self.prices < lower
        
        # Exit: price crosses above middle band
        price_above_middle = self.prices > middle
        exits = price_above_middle & (~price_above_middle.shift(1).fillna(False))
        
        return entries, exits
    
    def get_indicator_data(self) -> pd.DataFrame:
        """Return indicator values for plotting"""
        middle = self.prices.rolling(self.period).mean()
        std = self.prices.rolling(self.period).std()
        
        return pd.DataFrame({
            'price': self.prices,
            'middle': middle,
            'upper': middle + std * self.num_std,
            'lower': middle - std * self.num_std
        })


class RSIMeanReversion(BaseStrategy):
    """
    RSI Mean Reversion Strategy
    
    Logic:
        - ENTER LONG: When RSI drops below oversold level (30)
        - EXIT: When RSI rises above neutral level (50)
        
    Parameters:
        period: RSI calculation period
        oversold: Oversold threshold (entry)
        exit_level: Exit threshold
    """
    
    def __init__(self, prices: pd.Series, period: int = 14, 
                 oversold: float = 30, exit_level: float = 50):
        super().__init__(prices)
        self.period = period
        self.oversold = oversold
        self.exit_level = exit_level
        
    @property
    def name(self) -> str:
        return f"RSI_MeanRev({self.period}, OS={self.oversold})"
    
    def _calculate_rsi(self) -> pd.Series:
        """Calculate RSI indicator"""
        delta = self.prices.diff()
        
        gains = delta.where(delta > 0, 0)
        losses = (-delta).where(delta < 0, 0)
        
        avg_gain = gains.rolling(window=self.period).mean()
        avg_loss = losses.rolling(window=self.period).mean()
        
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        
        return rsi
    
    def generate_signals(self) -> Tuple[pd.Series, pd.Series]:
        rsi = self._calculate_rsi()
        
        # Entry: RSI drops below oversold
        entries = (rsi < self.oversold) & (rsi.shift(1) >= self.oversold)
        
        # Exit: RSI rises above exit level
        exits = (rsi > self.exit_level) & (rsi.shift(1) <= self.exit_level)
        
        return entries, exits


class MomentumBreakout(BaseStrategy):
    """
    Momentum Breakout Strategy
    
    Logic:
        - ENTER LONG: Price makes new N-day high
        - EXIT: Price makes new M-day low OR trailing stop hit
        
    This tests if "buying strength" works or is just chasing.
    
    Parameters:
        entry_period: Days for breakout detection
        exit_period: Days for breakdown exit
    """
    
    def __init__(self, prices: pd.Series, entry_period: int = 20, exit_period: int = 10):
        super().__init__(prices)
        self.entry_period = entry_period
        self.exit_period = exit_period
        
    @property
    def name(self) -> str:
        return f"Momentum({self.entry_period}/{self.exit_period})"
    
    def generate_signals(self) -> Tuple[pd.Series, pd.Series]:
        # Entry: new high
        rolling_high = self.prices.rolling(self.entry_period).max().shift(1)
        entries = self.prices > rolling_high
        
        # Exit: new low
        rolling_low = self.prices.rolling(self.exit_period).min().shift(1)
        exits = self.prices < rolling_low
        
        return entries, exits