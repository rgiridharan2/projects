"""
Main execution script for the Backtest vs Reality Engine.

This script demonstrates:
1. Strategy backtesting with realistic transaction costs
2. Monte Carlo simulation for statistical significance
3. Walk-forward analysis for overfitting detection
4. Comprehensive visualization

Author: [Your Name]
Purpose: Resume project for Quant Finance/Algorithmic Trading roles
"""

import warnings
warnings.filterwarnings('ignore')

import numpy as np
import pandas as pd

from config import BacktestConfig
from data_fetcher import DataFetcher
from strategies import (
    MovingAverageCrossover,
    BollingerBandsMeanReversion,
    RSIMeanReversion,
    MomentumBreakout
)
from backtest_engine import BacktestEngine
from monte_carlo import MonteCarloSimulator, WalkForwardValidator
from visualization import BacktestVisualizer


def print_header():
    """Print project header"""
    print("\n" + "="*70)
    print("   ALGORITHMIC TRADING: BACKTEST vs REALITY ENGINE")
    print("   Testing for Statistical Significance & Overfitting")
    print("="*70 + "\n")


def print_section(title: str):
    """Print section header"""
    print("\n" + "-"*60)
    print(f"   {title}")
    print("-"*60)


def analyze_strategy(
    name: str,
    strategy_class: type,
    strategy_params: dict,
    data_fetcher: DataFetcher,
    config: BacktestConfig,
    visualizer: BacktestVisualizer
) -> dict:
    """Run complete analysis for a single strategy"""
    
    print_section(f"Analyzing: {name}")
    
    # 1. Basic Backtest
    print("\n Running backtest on actual data...")
    strategy = strategy_class(data_fetcher.close, **strategy_params)
    engine = BacktestEngine(
        data_fetcher.close,
        initial_capital=config.initial_capital,
        commission=config.commission,
        slippage=config.slippage
    )
    result = engine.run(strategy)
    
    print(f"\n   Results:")
    print(f"   ├─ Total Return:    {result.total_return:>+8.2%}")
    print(f"   ├─ Sharpe Ratio:    {result.sharpe_ratio:>8.2f}")
    print(f"   ├─ Max Drawdown:    {result.max_drawdown:>8.2%}")
    print(f"   ├─ Win Rate:        {result.win_rate:>8.2%}")
    print(f"   └─ Total Trades:    {result.total_trades:>8}")
    
    # 2. Monte Carlo Simulation
    print("\n Running Monte Carlo simulation...")
    mc_simulator = MonteCarloSimulator(
        data_fetcher,
        n_simulations=config.n_simulations,
        confidence_level=config.confidence_level,
        random_seed=config.random_seed
    )
    
    mc_result = mc_simulator.run(
        strategy_class=strategy_class,
        strategy_params=strategy_params,
        commission=config.commission,
        slippage=config.slippage
    )
    
    # Print Monte Carlo results
    print(f"\n   Monte Carlo Results:")
    print(f"   ├─ Actual Return:       {mc_result.actual_return:>+8.2%}")
    print(f"   ├─ Mean Random Return:  {np.mean(mc_result.simulated_returns):>+8.2%}")
    print(f"   ├─ P-Value (Return):    {mc_result.p_value_return:>8.4f}")
    print(f"   ├─ P-Value (Sharpe):    {mc_result.p_value_sharpe:>8.4f}")
    print(f"   └─ 95% CI: [{mc_result.ci_lower_return:+.2%}, {mc_result.ci_upper_return:+.2%}]")
    
    # Verdict
    if mc_result.is_significant_1pct:
        print("\n   VERDICT: Strong statistical significance (p < 0.01)")
    elif mc_result.is_significant_5pct:
        print("\n   VERDICT: Moderate significance (p < 0.05)")
    else:
        print("\n   VERDICT: Not significant - likely luck/overfitting!")
    
    # 3. Visualization
    visualizer.plot_monte_carlo_results(
        mc_result,
        strategy_name=name,
        save_path=f"plots/{name.replace(' ', '_').replace('/', '_')}_monte_carlo.png"
    )
    
    return {
        'name': name,
        'backtest_result': result,
        'monte_carlo_result': mc_result
    }


