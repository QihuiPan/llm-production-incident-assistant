# Architecture

## System boundary

The assistant investigates incidents but never changes production. It accepts an authenticated alert and bounded time window, retrieves versioned evidence, proposes read-only queries, waits for human approval, and records audit metadata. Runtime factories select credential-free memory components or durable PostgreSQL, Redis, production telemetry, and external model components without moving safety decisions out of the API.

```text
React workspace
      |
      v
FastAPI + API-key RBAC ---- runtime factories ---- PostgreSQL + pgvector
      |                           |                    |
      |                           |                    +-- domain data / jobs / traces / cache / cost
      |                           +---- Redis Queue workers
      |
      +---- query planner ---- FTS + vector candidates ---- RRF / rerank / compress
      |
      +---- structured LLM chain ---- cache / cost budget / repair / safe fallback
      |
      +---- tool gateway ---- schema / scope / approval / budgets / audit / redaction
      |          |
      |          +---- simulator or read-only telemetry HTTP adapters
      |
      +---- Prometheus metrics + persistent trace dashboard
```

## Retrieval path

1. Parse headings and preserve code-block text.
2. Split on semantic section boundaries, then apply a bounded chunk size with overlap.
3. Attach document ID, source, version, service, environment, trust level, and section.
4. Filter candidates by service and environment.
5. Decompose the alert into at most four incident-specific subqueries.
6. Produce independent keyword and 768-dimension vector rankings.
7. Fuse rankings with reciprocal rank fusion and apply trust, section, and injection weights.
8. Remove near-duplicates and enforce a deterministic context-token budget.
9. Return evidence objects with stable IDs, provenance, rank metadata, and quote hashes.

The local hashed vector is intentionally credential-free and deterministic. Production deployments should write model embeddings to the 768-dimension pgvector column while keeping the keyword branch and the same evaluation gate.

## Tool path

Each tool has a Pydantic model with `extra="forbid"`. The gateway rejects unknown tools, cross-incident service scopes, excessive time windows, row-limit violations, repeated approvals, and per-incident budget overruns. The authenticated operator identity is stored with approval. Results are recursively redacted before they become evidence. Production adapters issue only fixed OpenSearch search, Prometheus range-query, deployment GET, and service-catalog GET requests to administrator-configured base URLs.

## Persistence

`MemoryStore` keeps the credential-free demo and most tests fast. `PostgresStore`, `PostgresHybridIndex`, `PostgresTraceRecorder`, `PostgresLLMCache`, `PostgresBudgetLedger`, and `PostgresJobRepository` implement the production path. `infra/postgres/001_init.sql` defines the durable domain, pgvector, queue, trace, cache, and daily-cost schema. Redis Queue transports work; PostgreSQL remains the job source of truth.

## Model path

External generation uses the OpenAI Responses API contract with a strict Pydantic-derived JSON Schema. One schema failure receives a correction request. A configured second model can run next; request failures, validation failures, and exhausted daily cost budgets degrade to the deterministic provider. Every result is citation-validated before persistence. Cache keys include the incident, evidence hashes, provider, and model.

## Authorization

Bearer API keys map to viewer, operator, evaluator, or administrator roles. Role checks run inside FastAPI for every domain endpoint. Health and Prometheus scrape endpoints remain unauthenticated for platform probes. Disabled authentication is an explicit local-demo mode and is surfaced by `/healthz`.

## Failure behavior

- No relevant evidence: return `insufficient_evidence=true`, avoid a root-cause guess, and propose specific read-only queries.
- Invalid citation: reject the answer before it is stored.
- Invalid structured input: return HTTP 422 without executing a tool.
- Prompt injection: isolate the text as untrusted evidence, lower its retrieval weight, emit a security event, and never interpret it as an instruction.
- Tool overflow: truncate at the server adapter boundary and preserve an audit reference.
- External model failure or budget exhaustion: use the deterministic grounded fallback and expose the fallback flag.
- Telemetry outage: mark the tool call failed, preserve the audit state, and return a bounded gateway error.
- Worker failure: persist a terminal `FAILED` job with a redacted error summary.
