"""
Visualization module for backtest results and Monte Carlo analysis.
Creates publication-quality charts suitable for a portfolio.
"""
import matplotlib.pyplot as plt
import seaborn as sns
import numpy as np
import pandas as pd
from typing import Optional, List, Dict

from monte_carlo import MonteCarloResult
from config import StrategyResult


# Set style
plt.style.use('seaborn-v0_8-whitegrid')
sns.set_palette("husl")


class BacktestVisualizer:
    """Creates visualizations for backtest results"""
    
    def __init__(self, figsize: tuple = (14, 10)):
        self.figsize = figsize
        
    def plot_monte_carlo_results(
        self,
        result: MonteCarloResult,
        strategy_name: str,
        save_path: Optional[str] = None
    ) -> None:
        """
        Create comprehensive Monte Carlo visualization.
        
        Shows:
        1. Return distribution with actual result
        2. Sharpe distribution with actual result  
        3. P-value visualization
        4. Summary statistics
        """
        fig, axes = plt.subplots(2, 2, figsize=self.figsize)
        fig.suptitle(
            f'Monte Carlo Analysis: {strategy_name}\n'
            f'Testing Statistical Significance ({result.n_simulations:,} simulations)',
            fontsize=14, fontweight='bold'
        )
        
        # Plot 1: Return Distribution
        ax1 = axes[0, 0]
        self._plot_distribution(
            ax1,
            result.simulated_returns,
            result.actual_return,
            'Total Return',
            'Probability of Return by Chance'
        )
        
        # Add CI shading
        ax1.axvspan(
            result.ci_lower_return, 
            result.ci_upper_return, 
            alpha=0.2, 
            color='green',
            label=f'95% CI: [{result.ci_lower_return:.1%}, {result.ci_upper_return:.1%}]'
        )
        ax1.legend(loc='upper right', fontsize=8)
        
        # Plot 2: Sharpe Distribution
        ax2 = axes[0, 1]
        self._plot_distribution(
            ax2,
            result.simulated_sharpes,
            result.actual_sharpe,
            'Sharpe Ratio',
            'Sharpe Ratio Distribution'
        )
        
        # Plot 3: P-Value Bar Chart
        ax3 = axes[1, 0]
        self._plot_pvalues(ax3, result)
        
        # Plot 4: Summary Report
        ax4 = axes[1, 1]
        self._plot_summary(ax4, result, strategy_name)
        
        plt.tight_layout()
        
        if save_path:
            plt.savefig(save_path, dpi=150, bbox_inches='tight', 
                       facecolor='white', edgecolor='none')
            print(f"Saved plot to {save_path}")
            
        plt.show()
        
    def _plot_distribution(
        self, 
        ax: plt.Axes, 
        data: np.ndarray, 
        actual: float,
        xlabel: str,
        title: str
    ) -> None:
        """Plot histogram with actual value marked"""
        
        # Histogram
        ax.hist(data, bins=50, alpha=0.7, color='steelblue', 
                edgecolor='white', density=True, label='Simulated')
        
        # KDE
        from scipy.stats import gaussian_kde
        kde = gaussian_kde(data)
        x_range = np.linspace(data.min(), data.max(), 200)
        ax.plot(x_range, kde(x_range), 'b-', linewidth=2, alpha=0.7)
        
        # Actual value
        ax.axvline(actual, color='red', linewidth=2.5, linestyle='--',
                   label=f'Actual: {actual:.2%}' if 'Return' in xlabel else f'Actual: {actual:.2f}')
        
        # Mean of simulations
        ax.axvline(np.mean(data), color='orange', linewidth=2, linestyle=':',
                   label=f'Mean: {np.mean(data):.2%}' if 'Return' in xlabel else f'Mean: {np.mean(data):.2f}')
        
        ax.set_xlabel(xlabel, fontsize=10)
        ax.set_ylabel('Density', fontsize=10)
        ax.set_title(title, fontsize=11, fontweight='bold')
        ax.legend(loc='upper right', fontsize=8)
        ax.grid(True, alpha=0.3)
        
        # Format x-axis as percentage if showing returns
        if 'Return' in xlabel:
            ax.xaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f'{x:.0%}'))
            
    def _plot_pvalues(self, ax: plt.Axes, result: MonteCarloResult) -> None:
        """Plot p-value comparison"""
        categories = ['Return\nP-Value', 'Sharpe\nP-Value']
        p_values = [result.p_value_return, result.p_value_sharpe]
        
        colors = ['#2ecc71' if p < 0.05 else '#e74c3c' for p in p_values]
        
        bars = ax.bar(categories, p_values, color=colors, edgecolor='black', linewidth=1.5)
        
        # Significance lines
        ax.axhline(0.05, color='orange', linestyle='--', linewidth=2, 
                   label='5% Significance')
        ax.axhline(0.01, color='red', linestyle='--', linewidth=2,
                   label='1% Significance')
        
        # Labels on bars
        for bar, p in zip(bars, p_values):
            height = bar.get_height()
            ax.annotate(f'{p:.3f}',
                       xy=(bar.get_x() + bar.get_width()/2, height),
                       xytext=(0, 3),
                       textcoords="offset points",
                       ha='center', va='bottom',
                       fontsize=12, fontweight='bold')
        
        ax.set_ylabel('P-Value', fontsize=10)
        ax.set_title('Statistical Significance Test', fontsize=11, fontweight='bold')
        ax.set_ylim(0, max(0.15, max(p_values) * 1.3))
        ax.legend(loc='upper right', fontsize=8)
        ax.grid(True, alpha=0.3, axis='y')
        
    def _plot_summary(
        self, 
        ax: plt.Axes, 
        result: MonteCarloResult,
        strategy_name: str
    ) -> None:
        """Create text summary panel"""
        ax.axis('off')
        
        # Determine verdict
        if result.is_significant_1pct:
            verdict = "STRONG EVIDENCE of genuine edge"
            verdict_color = '#27ae60'
        elif result.is_significant_5pct:
            verdict = "MODERATE EVIDENCE of edge"
            verdict_color = '#f39c12'
        else:
            verdict = "NO EVIDENCE of edge (likely luck/overfitting)"
            verdict_color = '#e74c3c'
            
        # Percentile rank
        pct_rank = (1 - result.p_value_return) * 100
        
        summary_text = f"""
╔══════════════════════════════════════════════════════════╗
║               STATISTICAL SIGNIFICANCE REPORT            ║
╠══════════════════════════════════════════════════════════╣
║  Strategy: {strategy_name:<45} ║
╠══════════════════════════════════════════════════════════╣
║  ACTUAL PERFORMANCE                                      ║
║  ├─ Total Return:        {result.actual_return:>+8.2%}                       ║
║  ├─ Sharpe Ratio:        {result.actual_sharpe:>8.2f}                        ║
║  └─ Max Drawdown:        {result.actual_max_dd:>8.2%}                        ║
╠══════════════════════════════════════════════════════════╣
║  MONTE CARLO ANALYSIS ({result.n_simulations:,} simulations)                 ║
║  ├─ Mean Random Return:  {np.mean(result.simulated_returns):>+8.2%}                       ║
║  ├─ Std Dev of Returns:  {np.std(result.simulated_returns):>8.2%}                        ║
║  └─ 95% CI: [{result.ci_lower_return:>+7.2%}, {result.ci_upper_return:>+7.2%}]                    ║
╠══════════════════════════════════════════════════════════╣
║  HYPOTHESIS TEST (H₀: Strategy has no edge)              ║
║  ├─ P-Value (Return):    {result.p_value_return:>8.4f}                        ║
║  ├─ P-Value (Sharpe):    {result.p_value_sharpe:>8.4f}                        ║
║  ├─ Percentile Rank:     {pct_rank:>7.1f}%                        ║
║  ├─ Significant (α=5%):  {'YES' if result.is_significant_5pct else 'NO':<4}                             ║
║  └─ Significant (α=1%):  {'YES' if result.is_significant_1pct else 'NO':<4}                             ║
╠══════════════════════════════════════════════════════════╣
║  VERDICT                                                 ║
║  {verdict:<55} ║
╚══════════════════════════════════════════════════════════╝
        """
        
        ax.text(0.05, 0.5, summary_text, fontsize=9, fontfamily='monospace',
               verticalalignment='center', transform=ax.transAxes,
               bbox=dict(boxstyle='round', facecolor='#f8f9fa', alpha=0.8,
                        edgecolor='#dee2e6', linewidth=2))
        
    def plot_equity_curves(
        self,
        equity_curves: Dict[str, pd.Series],
        benchmark: pd.Series,
        save_path: Optional[str] = None
    ) -> None:
        """Plot multiple equity curves with benchmark"""
        
        fig, axes = plt.subplots(2, 1, figsize=(14, 10), 
                                  gridspec_kw={'height_ratios': [3, 1]})
        
        ax1, ax2 = axes
        
        # Normalize to 100
        benchmark_norm = 100 * benchmark / benchmark.iloc[0]
        
        # Plot benchmark
        ax1.plot(benchmark_norm.index, benchmark_norm.values, 
                 'k--', linewidth=2, alpha=0.5, label='Buy & Hold')
        
        # Plot strategies
        colors = plt.cm.tab10(np.linspace(0, 1, len(equity_curves)))
        
        for (name, equity), color in zip(equity_curves.items(), colors):
            equity_norm = 100 * equity / equity.iloc[0]
            ax1.plot(equity_norm.index, equity_norm.values, 
                    linewidth=2, label=name, color=color)
            
            # Plot drawdowns
            dd = equity / equity.cummax() - 1
            ax2.fill_between(dd.index, dd.values, 0, alpha=0.3, color=color)
            ax2.plot(dd.index, dd.values, linewidth=1, color=color)
        
        ax1.set_title('Equity Curves Comparison', fontsize=14, fontweight='bold')
        ax1.set_ylabel('Portfolio Value (Indexed to 100)', fontsize=10)
        ax1.legend(loc='upper left', fontsize=9)
        ax1.grid(True, alpha=0.3)
        
        ax2.set_title('Drawdowns', fontsize=12, fontweight='bold')
        ax2.set_ylabel('Drawdown', fontsize=10)
        ax2.set_xlabel('Date', fontsize=10)
        ax2.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f'{x:.0%}'))
        ax2.grid(True, alpha=0.3)
        
        plt.tight_layout()
        
        if save_path:
            plt.savefig(save_path, dpi=150, bbox_inches='tight')
            
        plt.show()
        
    def plot_strategy_comparison(
        self,
        results: List[StrategyResult],
        save_path: Optional[str] = None
    ) -> None:
        """Create strategy comparison dashboard"""
        
        fig, axes = plt.subplots(2, 2, figsize=(14, 10))
        
        names = [r.strategy_name for r in results]
        
        # Return comparison
        ax1 = axes[0, 0]
        returns = [r.total_return for r in results]
        colors = ['#2ecc71' if r > 0 else '#e74c3c' for r in returns]
        ax1.barh(names, returns, color=colors, edgecolor='black')
        ax1.axvline(0, color='black', linewidth=1)
        ax1.set_xlabel('Total Return')
        ax1.set_title('Total Returns Comparison', fontweight='bold')
        ax1.xaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f'{x:.0%}'))
        
        # Sharpe comparison
        ax2 = axes[0, 1]
        sharpes = [r.sharpe_ratio for r in results]
        ax2.barh(names, sharpes, color='steelblue', edgecolor='black')
        ax2.axvline(0, color='black', linewidth=1)
        ax2.set_xlabel('Sharpe Ratio')
        ax2.set_title('Risk-Adjusted Returns (Sharpe)', fontweight='bold')
        
        # Max Drawdown comparison
        ax3 = axes[1, 0]
        drawdowns = [r.max_drawdown for r in results]
        ax3.barh(names, drawdowns, color='#e74c3c', edgecolor='black')
        ax3.set_xlabel('Maximum Drawdown')
        ax3.set_title('Maximum Drawdown', fontweight='bold')
        ax3.xaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f'{x:.0%}'))
        
        # Win Rate comparison
        ax4 = axes[1, 1]
        win_rates = [r.win_rate for r in results]
        ax4.barh(names, win_rates, color='#3498db', edgecolor='black')
        ax4.axvline(0.5, color='orange', linestyle='--', label='50% (Coin Flip)')
        ax4.set_xlabel('Win Rate')
        ax4.set_title('Win Rate', fontweight='bold')
        ax4.xaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f'{x:.0%}'))
        ax4.legend()
        
        plt.tight_layout()
        
        if save_path:
            plt.savefig(save_path, dpi=150, bbox_inches='tight')
            
        plt.show()