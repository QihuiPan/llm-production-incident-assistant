"""Bounded platform metrics and optional OTLP traces/logs for real requests."""

from __future__ import annotations

import json
import logging
import os
import time
from contextlib import contextmanager

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.propagate import extract
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from prometheus_client import CollectorRegistry, Counter, Histogram
from prometheus_client.openmetrics.exposition import generate_latest
from prometheus_client.parser import text_string_to_metric_families

REGISTRY = CollectorRegistry()
SERVICE = os.getenv("OTEL_SERVICE_NAME", "llm-assistant")
TENANT = os.getenv("OBSERVE_TENANT", "team-ai")
COUNTER = Counter(
    "http_requests_total",
    "Completed valid HTTP requests",
    ["service", "tenant", "status"],
    registry=REGISTRY,
)
LATENCY = Histogram(
    "http_request_duration_seconds",
    "Valid HTTP duration",
    ["service", "tenant"],
    buckets=[0.1, 0.3, 0.5, 1, 2, 5],
    registry=REGISTRY,
)
RESOURCE = Resource.create(
    {
        "service.name": SERVICE,
        "service.version": os.getenv("SERVICE_VERSION", "2.2.0"),
        "deployment.environment": os.getenv("DEPLOYMENT_ENVIRONMENT", "demo"),
        "cloud.region": os.getenv("CLOUD_REGION", "local"),
        "tenant": TENANT,
    }
)
PROVIDER = TracerProvider(resource=RESOURCE)
LOGGER = logging.getLogger("platform.telemetry")
LOGGER.setLevel(logging.INFO)
if os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT"):
    PROVIDER.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
    logs = LoggerProvider(resource=RESOURCE)
    logs.add_log_record_processor(BatchLogRecordProcessor(OTLPLogExporter()))
    LOGGER.addHandler(LoggingHandler(logger_provider=logs))
TRACER = PROVIDER.get_tracer(__name__)
for outcome in ("ok", "error"):
    COUNTER.labels(SERVICE, TENANT, outcome).inc(0)


@contextmanager
def provider_span():
    """Record dependency latency and errors without exporting prompts or answers."""
    with TRACER.start_as_current_span("llm.provider", kind=trace.SpanKind.CLIENT) as span:
        try:
            yield span
        except Exception:
            span.set_status(trace.Status(trace.StatusCode.ERROR, "Provider request failed"))
            raise


def render_metrics(legacy: str = "") -> str:
    class CombinedCollector:
        def collect(self):
            yield from text_string_to_metric_families(legacy)
            yield from REGISTRY.collect()

    combined = CollectorRegistry()
    combined.register(CombinedCollector())
    return generate_latest(combined).decode()


def install(app) -> None:
    @app.middleware("http")
    async def platform_request(request, call_next):
        if request.url.path in ("/healthz", "/readyz", "/metrics"):
            return await call_next(request)
        started = time.perf_counter()
        with TRACER.start_as_current_span(
            "http.request", context=extract(dict(request.headers)), kind=trace.SpanKind.SERVER
        ) as span:
            status = 500
            try:
                response = await call_next(request)
                status = response.status_code
                return response
            finally:
                span.set_attribute("http.request.method", request.method)
                span.set_attribute("http.response.status_code", status)
                if status >= 500:
                    span.set_status(trace.Status(trace.StatusCode.ERROR))
                context = span.get_span_context()
                trace_id = format(context.trace_id, "032x")
                if status < 400 or status >= 500:
                    COUNTER.labels(SERVICE, TENANT, "error" if status >= 500 else "ok").inc(
                        exemplar={"trace_id": trace_id}
                    )
                    LATENCY.labels(SERVICE, TENANT).observe(
                        time.perf_counter() - started, exemplar={"trace_id": trace_id}
                    )
                LOGGER.info(
                    json.dumps(
                        {
                            "service.name": SERVICE,
                            "trace_id": trace_id,
                            "span_id": format(context.span_id, "016x"),
                            "status": status,
                        }
                    )
                )
