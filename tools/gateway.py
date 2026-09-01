"""Allowlisted, approval-gated, audited execution for read-only tools."""

from __future__ import annotations

from collections import Counter
from datetime import timedelta
from typing import Any
from uuid import uuid4

from pydantic import ValidationError

from api.models import Incident, ToolExecutionResult, ToolProposal
from api.observability import metrics
from api.security import redact_value
from api.store import MemoryStore
from tools.adapters import ADAPTERS
from tools.schemas import TOOL_SCHEMAS, TimeWindow


class ToolPolicyError(ValueError):
    """Raised when a requested tool violates an authorization or budget policy."""


class ToolGateway:
    """Validate, authorize, budget, execute, and audit read-only tool calls."""

    def __init__(
        self,
        store: MemoryStore,
        *,
        max_calls_per_incident: int = 3,
        max_window_hours: int = 24,
        max_rows: int = 200,
    ) -> None:
        self.store = store
        self.max_calls_per_incident = max_calls_per_incident
        self.max_window = timedelta(hours=max_window_hours)
        self.max_rows = max_rows
        self._proposed_counts: Counter[str] = Counter()

    def propose(
        self, incident: Incident, tool: str, arguments: dict[str, Any], reason: str
    ) -> ToolProposal:
        """Create a pending call only after strict schema and policy validation."""

        if tool not in TOOL_SCHEMAS or tool not in ADAPTERS:
            metrics.increment("tool_not_allowlisted_total")
            raise ToolPolicyError(f"tool is not allowlisted: {tool}")
        if self._proposed_counts[incident.id] >= self.max_calls_per_incident:
            metrics.increment("tool_budget_exceeded_total")
            raise ToolPolicyError("tool-call budget exceeded")
        try:
            validated = TOOL_SCHEMAS[tool].model_validate(arguments)
        except ValidationError as exc:
            metrics.increment("tool_schema_failure_total")
            raise ToolPolicyError(str(exc)) from exc
        if isinstance(validated, TimeWindow):
            if validated.end - validated.start > self.max_window:
                raise ToolPolicyError("tool time window exceeds the configured limit")
            if (
                validated.service != incident.service
                or validated.environment != incident.environment
            ):
                raise ToolPolicyError("tool scope must match the incident service and environment")
        if tool == "search_logs" and validated.limit > self.max_rows:
            raise ToolPolicyError("log row limit exceeds the configured maximum")

        proposal = ToolProposal(
            id=f"TC-{uuid4().hex[:12].upper()}",
            tool=tool,
            arguments=validated.model_dump(mode="json"),
            reason=reason,
        )
        self._proposed_counts[incident.id] += 1
        return proposal

    def approve_and_execute(self, call_id: str, approved_by: str) -> ToolExecutionResult:
        """Execute one pending call after recording explicit human approval."""

        incident_id, proposal = self.store.get_tool_call(call_id)
        if proposal.status != "PENDING":
            raise ToolPolicyError(f"tool call is not pending: {proposal.status}")
        if not approved_by.strip():
            raise ToolPolicyError("approved_by is required")
        schema = TOOL_SCHEMAS[proposal.tool]
        validated = schema.model_validate(proposal.arguments)
        approved = proposal.model_copy(update={"status": "APPROVED"})
        self.store.update_tool_call(incident_id, approved)
        with metrics.timer("tool_latency_ms"):
            raw_result = ADAPTERS[proposal.tool](validated)
        clean_result, redactions = redact_value(raw_result)
        executed = approved.model_copy(update={"status": "EXECUTED"})
        self.store.update_tool_call(incident_id, executed)
        metrics.increment("tool_calls_total")
        metrics.increment("tool_output_redactions_total", redactions)
        return ToolExecutionResult(
            tool_call=executed,
            result=clean_result,
            redactions=redactions,
            audit_id=f"AUD-{uuid4().hex[:12].upper()}",
        )
