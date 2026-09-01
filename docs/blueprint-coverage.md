# Blueprint Coverage

| Blueprint requirement | Implementation |
| --- | --- |
| Incident workspace | React service, environment, alert, and time-window form |
| Markdown/PDF ingestion | Passive, size-bounded `/api/documents` extraction path |
| Hybrid retrieval | PostgreSQL FTS + pgvector candidates, RRF, query decomposition, metadata filtering, trust reranking, deduplication, and compression |
| Grounded structured output | Responses API strict JSON Schema, one repair, model chain, deterministic fallback, and citation validator |
| Three read-only tools | Logs, metrics, and recent deployments; service catalog is also available |
| Human approval | Separate approval endpoint and pending state |
| Tool allowlist and schema | Exact adapter map and Pydantic `extra="forbid"` contracts |
| Prompt-injection defense | Detection, isolation, ranking penalty, security metric, adversarial tests |
| PII and secret protection | Recursive redaction of tool output |
| Evaluation dataset | 100 labelled cases, development/held-out splits, vector/advanced A/B, and strict regression runner |
| Metrics | Accuracy, recall, citation, unsupported claims, tools, p50/p95 latency, tokens, cache, failures, and cost |
| Observability | Prometheus counters plus inspectable PostgreSQL operation traces and dashboard APIs |
| Data model | Runtime PostgreSQL/pgvector persistence for incidents, evidence, tools, feedback, jobs, traces, LLM cache, and daily costs |
| Background work | Redis Queue ingestion and evaluation jobs with PostgreSQL lifecycle state |
| Failure degradation | Insufficient-evidence response, bounded tools, invalid citation rejection |
| Feedback loop | Typed feedback endpoint and repository records |
| Postmortem export | Grounded Markdown draft with evidence register and review warning |
| Documentation | Architecture, API, threat model, rubric, and error analysis |
| Authentication | API-key identities with viewer, operator, evaluator, and administrator role enforcement |
| Production adapters | Fixed read-only OpenSearch, Prometheus, deployment, and service-catalog clients |
| Delivery | Non-root images, Compose, Kubernetes security resources, GHCR release workflow, Testcontainers, and Playwright |

## Explicit boundary

The repository intentionally excludes autonomous remediation and production write tools. It includes a deterministic offline provider and simulator telemetry so reviewers can run the complete investigation and evaluation loop without cloud credentials. Publishing a live public environment still requires an approved hosting account, secrets, domain, and repository visibility decision.
