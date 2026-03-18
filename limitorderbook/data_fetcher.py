"""
Data acquisition module using yfinance.
Handles downloading, caching, and preprocessing of market data.
"""
import pandas as pd
import numpy as np
import yfinance as yf
from typing import Optional, Tuple
import warnings
warnings.filterwarnings('ignore')


class DataFetcher:
    """
    Fetches and preprocesses market data from Yahoo Finance.
    
    Attributes:
        ticker: Stock/ETF symbol
        data: Downloaded OHLCV data
    """
    
    def __init__(self, ticker: str, start: str, end: str):
        self.ticker = ticker
        self.start = start
        self.end = end
        self.data: Optional[pd.DataFrame] = None
        self._returns: Optional[pd.Series] = None
        
    def fetch(self) -> pd.DataFrame:
        """Download data from Yahoo Finance"""
        print(f"Fetching {self.ticker} data from {self.start} to {self.end}...")
        
        self.data = yf.download(
            self.ticker, 
            start=self.start, 
            end=self.end, 
            progress=False
        )
        
        # Handle multi-level columns from newer yfinance versions
        if isinstance(self.data.columns, pd.MultiIndex):
            self.data.columns = self.data.columns.get_level_values(0)
        
        # Validate data
        if self.data.empty:
            raise ValueError(f"No data found for {self.ticker}")
            
        # Clean data
        self.data = self.data.dropna()
        self._calculate_returns()
        
        print(f"  Loaded {len(self.data):,} trading days")
        print(f"   Date range: {self.data.index[0].date()} to {self.data.index[-1].date()}")
        
        return self.data
    
    def _calculate_returns(self) -> None:
        """Calculate daily returns"""
        self._returns = self.data['Close'].pct_change().dropna()
        
    @property
    def returns(self) -> pd.Series:
        """Daily returns series"""
        if self._returns is None:
            self._calculate_returns()
        return self._returns
    
    @property
    def close(self) -> pd.Series:
        """Close price series"""
        return self.data['Close']
    
    def get_benchmark_stats(self) -> dict:
        """Calculate buy-and-hold benchmark statistics"""
        total_return = (self.close.iloc[-1] / self.close.iloc[0]) - 1
        
        # Annualized metrics
        n_years = len(self.data) / 252
        annual_return = (1 + total_return) ** (1/n_years) - 1
        annual_vol = self.returns.std() * np.sqrt(252)
        sharpe = annual_return / annual_vol if annual_vol > 0 else 0
        
        # Max drawdown
        cumulative = (1 + self.returns).cumprod()
        rolling_max = cumulative.expanding().max()
        drawdowns = cumulative / rolling_max - 1
        max_dd = drawdowns.min()
        
        return {
            'total_return': total_return,
            'annual_return': annual_return,
            'annual_volatility': annual_vol,
            'sharpe_ratio': sharpe,
            'max_drawdown': max_dd
        }
    
    def generate_shuffled_prices(self, seed: Optional[int] = None) -> pd.Series:
        """
        Generate price series from shuffled returns.
        This destroys autocorrelation and temporal patterns while
        preserving the return distribution.
        
        This is the key to our Monte Carlo test - if a strategy
        works on shuffled data, it's likely just curve-fitting!
        """
        if seed is not None:
            np.random.seed(seed)
            
        # Shuffle the returns (destroys any patterns)
        shuffled_returns = self.returns.sample(frac=1, replace=False)
        shuffled_returns.index = self.returns.index  # Reset index
        
        # Reconstruct prices from shuffled returns
        shuffled_prices = self.close.iloc[0] * (1 + shuffled_returns).cumprod()
        
        # Add initial price
        shuffled_prices = pd.concat([
            pd.Series([self.close.iloc[0]], index=[self.close.index[0]]),
            shuffled_prices
        ])
        
        return shuffled_prices