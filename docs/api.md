# API Contracts

Interactive OpenAPI documentation is available at `http://localhost:8000/docs`.

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/healthz` | Return readiness, indexed chunk count, and read-only mode. |
| `GET` | `/metrics` | Export Prometheus counters and summaries. |
| `GET` | `/api/demo/status` | Describe public-demo availability and allowed synthetic services. |
| `POST` | `/api/demo/investigate` | Create and investigate one bounded synthetic incident without an API key. |
| `GET` | `/api/whoami` | Return the authenticated subject and assigned roles. |
| `GET` | `/api/dashboard` | Aggregate trace count, p50/p95, tokens, cost, cache, and failures. |
| `GET` | `/api/traces` | List bounded operation traces, optionally by incident. |
| `POST` | `/api/documents` | Ingest a bounded Markdown, text, or PDF file with provenance. |
| `POST` | `/api/incidents` | Create a validated incident workspace. |
| `GET` | `/api/incidents/{id}` | Retrieve incident metadata. |
| `POST` | `/api/incidents/{id}/investigate` | Run retrieval and grounded composition and propose tools. |
| `GET` | `/api/incidents/{id}/evidence` | List document and approved-tool evidence. |
| `GET` | `/api/incidents/{id}/postmortem` | Export a grounded Markdown postmortem draft. |
| `POST` | `/api/tool-calls/{id}/approve` | Record approval and execute one pending read-only tool. |
| `POST` | `/api/incidents/{id}/feedback` | Store correctness, citation, and helpfulness labels. |
| `POST` | `/api/evaluations/run` | Run a committed JSONL benchmark configuration. |
| `POST` | `/api/evaluations/compare` | Compare vector-only and advanced retrieval on identical cases. |
| `GET` | `/api/evaluations` | List persisted aggregate evaluation reports. |
| `POST` | `/api/jobs/evaluations` | Queue a durable benchmark job. |
| `POST` | `/api/jobs/documents` | Queue durable extraction and indexing. |
| `GET` | `/api/jobs/{id}` | Inspect queued, running, succeeded, or failed job state. |

## Roles

| Minimum role | Operations |
| --- | --- |
| Viewer | Read incidents, evidence, postmortems, traces, dashboards, and submit feedback. |
| Operator | Create and investigate incidents and approve read-only tools. |
| Evaluator | Run or queue evaluations. |
| Administrator | Ingest documents and administer the runtime configuration. |

Roles are hierarchical in the order shown. When authentication is enabled, pass `Authorization: Bearer <api-key>`. The server derives tool approver identity from the authenticated principal.

The public-demo route is the only intentional authentication exception. It accepts the normal incident schema only for the configured synthetic service allowlist, applies per-client and global in-process sliding-window limits, redacts alert text, and returns pending read-only proposals without approving them. Enabling it requires deterministic generation and simulator telemetry at startup. All incident reads, approvals, dashboards, traces, feedback, exports, ingestion, jobs, and evaluation routes keep their normal role checks.

## Structured investigation output

Every timeline event and hypothesis references evidence IDs returned in the same payload. The server validates those links before persistence. Tool proposals remain `PENDING` until a separate approval request names an approver.

## Errors

- `400`: unsafe evaluation dataset path.
- `404`: incident, tool call, or dataset not found.
- `409`: approval or evaluation policy conflict.
- `429`: public-demo request budget exhausted; consult the `Retry-After` response header.
- `401`/`403`: missing, invalid, or insufficient API-key role.
- `502`: a configured production telemetry source failed safely.
- `413`: document exceeds the configured size limit.
- `422`: schema, file type, time window, or extraction failure.
