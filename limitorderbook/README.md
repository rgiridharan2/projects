# Limit Order Book: Signal Research & Optimal Execution

A self-contained research platform for microstructure alpha discovery. Reconstructs a limit order book from message-level data, engineers short-horizon predictive signals, validates them with autocorrelation-aware statistics, backtests a cost-aware strategy, and generates Almgren-Chriss optimal liquidation schedules.

Everything runs from a single file (`orderbook_core.py`) with no external data dependencies -- a synthetic data generator produces LOBSTER-format messages with realistic microstructure properties (autocorrelated order flow, informed trading episodes, mean-reverting spreads, trade impact).

## What it does

The pipeline runs six steps end-to-end:

1. Generate or load LOBSTER-format message data (50,000 messages, ~250 seconds of book activity).
2. Reconstruct the order book and extract snapshots every 10 messages.
3. Compute five signal families at each snapshot: Kalman-filtered OFI, delta OFI, trade imbalance, spread pressure, and a weighted composite.
4. Measure predictive power across horizons (100ms to 5s), then run Fisher-z tests with Newey-West effective-n adjustment, circular block bootstraps, and Benjamini-Hochberg correction across all horizon/signal pairs.
5. Backtest a threshold-based strategy with explicit transaction costs (1 bps round-trip), auto-inversion detection, and a 30% calibration holdout.
6. Compute Almgren-Chriss optimal execution trajectories and an efficient frontier across risk-aversion levels.

Unit tests and a throughput benchmark (~27,000 msg/s on synthetic data) run before the main analysis.

## Output

Running `python orderbook_core.py` produces five plots and a console report:

| File | Contents |
|------|----------|
| `signal_analysis.png` | OFI time series, correlation by horizon, directional accuracy, signal distribution, signal-vs-price scatter |
| `backtest_results.png` | Cumulative PnL curve, per-trade PnL histogram, return-vs-holding-time scatter, performance summary |
| `orderbook_snapshot.png` | Bid/ask depth at the midpoint of the simulation |
| `optimal_execution.png` | Almgren-Chriss efficient frontier, liquidation trajectories for several lambda values, execution rate schedules |
| `kalman_analysis.png` | Riccati recursion convergence, Kalman gain sensitivity to Q/R ratio, innovation autocorrelation diagnostics |

### Sample results (synthetic data, seed=42)

OFI predictive power:

| Horizon | Correlation | Hit rate |
|---------|-------------|----------|
| 100 ms  | 0.191       | 47.7%    |
| 500 ms  | 0.221       | 57.0%    |
| 1000 ms | 0.238       | 58.1%    |
| 5000 ms | 0.236       | 60.6%    |

Trade imbalance showed the strongest raw correlation (0.49 at 500ms) but decayed sharply and inverted by 5s. The composite signal balanced persistence and magnitude.

Best backtest configuration: OFI signal, threshold=0.5, 1000ms hold, auto-inverted. 51 trades, 94.1% win rate, $26.64 total PnL, 1.616 per-trade Sharpe, $0.32 max drawdown.

## Components

**OrderBook** -- Dict-backed book with sorted price lists. Handles LOBSTER event types 1-7 (new limit, cancel, delete, visible/hidden execution, cross trade, halt). Includes an `_uncross_book` guard.

**KalmanFilter** -- 1D random-walk state model. Used to denoise the raw OFI signal. Q/R = 0.10 (configurable).

**KalmanConvergenceAnalyzer** -- Solves the scalar DARE analytically (closed-form P_inf), verifies convergence numerically, estimates geometric contraction rate, and runs innovation consistency tests (zero-mean t-test, Ljung-Box whiteness, normalized innovation squared).

**SignalGenerator** -- Computes OFI (multi-level imbalance, Kalman-filtered), delta OFI (change in imbalance), trade imbalance (signed execution pressure over a rolling window), spread pressure (z-scored spread), and a heuristic composite (0.4 delta_OFI + 0.4 trade_imbalance + 0.2 inverted spread_pressure).

**PredictiveAnalyzer** -- Forward-return calculation at arbitrary horizons, correlation/hit-rate/quintile-spread analysis, and signal decay curves.

**SignalSignificanceTester** -- Fisher-z test with Newey-West autocorrelation adjustment for effective sample size. Circular block bootstrap (Politis & Romano, 1992) for non-parametric p-values. Benjamini-Hochberg, Bonferroni, and Holm corrections for multiple testing across horizons.

**SignalBacktester** -- Z-score threshold entry, signal-mean-reversion exit or max-hold timeout. Auto-inversion uses a 30% calibration window to detect whether the signal predicts returns directly or inversely. Explicit per-trade transaction cost deduction.

**OptimalExecutionScheduler** -- Almgren-Chriss (2001) linear-impact model. Computes optimal trajectories via the sinh formula, generates efficient frontiers (expected cost vs. std of cost), and compares optimal, TWAP, immediate, and VWAP-proxy strategies.

**RegimeDetector** -- Rolling volatility tercile classification (low/medium/high). Breaks down backtest performance by regime.

**LOBSTERDataLoader** -- Parses real LOBSTER message/orderbook CSVs. Also includes the synthetic data generator used for the demo run.

## Requirements

```
numpy
pandas
numba
scipy
matplotlib
```

No market data subscription needed for the demo. To use real data, provide LOBSTER-format message and orderbook files and swap `LOBSTERDataLoader.create_synthetic_data()` for `LOBSTERDataLoader.load_message_file()`.

## Usage

```bash
python orderbook_core.py
```

This runs unit tests, a throughput benchmark, and the full analysis pipeline. All five plots are saved to the working directory.

## Limitations and caveats

The synthetic data generator is tuned to produce detectable signals. Real LOBSTER data will likely show weaker correlations, and the backtest PnL numbers should not be taken at face value -- they exist to exercise the pipeline, not to demonstrate a tradeable edge.

The backtester does not model queue position, partial fills, or latency. Transaction costs are applied as a flat basis-point charge, which understates costs for large orders in thin books. The Almgren-Chriss implementation uses the standard linear permanent/temporary impact model and does not account for non-linear impact or time-varying liquidity.

The monolithic file structure was a deliberate choice for portability (single file, no package installation beyond pip dependencies), but it makes the codebase harder to extend. A natural next step would be splitting it into modules.
