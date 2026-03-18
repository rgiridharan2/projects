"""
Configuration settings for the backtesting engine.
Centralizes all parameters for easy experimentation.
"""
from dataclasses import dataclass
from typing import List

@dataclass
class BacktestConfig:
    """Main configuration for backtests"""
    # Data settings
    ticker: str = "SPY"
    start_date: str = "2018-01-01"
    end_date: str = "2024-01-01"
    
    # Backtest settings
    initial_capital: float = 100_000
    commission: float = 0.001      # 0.1% per trade
    slippage: float = 0.0005       # 0.05% slippage
    
    # Monte Carlo settings
    n_simulations: int = 1000
    confidence_level: float = 0.95
    random_seed: int = 42
    
    # Strategy parameters
    ma_fast_periods: List[int] = None
    ma_slow_periods: List[int] = None
    bb_periods: List[int] = None
    bb_std_devs: List[float] = None
    
    def __post_init__(self):
        self.ma_fast_periods = self.ma_fast_periods or [10, 20]
        self.ma_slow_periods = self.ma_slow_periods or [50, 100]
        self.bb_periods = self.bb_periods or [20]
        self.bb_std_devs = self.bb_std_devs or [2.0]


@dataclass  
class StrategyResult:
    """Container for strategy backtest results"""
    strategy_name: str
    total_return: float
    annualized_return: float
    sharpe_ratio: float
    sortino_ratio: float
    max_drawdown: float
    win_rate: float
    profit_factor: float
    total_trades: int
    avg_trade_duration: float
    
    def to_dict(self) -> dict:
        return {
            'Strategy': self.strategy_name,
            'Total Return': f"{self.total_return:.2%}",
            'Annual Return': f"{self.annualized_return:.2%}",
            'Sharpe Ratio': f"{self.sharpe_ratio:.2f}",
            'Sortino Ratio': f"{self.sortino_ratio:.2f}",
            'Max Drawdown': f"{self.max_drawdown:.2%}",
            'Win Rate': f"{self.win_rate:.2%}",
            'Profit Factor': f"{self.profit_factor:.2f}",
            'Total Trades': self.total_trades,
        }