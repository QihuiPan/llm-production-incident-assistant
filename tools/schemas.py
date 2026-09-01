"""Strict input contracts for every allowlisted read-only tool."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class TimeWindow(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    service: str = Field(min_length=2, max_length=80, pattern=r"^[a-zA-Z0-9._-]+$")
    environment: Literal["production", "staging", "development"]
    start: datetime
    end: datetime

    @model_validator(mode="after")
    def validate_time_window(self) -> TimeWindow:
        if self.end <= self.start:
            raise ValueError("end must be later than start")
        return self


class SearchLogsInput(TimeWindow):
    query: str = Field(min_length=1, max_length=500)
    limit: int = Field(default=100, ge=1, le=200)


class GetMetricsInput(TimeWindow):
    metric: Literal[
        "http_request_rate",
        "http_error_rate",
        "http_latency_p95",
        "cpu_utilization",
        "memory_utilization",
        "queue_depth",
    ]
    labels: dict[str, str] = Field(default_factory=dict)
    step_seconds: int = Field(default=60, ge=15, le=3600)


class GetDeploymentsInput(TimeWindow):
    pass


class GetDependenciesInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    service: str = Field(min_length=2, max_length=80, pattern=r"^[a-zA-Z0-9._-]+$")


TOOL_SCHEMAS = {
    "search_logs": SearchLogsInput,
    "get_metrics": GetMetricsInput,
    "get_recent_deployments": GetDeploymentsInput,
    "get_service_dependencies": GetDependenciesInput,
}
