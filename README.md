# LLM Production Incident Assistant

A cited, evaluated, read-only assistant for production incident investigation. The flagship v2 runtime combines PostgreSQL/pgvector retrieval, strict structured model output, approval-gated production telemetry, RBAC, durable jobs, trace dashboards, offline A/B evaluation, and a responsive operator workspace.

> Safety boundary: this assistant cannot restart services, deploy code, modify records, or execute arbitrary commands. Every tool is read-only, server-allowlisted, strictly validated, budgeted, audited, and separately approved by a human.

## What reviewers can verify

- Incident-specific retrieval over versioned runbooks and postmortems, not generic PDF chat.
- PostgreSQL full-text and 768-dimension pgvector candidates fused with reciprocal rank fusion.
- Query decomposition, trust-aware reranking, near-duplicate removal, and context compression.
- Evidence provenance, trust labels, quote hashes, and citation validation.
- Approval-gated log, metric, deployment, and service-catalog simulators or production HTTP adapters.
- Prompt-injection isolation and recursive email, token, API-key, and password redaction.
- A 100-case labelled dataset with development/held-out splits and vector-versus-advanced A/B gates.
- API-key RBAC, Redis Queue jobs, persistent model cache/cost budgets, and p50/p95 traces.
- Testcontainers, Playwright desktop/mobile E2E, Compose, Kubernetes, and release-image automation.
- A Render Blueprint that keeps the API, PostgreSQL, and Redis-compatible queue on private networking behind a same-origin web proxy.
- A responsive React workspace with evidence, timeline, approvals, dashboard, feedback, and export.

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

This starts the web workspace, API, PostgreSQL with pgvector, Redis, an RQ worker, and Prometheus. Compose enables durable PostgreSQL storage and queued jobs by default while retaining credential-free deterministic generation and simulator telemetry.

### Render deployment

`render.yaml` provisions the public web proxy, private API, private worker, PostgreSQL 17, and persistent Redis-compatible queue in Singapore. Connect the private repository to Render, create a Blueprint from the repository, and provide `API_KEYS_JSON` only when prompted. The committed pre-deploy command applies the idempotent pgvector schema before the API starts.

Review the selected region and paid plans before the first Blueprint sync because the region is immutable after resource creation. No OpenAI or production-telemetry secret is required for the safe simulator demo. See [deployment.md](docs/deployment.md) for the complete provisioning and smoke-test workflow.

## Production configuration

The safe local defaults are `STORAGE_BACKEND=memory`, `LLM_PROVIDER=deterministic`, `TOOL_BACKEND=simulator`, `JOB_BACKEND=inline`, and `AUTH_ENABLED=false`. A production deployment should set:

```text
STORAGE_BACKEND=postgres
DATABASE_URL=postgresql://...
JOB_BACKEND=rq
REDIS_URL=redis://...
AUTH_ENABLED=true
API_KEYS_JSON={"secret":{"subject":"operator@example","roles":["operator"]}}
LLM_PROVIDER=openai_compatible
LLM_API_URL=https://api.openai.com/v1/responses
LLM_API_KEY=...
LLM_MODEL=...
TOOL_BACKEND=production
OPENSEARCH_URL=https://...
PROMETHEUS_URL=https://...
DEPLOYMENT_API_URL=https://...
SERVICE_CATALOG_URL=https://...
```

Secrets must come from a secret manager or Kubernetes Secret and must never be committed. The external model uses strict JSON Schema through the Responses API, repairs one invalid response, optionally tries a second configured model, and then degrades to the deterministic grounded provider. See [deployment.md](docs/deployment.md).

## Demo incident

Create a production incident for `checkout-api` with an alert such as:

```text
HTTP 503 spike with connection pool exhausted errors after a deployment
```

The investigation should retrieve the checkout runbook and reviewed postmortem, produce a preliminary cited connection-pool hypothesis, and propose deployment, log, and error-rate queries. Approving a proposal executes only its bounded simulator adapter and stores the redacted result as tool evidence.

## Evaluation

```bash
python -m evals.runner --dataset evals/datasets/synthetic_incidents.jsonl --strict
python -m evals.runner --dataset evals/datasets/synthetic_incidents.jsonl --compare --strict
```

The strict gate requires root-cause accuracy >= 80%, evidence recall@10 >= 90%, citation precision >= 95%, unsupported claim rate < 5%, tool selection accuracy >= 85%, and p95 latency < 12 seconds. The A/B gate also prevents the advanced candidate from regressing vector-only root-cause accuracy or evidence recall. See [evals/rubric.md](evals/rubric.md) and [docs/error-analysis.md](docs/error-analysis.md). Synthetic results are regression evidence, not a production-performance claim.

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
render.yaml   Private-network Render Blueprint for the hosted demo
docs/         architecture, API, threat model, coverage, and error analysis
tests/        unit, API, contract, security, and evaluation tests
```

## Design notes

- The credential-free embedding branch uses deterministic feature hashing and writes the same 768-dimension representation to pgvector. A trained embedding provider can replace it behind the index boundary without removing keyword retrieval or the A/B gate.
- OpenAI deployments use the Responses API with strict JSON Schema output as documented by [official OpenAI documentation](https://developers.openai.com/api/reference/resources/responses/methods/create).
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
- [Deployment guide](docs/deployment.md)
- [Flagship v2 acceptance gates](docs/v2-acceptance.md)
- [Contributing](CONTRIBUTING.md)

## License

MIT
