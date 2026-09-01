"""Shared API and domain models."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator


def utc_now() -> datetime:
    """Return an aware UTC timestamp."""

    return datetime.now(UTC)


class IncidentStatus(StrEnum):
    OPEN = "OPEN"
    INVESTIGATING = "INVESTIGATING"
    RESOLVED = "RESOLVED"


class TrustLevel(StrEnum):
    OFFICIAL = "official"
    REVIEWED = "reviewed"
    UNVERIFIED = "unverified"


class IncidentCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    service: str = Field(min_length=2, max_length=80, pattern=r"^[a-zA-Z0-9._-]+$")
    environment: Literal["production", "staging", "development"]
    alert: str = Field(min_length=8, max_length=4000)
    window_start: datetime
    window_end: datetime

    @model_validator(mode="after")
    def validate_window(self) -> IncidentCreate:
        if self.window_end <= self.window_start:
            raise ValueError("window_end must be later than window_start")
        if (self.window_end - self.window_start).total_seconds() > 7 * 24 * 3600:
            raise ValueError("incident windows may not exceed seven days")
        return self


class Incident(IncidentCreate):
    id: str = Field(default_factory=lambda: f"INC-{uuid4().hex[:10].upper()}")
    status: IncidentStatus = IncidentStatus.OPEN
    created_at: datetime = Field(default_factory=utc_now)


class DocumentIngestResponse(BaseModel):
    document_id: str
    chunks_created: int
    injection_flagged: bool


class Evidence(BaseModel):
    id: str
    incident_id: str
    source_type: Literal["document", "tool"]
    source: str
    source_version: str
    trust_level: TrustLevel
    excerpt: str
    score: float = Field(ge=0)
    quote_hash: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class TimelineEvent(BaseModel):
    at: str
    event: str
    evidence_ids: list[str]


class Hypothesis(BaseModel):
    cause: str
    confidence: float = Field(ge=0, le=1)
    supporting_evidence: list[str]
    contradictions: list[str] = Field(default_factory=list)


class ToolProposal(BaseModel):
    id: str
    tool: str
    arguments: dict[str, Any]
    reason: str
    status: Literal["PENDING", "APPROVED", "EXECUTED", "REJECTED", "FAILED"] = "PENDING"


class RunMetrics(BaseModel):
    retrieval_ms: float = Field(ge=0)
    composition_ms: float = Field(ge=0)
    total_ms: float = Field(ge=0)
    estimated_tokens: int = Field(ge=0)
    estimated_cost_usd: float = Field(ge=0)
    config_version: str


class InvestigationOutput(BaseModel):
    incident_id: str
    summary: str
    timeline: list[TimelineEvent]
    hypotheses: list[Hypothesis]
    next_queries: list[ToolProposal]
    evidence: list[Evidence]
    security_events: list[str] = Field(default_factory=list)
    insufficient_evidence: bool = False
    metrics: RunMetrics


class ToolApproval(BaseModel):
    approved_by: str = Field(min_length=2, max_length=120)


class ToolExecutionResult(BaseModel):
    tool_call: ToolProposal
    result: list[dict[str, Any]]
    redactions: int
    audit_id: str


class FeedbackCreate(BaseModel):
    correctness: int = Field(ge=1, le=5)
    citation_quality: int = Field(ge=1, le=5)
    helpfulness: int = Field(ge=1, le=5)
    label: str = Field(max_length=80)
    correction: str | None = Field(default=None, max_length=4000)


class FeedbackRecord(FeedbackCreate):
    incident_id: str
    created_at: datetime = Field(default_factory=utc_now)


class EvaluationRequest(BaseModel):
    dataset: str = "evals/datasets/synthetic_incidents.jsonl"
    strict: bool = True


class EvaluationReport(BaseModel):
    cases: int
    root_cause_accuracy: float
    evidence_recall_at_10: float
    citation_precision: float
    unsupported_claim_rate: float
    tool_selection_accuracy: float
    p95_latency_ms: float
    passed: bool
    config_version: str
