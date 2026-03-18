"""
Monte Carlo simulation for statistical significance testing.

Upgrades vs original:
1) Keeps original "shuffle returns" test (works, but often answers a harsh question)
2) Adds alpha-vs-buy&hold testing (recommended default interpretation of "edge")
3) Adds block bootstraps (moving block + stationary) to preserve short-term dependence
4) Optional exposure-matched random timer baseline (controls for "mostly long" strategies)

Compatibility:
- Keeps the original MonteCarloResult fields so main.py and visualization.py still work.
- Adds extra fields for alpha and benchmark comparisons.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from typing import Dict, Optional, Tuple
from dataclasses import dataclass
from tqdm import tqdm

from backtest_engine import BacktestEngine
from data_fetcher import DataFetcher


# -----------------------------
# Result dataclass (compatible + extended)
# -----------------------------
@dataclass
class MonteCarloResult:
    """Results from Monte Carlo simulation"""
    # ORIGINAL FIELDS (kept for compatibility)
    actual_return: float
    actual_sharpe: float
    actual_max_dd: float

    simulated_returns: np.ndarray
    simulated_sharpes: np.ndarray

    p_value_return: float
    p_value_sharpe: float

    ci_lower_return: float
    ci_upper_return: float

    is_significant_5pct: bool
    is_significant_1pct: bool

    n_simulations: int

    # EXTENSIONS (new fields)
    # buy & hold on actual data
    actual_bh_return: float = 0.0
    actual_bh_sharpe: float = 0.0
    actual_bh_max_dd: float = 0.0

    # alpha on actual data
    actual_alpha_return: float = 0.0
    actual_alpha_sharpe: float = 0.0
    actual_dd_improvement: float = 0.0  # (bh_dd - strat_dd); larger is better

    # simulated benchmark + alpha distributions (for the same simulated paths)
    simulated_bh_returns: Optional[np.ndarray] = None
    simulated_bh_sharpes: Optional[np.ndarray] = None
    simulated_alpha_returns: Optional[np.ndarray] = None
    simulated_alpha_sharpes: Optional[np.ndarray] = None
    simulated_dd_improvements: Optional[np.ndarray] = None

    # p-values for "edge" metrics (recommended)
    p_value_alpha_return: Optional[float] = None
    p_value_alpha_sharpe: Optional[float] = None
    p_value_dd_improvement: Optional[float] = None

    # confidence interval for alpha return (optional)
    ci_lower_alpha_return: Optional[float] = None
    ci_upper_alpha_return: Optional[float] = None

    # Exposure matched test (optional)
    exposure_fraction: Optional[float] = None
    p_value_exposure_matched_alpha_return: Optional[float] = None
    simulated_exposure_matched_alpha_returns: Optional[np.ndarray] = None


# -----------------------------
# Monte Carlo Simulator
# -----------------------------
class MonteCarloSimulator:
    """
    Monte Carlo simulation for testing strategy significance.

    Methods supported for simulating alternate histories:
    - method="shuffle": permute daily returns (destroys all temporal structure)
    - method="mbb": moving block bootstrap (preserves short-term dependence in blocks)
    - method="stationary": stationary bootstrap (random block lengths; preserves dependence better)

    Metrics produced:
    - raw strategy return/sharpe distributions (for backwards compatibility)
    - alpha-vs-buy&hold return/sharpe distributions (recommended to judge "edge")
    - optional drawdown improvement distribution (bh_dd - strat_dd)
    - optional exposure-matched random timer p-value (controls for long exposure)
    """

    def __init__(
        self,
        data_fetcher: DataFetcher,
        n_simulations: int = 1000,
        confidence_level: float = 0.95,
        random_seed: int = 42,
    ):
        self.data_fetcher = data_fetcher
        self.n_simulations = n_simulations
        self.confidence_level = confidence_level
        self.random_seed = random_seed
        np.random.seed(random_seed)

    # -----------------------------
    # Public API
    # -----------------------------
    def run(
        self,
        strategy_class: type,
        strategy_params: dict,
        commission: float = 0.001,
        slippage: float = 0.0005,
        show_progress: bool = True,
        # NEW OPTIONS:
        method: str = "shuffle",
        block_length: int = 20,
        stationary_p: Optional[float] = None,
        # Optional: exposure-matched baseline (slow-ish but useful)
        exposure_matched: bool = False,
        exposure_matched_hold_min: int = 1,
        exposure_matched_hold_max: int = 20,
    ) -> MonteCarloResult:
        """
        Run Monte Carlo simulation for a strategy.

        Args:
            method:
                "shuffle" | "mbb" | "stationary"
            block_length:
                For "mbb": fixed block length L
                For "stationary": average block length if stationary_p is not provided
            stationary_p:
                For "stationary": probability of starting a new block.
                If None, uses p = 1/block_length.
            exposure_matched:
                If True, adds a second p-value where the null is
                a random timer with the SAME exposure fraction as the strategy.
        """
        prices = self.data_fetcher.close
        rets = self.data_fetcher.returns

        # 1) Actual strategy backtest on real prices
        actual_strategy = strategy_class(prices, **strategy_params)
        actual_engine = BacktestEngine(prices, commission=commission, slippage=slippage)
        actual_result = actual_engine.run(actual_strategy)

        # 2) Actual buy & hold stats
        actual_bh_return, actual_bh_sharpe, actual_bh_max_dd = self._buy_and_hold_stats(prices)

        actual_alpha_return = actual_result.total_return - actual_bh_return
        actual_alpha_sharpe = actual_result.sharpe_ratio - actual_bh_sharpe
        actual_dd_improvement = actual_bh_max_dd - actual_result.max_drawdown  # bigger = better

        # 3) For exposure-matched baseline, estimate exposure fraction from signals on real data
        exposure_fraction = None
        if exposure_matched:
            entries, exits = actual_strategy.generate_signals()
            exposure_fraction = self._compute_exposure_fraction(entries, exits)

        # 4) Simulations
        sim_strat_returns = []
        sim_strat_sharpes = []
        sim_bh_returns = []
        sim_bh_sharpes = []
        sim_alpha_returns = []
        sim_alpha_sharpes = []
        sim_dd_improvements = []

        sim_exposure_matched_alpha_returns = []

        iterator = range(self.n_simulations)
        if show_progress:
            iterator = tqdm(iterator, desc="🎲 Monte Carlo Simulation")

        for i in iterator:
            sim_prices = self._generate_simulated_prices(
                prices=prices,
                returns=rets,
                seed=i,
                method=method,
                block_length=block_length,
                stationary_p=stationary_p,
            )

            # Strategy on simulated prices
            sim_strategy = strategy_class(sim_prices, **strategy_params)
            sim_engine = BacktestEngine(sim_prices, commission=commission, slippage=slippage)
            sim_result = sim_engine.run(sim_strategy)

            # Buy & hold on same simulated prices
            bh_ret, bh_sharpe, bh_dd = self._buy_and_hold_stats(sim_prices)

            # Collect
            sim_strat_returns.append(sim_result.total_return)
            sim_strat_sharpes.append(sim_result.sharpe_ratio)

            sim_bh_returns.append(bh_ret)
            sim_bh_sharpes.append(bh_sharpe)

            sim_alpha_returns.append(sim_result.total_return - bh_ret)
            sim_alpha_sharpes.append(sim_result.sharpe_ratio - bh_sharpe)
            sim_dd_improvements.append(bh_dd - sim_result.max_drawdown)

            # Exposure-matched random timer on the SAME simulated prices
            if exposure_matched and exposure_fraction is not None:
                timer_alpha = self._exposure_matched_timer_alpha_return(
                    prices=sim_prices,
                    exposure_fraction=exposure_fraction,
                    hold_min=exposure_matched_hold_min,
                    hold_max=exposure_matched_hold_max,
                    commission=commission,
                    slippage=slippage,
                    seed=self.random_seed + i,
                )
                sim_exposure_matched_alpha_returns.append(timer_alpha)

        # Convert to arrays
        sim_strat_returns = np.asarray(sim_strat_returns, dtype=float)
        sim_strat_sharpes = np.asarray(sim_strat_sharpes, dtype=float)
        sim_bh_returns = np.asarray(sim_bh_returns, dtype=float)
        sim_bh_sharpes = np.asarray(sim_bh_sharpes, dtype=float)
        sim_alpha_returns = np.asarray(sim_alpha_returns, dtype=float)
        sim_alpha_sharpes = np.asarray(sim_alpha_sharpes, dtype=float)
        sim_dd_improvements = np.asarray(sim_dd_improvements, dtype=float)

        # 5) P-values
        # Raw p-values (compatibility): "what % of simulated strategies beat the actual strategy"
        p_value_return_raw = float(np.mean(sim_strat_returns >= actual_result.total_return))
        p_value_sharpe_raw = float(np.mean(sim_strat_sharpes >= actual_result.sharpe_ratio))

        # Alpha p-values (recommended): "what % of simulated paths produce >= alpha"
        p_value_alpha_return = float(np.mean(sim_alpha_returns >= actual_alpha_return))
        p_value_alpha_sharpe = float(np.mean(sim_alpha_sharpes >= actual_alpha_sharpe))

        # Drawdown improvement p-value (bigger is better)
        p_value_dd_improvement = float(np.mean(sim_dd_improvements >= actual_dd_improvement))

        # 6) Confidence intervals
        alpha = 1 - self.confidence_level
        ci_lower_return = float(np.percentile(sim_strat_returns, (alpha / 2) * 100))
        ci_upper_return = float(np.percentile(sim_strat_returns, (1 - alpha / 2) * 100))

        ci_lower_alpha_return = float(np.percentile(sim_alpha_returns, (alpha / 2) * 100))
        ci_upper_alpha_return = float(np.percentile(sim_alpha_returns, (1 - alpha / 2) * 100))

        # 7) Exposure matched p-value (alpha)
        p_value_exposure_matched_alpha = None
        sim_exposure_alpha_arr = None
        if exposure_matched and len(sim_exposure_matched_alpha_returns) > 0:
            sim_exposure_alpha_arr = np.asarray(sim_exposure_matched_alpha_returns, dtype=float)
            p_value_exposure_matched_alpha = float(
                np.mean(sim_exposure_alpha_arr >= actual_alpha_return)
            )

        # 8) “Significance” flags:
        # Keep your original logic tied to RAW return p-value for backward compatibility,
        # but you should *primarily* look at p_value_alpha_return going forward.
        is_sig_5 = p_value_return_raw < 0.05
        is_sig_1 = p_value_return_raw < 0.01

        return MonteCarloResult(
            # original fields
            actual_return=float(actual_result.total_return),
            actual_sharpe=float(actual_result.sharpe_ratio),
            actual_max_dd=float(actual_result.max_drawdown),
            simulated_returns=sim_strat_returns,
            simulated_sharpes=sim_strat_sharpes,
            p_value_return=p_value_return_raw,
            p_value_sharpe=p_value_sharpe_raw,
            ci_lower_return=ci_lower_return,
            ci_upper_return=ci_upper_return,
            is_significant_5pct=is_sig_5,
            is_significant_1pct=is_sig_1,
            n_simulations=self.n_simulations,
            # extensions
            actual_bh_return=float(actual_bh_return),
            actual_bh_sharpe=float(actual_bh_sharpe),
            actual_bh_max_dd=float(actual_bh_max_dd),
            actual_alpha_return=float(actual_alpha_return),
            actual_alpha_sharpe=float(actual_alpha_sharpe),
            actual_dd_improvement=float(actual_dd_improvement),
            simulated_bh_returns=sim_bh_returns,
            simulated_bh_sharpes=sim_bh_sharpes,
            simulated_alpha_returns=sim_alpha_returns,
            simulated_alpha_sharpes=sim_alpha_sharpes,
            simulated_dd_improvements=sim_dd_improvements,
            p_value_alpha_return=p_value_alpha_return,
            p_value_alpha_sharpe=p_value_alpha_sharpe,
            p_value_dd_improvement=p_value_dd_improvement,
            ci_lower_alpha_return=ci_lower_alpha_return,
            ci_upper_alpha_return=ci_upper_alpha_return,
            exposure_fraction=exposure_fraction,
            p_value_exposure_matched_alpha_return=p_value_exposure_matched_alpha,
            simulated_exposure_matched_alpha_returns=sim_exposure_alpha_arr,
        )

    # -----------------------------
    # Simulation generators
    # -----------------------------
    def _generate_simulated_prices(
        self,
        prices: pd.Series,
        returns: pd.Series,
        seed: int,
        method: str,
        block_length: int,
        stationary_p: Optional[float],
    ) -> pd.Series:
        rng = np.random.default_rng(self.random_seed + seed)

        method = (method or "shuffle").lower().strip()
        if method not in {"shuffle", "mbb", "stationary"}:
            raise ValueError(f"Unknown method='{method}'. Use 'shuffle', 'mbb', or 'stationary'.")

        if method == "shuffle":
            sim_rets = returns.sample(frac=1, replace=False, random_state=int(rng.integers(0, 2**31 - 1)))
            sim_rets = sim_rets.to_numpy()
        elif method == "mbb":
            sim_rets = self._moving_block_bootstrap(returns.to_numpy(), block_length, rng)
        else:
            p = stationary_p if stationary_p is not None else (1.0 / max(1, block_length))
            sim_rets = self._stationary_bootstrap(returns.to_numpy(), p, rng)

        # Rebuild prices (align to original close index)
        # returns has one fewer item than prices (because pct_change drops first)
        start_price = float(prices.iloc[0])
        sim_path = start_price * np.cumprod(1.0 + sim_rets)

        sim_prices = pd.Series(index=prices.index, dtype=float)
        sim_prices.iloc[0] = start_price
        # fill from index 1 onward with the reconstructed path
        sim_prices.iloc[1:] = sim_path
        return sim_prices

    @staticmethod
    def _moving_block_bootstrap(x: np.ndarray, block_length: int, rng: np.random.Generator) -> np.ndarray:
        n = len(x)
        L = max(1, int(block_length))
        out = np.empty(n, dtype=float)
        pos = 0
        while pos < n:
            start = int(rng.integers(0, n))
            end = min(start + L, n)
            block = x[start:end]
            take = min(len(block), n - pos)
            out[pos:pos + take] = block[:take]
            pos += take
        return out

    @staticmethod
    def _stationary_bootstrap(x: np.ndarray, p: float, rng: np.random.Generator) -> np.ndarray:
        n = len(x)
        p = float(np.clip(p, 1e-6, 1.0))
        out = np.empty(n, dtype=float)
        idx = int(rng.integers(0, n))
        for t in range(n):
            out[t] = x[idx]
            if rng.random() < p:
                idx = int(rng.integers(0, n))
            else:
                idx = (idx + 1) % n
        return out

    # -----------------------------
    # Benchmark + helpers
    # -----------------------------
    @staticmethod
    def _buy_and_hold_stats(prices: pd.Series) -> Tuple[float, float, float]:
        """Compute buy & hold total return, sharpe (annualized), and max drawdown from prices."""
        prices = prices.dropna()
        if len(prices) < 3:
            return 0.0, 0.0, 0.0

        rets = prices.pct_change().dropna()
        total_return = float(prices.iloc[-1] / prices.iloc[0] - 1.0)

        n_years = len(prices) / 252.0
        annual_return = (1.0 + total_return) ** (1.0 / n_years) - 1.0 if n_years > 0 else 0.0
        annual_vol = float(rets.std() * np.sqrt(252.0)) if rets.std() > 0 else 0.0
        sharpe = float(annual_return / annual_vol) if annual_vol > 0 else 0.0

        cumulative = (1.0 + rets).cumprod()
        rolling_max = cumulative.expanding().max()
        drawdowns = cumulative / rolling_max - 1.0
        max_dd = float(drawdowns.min()) if len(drawdowns) else 0.0

        return total_return, sharpe, max_dd

    @staticmethod
    def _compute_exposure_fraction(entries: pd.Series, exits: pd.Series) -> float:
        """Estimate fraction of time in market from entry/exit signals (long/flat)."""
        entries = entries.fillna(False).to_numpy(dtype=bool)
        exits = exits.fillna(False).to_numpy(dtype=bool)
        pos = 0
        in_pos = np.zeros(len(entries), dtype=int)
        for i in range(len(entries)):
            if pos == 0 and entries[i]:
                pos = 1
            elif pos == 1 and exits[i]:
                pos = 0
            in_pos[i] = pos
        return float(in_pos.mean()) if len(in_pos) else 0.0

    def _exposure_matched_timer_alpha_return(
        self,
        prices: pd.Series,
        exposure_fraction: float,
        hold_min: int,
        hold_max: int,
        commission: float,
        slippage: float,
        seed: int,
    ) -> float:
        """
        Create a random long/flat timer with ~same exposure fraction, run it, and compute alpha return vs BH.
        We build contiguous "long blocks" with random holding periods to roughly mimic trades.
        """
        rng = np.random.default_rng(seed)

        n = len(prices)
        if n < 5:
            return 0.0

        target_long_bars = int(round(exposure_fraction * n))
        target_long_bars = max(0, min(n, target_long_bars))

        # Build a random position mask with contiguous blocks
        pos = np.zeros(n, dtype=bool)
        i = 0
        long_used = 0

        hold_min = max(1, int(hold_min))
        hold_max = max(hold_min, int(hold_max))

        while i < n and long_used < target_long_bars:
            # random "flat" gap
            gap = int(rng.integers(0, hold_max + 1))
            i += gap
            if i >= n:
                break

            # random long hold
            hold = int(rng.integers(hold_min, hold_max + 1))
            j = min(n, i + hold)

            # only fill up to remaining long bars target
            remaining = target_long_bars - long_used
            block_len = min(j - i, remaining)
            if block_len <= 0:
                break

            pos[i:i + block_len] = True
            long_used += block_len
            i = i + block_len

        # Convert position mask to entry/exit signals
        entries = pd.Series(False, index=prices.index)
        exits = pd.Series(False, index=prices.index)

        # Entry: False->True ; Exit: True->False
        pos_s = pd.Series(pos, index=prices.index)
        entries.iloc[1:] = (~pos_s.shift(1).fillna(False) & pos_s).iloc[1:]
        exits.iloc[1:] = (pos_s.shift(1).fillna(False) & ~pos_s).iloc[1:]

        engine = BacktestEngine(prices, commission=commission, slippage=slippage)
        timer_result = engine.run_from_signals(entries, exits, strategy_name="ExposureMatchedTimer")

        bh_ret, _, _ = self._buy_and_hold_stats(prices)
        return float(timer_result.total_return - bh_ret)

    # -----------------------------
    # Extra utility
    # -----------------------------
    @staticmethod
    def calculate_expected_shortfall(simulated_returns: np.ndarray, percentile: float = 5) -> float:
        """
        Calculate Expected Shortfall (CVaR).
        Average of the worst X% of outcomes.
        """
        if simulated_returns is None or len(simulated_returns) == 0:
            return 0.0
        threshold = np.percentile(simulated_returns, percentile)
        tail = simulated_returns[simulated_returns <= threshold]
        return float(tail.mean()) if len(tail) else 0.0


# -----------------------------
# Walk-Forward Validator (unchanged from your original)
# -----------------------------
class WalkForwardValidator:
    """
    Walk-Forward Analysis for overfitting detection.
    Splits data into multiple train/test periods and compares
    in-sample vs out-of-sample performance.
    """

    def __init__(self, data_fetcher: DataFetcher, n_splits: int = 5):
        self.data_fetcher = data_fetcher
        self.n_splits = n_splits

    def run(
        self,
        strategy_class: type,
        strategy_params: dict,
        commission: float = 0.001,
        slippage: float = 0.0005
    ) -> Dict:
        prices = self.data_fetcher.close
        n = len(prices)
        split_size = n // self.n_splits

        in_sample_returns = []
        out_sample_returns = []
        in_sample_sharpes = []
        out_sample_sharpes = []

        print(f"\n📊 Walk-Forward Analysis ({self.n_splits} splits)")
        print("-" * 50)

        for i in range(self.n_splits - 1):
            is_start = 0
            is_end = (i + 1) * split_size
            os_start = is_end
            os_end = min((i + 2) * split_size, n)

            is_prices = prices.iloc[is_start:is_end]
            os_prices = prices.iloc[os_start:os_end]

            if len(is_prices) < 50 or len(os_prices) < 20:
                continue

            # In-sample
            is_strategy = strategy_class(is_prices, **strategy_params)
            is_engine = BacktestEngine(is_prices, commission=commission, slippage=slippage)
            is_result = is_engine.run(is_strategy)

            # Out-of-sample
            os_strategy = strategy_class(os_prices, **strategy_params)
            os_engine = BacktestEngine(os_prices, commission=commission, slippage=slippage)
            os_result = os_engine.run(os_strategy)

            in_sample_returns.append(is_result.total_return)
            out_sample_returns.append(os_result.total_return)
            in_sample_sharpes.append(is_result.sharpe_ratio)
            out_sample_sharpes.append(os_result.sharpe_ratio)

            print(f"  Split {i+1}: IS Return={is_result.total_return:+.2%}, "
                  f"OS Return={os_result.total_return:+.2%}")

        mean_is = float(np.mean(in_sample_returns)) if in_sample_returns else 0.0
        mean_os = float(np.mean(out_sample_returns)) if out_sample_returns else 0.0
        degradation = mean_is - mean_os
        degradation_ratio = degradation / abs(mean_is) if mean_is != 0 else 0.0

        print("-" * 50)
        print(f"  Mean In-Sample Return:     {mean_is:+.2%}")
        print(f"  Mean Out-of-Sample Return: {mean_os:+.2%}")
        print(f"  Performance Degradation:   {degradation:+.2%} ({degradation_ratio:.1%})")

        return {
            'in_sample_returns': in_sample_returns,
            'out_sample_returns': out_sample_returns,
            'in_sample_sharpes': in_sample_sharpes,
            'out_sample_sharpes': out_sample_sharpes,
            'mean_is_return': mean_is,
            'mean_os_return': mean_os,
            'degradation': degradation,
            'degradation_ratio': degradation_ratio,
            'is_overfit': degradation_ratio > 0.5
        }
