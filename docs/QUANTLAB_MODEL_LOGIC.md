# QuantLab model logic: from evidence to a consumer research view

## Executive statement

QuantLab is a research and decision-support system. It does not currently prove a
profitable trading edge, and it does not authorize or submit trades. A consumer
view may provide a clearly labeled research opinion such as *setup worth
investigating*, *risk is elevated*, or *reassess below this observed level*, but
those statements are not personalized financial advice, guaranteed exits, or
broker instructions.

The system becomes worth exposing to consumers only after it demonstrates
repeatable **after-cost** performance on untouched data, survives realistic
execution assumptions, and beats simple baselines without taking unacceptable
risk.

## The implemented mathematical pipeline

### 1. Point-in-time features

For an observation at time $t$, QuantLab constructs a feature vector using only
information known at $t$:

$$
\mathbf{x}_t = \left[
\frac{P_t}{P_{t-1}} - 1,
\frac{P_t}{P_{t-k}} - 1,
\frac{V_t}{\overline{V}_{t-k:t-1}},
\mathbf{1}_{\text{volume missing}}
\right].
$$

The future label is separate:

$$
 y_t = \frac{P_{t+h}}{P_t} - 1 - c,
$$

where $h$ is the forecast horizon and $c$ is the declared trading-cost
assumption. The future label is for training/evaluation only; it is never an
online feature.

Layman meaning: describe what the market looked like now, then later record what
actually happened after fees. Never let the later result leak into the earlier
decision.

### 2. Standardization and Ridge baseline

The baseline standardizes each training feature:

$$
 z_{ij} = \frac{x_{ij} - \mu_j}{\sigma_j}.
$$

Ridge regression estimates the coefficient vector:

$$
\hat{\mathbf{w}} = (Z^T Z + \alpha I)^{-1} Z^T\mathbf{y},
$$

and forecasts:

$$
\hat{y}_t = \hat{\beta}_0 + \mathbf{z}_t^T\hat{\mathbf{w}}.
$$

QuantLab currently fits this model independently inside chronological
walk-forward folds. It does **not** use `partial_fit`, online weight mutation,
or an undisclosed tensor optimizer.

Layman meaning: each feature gets a learned influence weight. Ridge regularizes
the weights so noisy features cannot dominate simply because they fit old data.
A positive forecast is not enough: it must exceed the declared minimum edge and
still work on later data.

### 3. Regime transition matrix

The regime baseline labels a historical close sequence as `QUIET`, `TRENDING`,
or `STRESS` using declared volatility and mean-return thresholds. It counts
transitions in a matrix $C$ and applies Laplace smoothing:

$$
P(s_{t+1}=j \mid s_t=i) =
\frac{C_{ij}+\alpha}{\sum_k(C_{ik}+\alpha)}.
$$

Layman meaning: the matrix answers, “When markets looked like this before, what
conditions tended to follow?” It describes context. It does not predict a price
direction or guarantee that history repeats.

### 4. Candidate entry plan

The live research signal checks freshness, spread, relative volume, momentum, and
optional verified event evidence. For an eligible long candidate:

$$
\text{stop} = \text{entry} - a\cdot ATR,
\qquad
\text{target} = \text{entry} + b\cdot ATR.
$$

For a short candidate the signs reverse. Position quantity is bounded by both
risk budget and notional cap:

$$
q = \min\left(\frac{R}{|\text{entry}-\text{stop}|},
              \frac{N_{max}}{\text{entry}}\right).
$$

The current implementation uses fixed policy values, not learned weights, and
returns a candidate plan only. The broker and consent layers remain separate.

Layman meaning: the system asks whether the market data is fresh enough, whether
the move is large enough, whether trading friction is tolerable, and how much
could be lost if the stop logic fails. It does not turn a signal into an order.

### 5. Historical outcome labels

For supervised research, each historical candidate is labeled by the first
barrier reached:

- `TARGET`: target was reached first.
- `STOP`: stop was reached first.
- `TIMEOUT`: neither barrier was reached before the horizon.

If one OHLC bar crosses both barriers, QuantLab labels `STOP` first because the
intrabar order is unknown and the conservative assumption avoids overstating
historical success. Round-trip costs are deducted from the return.

### 6. Scenario matrices

The stress module generates a matrix of hypothetical paths:

$$
S_{t+\Delta t} = S_t\exp\left[
(\mu - \tfrac12\sigma^2)\Delta t +
\sigma\sqrt{\Delta t}\,\epsilon_t
\right],
$$

