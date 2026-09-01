from api.observability import MetricsRegistry
from tools.adapters import (
    get_metrics,
    get_recent_deployments,
    get_service_dependencies,
    search_logs,
)
from tools.schemas import (
    GetDependenciesInput,
    GetDeploymentsInput,
    GetMetricsInput,
    SearchLogsInput,
)


def test_every_simulator_adapter_returns_bounded_read_only_records(incident) -> None:
    window = {
        "service": incident.service,
        "environment": incident.environment,
        "start": incident.window_start,
        "end": incident.window_end,
    }
    logs = search_logs(SearchLogsInput(**window, query="timeout", limit=5))
    series = get_metrics(
        GetMetricsInput(
            **window,
            metric="http_error_rate",
            labels={},
            step_seconds=60,
        )
    )
    deployments = get_recent_deployments(GetDeploymentsInput(**window))
    dependencies = get_service_dependencies(GetDependenciesInput(service=incident.service))
    assert len(logs) == 5
    assert series
    assert len(deployments) <= 1
    assert dependencies[0]["service"] == incident.service


def test_prometheus_registry_exports_counters_and_summaries() -> None:
    registry = MetricsRegistry()
    registry.increment("requests_total", 2)
    with registry.timer("latency_ms"):
        pass
    rendered = registry.render_prometheus()
    assert "requests_total 2.0" in rendered
    assert "latency_ms_count 1" in rendered
    registry.clear()
    assert registry.render_prometheus() == "\n"
