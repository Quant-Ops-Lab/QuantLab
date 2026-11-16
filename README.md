# QuantLab — research and runtime prototype

**New:** one long-running alert worker for Discord, Slack, encrypted SMTP, and
SMS through SNS or Twilio, with per-channel leases, deduplication and retries.
Added independent observed Markov regime baseline, stochastic stress scenarios,
conservative stop-first OHLC trade labeling, and offline `quantlab-stress` CLI.

No live provider alert or brokerage order has been sent. Results from scenario
simulations are not forward price predictions or proven trading edges.
See `docs/QUANT_GUILD_RESEARCH.md` for the reviewed Roman Paolucci sources.

## Quick use (research mode)

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev,console,postgres,stream,api,aws]'
pytest -q
quantlab-stress --entry 100 --stop 95 --target 110 --vol .45 --paths 2000
```

## Private alert destinations (disabled until configured)

Copy `.env.example` to `.env`. Choose `QUANTLAB_DISCORD_WEBHOOK_URL`,
`QUANTLAB_SLACK_WEBHOOK_URL`, encrypted SMTP `QUANTLAB_EMAIL_*`, or
`QUANTLAB_SMS_PROVIDER=sns|twilio` and corresponding numbers/credentials.
Source secrets from a private environment or secret store, never commit them.

```bash
# After exporting your private environment variables:
quantlab-notify --check
quantlab-notify --once
# Explicitly send provider test messages (SMS charges may apply):
quantlab-notify --send-test --confirm-send
# Continuous delivery (run under supervisor):
quantlab-notify --poll-seconds 5
```

Only verified-shape, recent, research-only trade candidate alerts are eligible;
the notifier does NOT approve orders, ingest market data or execute trades.
Closed browsers need the separate worker and persistent storage to receive
notifications. Provider acceptance is not confirmation of user delivery.

---

# QuantLab v0.5.0 — Market Command (source release)

A low-overhead market research and consent-controlled trading **prototype**.
The GUI now offers **Consumer** (brokerage-style) and **Admin** (research/operations)
views, plus **Deck / Standard / Terminal / Blackout** theme tokens inspired by
the user's NullPointVector design system.

**Live sources (not fabricated):** Kraken public OHLC for crypto (no key),
Kraken public WebSocket ticker adapter; Alpaca IEX bars/news snapshots and
live WebSockets when Alpaca keys are supplied; existing Public API quotes,
SEC EDGAR, and configurable RSS. The stock feed is IEX **single venue**,
not SIP. Absence/denial of data gives a visible unavailable state, not demo
prices. The prior synthetic preview remains isolated in the **Admin** terminal
for design testing only, never inference or order authorization.

**Interpreter:** ATR-based stop/target candidates; momentum, relative volume,
spread, freshness checks; original event topics classified without LLM tokens;
rumors and allegations held for verification. These are experimental rules,
**not backtested market-beating strategies**. A candidate is NOT an instruction
to trade. The native Public `BRACKET` payload can package take-profit and
stop-loss exits for whole-share equity entries; brackets can slip/gap and do
not guarantee a price.

**Consent:** Admin can create a strategy/account/notional/time-scoped grant.
`AuthorizedExecutor` wraps `ManagedExecutor` and rejects orders without
valid consent and broker risk checks. **It is not connected to a fully
validated unattended broker worker**. No real orders were submitted. Existing
Public API order-write scaffolding is not production-certified.

**Sound:** the Consumer Signals view checks the shared alert journal every
five seconds and plays a generated tone when a new candidate arrives. Browser
autoplay policies may require first clicking `Test audible alert`. With a
closed browser use external push (SNS/mobile) or OS notification process; a
web tab cannot emit sound while closed.

**Access:** Render web has a console passphrase and separate Admin password.
For real consumer accounts replace passphrase/session-based auth with OIDC,
server-managed sessions, per-account RBAC and audit logging. Never publish
broker API keys to the browser, GitHub or model prompts.

## Quickstart (macOS/Linux)

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev,console,postgres,stream,api,aws]'
pytest -q
cp -i .env.example .env
python -m streamlit run src/quantlab/console/app.py
```

`.env` must be a file, not a directory. If `mkdir .env` was run by mistake,
remove only that empty directory with `rmdir .env`, then run the `cp` command.
If package installation reports DNS or connection failures, restore network
access and rerun the install; `streamlit` and `pytest` are not available until
that install succeeds. The Streamlit command uses spaces, not comma-separated
arguments.

