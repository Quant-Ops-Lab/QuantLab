## v0.4.1 packaging correction — 2026-11-12

- Corrected `pyproject.toml` package metadata from 0.3.0 to 0.4.1, addressing misleading installed version report.
- GitHub not updated; local ZIP release.
- Upgrade with `pip install --upgrade -e ".[dev,console,postgres]"` after extracting the ZIP to a new working directory.

# Release checkpoint — v0.4 (2026-11-12)

- Baseline source: user-provided QuantLab v0.3 ZIP; existing repo content was empty when last inspected.
- UI: `src/quantlab/console/app.py` rewritten as candlestick-first Streamlit operator terminal.
- Charts: `console/charts.py` aggregates real, timestamped **quote samples**; no invented high/low beyond samples. Synthetic preview is deterministically generated and conspicuously labeled. No traded-volume data is invented.
- Connectors: `console/integrations.py` lists environment configuration, **not verified connectivity**; never prints secrets.
- Quote history: `QuoteJournal.history` added. Auth gate required on Render via `QUANTLAB_REQUIRE_AUTH=1` and `QUANTLAB_CONSOLE_PASSWORD`.
- Live broker execution remains unarmed and untested; no automation or broker submits run in this release.
- Rollback: pin a known Git commit; `git revert <commit>` or redeploy previous Render revision. Keep prior v0.3 ZIP available.
- Test command: `python -m pytest -q`; test the UI manually with `streamlit run src/quantlab/console/app.py`.

---

# QuantLab — AI Dev Checkpoint

_Last updated 2026-11-12. Status: local bootstrap artifact only; not deployed._

## LOCKS

- Core repo target: `Quant-Ops-Lab/QuantLab` after GitHub installation grants access.
- Keep `EPdacoder05/algorithmic-data-pipeline` intact and separate; reuse concepts.
- Do not add broker write credentials, market orders, leverage, or options in v0.1.
- Do not claim a profitable edge from synthetic or historical data without a real
  point-in-time, out-of-sample, cost-aware evaluation.
- Two agents must receive the identical immutable evidence packet after every
  result; agent outputs are *candidate suggestions*, not deployment authority.
- Risk checks are deterministic, fail-closed, and independent from ML/LLMs.

## SOURCE HEADS (audit anchors)

- Sports engine main: `0f19397b94a1f6bf7de632b0c5c3b34c5c23f556`
- NullPoint main: `60d02d5e7b5f0dec297c038828602df8bdbae76f`
- QuantLab GitHub target heads: UNKNOWN (GitHub connector returned 404)

## VERIFIED IN BOOTSTRAP

- Point-in-time lagged features and forward labels on completed horizons
- Chronological fold generator with configurable gap
- Standardized Ridge research baseline
- Observed positioning/price divergence flag (NO TRADE ACTION)
- Dual-agent identical-evidence protocol with immutable JSON hashes
- SQLite journal with hash-chain integrity checks for review proposals
- Challenger evaluation gate returning recommendations, never deployment
- A preflight risk gate rejecting stale data, insufficient settled cash,
  duplicate IDs, drawdown breaches and disabled trading
- Read-only broker contract; no live execution implementation
- Reproducible synthetic example and unit tests

## NOT YET VERIFIED / OPEN

- Market feed, corporate-action handling, SEC/FRED/X ingestion, news timestamps
- Brokerage authentication, read-only account access, settled-funds reconciliation
- Empirical backtest and real trade performance
- Risk reservations/partial fills, durable multi-process order idempotency
- Real LLM API calls: experiment supports prompt generation/recording only
- CI result on GitHub, protection rules and deploy state

## LOCAL VERIFICATION RESULTS (2026-11-12)

- `PYTHONPATH=src pytest -q`: 20 tests passed.
- `PYTHONPATH=src python -m quantlab.demo`: 3 synthetic walk-forward folds; zero orders.
- These do **not** represent real market validation or broker/API integration.

## EXACT LOCAL VERIFY

```bash
pip install -e '.[dev]'
pytest -q
quantlab-demo
```

## RELEASE/ROLLBACK

1. Preserve GitHub main; develop in `feature/quantlab-bootstrap` and review PR.
2. Pin strategy/model artifact SHA and requirements lockfile before deployment.
3. Persist champion/previous champion with hash and evaluation manifest.
4. Revert the PR merge to restore previous code; no production order path exists.
5. Any future live deployment requires separately revocable credentials,
   exposure kill switch, and a broker-position reconciliation playbook.