def main():
    """Main execution function"""
    
    print_header()
    
    # Configuration
    config = BacktestConfig(
        ticker="SPY",
        start_date="2015-01-01",
        end_date="2024-01-01",
        initial_capital=100_000,
        n_simulations=1000
    )
    
    print(f"Configuration:")
    print(f"   ├─ Ticker:           {config.ticker}")
    print(f"   ├─ Period:           {config.start_date} to {config.end_date}")
    print(f"   ├─ Initial Capital:  ${config.initial_capital:,.0f}")
    print(f"   ├─ Commission:       {config.commission:.2%}")
    print(f"   ├─ Slippage:         {config.slippage:.2%}")
    print(f"   └─ MC Simulations:   {config.n_simulations:,}")
    
    # Fetch data
    print_section("Data Acquisition")
    data_fetcher = DataFetcher(config.ticker, config.start_date, config.end_date)
    data_fetcher.fetch()
    
    # Benchmark stats
    benchmark = data_fetcher.get_benchmark_stats()
    print(f"\n   Buy & Hold Benchmark:")
    print(f"   ├─ Total Return:    {benchmark['total_return']:>+8.2%}")
    print(f"   ├─ Annual Return:   {benchmark['annual_return']:>+8.2%}")
    print(f"   ├─ Sharpe Ratio:    {benchmark['sharpe_ratio']:>8.2f}")
    print(f"   └─ Max Drawdown:    {benchmark['max_drawdown']:>8.2%}")
    
    # Initialize visualizer
    visualizer = BacktestVisualizer()
    
    # Define strategies to test
    strategies_to_test = [
        {
            'name': 'MA Crossover (10/50)',
            'class': MovingAverageCrossover,
            'params': {'fast_period': 10, 'slow_period': 50}
        },
        {
            'name': 'MA Crossover (20/100)',
            'class': MovingAverageCrossover,
            'params': {'fast_period': 20, 'slow_period': 100}
        },
        {
            'name': 'Bollinger Bands (20, 2σ)',
            'class': BollingerBandsMeanReversion,
            'params': {'period': 20, 'num_std': 2.0}
        },
        {
            'name': 'RSI Mean Reversion',
            'class': RSIMeanReversion,
            'params': {'period': 14, 'oversold': 30, 'exit_level': 50}
        },
        {
            'name': 'Momentum Breakout',
            'class': MomentumBreakout,
            'params': {'entry_period': 20, 'exit_period': 10}
        }
    ]
    
    # Analyze each strategy
    all_results = []
    
    for strat in strategies_to_test:
        result = analyze_strategy(
            name=strat['name'],
            strategy_class=strat['class'],
            strategy_params=strat['params'],
            data_fetcher=data_fetcher,
            config=config,
            visualizer=visualizer
        )
        all_results.append(result)
    
    # Walk-Forward Analysis on best strategy
    print_section("Walk-Forward Analysis (Overfitting Detection)")
    
    wf_validator = WalkForwardValidator(data_fetcher, n_splits=5)
    wf_result = wf_validator.run(
        strategy_class=MovingAverageCrossover,
        strategy_params={'fast_period': 10, 'slow_period': 50},
        commission=config.commission,
        slippage=config.slippage
    )
    
    if wf_result['is_overfit']:
        print("\n   WARNING: High degradation suggests potential overfitting!")
    else:
        print("\n   Performance is relatively stable across periods")
    
    # Summary comparison
    print_section("Strategy Comparison Summary")
    
    # Create comparison table
    comparison_data = []
    for r in all_results:
        mc = r['monte_carlo_result']
        bt = r['backtest_result']
        
        significance = "Y" if mc.is_significant_5pct else "N"
        
        comparison_data.append({
            'Strategy': r['name'],
            'Return': f"{bt.total_return:+.1%}",
            'Sharpe': f"{bt.sharpe_ratio:.2f}",
            'MaxDD': f"{bt.max_drawdown:.1%}",
            'P-Value': f"{mc.p_value_return:.3f}",
            'Significant': significance
        })
    
    df = pd.DataFrame(comparison_data)
    print(f"\n{df.to_string(index=False)}")
    
    # Plot comparison
    backtest_results = [r['backtest_result'] for r in all_results]
    visualizer.plot_strategy_comparison(backtest_results, save_path="plots/strategy_comparison.png")
    
    # Final summary
    print("\n" + "="*70)
    print("   ANALYSIS COMPLETE")
    print("="*70)
    
    significant_strategies = [r['name'] for r in all_results 
                             if r['monte_carlo_result'].is_significant_5pct]
    
    if significant_strategies:
        print(f"\n   Strategies with statistical significance:")
        for s in significant_strategies:
            print(f"      Y {s}")
    else:
        print("\n  No strategies showed statistical significance!")
        print("   This is actually a common and important finding.")
    
    print("\n   Key Takeaways:")
    print("   1. Backtested returns ≠ future returns")
    print("   2. Many 'profitable' strategies are just lucky")
    print("   3. Always test for statistical significance")
    print("   4. Watch for in-sample vs out-of-sample degradation")
    print("\n")
    
    return all_results


if __name__ == "__main__":
    # Create plots directory
    import os
    os.makedirs("plots", exist_ok=True)
    
    results = main()