**Real crypto charts require no credentials.** They call the public Kraken
REST OHLC endpoint. Network access, data availability, rate limits and market
conditions can affect the result.

For US equity candlesticks and news, set `APCA_API_KEY_ID` and
`APCA_API_SECRET_KEY` in a private server environment, subject to the provider's
access plan. Then run the isolated services under a supervisor. Optional SEC
filing worker uses `quantlab-edgar` and a real `SEC_USER_AGENT`.

```bash
# Crypto remains active continuously.
quantlab-crypto
# Equity monitoring uses XNYS premarket, regular, and after-hours phases.
quantlab-equities
# Verified SEC and configured RSS ingestion stays active independently.
quantlab-edgar
# Scheduled EOD collection and opportunity autopsy.
quantlab-research
# Shared alert delivery with retry and lease state.
quantlab-notify
# Streamlit can be closed; workers keep running under a supervisor.
```

Start all local Docker services:

```bash
docker compose -f deploy/docker-compose.yml up --build -d
```

Render `render.yaml` is a blueprint **only**. Connecting a repository and
configuring paid services/secrets in Render is required; nothing is deployed
by including a blueprint. On Render set `QUANTLAB_ALERT_DB` to the shared
PostgreSQL DSN (the blueprint maps it automatically). Local development uses
`artifacts/alerts.jsonl` for simple single-host notifications. Never use the
local JSONL or SQLite order journal as a multi-replica production order bus.

### One-button operator grant (prototype)

In Consumer, navigate to signals and view candidate entry/stop/target details.
In Admin, set `QUANTLAB_ADMIN_PASSWORD` (16+ characters), open **Execution Consent**,
select one account + strategy + maximum order notional and duration, explicitly
consent, then click **Grant scoped permission**. This stores permission; it does
not automatically submit an order in v0.5. The execution adapter requires an
additional, independently verified account context and production single-writer
order manager to place real trades. Short selling additionally requires
margin/borrow approval from the chosen broker.

### The market does not run at one universal schedule

Crypto trades continuously, the US stock exchange's regular session is
weekdays 9:30 a.m.–4:00 p.m. ET (with differing extended-hours rules),
commodities futures follow their own calendars, and company filings/news
arrive around the clock. Process uptime can be 24/7 even while a venue is
closed. News is public information; unverified scandals are NOT treated as fact.

**X / Grok:** No free xAI developer API entitlement is assumed. The project
keeps X/Grok optional and disabled without valid credentials and budget.
The deterministic interpreter uses no LLM token calls. An LLM can eventually
explain evidence, never authoritatively set execution size or bypass risk.

**Production blockers:** real brokerage/price data integration test; account-
scoped leadership lease/transactional reservation; order reconciliation and
unknown-timeout recovery; stock corporate actions and tax-lot handling; short
borrow confirmations; auth/RBAC; model backtests with point-in-time data;
source verification; cost attribution; deployment credentials, security and
market-data licenses. **No validated edge and no live account connected.**

---

# Packaging hotfix v0.4.1

Package metadata corrected to `quantlab-research==0.4.1`. This does not add unimplemented live trading features.

# QuantLab v0.4 — candlestick-first operator terminal

**New:** Market Terminal homepage with Plotly candlesticks from stored quote snapshots (indicative, not official OHLCV), an explicitly marked synthetic design preview, AI/semiconductor thematic navigation, an Integrations panel that never exposes secrets, and passphrase authentication required by Render Blueprint.

The repository includes research and broker adapter scaffolding, but **real-money execution is NOT connected, certified or enabled**. No LLM has authority to submit orders. A push to GitHub does not automatically deploy Render.

# QuantLab v0.4 — private investment research, watch intelligence, broker contracts

QuantLab is an engineering project, **not a proven profitable trading system**. The
v0.4 release builds on v0.2 and includes 50+ curated stock/ETF research
candidates, SEC EDGAR monitoring, optional verified RSS feeds, Public API quotes,
positions harvest policy, an execution adapter with a non-mutating Public
preflight and durable order IDs, and a lightweight Streamlit console.

