"""Read-only HTTP adapters for production telemetry and metadata systems."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any
from urllib.parse import quote, urlparse

import httpx2 as httpx

from api.config import Settings
from tools.schemas import (
    GetDependenciesInput,
    GetDeploymentsInput,
    GetMetricsInput,
    SearchLogsInput,
)

Adapter = Callable[[Any], list[dict[str, Any]]]


class ProductionAdapterError(RuntimeError):
    """Raised when a configured read-only telemetry query fails safely."""


def _safe_base_url(value: str | None, name: str) -> str:
    if not value:
        raise ValueError(f"{name} must be configured for production tools")
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username:
        raise ValueError(f"{name} must be an absolute HTTP(S) URL without user information")
    return value.rstrip("/")


class ProductionAdapters:
    """Map the fixed tool allowlist to bounded GET or search-only POST requests."""

    def __init__(
        self,
        settings: Settings,
        *,
        requester: Callable[..., dict[str, Any]] | None = None,
    ) -> None:
        self.opensearch_url = _safe_base_url(settings.opensearch_url, "OPENSEARCH_URL")
        self.opensearch_index = settings.opensearch_index
        self.prometheus_url = _safe_base_url(settings.prometheus_url, "PROMETHEUS_URL")
        self.deployment_url = _safe_base_url(
            settings.deployment_api_url, "DEPLOYMENT_API_URL"
        )
        self.catalog_url = _safe_base_url(settings.service_catalog_url, "SERVICE_CATALOG_URL")
        self.token = (
            settings.telemetry_bearer_token.get_secret_value()
            if settings.telemetry_bearer_token
            else None
        )
        self.requester = requester

    @property
    def mapping(self) -> Mapping[str, Adapter]:
        return {
            "search_logs": self.search_logs,
            "get_metrics": self.get_metrics,
            "get_recent_deployments": self.get_recent_deployments,
            "get_service_dependencies": self.get_service_dependencies,
        }

    def _request(
        self,
        method: str,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if self.requester:
            return self.requester(method, url, params=params, json=json_body)
        headers = {"Accept": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        try:
            with httpx.Client(timeout=15.0, follow_redirects=False) as client:
                response = client.request(
                    method,
                    url,
                    params=params,
                    json=json_body,
                    headers=headers,
                )
                response.raise_for_status()
                payload = response.json()
        except Exception as exc:
            raise ProductionAdapterError(f"read-only telemetry request failed: {exc}") from exc
        if not isinstance(payload, dict):
            raise ProductionAdapterError("telemetry endpoint returned a non-object response")
        return payload

    def search_logs(self, arguments: SearchLogsInput) -> list[dict[str, Any]]:
        payload = self._request(
            "POST",
            f"{self.opensearch_url}/{quote(self.opensearch_index, safe='*-_')}/_search",
            json_body={
                "size": arguments.limit,
                "sort": [{"@timestamp": "asc"}],
                "_source": ["@timestamp", "service", "environment", "level", "message", "trace_id"],
                "query": {
                    "bool": {
                        "filter": [
                            {"term": {"service.keyword": arguments.service}},
                            {"term": {"environment.keyword": arguments.environment}},
                            {
                                "range": {
                                    "@timestamp": {
                                        "gte": arguments.start.isoformat(),
                                        "lte": arguments.end.isoformat(),
                                    }
                                }
                            },
                        ],
                        "must": [{"simple_query_string": {"query": arguments.query}}],
                    }
                },
            },
        )
        hits = payload.get("hits", {}).get("hits", [])
        return [dict(hit.get("_source", {})) for hit in hits[: arguments.limit]]

    def get_metrics(self, arguments: GetMetricsInput) -> list[dict[str, Any]]:
        labels = {
            "service": arguments.service,
            "environment": arguments.environment,
            **arguments.labels,
        }
        selectors = ",".join(
            f'{key}="{value.replace(chr(34), "").replace(chr(92), "")}"'
            for key, value in sorted(labels.items())
        )
        payload = self._request(
            "GET",
            f"{self.prometheus_url}/api/v1/query_range",
            params={
                "query": f"{arguments.metric}{{{selectors}}}",
                "start": arguments.start.timestamp(),
                "end": arguments.end.timestamp(),
                "step": arguments.step_seconds,
            },
        )
        rows: list[dict[str, Any]] = []
        for series in payload.get("data", {}).get("result", []):
            for timestamp, value in series.get("values", []):
                rows.append(
                    {
                        "at": timestamp,
                        "metric": arguments.metric,
                        "value": value,
                        "labels": series.get("metric", {}),
                    }
                )
        return rows[:1000]

    def get_recent_deployments(self, arguments: GetDeploymentsInput) -> list[dict[str, Any]]:
        payload = self._request(
            "GET",
            f"{self.deployment_url}/deployments",
            params={
                "service": arguments.service,
                "environment": arguments.environment,
                "start": arguments.start.isoformat(),
                "end": arguments.end.isoformat(),
                "limit": 100,
            },
        )
        records = payload.get("deployments", payload.get("items", []))
        return [dict(item) for item in records[:100]]

    def get_service_dependencies(
        self, arguments: GetDependenciesInput
    ) -> list[dict[str, Any]]:
        payload = self._request(
            "GET",
            f"{self.catalog_url}/services/{quote(arguments.service, safe='-_')}/dependencies",
        )
        records = payload.get("dependencies")
        if isinstance(records, list):
            return [dict(item) for item in records[:200]]
        return [{"service": arguments.service, **payload}]