## NEXT TASK

Grant the GitHub integration access to `Quant-Ops-Lab/QuantLab`, then upload
this bootstrap onto a feature branch; run CI and submit a reviewable PR. Do not
blindly overwrite existing repository content.

## v0.2 increment — operator shell / 2026-11-12

Build directory: `quantlab-v0.2` (copy of v0.1 with changes). This is not a
committed or deployed GitHub release. Nothing changed in external repos.

- Strict typed `StrategySpec` JSON config; `Mode.LIVE_BOUNDED` rejects.
- `quantlabctl draft/check/run` CLI. Operator-input `run` is deliberately
  rejected as actionable feed input; it never submits orders.
- `MarketWorker` has injected `VerifiedFeed` interface; no provider connected.
- `QuantLabClient` handles research-only alert routing.
- Local JSONL events and optional SNS/SQS/MQTT outbound publishers. No SQS
  consumer, continuously hosted queue, or guarantee of exactly-once delivery.
- Optional Streamlit neon command center and authenticated FastAPI validation
  shell; no brokerage keys, no external LLM call, no order-write methods.
- Current signal threshold is a rule demonstration, NOT a validated ML edge.

## v0.2 release verification and rollback

Run `PYTHONPATH=src pytest -q` (see results in release notes). If reviewed
later in the org repo, merge only via feature PR. To revert v0.2 to v0.1,
restore the v0.1 ZIP; there is no database migration or live order state.
The strategy SHA is a config hash, not a signed production deployment token.

- Read-only provider-agnostic LLM explanation and strategy draft ports added;
  no model API provider or invocation tokens configured.

## v0.3 increment — 2026-11-12

- Canonical repo: `Quant-Ops-Lab/QuantLab`. The connector now CAN resolve both
  org and personal QuantLab repos; both reported size=0 before this local build.
- No GitHub writes, brokerage orders, broker authentication or Render deploys
  were performed during this local build.
- New curated theme research universe. Listings are unverified candidates.
- New SEC submissions poller using official CIK mapping; data time zone and
  publication/receipt timestamps retained. This does not parse complete 8-Ks.
- Optional whitelisted RSS/Atom feeds with explicit linked symbols, no trade
  authority; no external LLM provider wired.
- New idempotent event and quote journals: SQLite on one host or optional
  PostgreSQL for shared services. Postgres paths are implemented but not
  integration-tested against an actual Postgres server.
- Public API supports quotes, portfolio, instrument, preflight, submit, and
  order status; methods are only mock-tested. No live credentials supplied.
- Position policy: trim tactical sleeve at profit threshold, protect designated
  core, candidate exit on trailing decline from high-water mark.
- Execution adapter includes order UUIDs and state transitions, fail-closed
  risk checks, cash/margin constraints, broker preflight. Not production OMS.
- Notification fanout for SEC and quote alerts to JSONL and optional SNS.
- Render YAML, Dockerfile and localhost-bound Docker Compose development stack.
- Streamlit: thematic universe, SEC events, portfolio policy sandbox.

### Outstanding critical items before autonomous live execution

1. Account-verified preflight context derived from Public rather than supplied
   caller context; hard-to-borrow locates and expense checks.
2. Postgres order journal with atomic cash/position reservations and single
   account-scoped executor lease; reconcile outstanding and partial fills.
3. Market calendar and corporate action/split adjustment of inventory.
4. Live feature/strategy signals from verified quotes, not only 5% move alerts.
5. Production identity layer for command console; secure secret rotation.
6. Real historical trading study, cost model, regime testing and independent
   champion promotion.
7. Cloud deployment verification, secrets and public domain. None performed.

### Rollback

Existing v0.2 ZIP remains the last prior runnable local artifact. No migrations
are applied externally. Before pushing to GitHub, create the feature branch,
review the source and deploy diff, and pin a commit SHA. On a future live system,
rolling code back must NOT blindly roll back broker positions.


## 2026-11-12 — v0.5.0 implementation handoff

