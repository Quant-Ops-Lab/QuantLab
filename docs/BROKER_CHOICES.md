# Broker decision record

Public official API documentation: https://public.com/api/docs
Alpaca trading MCP: https://docs.alpaca.markets/us/docs/trading-api-mcp
Webull OpenAPI: https://developer.webull.com/apis/docs/

Recommended sequence: broker-independent contracts, read-only account/market
adapter, deterministic preflight risk checker, broker reconciliation, then
separately reviewed live execution. An LLM/MCP research integration is not an
order-router. MCP tools can place live orders if given live write access; scope
permissions to read-only features where available.

No adapter here is authenticated and **no trades can be submitted from this
bootstrap**. API eligibility, market data entitlements, account restrictions,
asset permissions and fees must be verified with the selected broker.
