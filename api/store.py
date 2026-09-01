"""Thread-safe in-memory repository used by the local demo and tests."""

from __future__ import annotations

from threading import RLock

from api.models import Evidence, FeedbackRecord, Incident, InvestigationOutput, ToolProposal


class NotFoundError(KeyError):
    """Raised when a requested domain record does not exist."""


class MemoryStore:
    """Small repository whose interface can be replaced by PostgreSQL in deployment."""

    def __init__(self) -> None:
        self._lock = RLock()
        self._incidents: dict[str, Incident] = {}
        self._investigations: dict[str, InvestigationOutput] = {}
        self._evidence: dict[str, list[Evidence]] = {}
        self._tool_calls: dict[str, tuple[str, ToolProposal]] = {}
        self._feedback: dict[str, list[FeedbackRecord]] = {}

    def add_incident(self, incident: Incident) -> Incident:
        with self._lock:
            self._incidents[incident.id] = incident
        return incident

    def get_incident(self, incident_id: str) -> Incident:
        try:
            return self._incidents[incident_id]
        except KeyError as exc:
            raise NotFoundError(incident_id) from exc

    def save_investigation(self, output: InvestigationOutput) -> InvestigationOutput:
        with self._lock:
            self._investigations[output.incident_id] = output
            self._evidence[output.incident_id] = list(output.evidence)
            for proposal in output.next_queries:
                self._tool_calls[proposal.id] = (output.incident_id, proposal)
        return output

    def get_investigation(self, incident_id: str) -> InvestigationOutput:
        try:
            return self._investigations[incident_id]
        except KeyError as exc:
            raise NotFoundError(incident_id) from exc

    def list_evidence(self, incident_id: str) -> list[Evidence]:
        self.get_incident(incident_id)
        return list(self._evidence.get(incident_id, []))

    def add_evidence(self, incident_id: str, evidence: Evidence) -> Evidence:
        self.get_incident(incident_id)
        with self._lock:
            self._evidence.setdefault(incident_id, []).append(evidence)
        return evidence

    def get_tool_call(self, call_id: str) -> tuple[str, ToolProposal]:
        try:
            return self._tool_calls[call_id]
        except KeyError as exc:
            raise NotFoundError(call_id) from exc

    def update_tool_call(self, incident_id: str, proposal: ToolProposal) -> None:
        with self._lock:
            self._tool_calls[proposal.id] = (incident_id, proposal)

    def add_feedback(self, feedback: FeedbackRecord) -> FeedbackRecord:
        self.get_incident(feedback.incident_id)
        with self._lock:
            self._feedback.setdefault(feedback.incident_id, []).append(feedback)
        return feedback

    def clear(self) -> None:
        """Reset process state for deterministic tests."""

        with self._lock:
            self._incidents.clear()
            self._investigations.clear()
            self._evidence.clear()
            self._tool_calls.clear()
            self._feedback.clear()
