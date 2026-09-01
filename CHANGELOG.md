# Changelog

All notable changes to this project are documented in this file. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and releases use
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [2.0.0] - 2026-09-01

### Added

- PostgreSQL/pgvector runtime persistence and production hybrid retrieval wiring.
- Configurable structured LLM providers with validation repair, fallback, caching, token accounting, and cost budgets.
- Query decomposition, context compression, trust-aware reranking, and retrieval A/B configuration.
- API-key authentication, role-based authorization, production telemetry adapters, and queued background jobs.
- Trace, latency, token, cost, cache, feedback, and evaluation dashboard APIs and UI.
- One hundred labelled incidents, held-out A/B reports, Testcontainers integration, expanded adversarial security tests, and Playwright E2E coverage.
- Production container, Kubernetes, release, and deployment assets.

### Changed

- Upgraded the project from the credential-free MVP baseline to the full flagship architecture described by the implementation blueprint.

## [1.0.0] - 2026-09-01

### Added

- FastAPI incident, evidence, tool approval, feedback, document ingestion, and evaluation APIs.
- Deterministic hybrid keyword/vector retrieval with reciprocal rank fusion and trust-aware reranking.
- Read-only, schema-constrained tool gateway with budgets, audit records, and output redaction.
- Citation validation, prompt-injection detection, PII redaction, and safe insufficient-evidence behavior.
- React incident workspace with investigation, evidence, hypothesis, and tool-approval panels.
- Grounded Markdown postmortem draft export with an evidence register and operator-review warning.
- Fifty-case synthetic evaluation dataset, benchmark runner, and regression thresholds.
- PostgreSQL/pgvector schema, Docker Compose stack, Prometheus configuration, and runtime health checks.
- Unit, contract, security, integration-style API, and evaluation tests.
- English architecture, API, threat-model, error-analysis, and blueprint-coverage documentation.
- CI enforcement requiring a changelog update for every behavior-changing pull request.

[Unreleased]: https://github.com/QihuiPan/llm-production-incident-assistant/compare/v2.0.0...HEAD
[2.0.0]: https://github.com/QihuiPan/llm-production-incident-assistant/compare/v1.0.0...v2.0.0
[1.0.0]: https://github.com/QihuiPan/llm-production-incident-assistant/releases/tag/v1.0.0
