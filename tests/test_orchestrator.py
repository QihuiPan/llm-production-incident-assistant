from api.models import TrustLevel
from api.orchestrator import IncidentOrchestrator, validate_citations
from api.store import MemoryStore
from retrieval.chunking import chunk_document
from retrieval.hybrid import HybridIndex
from retrieval.models import DocumentRecord
from tools.gateway import ToolGateway


def test_investigation_is_grounded_and_proposes_read_only_tools(incident) -> None:
    store = MemoryStore()
    store.add_incident(incident)
    index = HybridIndex()
    document = DocumentRecord(
        id="DOC-1",
        source="checkout-runbook.md",
        version="2",
        service="checkout-api",
        environment="production",
        trust_level=TrustLevel.OFFICIAL,
        content=(
            "# Database\nConnection pool exhausted errors follow long transactions. "
            "password=hunter2"
        ),
    )
    index.add(chunk_document(document, target_words=50, overlap_words=5))
    orchestrator = IncidentOrchestrator(store, index, ToolGateway(store))

    output = orchestrator.investigate(incident)

    validate_citations(output)
    assert "connection pool" in output.hypotheses[0].cause.lower()
    assert output.hypotheses[0].supporting_evidence[0] in {item.id for item in output.evidence}
    assert {item.tool for item in output.next_queries} == {
        "get_recent_deployments",
        "search_logs",
        "get_metrics",
    }
    assert output.metrics.estimated_cost_usd == 0
    assert "hunter2" not in output.evidence[0].excerpt
    assert any("redacted" in event for event in output.security_events)


def test_no_evidence_returns_safe_degradation(incident) -> None:
    store = MemoryStore()
    store.add_incident(incident)
    orchestrator = IncidentOrchestrator(store, HybridIndex(), ToolGateway(store))

    output = orchestrator.investigate(incident)

    assert output.insufficient_evidence is True
    assert output.hypotheses == []
    assert "Insufficient evidence" in output.summary
