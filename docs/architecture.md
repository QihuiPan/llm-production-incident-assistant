# Architecture

## System boundary

The assistant investigates incidents but never changes production. It accepts an alert and a bounded time window, retrieves versioned evidence, proposes read-only queries, waits for human approval, and records audit metadata. A deterministic local composer makes the repository runnable without credentials; a hosted model adapter can replace it only if the same structured-output and citation-validation boundary is preserved.

```text
React workspace
      |
      v
FastAPI orchestrator ---- repository interface ---- PostgreSQL + pgvector
      |                         |
      |                         +---- incidents, evidence, feedback, evaluations
      |
      +---- hybrid retriever ---- full-text candidates + vector candidates + RRF
      |
      +---- tool gateway ---- schema validation + approval + budgets + audit
      |          |
      |          +---- logs / metrics / deployments / service catalog simulators
      |
      +---- metrics registry ---- Prometheus
```

## Retrieval path

1. Parse headings and preserve code-block text.
2. Split on semantic section boundaries, then apply a bounded chunk size with overlap.
3. Attach document ID, source, version, service, environment, trust level, and section.
4. Filter candidates by service and environment.
5. Produce independent keyword and deterministic-vector rankings.
6. Fuse rankings with reciprocal rank fusion and apply trust and injection penalties.
7. Return evidence objects with stable IDs, provenance, rank metadata, and quote hashes.

The local hashed vector is intentionally credential-free and deterministic. Production deployments should write model embeddings to the 768-dimension pgvector column while keeping the keyword branch and the same evaluation gate.

## Tool path

Each tool has a Pydantic model with `extra="forbid"`. The gateway rejects unknown tools, cross-incident service scopes, excessive time windows, row-limit violations, repeated approvals, and per-incident budget overruns. Results are recursively redacted before they become evidence.

## Persistence

`MemoryStore` keeps the demo and tests simple. `infra/postgres/001_init.sql` defines the production data model and indexes. The store is deliberately isolated behind a small repository surface so a PostgreSQL adapter can be introduced without moving policy decisions into the database layer.

## Failure behavior

- No relevant evidence: return `insufficient_evidence=true`, avoid a root-cause guess, and propose specific read-only queries.
- Invalid citation: reject the answer before it is stored.
- Invalid structured input: return HTTP 422 without executing a tool.
- Prompt injection: isolate the text as untrusted evidence, lower its retrieval weight, emit a security event, and never interpret it as an instruction.
- Tool overflow: truncate at the server adapter boundary and preserve an audit reference.
