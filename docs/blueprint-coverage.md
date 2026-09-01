# Blueprint Coverage

| Blueprint requirement | Implementation |
| --- | --- |
| Incident workspace | React service, environment, alert, and time-window form |
| Markdown/PDF ingestion | Passive, size-bounded `/api/documents` extraction path |
| Hybrid retrieval | Keyword + hashed-vector candidates, RRF, metadata filtering, trust reranking |
| Grounded structured output | Typed investigation response and citation validator |
| Three read-only tools | Logs, metrics, and recent deployments; service catalog is also available |
| Human approval | Separate approval endpoint and pending state |
| Tool allowlist and schema | Exact adapter map and Pydantic `extra="forbid"` contracts |
| Prompt-injection defense | Detection, isolation, ranking penalty, security metric, adversarial tests |
| PII and secret protection | Recursive redaction of tool output |
| Evaluation dataset | 50 labelled synthetic cases and strict regression runner |
| Metrics | Accuracy, recall, citation, unsupported claims, tools, latency, and cost field |
| Observability | Prometheus counters and latency summaries |
| Data model | PostgreSQL/pgvector schema for all blueprint collections |
| Background work | Ingestion and evaluation worker entry points |
| Failure degradation | Insufficient-evidence response, bounded tools, invalid citation rejection |
| Feedback loop | Typed feedback endpoint and repository records |
| Postmortem export | Grounded Markdown draft with evidence register and review warning |
| Documentation | Architecture, API, threat model, rubric, and error analysis |

## Explicit boundary

The repository intentionally excludes autonomous remediation and production write tools. It includes a deterministic offline composer and simulator telemetry so reviewers can run the complete investigation and evaluation loop without cloud credentials.
