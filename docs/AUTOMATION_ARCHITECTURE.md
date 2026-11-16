# QuantLab operator and automation architecture — v0.2

## What `run` means

1. Natural-language **description** is collected; the current UI is a typed draft
   builder, not an LLM compiler. A future LLM must produce JSON only, validated
   by `StrategySpec.from_dict`. Free-form executable code is never accepted.
2. A **strategy review** separately verifies data sources, historical validation,
   execution costs, limits, short borrow eligibility, and mode approval.
3. A supervised `MarketWorker` obtains point-in-time, timestamped observations
   through an audited `VerifiedFeed` implementation. Only this trusted adapter
   creates market-feed observations. No such adapter ships in v0.2.
4. The signal engine evaluates approved features, observations, and expiration;
   eligible observations emit an alert, not a live trade.
5. An independent future order service could consume reviewed trade intents,
   fetch current broker positions, enforce reserves/borrow/locates/risk limits,
   submit using deterministic client order IDs, and reconcile asynchronous fills.
6. Notification adapters can publish to SNS, MQTT or a durable SQS queue
   once credentials and trusted destinations are supplied. Never treat a device notification as an execution
   command. SNS at-least-once fanout implies consumers need idempotency.

## Deployment topography

```text
Streamlit operator console  → authenticated FastAPI (control only)
                                            │
                        typed strategy spec + fixed model SHA
                                            │
Verified data feed → independent Python worker → signal evaluator
                                            │
                        event bus → SNS / SQS / MQTT / dashboard
                                            │
                  approval workflow (future) → independent risk gate
                                            │
                                  broker order service (future)
                                            │
                               broker reconciliation + audit
```

No background market worker or broker client is connected yet; `MarketWorker`
requires an injected audited feed. Streamlit reruns should never open broker
orders or launch child worker processes.

## Broker notes

- Public: personal API, read/write SDK and MCP. Shorting requires approved
  margin, sufficient usable margin equity, and available borrow. Confirm
  Public's personal/non-commercial API terms before productizing an SDK.
- Webull: HTTP trading, MQTT streaming market data, gRPC order event channels.
- Alpaca: Python SDK + MCP. MCP trading tools must be disabled for reasoning
  agents; separate an audited broker adapter from natural-language tools.
- `SHORT` is not a value of `Direction` in v0.2 because `bearish` is an
  informational context, not an instruction to borrow/sell short.

## AI reasoning agent

Read-only agent input: model SHA, source timestamps, explanation codes,
market/regime observations, net expected edge and uncertainty, risk objections.
Agent outputs: evidence-based explanation, missing facts, counterarguments,
questions, and suggested tests. No brokerage credentials, direct order calls,
agent-submitted strategies, or risk-limit changes. Send the same immutable
post-trade packet to Preserve / Challenge / Neutral reviewers, record outputs,
then evaluate challengers offline.

## Operator permissions

Draft → review → alert-only → approval-required → future bounded-live.
The future bounded-live transition must require strong authorization and
separate operator approval. A one-word chat `run` must not bypass validation
or silently enable shorting, options, leverage, or large order sizes.

## Operational safeguards before any live broker

- Secrets in a cloud secret store or OS keychain, never Streamlit/browser state.
- Strong per-user authentication, access log, MFA and least-privilege tokens.
- Broker state reconciliation, settlement, borrowing and short-locate eligibility.
- Atomic capital reservations, idempotent orders, ack/reject/fill/cancel handling.
- Distributed rate limit, retry-with-jitter and dead-letter queues.
- Hard cap on daily loss, per-trade risk, gross and correlated exposure.
- No new entry upon stale data, market halt, disconnected feed, or drift alert.
- Alert status not equal to profitable trade, and does not guarantee outcome.
- Restrict live deployment to discretionary money not needed for obligations.

## LLM integration ports (v0.2)

`quantlab.control.reasoner.compile_description_read_only` accepts an injected
text model callable and validates the resulting **data-only** draft; the
operator must verify all symbol/risk parameters before approval.
`explain_read_only` supplies a read-only candidate decision for structured
explanations. These are callable interfaces, not connected providers.

MQTT is configured as outbound notification only. The code does not accept
inbound MQTT trade commands, and SQS consumer execution isn't implemented.