- Based on v0.4.1 working tree, retained existing project modules and tests.
- Added `console/consumer.py`: true Kraken public crypto OHLC, Alpaca IEX real exchange bars and news, portfolio empty state, alert journal with sound.
- Added `console/theme.py`: four consistent NullPoint-inspired palettes and CSS tokens.
- Added `console/alerts.py`: original locally synthesized short alert sound.
- Added `market/{kraken_rest,kraken,alpaca_stream}.py`: read-only market data and streaming adapters.
- Added `services/{daemon,stock_stream,entry_worker}.py`: continuous research workers; no broker order writes.
- Added `intelligence/context.py`: public-event topics and provenance/rumor treatment.
- Added `signals/entry.py`: timestamped deterministic trade candidates with stop and target.
- Added `execution/consent.py`: scoped time-limited consent and executor wrapper.
- Updated Public `EquityOrder` with optional **whole-share** native BRACKET orders; verify status with the broker, do not assume submission == fill.
- Added `control/alert_store.py`: shared PostgreSQL/SQLite alert journal for web/worker separation.
- Docker and Render service references extended. Nothing remotely deployed.
- **Tests**: `PYTHONPATH=src pytest -q` => 81 passed at authoring time (run again after edits).
- **GitHub**: `Quant-Ops-Lab/QuantLab` is readable but GitHub App create-blob (non-mutating capability test) returned 403. No repo push.
- **Rollback**: retain `QuantLab_v0.4.1_Candlestick_Command_FIXED.zip`; do NOT overwrite existing local deployments. To roll back, stop v0.5 workers, restart the previous tested container image/commit, and preserve PostgreSQL/SQLite backup. New v0.5 consent/alert journals are additive, not required by v0.4.1.
- **Do not misstate**: Streamlit interface has not been browser-tested here; Public live order path has not been verified against a production account; no real trades placed; market data access not verified in this offline build container.
- **Next**: integration tests with actual provider credentials; broker order event WebSocket + REST reconciliation, authenticated role management, safe pre-funded order management; walk-forward evidence that signals outperform baselines after costs.

## 2026-11-12 — v0.6.0 notification + Quant Guild research handoff

- New `delivery/channels.py`, `delivery/dispatcher.py`, and
  `services/alert_dispatcher.py` provide Discord/Slack/SNS/Twilio/SMTP research
  alerts using per-channel leases, retry and deduplication; a deliberate
  `--send-test --confirm-send` trigger is required to send test messages.
- New `research/regimes.py`, `research/stochastic.py`,
  `research/triple_barrier.py`, and `research/stress_cli.py` add original,
  NumPy-only stochastic scenario and historical label research utilities.
- They are **not linked to order submission or model promotion**. A simulated
  win fraction is never broker execution evidence or predicted profitability.
- `docs/QUANT_GUILD_RESEARCH.md` records links and reviewed source scope.
- All tests are local; no live Discord/SMS/email/Slack provider interaction,
  IBKR data, brokerage orders, GitHub write, or Render deployment occurred.
- Rollback: stop both alert producer and notifier, preserve delivery ledger and
  provider delivery history (avoid duplicate messages), retain order state,
  and restart prior tested version. Never blindly revert broker positions.
- Packaging smoke-test correction: the notifier now creates the missing local
  SQLite `artifacts/` parent directory on first launch. Verified from a clean
  checkout with `quantlab-notify --check` returning zero configured channels.
- Final local test count after this fix: 103 passed.

## v0.7.0 — November 16, 2026 — Opportunity Intelligence

- Base: QuantLab v0.6.0 notification/Quant Guild research source ZIP.
- Added `research/opportunity.py` and CLI; `market/massive_eod.py` optional historical bulk data collector.
- Added Admin `Opportunity Intelligence` report page, with explicit no-report warning rather than fabricated data.
- Added tests for 1/5/21 equity windows, 1/7/30 crypto windows, historical reject vs late signal, no-coverage handling, adjustment issues, and bulk data adapter schema/deduplication.
- Activation: offline only. `quantlab-eod` requires provider key and is not a live-feed or trading component.
- Unimplemented: daily scheduler, crypto-breadth collector, automatic alert delivery, raw data provenance/contract manifest, security master, corporate-action reconciliation, point-in-time full universe capture and true counterfactual fills.
- Rollback: retain earlier v0.6.0 ZIP; replace v0.7 extracted project with clean v0.6.0 source. No DB migration or brokerage state touched.
