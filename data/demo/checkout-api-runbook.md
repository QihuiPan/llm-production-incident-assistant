# Checkout API Runbook

## Symptoms

High HTTP 5xx rate combined with rising p95 latency commonly indicates a downstream dependency failure. Check deployment history, database pool saturation, and inventory dependency latency before assigning a root cause.

## Database connection pool

The checkout API uses a bounded database connection pool. `pool_acquire_timeout` and repeated `connection pool exhausted` log events indicate that sessions are not returning quickly enough. Compare active connections with the configured pool size and inspect long-running queries. A deployment that changes transaction boundaries can trigger rapid pool exhaustion.

## Safe investigation

Use `get_recent_deployments`, `search_logs`, and `get_metrics`. Investigation is read-only. Do not restart the service, change pool size, terminate queries, or roll back a deployment from this assistant.

## Evidence standard

Require at least one service log or metric and one authoritative runbook or reviewed postmortem before presenting a high-confidence root-cause hypothesis.
