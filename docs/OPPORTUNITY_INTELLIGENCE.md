# QuantLab Opportunity Intelligence — v0.7

## Why this exists

Prior releases mostly monitor a curated universe and evaluate already-generated candidate signals. That cannot explain big moves in equities outside the watchlist, and it creates survivorship bias in the research record. This is not a solved alpha engine. The new *daily market autopsy* is the first concrete independent research loop.

A large realized return is NOT an actionable missed opportunity. Every purported miss needs evidence available before the move, a tradeable execution point, a broker-eligible instrument and measured after-cost results.

## Data ingestion: a low-cost broad-market path

Massive's grouped U.S. stock OHLC daily aggregate returns the entire listed U.S. equity market for one date in one request (subject to plan limits). Stocks Basic includes end-of-day historical data, but yesterday's data is generally accessible after midnight Eastern on the next calendar day. It is **not an intraday live-all-market feed**. Source: https://massive.com/docs/rest/stocks/overview and https://massive.com/knowledge-base/article/on-the-free-basic-plan-when-can-i-pull-the-previous-trading-days-data .

For your operator Mac, after obtaining a personal Massive API key:

```bash
export MASSIVE_API_KEY='...from private shell or secret manager...'
# One-time backfill, 6–10 weeks of calendar days. Default 13-second call pacing.
quantlab-eod --start 2026-09-15 --end 2026-11-13 \
  --output artifacts/opportunity/daily_bars.csv
# Once enough sessions exist:
quantlab-opportunity --bars artifacts/opportunity/daily_bars.csv \
  --decisions artifacts/opportunity/decisions.jsonl \
  --coverage artifacts/opportunity/watchlist_history.jsonl \
  --output artifacts/opportunity
```

If no decision ledger or historical watchlist snapshots exist, OMIT those flags. The report will still rank movers, but mark `COVERAGE_UNKNOWN`. **Never create fake historic decisions to make the report look complete.**

Daily refresh (after data release) can call `quantlab-eod` for the latest eligible trading day, then `quantlab-opportunity`. Schedule using cron/systemd/Render Cron. This is **not automatically scheduled or deployed in the supplied release.** An always-running low-latency streaming worker remains a different service.

The CLI accepts any user-provided CSV with `symbol,session,close,volume,market,adjusted_close,source`; for non-U.S.-equities and crypto ingestion this permits a normalizing adapter. Valid markets: `equity`, `crypto`. `adjusted_close` is optional and null for raw prices. The engine does not invent data when a provider is absent. Existing Kraken public crypto OHLC can supply a later normalized crypto adapter; this version's broad-market collector is equities only.

## Ranking definitions

- Equities: 1, 5, 21 observed trading sessions, provided the exact start and end session have prices.
- Crypto: 1, 7, 30 calendar-day periods (assuming daily observations).
- Rank by historical percentage return, **not claimed attainable profit**.
- Show liquidity proxy (`last close × reported daily share volume`), but this is NOT order-book depth.
- Missing start bars are explicitly excluded and counted. Unadjusted equity moves over 25% are flagged for corporate-action inspection.
- Use `adjusted_close` when available. EOD adjusted close is useful for retrospective comparisons, but a proper live replay must use historically available corporate-action revisions and real-time quotes.

## Point-in-time decision and coverage contracts

`decisions.jsonl` example:

```json
{"symbol":"NVDA","decision_at":"2026-11-12T20:00:00Z","decision":"REJECT","strategy":"ridge_baseline_v3","reason":"Estimated net edge below threshold"}
```

`watchlist_history.jsonl` example:

```json
{"symbol":"NVDA","asof":"2026-11-11T21:00:00Z","monitored":true}
```

Use genuine historical logs captured by the deployed watcher, NOT retrospective reconstructions. The report determines whether the latest timely record was ENTER, REJECT, WATCH, or EXIT. An entry made after the start boundary is marked `LATE_DETECTION`, never credited as a successful pre-move forecast. A missing ledger means `COVERAGE_UNKNOWN`, not "the model missed it." The classification cannot prove an executable trade or a profitable fill.

## What's next before it becomes an alpha feedback loop

1. **Security master:** split and symbol-change history, delistings, exchange/OTC filter, trade-halt detection, point-in-time listings; do not survivorship-filter today's winners backward.
2. **Coverage ledger:** every observed symbol and decision timestamp committed in a durable database, including rejections and stale feeds. Log why something was ignored *before* it moves.
3. **Event attribution:** immutable publication time and receipt time for earnings, 8-Ks, merger news, social posts; distinguish actual material news from explanations invented after a move.
4. **Ex-ante replay:** sample news and market data as-of each potential decision time; include bid/ask spread, realistic slippage and minimum market depth. Compare baseline signals and models with walk-forward holdouts. Include *no-trade* and cheap index/passive benchmarks.
5. **Counterfactual outcomes:** replay only opportunities the strategy could actually have entered, assigning conservative stop-first labels when intra-bar ordering is unknown.
6. **Alpha attribution:** false negatives, false positives, missed-entry time, capture fraction of feasible upside, realized net P&L, drawdown, and whether added features improve performance out of sample.
7. **Coverage-gap alerts:** identify repeated movers outside the current watchlist and automatically propose *research* universe expansion. Never automatically enable live trading of a newly discovered ticker.

## Deployment caveats

`QuantLab/` is a source package; `quantlab-opportunity` creates the audit locally. The new report UI is in the **Admin → Opportunity Intelligence** navigation. There is no remote deployment or automatic email/Discord distribution in v0.7, and an API key must be configured before real U.S. breadth data can be obtained.
