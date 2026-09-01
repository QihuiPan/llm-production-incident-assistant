"""Inspectable in-memory and PostgreSQL operation traces."""

from __future__ import annotations

import json
from collections import defaultdict
from threading import RLock
from typing import Any, Protocol
from uuid import uuid4

import psycopg
from psycopg.rows import dict_row

from api.models import DashboardSummary, TraceRecord


class TraceRecorder(Protocol):
    def record(
        self,
        operation: str,
        duration_ms: float,
        *,
        incident_id: str | None = None,
        status: str = "ok",
        attributes: dict[str, Any] | None = None,
    ) -> TraceRecord: ...

    def list(self, incident_id: str | None = None, limit: int = 100) -> list[TraceRecord]: ...

    def summary(self) -> DashboardSummary: ...


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    position = min(len(ordered) - 1, max(0, round((len(ordered) - 1) * percentile)))
    return ordered[position]


def _summarize(records: list[TraceRecord]) -> DashboardSummary:
    operation_counts: defaultdict[str, int] = defaultdict(int)
    latencies: list[float] = []
    llm_cost = 0.0
    tokens = 0
    cache_hits = 0
    failures = 0
    for record in records:
        operation_counts[record.operation] += 1
        latencies.append(record.duration_ms)
        llm_cost += float(record.attributes.get("cost_usd", 0.0))
        tokens += int(record.attributes.get("input_tokens", 0))
        tokens += int(record.attributes.get("output_tokens", 0))
        cache_hits += int(bool(record.attributes.get("cache_hit", False)))
        failures += int(record.status != "ok")
    return DashboardSummary(
        trace_count=len(records),
        operation_counts=dict(operation_counts),
        p50_latency_ms=_percentile(latencies, 0.50),
        p95_latency_ms=_percentile(latencies, 0.95),
        llm_cost_usd=llm_cost,
        token_count=tokens,
        cache_hits=cache_hits,
        failures=failures,
    )


class MemoryTraceRecorder:
    """Thread-safe trace recorder for the credential-free runtime."""

    def __init__(self) -> None:
        self._records: list[TraceRecord] = []
        self._lock = RLock()

    def record(
        self,
        operation: str,
        duration_ms: float,
        *,
        incident_id: str | None = None,
        status: str = "ok",
        attributes: dict[str, Any] | None = None,
    ) -> TraceRecord:
        record = TraceRecord(
            id=f"TR-{uuid4().hex[:12].upper()}",
            incident_id=incident_id,
            operation=operation,
            status=status,
            duration_ms=duration_ms,
            attributes=attributes or {},
        )
        with self._lock:
            self._records.append(record)
        return record

    def list(self, incident_id: str | None = None, limit: int = 100) -> list[TraceRecord]:
        with self._lock:
            records = [
                record
                for record in reversed(self._records)
                if incident_id is None or record.incident_id == incident_id
            ]
        return records[:limit]

    def summary(self) -> DashboardSummary:
        with self._lock:
            return _summarize(list(self._records))


class PostgresTraceRecorder:
    """Persist traces for cross-process dashboards and incident audits."""

    def __init__(self, database_url: str) -> None:
        self.database_url = database_url

    def record(
        self,
        operation: str,
        duration_ms: float,
        *,
        incident_id: str | None = None,
        status: str = "ok",
        attributes: dict[str, Any] | None = None,
    ) -> TraceRecord:
        record = TraceRecord(
            id=f"TR-{uuid4().hex[:12].upper()}",
            incident_id=incident_id,
            operation=operation,
            status=status,
            duration_ms=duration_ms,
            attributes=attributes or {},
        )
        with psycopg.connect(self.database_url) as connection:
            connection.execute(
                """
                INSERT INTO traces
                    (id, incident_id, operation, status, started_at, duration_ms, attributes)
                VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb)
                """,
                (
                    record.id,
                    record.incident_id,
                    record.operation,
                    record.status,
                    record.started_at,
                    record.duration_ms,
                    json.dumps(record.attributes),
                ),
            )
        return record

    def list(self, incident_id: str | None = None, limit: int = 100) -> list[TraceRecord]:
        query = "SELECT * FROM traces"
        params: list[Any] = []
        if incident_id is not None:
            query += " WHERE incident_id = %s"
            params.append(incident_id)
        query += " ORDER BY started_at DESC LIMIT %s"
        params.append(limit)
        with psycopg.connect(self.database_url, row_factory=dict_row) as connection:
            rows = connection.execute(query, params).fetchall()
        return [TraceRecord.model_validate(row) for row in rows]

    def summary(self) -> DashboardSummary:
        return _summarize(self.list(limit=10_000))
