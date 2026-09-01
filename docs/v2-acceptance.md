# Flagship v2 Acceptance Gates

This checklist turns every MVP and advanced requirement in the source blueprint into a verifiable repository outcome.

| Area | Acceptance gate |
| --- | --- |
| Document ingestion | Markdown, text, and PDF ingestion preserves provenance, trust, service, version, section, and injection flags. |
| Persistence | Incidents, messages, evidence, tool calls, evaluations, feedback, jobs, traces, and cache survive API restarts in PostgreSQL. |
| Retrieval | PostgreSQL full-text and pgvector candidates are fused with RRF, decomposed queries, metadata filters, deduplication, compression, and reranking. |
| Generation | A configurable external structured LLM provider validates output, repairs once, falls back safely, and never emits an invalid citation. |
| Tooling | Logs, metrics, deployments, and service dependencies have simulator and production HTTP adapters behind the same strict allowlist. |
| Authorization | Authenticated viewer, operator, evaluator, and administrator roles are enforced server-side. |
| Budgets | Tool calls, rows, time windows, model tokens, timeouts, cache, and daily cost are bounded and observable. |
| Safety | Injection, secret exfiltration, cross-service access, argument smuggling, SSRF, invalid citations, and mutation requests have automated adversarial tests. |
| Evaluation | One hundred labelled cases include held-out splits, vector-only and hybrid A/B runs, error attribution, regression gates, and saved reports. |
| Observability | Request traces expose retrieval, reranking, model, tool, token, cache, cost, and p50/p95 latency summaries. |
| Background work | Ingestion and evaluation can run through a durable queue with inspectable job status. |
| User experience | The React workspace supports investigation, evidence review, tool approval, feedback, postmortem export, and operational dashboards. |
| Testing | Unit, contract, security, API, PostgreSQL Testcontainers, evaluation, and Playwright end-to-end suites are automated. |
| Delivery | Reproducible containers, Kubernetes resources, CI, release automation, English documentation, and mandatory changelog enforcement are present. |

Public cloud deployment is an external operation. The repository is complete when its image and deployment artifacts pass verification; publishing a live demo additionally requires an approved hosting account, domain, credentials, and repository visibility policy.