**All automated live orders remain unarmed.** There is no account connected or
validated, no broker-authenticated integration test, and no production order
reconciliation across workers. The order-write implementation is intended for
reviewed integration work; do not expose it through a public AI/HTTP endpoint.

## Architecture

```text
               Curated universe: AI chips / materials / metals / ETFs
                              |
           +------------------+--------------------+
           |                                       |
   SEC/RSS intelligence                         Public quotes
   publication + receive times                  bid/ask + timestamps
           |                                       |
   event dedup + classification             market quote journal
           +------------------+--------------------+
                              |
                   verified research signals
                              |
               market / model / position policy
                              |
                independent risk + order journal
                              |
             Public broker preflight + order API
                              |
                   order status + reconciliation

Streamlit UI <--> data store <--> event workers / SNS / MQTT subscribers
```

### What is working locally

- `src/quantlab/universe/catalog.py`: curated, theme-based security candidates.
- `src/quantlab/intelligence/edgar.py`: SEC submissions from verified CIKs.
- `src/quantlab/intelligence/news.py`: trusted RSS/Atom ingestion and read-only news-assessment interface (rule fallback; **no live LLM provider**).
- `src/quantlab/intelligence/pipeline.py`: deduplicated event pipeline.
- `src/quantlab/services/market_monitor.py`: real Public quote API polling and signal alerts on configured daily change thresholds; requires API credentials and access.
- `src/quantlab/portfolio/policy.py`: candidate partial trims and trailing exits, with core-sleeve preservation.
- `src/quantlab/execution/public_api.py`: authenticated read methods, preflight and order submission methods according to Public docs. Untested against a live account.
- `src/quantlab/execution/managed.py`: order ID and SQLite audit lifecycle, order-level preflight, risk constraints, and status reconciliation. **Not a full production OMS**.
- Prior v0.2 features: research walk-forward baseline, divergence, adversarial preserve/challenge agent evidence, SDK, notifications and Streamlit UI.

