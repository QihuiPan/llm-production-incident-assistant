# Observability platform integration

Set `OTEL_EXPORTER_OTLP_ENDPOINT` to the authenticated gateway, `OTEL_EXPORTER_OTLP_HEADERS` to `Authorization=Bearer%20TOKEN`, and `OBSERVE_TENANT=team-ai`. The token must be short-lived and scoped to the applied llm-assistant specification. Credentials stay in the runtime environment.

The existing `/metrics` endpoint retains legacy metrics and adds canonical HTTP SLO counters, exact 300ms latency buckets and trace exemplars. Request and provider dependency spans export through OTLP. Structured telemetry logs carry trace/span IDs. Prompts, responses, raw URLs and user IDs are not exported by this integration.

Kubernetes workloads should send OTLP to the platform's local identity-exporter sidecar; the sidecar reads a rotating projected service-account token with the observability audience. Health, readiness, metrics and HTTP 4xx are excluded from the SLO population.
