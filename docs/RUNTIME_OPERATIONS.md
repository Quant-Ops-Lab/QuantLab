# Runtime worker model

Production deployment uses independent restartable processes. `quantlab-live`
remains a local-development supervisor only.

- **Crypto (`quantlab-crypto`):** runs continuously because the configured
  crypto venues operate continuously. Poll failures restart the crypto worker
  with bounded backoff.
- **Intelligence (`quantlab-edgar`):** runs continuously for SEC filings and
  configured trusted feeds. It is not stopped at the equity close.
- **Equities (`quantlab-equities`):** uses the XNYS calendar and exposes four
  phases: premarket 04:00–09:30, regular session, after-hours through 20:00,
  and overnight. Monitoring can continue in premarket and after-hours, while
  order eligibility is separately limited to the regular session unless a
  broker capability explicitly supports extended hours.
- **Research (`quantlab-research`):** runs the EOD collection and opportunity
  autopsy at 01:30 America/New_York, after the free EOD provider release window.
- **Notifier:** remains a separate delivery process with retry and lease state.

The workers publish research candidates only. They do not submit brokerage
orders. A worker restart is not a trade retry: signal deduplication and broker
execution require separate durable services. Exchange holidays and shortened
sessions come from XNYS; broker extended-hours availability still requires a
broker-specific capability check.

Run the daemon under a process supervisor or container restart policy. The
daemon keeps crypto and equity failures isolated, logs reconnects without
secrets, and exits cleanly on `SIGTERM`/`SIGINT`.