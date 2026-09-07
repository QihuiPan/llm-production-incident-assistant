import pytest
from fastapi import FastAPI, Response
from fastapi.testclient import TestClient
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from api import platform_telemetry as telemetry


def test_request_metrics_spans_and_exclusions():
    exporter = InMemorySpanExporter()
    telemetry.PROVIDER.add_span_processor(SimpleSpanProcessor(exporter))
    app = FastAPI()
    telemetry.install(app)

    @app.get("/work/{status}")
    def work(status: int):
        return Response(status_code=status)

    @app.get("/healthz")
    def health():
        return {"status": "ok"}

    with TestClient(app) as client:
        for status in (200, 400, 500):
            assert client.get(f"/work/{status}").status_code == status
        client.get("/healthz")
    spans = exporter.get_finished_spans()
    assert len(spans) == 3
    assert spans[-1].status.is_ok is False
    metrics = telemetry.render_metrics()
    assert 'le="0.3"' in metrics
    assert "trace_id=" in metrics
    assert "user_id" not in metrics


def test_provider_failure_creates_error_span():
    exporter = InMemorySpanExporter()
    telemetry.PROVIDER.add_span_processor(SimpleSpanProcessor(exporter))
    with pytest.raises(RuntimeError), telemetry.provider_span():
        raise RuntimeError("Provider timeout")
    assert exporter.get_finished_spans()[-1].name == "llm.provider"
    assert exporter.get_finished_spans()[-1].status.is_ok is False
