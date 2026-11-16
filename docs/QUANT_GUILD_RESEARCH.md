# Quant Guild / Gaussian Cookbook: audit and QuantLab mapping (2026-11-12)

This is a research map, **not** a claim to have completed the 14 videos or
proven an edge. We reviewed the public YouTube descriptions and chapter guides,
plus repository trees and selected source files. Original source code is NOT
vendored into QuantLab; new modules are independent implementations.

## Verified references

- Gaussian Cookbook: https://github.com/romanmichaelpaolucci/GaussianCookbook
  - Brownian motion, bridge, fBM notebooks, and Volterra material.
  - Use in **scenario generation / tail-risk stress tests**, not price forecasting.
- Q-Fin: https://github.com/romanmichaelpaolucci/Q-Fin
  - `QFin/simulations.py`: GBM, stochastic variance, option Monte Carlo routines.
  - `QFin/stochastics.py`: pricing/model interfaces.
  - Borrow ideas only; no unreviewed dependency or code copy.
- Quant Guild Library: https://github.com/romanmichaelpaolucci/Quant-Guild-Library
  - Broad notebook collection for tails, Sharpe pitfalls, portfolio risk, and returns.
- Regime switching bot Part 1: https://www.youtube.com/watch?v=GZnCiXMNZcQ
  - Live streaming prices, OHLC bars, Markov regime class, dashboard with IBKR.
- Earnings event dashboard: https://www.youtube.com/watch?v=Xtth2F1xm5Q
  - Earnings implied volatility crush and event-window visualization.
- AI stock trading bot with IBKR: https://www.youtube.com/watch?v=ogZmSXD_56U
  - Portfolio VaR/CVaR, persistent thesis memory, integration of agent + TWS.
  - QuantLab should **not** grant LLM direct order authority as shown in the video.
- Live volatility surface: https://www.youtube.com/watch?v=5JEeAsQqlro
  - Strike/maturity implied-volatility interpolation (requires options chain data).
- When-to-stop notebook: https://github.com/romanmichaelpaolucci/When-To-Stop-Trading-Profitable-Strategies
  - Research candidate for trade-stop / strategy quarantine criteria.

## Implementation now

1. `research/regimes.py` uses fixed thresholds and observed lagged returns to
   characterize QUIET / TRENDING / STRESS states and estimate Laplace-smoothed
   transition probabilities. **Not an HMM**, not directional predictions.
2. `research/stochastic.py` produces deterministic GBM-with-optional-jumps
   price-path scenarios and stop/target first-touch counts, cost adjustment,
   and expected shortfall (CVaR of the worst 5% of simulated net returns).
3. `research/triple_barrier.py` labels historical hypothetical trade outcomes
   TARGET / STOP / TIMEOUT. When stop and target are touched in the same OHLC
   interval, it conservatively records STOP and marks the ambiguity. Gapped
   opens can fill worse than the stop. Future labels are **not online features**.
4. `quantlab-stress` runs offline hypothetical scenarios with no network,
   brokerage access, LLM, or automatically generated trades.
5. Existing v0.6 code provides SMS/Discord/Slack/email **candidate alerts**
   with per-channel deduplication, retry and no password/number logging.

## Explicit limitations

- Gaussian assumptions miss volatility clustering, heavy tails and structural
  breaks unless calibrated and stress-tested appropriately; jump probabilities
  are *user assumptions*, not derived from data.
- Markov transition counts do not identify the source of a profitable signal.
- A target-first simulation probability is **not** an observed win rate.
- Stress analysis is not a broker fill simulator. It does not model real market
  depth, latency, queue position, borrow costs, trading halts or all fees.
- No broker orders, live SMS, Discord, email, or Slack messages were sent from
  the test environment.
- IBKR APIs generally require relevant market-data subscriptions and an active
  authenticated brokerage session. It remains an optional future adapter.

## Recommended integration order

- Label observed historical candidates with triple barriers + explicit costs.
- Compare no-trade, logistic regression meta-gate, ridge, and combined model
  under *purged* chronological walk-forward validation.
- Stratify metrics by observed regimes; quarantine failures instead of boosting
  model confidence automatically.
- Compare actual out-of-sample drawdowns to **plausible** GBM/jump stress
  scenarios, then improve them with block-bootstrap and empirical fat-tail paths.
- Add earnings, positioning, options IV and cross-asset covariates only after
  timestamp/source verification; include ablation studies for every feature.
- Extend IBKR options/volatility surfaces only when subscriptions, permissions,
  development and maintenance costs are justified by measured improvement.
