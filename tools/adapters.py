"""Deterministic read-only simulator adapters used by the portfolio demo."""

from __future__ import annotations

import hashlib
from datetime import timedelta
from typing import Any

from tools.schemas import (
    GetDependenciesInput,
    GetDeploymentsInput,
    GetMetricsInput,
    SearchLogsInput,
)


def _seed(value: str) -> int:
    return int(hashlib.sha256(value.encode("utf-8")).hexdigest()[:8], 16)


def search_logs(arguments: SearchLogsInput) -> list[dict[str, Any]]:
    """Return bounded synthetic log records without changing any service."""

    patterns = [
        "upstream request timed out after 3000ms",
        "connection pool exhausted while acquiring database session",
        "HTTP 503 returned by dependency payments-db",
        "retry budget consumed for downstream request",
        "request completed with elevated latency",
    ]
    base = _seed(f"{arguments.service}:{arguments.query}")
    count = min(arguments.limit, 12)
    span = max((arguments.end - arguments.start).total_seconds(), 1)
    rows: list[dict[str, Any]] = []
    for index in range(count):
        at = arguments.start + timedelta(seconds=span * index / max(count - 1, 1))
        rows.append(
            {
                "at": at.isoformat(),
                "service": arguments.service,
                "environment": arguments.environment,
                "level": "ERROR" if index % 3 == 0 else "WARN",
                "message": patterns[(base + index) % len(patterns)],
                "trace_id": hashlib.sha1(f"{base}:{index}".encode()).hexdigest()[:16],
            }
        )
    return rows


def get_metrics(arguments: GetMetricsInput) -> list[dict[str, Any]]:
    """Return a deterministic metric series within the requested window."""

    base = _seed(f"{arguments.service}:{arguments.metric}")
    points = min(
        30,
        max(2, int((arguments.end - arguments.start).total_seconds() / arguments.step_seconds) + 1),
    )
    rows: list[dict[str, Any]] = []
    for index in range(points):
        at = arguments.start + timedelta(seconds=index * arguments.step_seconds)
        if at > arguments.end:
            break
        baseline = 0.02 if "error" in arguments.metric else 40.0
        spike = (base % 13) * (index / max(points - 1, 1))
        rows.append(
            {
                "at": at.isoformat(),
                "metric": arguments.metric,
                "value": round(baseline + spike, 4),
                "labels": {
                    "service": arguments.service,
                    "environment": arguments.environment,
                    **arguments.labels,
                },
            }
        )
    return rows


def get_recent_deployments(arguments: GetDeploymentsInput) -> list[dict[str, Any]]:
    """Return immutable deployment metadata for the requested service."""

    base = _seed(arguments.service)
    at = arguments.end - timedelta(minutes=17 + base % 41)
    if at < arguments.start:
        return []
    return [
        {
            "at": at.isoformat(),
            "service": arguments.service,
            "environment": arguments.environment,
            "commit_sha": hashlib.sha1(arguments.service.encode()).hexdigest(),
            "actor": "deployment-bot",
            "status": "SUCCEEDED",
        }
    ]


def get_service_dependencies(arguments: GetDependenciesInput) -> list[dict[str, Any]]:
    """Return read-only service-catalog relationships."""

    catalog = {
        "checkout-api": {"upstream": ["web-store"], "downstream": ["payments-db", "inventory-api"]},
        "payments-api": {"upstream": ["checkout-api"], "downstream": ["payments-db", "fraud-api"]},
        "inventory-api": {"upstream": ["checkout-api"], "downstream": ["inventory-db"]},
    }
    dependencies = catalog.get(arguments.service, {"upstream": [], "downstream": []})
    return [{"service": arguments.service, **dependencies}]


ADAPTERS = {
    "search_logs": search_logs,
    "get_metrics": get_metrics,
    "get_recent_deployments": get_recent_deployments,
    "get_service_dependencies": get_service_dependencies,
}
