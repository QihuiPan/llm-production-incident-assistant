"""Repository contracts shared by memory and PostgreSQL implementations."""

from __future__ import annotations

from typing import Protocol

from api.models import (
    EvaluationReport,
    Evidence,
    FeedbackRecord,
    Incident,
    InvestigationOutput,
    ToolProposal,
)


class Store(Protocol):
    """Persistence contract used by orchestration and API layers."""

    def add_incident(self, incident: Incident) -> Incident: ...

    def get_incident(self, incident_id: str) -> Incident: ...

    def save_investigation(self, output: InvestigationOutput) -> InvestigationOutput: ...

    def get_investigation(self, incident_id: str) -> InvestigationOutput: ...

    def list_evidence(self, incident_id: str) -> list[Evidence]: ...

    def add_evidence(self, incident_id: str, evidence: Evidence) -> Evidence: ...

    def get_tool_call(self, call_id: str) -> tuple[str, ToolProposal]: ...

    def update_tool_call(self, incident_id: str, proposal: ToolProposal) -> None: ...

    def record_approval(self, call_id: str, approved_by: str) -> None: ...

    def add_feedback(self, feedback: FeedbackRecord) -> FeedbackRecord: ...

    def save_evaluation(self, report: EvaluationReport) -> EvaluationReport: ...

    def list_evaluations(self) -> list[EvaluationReport]: ...
