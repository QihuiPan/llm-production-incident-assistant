# LLM Production Incident Assistant

A cited, evaluated, read-only assistant for production incident investigation. It combines hybrid retrieval, schema-constrained tool calling, evidence validation, prompt-injection defenses, offline evaluation, and operational telemetry in a runnable portfolio project.

> Safety boundary: this assistant cannot restart services, deploy code, modify records, or execute arbitrary commands. Every tool is read-only, server-allowlisted, strictly validated, budgeted, audited, and separately approved by a human.

## What reviewers can verify

- Incident-specific retrieval over versioned runbooks and postmortems, not generic PDF chat.
- Keyword and deterministic-vector candidates fused with reciprocal rank fusion.
- Evidence provenance, trust labels, quote hashes, and citation validation.
- Approval-gated log, metric, deployment, and service-catalog simulators.
- Prompt-injection isolation and recursive email, token, API-key, and password redaction.
- A 50-case labelled dataset with strict accuracy, recall, citation, tool, and latency gates.
- Prometheus metrics, a PostgreSQL/pgvector schema, Docker Compose, CI, and an English threat model.
- A responsive React investigation workspace with evidence and approval panels.

## Quick start

### API

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
uvicorn api.main:app --reload
```

On Windows PowerShell, activate with `.venv\Scripts\Activate.ps1`. Open [http://localhost:8000/docs](http://localhost:8000/docs) for the interactive API contract.

### Web workspace

```bash
cd web
pnpm install --frozen-lockfile
pnpm dev
```

Open [http://localhost:5173](http://localhost:5173). The API URL defaults to `http://localhost:8000` and can be changed with `VITE_API_URL`.

### Full local stack

```bash
docker compose up --build
```

This starts the API, PostgreSQL with pgvector, and Prometheus. The credential-free demo uses its in-process repository; `infra/postgres/001_init.sql` is the deployment schema and retrieval-index definition.

## Demo incident

Create a production incident for `checkout-api` with an alert such as:

```text
HTTP 503 spike with connection pool exhausted errors after a deployment
```

The investigation should retrieve the checkout runbook and reviewed postmortem, produce a preliminary cited connection-pool hypothesis, and propose deployment, log, and error-rate queries. Approving a proposal executes only its bounded simulator adapter and stores the redacted result as tool evidence.

## Evaluation

```bash
python -m evals.runner --dataset evals/datasets/synthetic_incidents.jsonl --strict
```

The strict gate requires root-cause accuracy >= 80%, evidence recall@10 >= 90%, citation precision >= 95%, unsupported claim rate < 5%, tool selection accuracy >= 85%, and p95 latency < 12 seconds. See [evals/rubric.md](evals/rubric.md) and [docs/error-analysis.md](docs/error-analysis.md). Synthetic results are regression evidence, not a production-performance claim.

## Repository map

```text
api/          FastAPI contracts, orchestration, storage, safety, and metrics
retrieval/    structure-aware chunking, ingestion, hybrid ranking, demo corpus
tools/        strict schemas, read-only adapters, approval and audit gateway
prompts/      structured-output and system-boundary artifacts
evals/        labelled dataset, rubric, runner, and reports
workers/      ingestion and batch-evaluation job boundaries
web/          React incident workspace and evidence viewer
infra/        PostgreSQL/pgvector and Prometheus configuration
docs/         architecture, API, threat model, coverage, and error analysis
tests/        unit, API, contract, security, and evaluation tests
```

## Design notes

- The local vector branch uses deterministic feature hashing so the full project runs without a model key. A production embedding provider can populate the 768-dimension pgvector column without removing keyword retrieval or the evaluation gate.
- Retrieved content and tool output remain data. They never become system instructions.
- Every hypothesis and timeline event must cite IDs present in the response. Invalid IDs stop persistence.
- All comments, annotations, contracts, and documentation are English.
- Every code, behavior, configuration, documentation, dependency, or deployment change must update [CHANGELOG.md](CHANGELOG.md); CI enforces this rule.

## Documentation

- [Architecture](docs/architecture.md)
- [Threat model](docs/threat-model.md)
- [API contracts](docs/api.md)
- [Blueprint coverage](docs/blueprint-coverage.md)
- [Error analysis](docs/error-analysis.md)
- [Contributing](CONTRIBUTING.md)

## License

MIT
