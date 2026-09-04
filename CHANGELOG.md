# Changelog

All notable changes to this project are documented in this file. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and releases use
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Changed

- 2026-09-04: Changed the GitHub repository visibility from private to public at the owner's request after checking committed history for credentials and private documents.

## [2.1.2] - 2026-09-02

### Fixed

- Let the combined Render image use its tested Docker `CMD` so Render does not reinterpret a nested shell command as an executable path.

## [2.1.1] - 2026-09-01

### Added

- A combined React and FastAPI image for a single-service Render free-tier deployment.
- Deployment contract coverage that rejects paid Render plans and verifies the bundled workspace route.

### Changed

- Replace the paid private API, worker, persistent queue, and database Blueprint with one free web service and one free PostgreSQL database.
- Run public-demo background jobs inline because Render does not offer free background-worker instances.
- Document free-tier sleep, monthly usage, ephemeral runtime, and 30-day database-expiration constraints.

## [2.1.0] - 2026-09-01

### Added

- Render Blueprint delivery for a private API, background worker, public web proxy, managed PostgreSQL 17 with pgvector, and persistent Redis-compatible queue.
- An idempotent PostgreSQL migration command for managed pre-deploy workflows.
- Deployment contract tests covering private networking, generated datastore credentials, secret prompting, and public web routing.

### Changed

- Route browser API traffic through the same-origin Nginx web service so the application API can remain on Render's private network.
- Make API and web containers honor platform-provided ports while preserving local Docker Compose defaults.
- Expand the deployment guide with the Render provisioning, secret, DNS, smoke-test, and rollback workflow.

## [2.0.1] - 2026-09-01

### Fixed

- Cast optional PostgreSQL retrieval filters explicitly so prepared pgvector searches work on PostgreSQL 17 without ambiguous parameter types.

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

[Unreleased]: https://github.com/QihuiPan/llm-production-incident-assistant/compare/v2.1.2...HEAD
[2.1.2]: https://github.com/QihuiPan/llm-production-incident-assistant/compare/v2.1.1...v2.1.2
[2.1.1]: https://github.com/QihuiPan/llm-production-incident-assistant/compare/v2.1.0...v2.1.1
[2.1.0]: https://github.com/QihuiPan/llm-production-incident-assistant/compare/v2.0.1...v2.1.0
[2.0.1]: https://github.com/QihuiPan/llm-production-incident-assistant/compare/v2.0.0...v2.0.1
[2.0.0]: https://github.com/QihuiPan/llm-production-incident-assistant/compare/v1.0.0...v2.0.0
[1.0.0]: https://github.com/QihuiPan/llm-production-incident-assistant/releases/tag/v1.0.0
