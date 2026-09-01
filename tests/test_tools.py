from datetime import timedelta

import pytest

from api.store import MemoryStore
from tools.gateway import ToolGateway, ToolPolicyError


def test_tool_requires_allowlist_and_scope(incident) -> None:
    store = MemoryStore()
    store.add_incident(incident)
    gateway = ToolGateway(store)

    with pytest.raises(ToolPolicyError, match="not allowlisted"):
        gateway.propose(incident, "restart_service", {}, "unsafe")

    with pytest.raises(ToolPolicyError, match="scope"):
        gateway.propose(
            incident,
            "search_logs",
            {
                "service": "payments-api",
                "environment": "production",
                "start": incident.window_start,
                "end": incident.window_end,
                "query": "error",
                "limit": 10,
            },
            "cross-service query",
        )


def test_tool_schema_forbids_unknown_arguments(incident) -> None:
    store = MemoryStore()
    gateway = ToolGateway(store)
    arguments = {
        "service": incident.service,
        "environment": incident.environment,
        "start": incident.window_start,
        "end": incident.window_end,
        "query": "error",
        "limit": 10,
        "shell": "rm -rf /",
    }
    with pytest.raises(ToolPolicyError):
        gateway.propose(incident, "search_logs", arguments, "test")


def test_approved_tool_executes_once_and_is_audited(incident) -> None:
    store = MemoryStore()
    store.add_incident(incident)
    gateway = ToolGateway(store)
    proposal = gateway.propose(
        incident,
        "get_recent_deployments",
        {
            "service": incident.service,
            "environment": incident.environment,
            "start": incident.window_start,
            "end": incident.window_end,
        },
        "correlate deployment",
    )
    store.update_tool_call(incident.id, proposal)

    result = gateway.approve_and_execute(proposal.id, "operator@example.invalid")

    assert result.tool_call.status == "EXECUTED"
    assert result.audit_id.startswith("AUD-")
    with pytest.raises(ToolPolicyError, match="not pending"):
        gateway.approve_and_execute(proposal.id, "operator@example.invalid")


def test_tool_time_window_is_bounded(incident) -> None:
    store = MemoryStore()
    gateway = ToolGateway(store, max_window_hours=1)
    with pytest.raises(ToolPolicyError, match="time window"):
        gateway.propose(
            incident,
            "get_metrics",
            {
                "service": incident.service,
                "environment": incident.environment,
                "start": incident.window_start - timedelta(hours=2),
                "end": incident.window_end,
                "metric": "http_error_rate",
            },
            "oversized query",
        )
