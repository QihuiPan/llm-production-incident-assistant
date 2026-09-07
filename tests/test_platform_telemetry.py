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
    assert spans[-1].attributes["prometheus.exemplar"] is True
    metrics = telemetry.render_metrics()
    assert 'le="0.3"' in metrics
    assert "trace_id=" in metrics
    assert "user_id" not in metrics


def test_selected_fast_exemplar_is_marked_for_tail_retention():
    exporter = InMemorySpanExporter()
    telemetry.PROVIDER.add_span_processor(SimpleSpanProcessor(exporter))
    app = FastAPI()
    telemetry.install(app)

    @app.get("/selected")
    def selected():
        return {"ok": True}

    trace_id = "0000000000000000000000000000000a"
    with TestClient(app) as client:
        response = client.get(
            "/selected", headers={"traceparent": f"00-{trace_id}-0000000000000001-01"}
        )
        assert response.status_code == 200
    assert exporter.get_finished_spans()[-1].attributes["prometheus.exemplar"] is True
    assert f'trace_id="{trace_id}"' in telemetry.render_metrics()


def test_provider_failure_creates_error_span():
    exporter = InMemorySpanExporter()
    telemetry.PROVIDER.add_span_processor(SimpleSpanProcessor(exporter))
    with pytest.raises(RuntimeError), telemetry.provider_span():
        raise RuntimeError("Provider timeout")
    assert exporter.get_finished_spans()[-1].name == "llm.provider"
    assert exporter.get_finished_spans()[-1].status.is_ok is False


def test_openmetrics_combines_legacy_and_exemplars():
    from prometheus_client.openmetrics.parser import text_string_to_metric_families

    from api.platform_telemetry import render_metrics

    legacy = "# TYPE llm_calls_total counter\nllm_calls_total 2\n"
    families = list(text_string_to_metric_families(render_metrics(legacy)))
    assert any(
        sample.name == "llm_calls_total" and sample.value == 2
        for family in families
        for sample in family.samples
    )
    assert any(family.name == "http_requests" for family in families)
    assert list(text_string_to_metric_families(render_metrics("\n")))