with optional jump shocks. It reports target-first, stop-first, horizon-exit,
mean, tail, and worst-case scenario outcomes.

These are scenario assumptions, not estimated probabilities of future profit.
They omit real spread depth, latency, market impact, borrow, halts, and fill
availability.

## What “weights, matrices, and tensors” mean here

- **Weights:** Ridge coefficients that map standardized features to a forecast.
- **Matrices:** the training design matrix $Z$, the regularization matrix $I$,
  the regime transition counts, and simulated path matrices.
- **Tensors:** not currently a production QuantLab model. A future tensor could
  organize dimensions such as time × asset × feature × event, but adding a
  tensor model would not create an edge by itself.

Complexity is not a moat. A more complicated model is justified only when it
improves untouched walk-forward results after costs, remains calibrated, and
beats simpler baselines under the same information boundary.

## What could make the system profitable

No formula makes a trading system profitable automatically. The candidate edge
must survive this chain:

$$
\text{net expectancy} =
P(\text{win})\cdot\text{average win}
-
P(\text{loss})\cdot\text{average loss}
-
\text{fees}
-
\text{spread}
-
\text{slippage}
-
\text{market impact}.
$$

A credible release requires:

1. Point-in-time data and event timestamps.
2. Chronological walk-forward validation with untouched holdouts.
3. Comparison with buy-and-hold, index, momentum, and previous champion baselines.
4. Calibration, drawdown, turnover, tail loss, and regime breakdowns.
5. Executable replay using bid/ask, liquidity, halts, borrow, latency, and fees.
6. No survivorship, look-ahead, selection, or repeated-holdout tuning leakage.
7. A durable record of every monitored asset, rejection, missing feed, and signal.
8. Human review and a kill switch before any consumer-facing action path.

Until these are measured on real data, QuantLab must describe outputs as
research candidates and observations, not profitable trades.

## How the assistant should advise

The assistant can answer factual questions:

- observed high, low, close, return windows, and volatility;
- utility and research-universe metadata;
- recent verified news, filings, sources, publication times, and receipt times;
- what evidence supports or weakens a research thesis;
- scenario-based levels where a thesis might be reassessed.

It may also provide a **research view** such as:

> Observed momentum is positive, but the current evidence lacks verified spread,
> depth, borrow, fees, and broker preflight. This is a setup worth investigating,
> not a validated entry.

Every model-assisted response must include the heavy disclaimer: **not
personalized financial advice, not a buy/sell instruction, not a guarantee of
profit, and not an authorization to trade.** The model receives serialized
evidence only. It has no broker credentials, order tools, risk-limit mutation,
or execution authority. If evidence is missing, it must say that it is missing.

The deterministic fallback must remain available during model downtime. Kimi,
DeepSeek, or another OpenAI-compatible provider can be configured through the
read-only gateway, but provider choice is an engineering decision to validate
with latency, cost, groundedness, citation, refusal, and hallucination tests.

## From prior event-forecasting systems to markets

The transferable idea is not a secret formula. It is the discipline of turning
an event into a time-stamped probability or outcome record, separating features
known before the event from outcomes observed afterward, pricing uncertainty,
and evaluating decisions after costs.

QuantLab reverse-engineers that discipline into market data by replacing the
old event outcome with a forward return or barrier outcome, replacing context
features with point-in-time price/volume/news features, and replacing a simple
win/loss ledger with walk-forward net expectancy, drawdown, calibration, and
execution feasibility. The transfer is a hypothesis, not proof that an edge
transfers across domains.

## Expansion path

- **Shorts:** require borrow availability, locate status, margin rules, and
  asymmetric gap/recall risk.
- **Options/calls:** require an options-chain adapter, implied volatility,
  Greeks, spread/depth, expiration, assignment, exercise, and volatility-surface
  replay. Equity signals cannot be relabeled as call recommendations.
- **Day trading:** requires session calendars, latency, consolidated or clearly
  scoped feeds, intrabar replay, realistic fills, and strict loss controls.
- **Crypto:** requires venue-specific liquidity, 24/7 session logic, funding,
  custody, exchange outages, and independent venue reconciliation.
- **ETFs:** require creation/redemption, holdings, spread, premium/discount,
  liquidity, and tracking-error context.

Each expansion needs its own data contract, execution simulator, risk policy,
walk-forward benchmark, and release evidence. A chatbot can explain that work;
it cannot turn unproven research into a guaranteed profitable product.
