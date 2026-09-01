import pytest

from api.config import Settings
from tools.production_adapters import ProductionAdapters
from tools.schemas import (
    GetDependenciesInput,
    GetDeploymentsInput,
    GetMetricsInput,
    SearchLogsInput,
)


def _settings() -> Settings:
    return Settings(
        opensearch_url="https://logs.example.test",
        prometheus_url="https://metrics.example.test",
        deployment_api_url="https://deployments.example.test",
        service_catalog_url="https://catalog.example.test",
    )


def test_log_adapter_emits_only_bounded_search_request(incident) -> None:
    calls = []

    def requester(method, url, **kwargs):
        calls.append((method, url, kwargs))
        return {"hits": {"hits": [{"_source": {"message": "timeout"}}]}}

    adapters = ProductionAdapters(_settings(), requester=requester)
    rows = adapters.search_logs(
        SearchLogsInput(
            service=incident.service,
            environment=incident.environment,
            start=incident.window_start,
            end=incident.window_end,
            query="timeout",
            limit=10,
        )
    )
    assert rows == [{"message": "timeout"}]
    assert calls[0][0] == "POST"
    assert calls[0][1].endswith("/_search")
    assert calls[0][2]["json"]["size"] == 10


def test_adapter_configuration_rejects_non_http_and_userinfo_urls() -> None:
    with pytest.raises(ValueError):
        ProductionAdapters(
            _settings().model_copy(update={"opensearch_url": "file:///etc/passwd"})
        )
    with pytest.raises(ValueError):
        ProductionAdapters(
            _settings().model_copy(update={"prometheus_url": "https://user@host.test"})
        )


def test_production_metric_deployment_and_catalog_response_mapping(incident) -> None:
    def requester(method, url, **kwargs):
        if "query_range" in url:
            return {
                "data": {
                    "result": [
                        {"metric": {"service": "checkout-api"}, "values": [[1, "0.2"]]}
                    ]
                }
            }
        if url.endswith("/deployments"):
            return {"deployments": [{"commit_sha": "abc"}]}
        return {"dependencies": [{"service": "payments-db"}]}

    adapters = ProductionAdapters(_settings(), requester=requester)
    window = {
        "service": incident.service,
        "environment": incident.environment,
        "start": incident.window_start,
        "end": incident.window_end,
    }
    metrics = adapters.get_metrics(
        GetMetricsInput(
            **window,
            metric="http_error_rate",
            labels={},
            step_seconds=60,
        )
    )
    deployments = adapters.get_recent_deployments(GetDeploymentsInput(**window))
    dependencies = adapters.get_service_dependencies(
        GetDependenciesInput(service=incident.service)
    )
    assert metrics[0]["value"] == "0.2"
    assert deployments[0]["commit_sha"] == "abc"
    assert dependencies[0]["service"] == "payments-db"
