# API Contracts

Interactive OpenAPI documentation is available at `http://localhost:8000/docs`.

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/healthz` | Return readiness, indexed chunk count, and read-only mode. |
| `GET` | `/metrics` | Export Prometheus counters and summaries. |
| `POST` | `/api/documents` | Ingest a bounded Markdown, text, or PDF file with provenance. |
| `POST` | `/api/incidents` | Create a validated incident workspace. |
| `GET` | `/api/incidents/{id}` | Retrieve incident metadata. |
| `POST` | `/api/incidents/{id}/investigate` | Run retrieval and grounded composition and propose tools. |
| `GET` | `/api/incidents/{id}/evidence` | List document and approved-tool evidence. |
| `GET` | `/api/incidents/{id}/postmortem` | Export a grounded Markdown postmortem draft. |
| `POST` | `/api/tool-calls/{id}/approve` | Record approval and execute one pending read-only tool. |
| `POST` | `/api/incidents/{id}/feedback` | Store correctness, citation, and helpfulness labels. |
| `POST` | `/api/evaluations/run` | Run a committed JSONL benchmark configuration. |

## Structured investigation output

Every timeline event and hypothesis references evidence IDs returned in the same payload. The server validates those links before persistence. Tool proposals remain `PENDING` until a separate approval request names an approver.

## Errors

- `400`: unsafe evaluation dataset path.
- `404`: incident, tool call, or dataset not found.
- `409`: approval or evaluation policy conflict.
- `413`: document exceeds the configured size limit.
- `422`: schema, file type, time window, or extraction failure.
