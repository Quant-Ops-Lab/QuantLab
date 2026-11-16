# Deployment plan — QuantLab v0.3

## Recommendation: Docker image + Render managed services initially

- `quantlab-command`: Render web service, Streamlit UI. **Do not publish a
  naked dashboard**; authenticate via Cloudflare Access or another trusted
  identity proxy. Render handles TLS but it is not a substitute for user auth.
- `quantlab-edgar`: Render background worker; polls verified SEC CIK submissions
  and optionally preapproved company IR RSS feeds. Interval 15 minutes.
- `quantlab-quotes`: Render background worker; polls Public in batches; records
  quotes in managed PostgreSQL. API keys only in service secrets.
- PostgreSQL: managed shared store. v0.3 has Postgres paths for event and market
  quote journals; it does not have a Postgres-backed live OMS.
- SNS: optional research alerts; SQS/MQTT adapters exist but are not consumers.

Cost drivers: three paid services, managed PostgreSQL compute/storage,
network fees, LLM provider consumption, and market data subscription terms.
An always-on cloud deployment is not "free". Render Docker services are
separately billed; get a live quote at deployment time.

## Production acceptance checklist

1. Verify per-service image build, health, logs, restart behavior, and timeouts.
2. Configure verified custom domain and identity proxy BEFORE enabling public URL.
3. Test managed Postgres persistence across worker restart and deploy.
4. Verify a full day of SEC feed and Public quote observations with timestamps.
5. Confirm quote freshness, rate limits, delayed/out-of-hours treatment, and fees.
6. Add migration tooling and operational backups/retention to database.
7. Prove SNS event delivery; add SQS DLQ when consuming events for decisions.
8. Validate model on point-in-time history net of realistic costs.
9. Implement production order ledger and reconcile broker position, cash,
   borrow approval, outstanding orders, and partial fills before auto trading.
10. Prove kill switch, no duplicate orders, stale-data shutdown, broker outage,
    clock skew, and disaster recovery before live deployment.

## Self-host alternative

`deploy/docker-compose.yml` mounts a single shared local volume. Use a VPN or
loopback port bind; add healthchecks, log rotation, backups, supervised process
restarts and power/internet redundancy. A home PC cannot match managed uptime
without redundant connectivity and hardware. Do not directly expose API keys,
Streamlit, MQTT brokers or management ports.

## Live brokerage cautions

Public's order API is asynchronous. A successful POST is **acknowledged**, not
FILLED. The order UUID must be preserved across ambiguous network failures;
never invent a new UUID and submit again after a timeout. Account margin and
short eligibility must be verified with Public in live account context.


## v0.4 operator dashboard release

- Set `QUANTLAB_REQUIRE_AUTH=1` and a strong, unique `QUANTLAB_CONSOLE_PASSWORD` (min 16 chars). This Streamlit passphrase is an MVP gate, not a replacement for identity-aware perimeter access (Cloudflare Access, VPN).
- Render uses PostgreSQL connection via `QUANTLAB_EVENT_DB` and `QUANTLAB_MARKET_DB`; Docker image installs the `postgres` optional dependency.
- Only a linked Render Blueprint deployment creates public services. Pushing `render.yaml` to GitHub alone does **not** deploy.
- Market Terminal uses Plotly on observed quote samples; 1m/5m OHLC is indicative (no volume and no officially reconstructed exchange OHLC). Do not feed synthetic UI preview candles into models.
- Do not store brokerage keys in Streamlit widgets, code or public repository. Use Render secret env vars.
- To roll back, pin and redeploy the previous container/git SHA.
