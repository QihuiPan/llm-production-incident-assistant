# Checkout API Database Pool Exhaustion Postmortem

## Incident summary

On 2026-07-18, checkout-api returned HTTP 503 responses for 21 minutes. The first error followed deployment `7a42e9c`, which introduced an unbounded retry inside a database transaction.

## Root cause

Retries retained database sessions while waiting for a downstream response. Active sessions reached the pool limit, and new requests failed with `connection pool exhausted while acquiring database session`.

## Contradicting evidence

CPU utilization remained below 45 percent, so compute saturation did not explain the error rate. The database itself remained available.

## Follow-up

The team moved retries outside transaction scope, added pool-acquire latency alerts, and introduced a regression test for session release.
