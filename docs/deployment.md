# Deployment Guide

## Verified delivery targets

The repository produces two non-root, read-only images:

- `llm-production-incident-assistant`: FastAPI and RQ worker runtime.
- `llm-production-incident-assistant-web`: static React workspace on unprivileged Nginx.

`docker-compose.yml` is the reproducible local integration target. `infra/k8s` is the production-oriented Kubernetes base. Tag pushes run `.github/workflows/release.yml`, which publishes multi-architecture GHCR images with provenance and SBOM metadata.

## Local durable stack

```bash
docker compose up --build
```

The stack exposes the workspace on port 5173, API on 8000, PostgreSQL on 5432, and Prometheus on 9090. Redis and the worker remain internal except for their container health checks. Compose uses deterministic generation and simulator tools so it requires no external secrets.

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
2. Apply the additive database migration.
3. Deploy a pinned image to staging and execute a simulator smoke test.
4. Enable production telemetry for a canary API deployment.
5. Inspect `/api/dashboard`, `/api/traces`, `/metrics`, queue failures, and daily cost.
6. Increase traffic only when citation, tool, latency, and safety signals remain healthy.

Rollback by restoring the prior pinned API and web image tags. The v2 schema changes are additive; do not delete v2 columns or tables during application rollback.

## Public demo boundary

Repository delivery does not authorize publishing data or changing GitHub visibility. A public deployment requires the owner's explicit choice of hosting account, region, domain, cost policy, repository visibility, and credentials. Use simulator tools and synthetic data for any public demo.
