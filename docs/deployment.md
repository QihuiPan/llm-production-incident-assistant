# Deployment Guide

## Verified delivery targets

The repository produces three non-root, read-only images:

- `llm-production-incident-assistant`: FastAPI and RQ worker runtime.
- `llm-production-incident-assistant-web`: static React workspace on unprivileged Nginx.
- `llm-production-incident-assistant-render-free`: combined React and FastAPI public-demo runtime.

`docker-compose.yml` is the reproducible local integration target. `render.yaml` is the managed public-demo target, and `infra/k8s` is the production-oriented Kubernetes base. Tag pushes run `.github/workflows/release.yml`, which publishes multi-architecture GHCR images with provenance and SBOM metadata.

## Local durable stack

```bash
docker compose up --build
```

The stack exposes the workspace on port 5173, API on 8000, PostgreSQL on 5432, and Prometheus on 9090. Redis and the worker remain internal except for their container health checks. Compose uses deterministic generation and simulator tools so it requires no external secrets.

## Render public demo

The committed Blueprint creates the following topology in the `singapore` region:

- One free web service that serves the bundled React workspace and authenticated FastAPI routes from the same origin.
- One free PostgreSQL 17 database with pgvector and no public IP allowlist.

Every resource in `render.yaml` explicitly selects the `free` plan. Render does not provide free Private Service or Background Worker instances, so this public-demo profile uses an inline thread pool for inspectable ingestion and evaluation jobs. The production Compose and Kubernetes targets retain the separate API, queue, and worker boundaries.

1. Sign in to Render and install the Render GitHub App for only this private repository.
2. Create a Blueprint from the repository and select `render.yaml`.
3. Confirm that the proposed resource names and `singapore` region are acceptable.
4. Provide `API_KEYS_JSON` when Render prompts for the `sync: false` secret. A suitable administrator record is `{"generated-secret":{"subject":"owner@example.com","roles":["administrator"]}}`; replace both placeholders and store the generated key outside the repository.
5. Verify that the estimated monthly price is zero before deploying. The container startup command runs `python -m api.migrate`, which enables pgvector and applies the idempotent schema.
6. Wait for the database and combined web service to become healthy.
7. Open the web service URL, enter the generated application key, create the documented checkout incident, run an investigation, approve one simulator proposal, and inspect the dashboard and postmortem export.

The browser sends API calls to the same public origin. API-key authentication remains enabled, and the database accepts no public IP ranges. Render injects the database connection string through a Blueprint reference, so its credentials are never committed.

The free profile is a portfolio demonstration, not a production topology. Render free web services spin down after 15 minutes without inbound traffic and can take about one minute to wake. A workspace receives 750 free instance hours per month. The service filesystem is ephemeral, and free PostgreSQL is limited to 1 GB, has no backups, and expires 30 days after creation. Recreate the free database or upgrade it before expiry if the demo must remain available.

To add a custom domain, attach the web hostname in Render and create the requested DNS record with the domain provider. Render provisions and renews TLS. No API subdomain is required.

For a real OpenAI deployment, add `LLM_PROVIDER=openai_compatible`, `LLM_API_URL`, `LLM_API_KEY`, `LLM_MODEL`, explicit input/output price variables, and the approved daily budget as server-side Render environment secrets. For production telemetry, move to the production topology, add the four fixed telemetry URLs and optional bearer token, then change `TOOL_BACKEND` only for a private canary. Never expose model or telemetry secrets in the web build.

Rollback by selecting one of the two previous successful web-service deploys available to free instances. The migration is additive and idempotent; do not delete schema objects during an application rollback. Free PostgreSQL has no managed backups.

## Kubernetes prerequisites

Provide managed PostgreSQL 17 with pgvector, managed Redis, an ingress controller, TLS, and an external secret manager. Create the required secret from a protected values source; never apply `secret.example.yaml` unchanged.

```bash
kubectl apply -f infra/k8s/namespace.yaml
kubectl -n incident-assistant create secret generic incident-assistant-secrets \
  --from-literal=DATABASE_URL='postgresql://...' \
  --from-literal=REDIS_URL='redis://...' \
  --from-literal=API_KEYS_JSON='{"key":{"subject":"on-call","roles":["operator"]}}'
kubectl apply -k infra/k8s
```

Before applying, pin image tags to the intended release, replace the example hostname, configure TLS, and choose simulator or production telemetry. Apply `infra/postgres/001_init.sql` with a migration identity before starting API or worker pods.

## External model

Set `LLM_PROVIDER=openai_compatible`, a Responses endpoint in `LLM_API_URL`, an API key, a model, and optional fallback model. Configure price inputs explicitly because the application does not guess provider pricing. Set `DAILY_COST_BUDGET_USD`, output-token limit, timeout, and cache TTL to approved values. If the endpoint fails, returns invalid structure twice, or the daily budget is exhausted, the runtime records the degradation and uses its deterministic grounded provider.

## Production telemetry

Set `TOOL_BACKEND=production` and all four fixed base URLs. Optional `TELEMETRY_BEARER_TOKEN` is applied server-side. No tool accepts a URL, HTTP method, index, or arbitrary query language from the model. Use network policy or an egress gateway to restrict the API and worker to the configured systems.

## Authentication

Enable `AUTH_ENABLED=true`. `API_KEYS_JSON` maps opaque keys to subjects and role arrays. Rotate keys in the secret manager and restart pods. Do not place keys in the web build. Operators may enter a key into the workspace for session storage only, or a production reverse proxy or identity-aware gateway may supply a protected credential flow. The built-in API-key layer remains the server-side authorization backstop.

## Rollout and rollback

1. Run CI, the 100-case strict gate, A/B comparison, Testcontainers, and Playwright.
2. Apply the additive database migration with `python -m api.migrate` or the equivalent migration identity.
3. Deploy a pinned image to staging and execute a simulator smoke test.
4. Enable production telemetry for a canary API deployment.
5. Inspect `/api/dashboard`, `/api/traces`, `/metrics`, queue failures, and daily cost.
6. Increase traffic only when citation, tool, latency, and safety signals remain healthy.

Rollback by restoring the prior pinned API and web image tags. The v2 schema changes are additive; do not delete v2 columns or tables during application rollback.

## Public demo boundary

Repository delivery does not authorize publishing data or changing GitHub visibility. A public deployment requires the owner's explicit approval of the Render account, region, optional domain, and application credentials. Verify a zero-dollar estimate when using the free-demo Blueprint. Use simulator tools and synthetic data for any public demo.