## Quickstart

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e '.[dev,console,api,aws]'
pytest -q
cp .env.example .env
streamlit run src/quantlab/console/app.py
```

### Live-data read services (still no orders)

Set `PUBLIC_API_TOKEN`, `PUBLIC_ACCOUNT_ID` in your shell/secret manager. For
EDGAR, use a real operator-contact email in `SEC_USER_AGENT`, never the example.

```bash
# Source secrets from an appropriate private environment, not from repo.
set -a; source .env; set +a
quantlab-edgar        # ~15min SEC poll, plus configured company RSS
quantlab-quotes       # Public quotes; monitor feed age and broker limits
```

Each service is a long-running process and belongs in its own container or
supervisor. Render `render.yaml` is a **deployment reference**, not a verified
running deployment. `deploy/docker-compose.yml` is for single-host development
using shared local state; never expose port 8501 publicly without an identity
proxy and HTTPS. It uses `../.env` and starts the UI and workers. Compose's
`restart: unless-stopped` restarts crashed processes but does **not** create
multi-host failover or restart unhealthy processes by itself.

### Market monitoring behavior

- Quote and SEC polling are independent.
- Company names/tickers are candidates; resolve symbol and instrument status at the broker.
- A 5% daily move sends a research alert, not a short/buy instruction.
- SEC filing descriptions are observations. Company split/M&A events need source
  document verification (a generic 8-K is not inherently a merger).
- Optional RSS sources must be explicitly added in `config/news_feeds.json`.
- SEC endpoints require identification and conservative API usage.
- Mutual funds and savings bonds are not intraday traded in the equity engine.

### Profit harvest example

At cost $100 and price $120, 10 shares have $200 **unrealized** gain.
Selling 25% of the position sells 2.5 shares with $300 gross proceeds and
approximately $50 realized gain before fees/taxes, assuming uniform cost basis.
You do **not** sell $200 of gain without reducing your position. A 30% trailing
decline from a $200 high-water mark triggers a candidate exit at $140, but a
real stop-market fill can be worse. Track lot-level basis, distributions,
corporate actions and highest observed prices before applying policies live.

### Execution path

`EquityOrder` supports BUY, SELL, SELL_SHORT, BUY_TO_COVER. `PublicBroker`
exposes `portfolio()`, `instrument()`, `quotes()`, `preflight()`,
`submit()`, `order_status()`. The `ManagedExecutor` requires explicit
`ExecutionPolicy(allow_live=True)` and a trusted, reconciled execution context.
It checks notionals, cash, borrow status (if short), risk stops and idempotent
order IDs before invoking broker preflight and eventual submit. Do not infer
borrow eligibility from a market signal. Public's short-selling feature
requires a margin-approved account and borrower availability.

The current order journal is SQLite/single-writer. Production needs a
transactional PostgreSQL order ledger, instrument/account validation within
the execution request, position/reservation management, unknown-timeout
recovery, trade confirmations, corporate-action adjustments and an operator
kill switch before any autonomous execution is activated.

### Deployment notes

- Local Docker: `docker compose -f deploy/docker-compose.yml up --build -d`
- Render: `render.yaml` describes UI + two workers + shared managed PostgreSQL,
  with auto-deploy disabled by default. Configure an identity layer (e.g.,
  Cloudflare Access), verify database persistence, and set protected secrets.
- AWS: optional SNS topic for outbound research alerts; v0.2 provides SQS and
  MQTT publisher interfaces, but no durable queue consumer is deployed yet.
- AI models are **research and explanation services**, not broker auth holders.
- See `docs/AI_DEV_CHECKPOINT.md` for exact feature status and rollback.

### GitHub

Canonical target: `Quant-Ops-Lab/QuantLab`; keep `EPdacoder05/Quant-lab`
independent. The other project repositories are sources of reusable design,
not submodules. No secrets or borrowed proprietary data should be committed.

## Release v0.4 / interface preview

- **Market Terminal (home):** watchlist symbol selection and candle chart. Source is stored Public API **quote snapshots**; this is indicative sampled-quote OHLC and must never be described as authoritative exchange trade OHLCV. Turn on **Synthetic design preview** for a clearly labeled, deterministic demonstration when no live quotes exist. This mode never feeds signals or orders.
- **Intelligence:** SEC / corporate-action events with publication and receipt timestamps and original-source links.
- **Universe:** AI chips, hardware/storage, cloud, materials/ceramics, precious metals, ETFs, defensive funds. Candidate list is not an order-eligible instrument list.
- **Portfolio Lab:** candidate harvest/trailing-exit simulation, not real orders.
- **Strategy Studio & Signals:** typed strategy JSON and rule-based research preflight (no live order).
- **Integrations:** Public, Webull, Alpaca, SEC, Grok/X, SNS, SQS, MQTT, PostgreSQL/Neon; environment detection is **configured/unverified**, not connected.
- **Operations:** audit events and deployment instructions.

### Run dashboard locally

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e '.[dev,console,postgres]'
pytest -q
streamlit run src/quantlab/console/app.py
```

### Protect external access

Any internet-accessible instance must set `QUANTLAB_REQUIRE_AUTH=1` and a unique 16+ character `QUANTLAB_CONSOLE_PASSWORD`, or run the service behind an access proxy with equivalent controls. The Render blueprint enforces the environment gate but **does not automatically deploy**, provision the requested services, or confirm your identity settings. Never commit tokens or passwords. Research-only until a broker API account, order reconciliation, and business constraints are independently verified.

### GitHub publishing

Canonical target: `Quant-Ops-Lab/QuantLab`. This snapshot was prepared locally; GitHub API writes may need a new connector installation with `Contents: Read and write` and organization repository access. Before deploying, check CI and review all changes. The platform is not connected to an active brokerage account.

---

## v0.7.0 — Opportunity Intelligence (retrospective, broad-market audit)

The prior curated watchlist alone could not identify unmonitored breakouts.
This release adds a separate EOD full-market audit, not an asserted trading edge:

- `quantlab-eod`: optional Massive grouped daily bulk-data pull (key needed).
- `quantlab-opportunity`: daily/weekly/monthly top-mover reports in JSON and Markdown.
- Point-in-time decision/watchlist joins; absent history is **UNKNOWN**, not a fake miss.
- Explicit corporate-action, missing-bar, liquidity and future-leakage warnings.
- Admin UI `Opportunity Intelligence` report viewer; no synthetic report fallback.

Read `docs/OPPORTUNITY_INTELLIGENCE.md` for setup, source limitations and the
separate requirements for an actual missed-executable-profit and alpha audit.

The code is implemented and unit-tested locally, but no live provider credentials,
production feeds or broker accounts were used in this release. No real trades
or hosted deployments were attempted.
