"""
Backtesting engine using vectorbt for vectorized performance.
Calculates comprehensive performance metrics.
"""
import pandas as pd
import numpy as np
import vectorbt as vbt
from typing import Tuple, Optional
from config import StrategyResult
from strategies import BaseStrategy


class BacktestEngine:
    """
    Vectorized backtesting engine.
    
    Uses vectorbt for fast, vectorized backtesting with realistic
    transaction costs and slippage modeling.
    
    Attributes:
        prices: Price series to backtest on
        initial_capital: Starting capital
        commission: Commission per trade (as decimal)
        slippage: Slippage per trade (as decimal)
    """
    
    def __init__(
        self, 
        prices: pd.Series,
        initial_capital: float = 100_000,
        commission: float = 0.001,
        slippage: float = 0.0005
    ):
        self.prices = prices
        self.initial_capital = initial_capital
        self.commission = commission
        self.slippage = slippage
        
    def run(self, strategy: BaseStrategy) -> StrategyResult:
        """
        Run backtest for a given strategy.
        
        Args:
            strategy: Strategy instance with generate_signals method
            
        Returns:
            StrategyResult with comprehensive metrics
        """
        entries, exits = strategy.generate_signals()
        
        # Run vectorbt portfolio simulation
        portfolio = vbt.Portfolio.from_signals(
            close=self.prices,
            entries=entries.shift(1).fillna(False),
            exits=exits.shift(1).fillna(False),
            init_cash=self.initial_capital,
            fees=self.commission,
            slippage=self.slippage,
            freq='1D'
        )
        
        # Extract metrics
        return self._extract_metrics(portfolio, strategy.name)
    
    def run_from_signals(
        self, 
        entries: pd.Series, 
        exits: pd.Series,
        strategy_name: str = "Custom"
    ) -> StrategyResult:
        """Run backtest from raw signals"""
        portfolio = vbt.Portfolio.from_signals(
            close=self.prices,
            entries=entries.shift(1).fillna(False),
            exits=exits.shift(1).fillna(False),
            init_cash=self.initial_capital,
            fees=self.commission,
            slippage=self.slippage,
            freq='1D'
        )
        
        return self._extract_metrics(portfolio, strategy_name)
    
    def _extract_metrics(self, portfolio: vbt.Portfolio, name: str) -> StrategyResult:
        """Extract performance metrics from portfolio"""
        
        # Basic returns
        total_return = portfolio.total_return()
        
        # Annualized metrics
        n_years = len(self.prices) / 252
        annual_return = (1 + total_return) ** (1/n_years) - 1 if n_years > 0 else 0
        
        # Risk metrics
        try:
            sharpe = portfolio.sharpe_ratio()
            sharpe = sharpe if not np.isnan(sharpe) else 0
        except:
            sharpe = 0
            
        try:
            sortino = portfolio.sortino_ratio()
            sortino = sortino if not np.isnan(sortino) else 0
        except:
            sortino = 0
            
        max_dd = portfolio.max_drawdown()
        
        # Trade statistics
        trades = portfolio.trades
        if len(trades.records) > 0:
            win_rate = trades.win_rate()
            total_trades = trades.count()
            
            # Profit factor
            winning = trades.pnl.values[trades.pnl.values > 0].sum()
            losing = abs(trades.pnl.values[trades.pnl.values < 0].sum())
            profit_factor = winning / losing if losing > 0 else float('inf')
            
            # Average duration
            try:
                avg_duration = trades.duration.mean().days if hasattr(trades.duration.mean(), 'days') else 0
            except:
                avg_duration = 0
        else:
            win_rate = 0
            total_trades = 0
            profit_factor = 0
            avg_duration = 0
            
        return StrategyResult(
            strategy_name=name,
            total_return=total_return,
            annualized_return=annual_return,
            sharpe_ratio=sharpe,
            sortino_ratio=sortino,
            max_drawdown=max_dd,
            win_rate=win_rate,
            profit_factor=profit_factor,
            total_trades=total_trades,
            avg_trade_duration=avg_duration
        )
    
    def get_equity_curve(self, strategy: BaseStrategy) -> pd.Series:
        """Get equity curve for plotting"""
        entries, exits = strategy.generate_signals()
        
        portfolio = vbt.Portfolio.from_signals(
            close=self.prices,
            entries=entries,
            exits=exits,
            init_cash=self.initial_capital,
            fees=self.commission,
            slippage=self.slippage,
            freq='1D'
        )
        
        return portfolio.value()
    
    def get_drawdown_series(self, strategy: BaseStrategy) -> pd.Series:
        """Get drawdown series for plotting"""
        entries, exits = strategy.generate_signals()
        
        portfolio = vbt.Portfolio.from_signals(
            close=self.prices,
            entries=entries,
            exits=exits,
            init_cash=self.initial_capital,
            fees=self.commission,
            slippage=self.slippage,
            freq='1D'
        )
        
        return portfolio.drawdown()