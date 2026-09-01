from api.models import TrustLevel
from retrieval.hybrid import HybridIndex
from retrieval.models import ChunkRecord


def chunk(
    identifier: str, service: str, content: str, trust: TrustLevel = TrustLevel.OFFICIAL
) -> ChunkRecord:
    return ChunkRecord(
        id=identifier,
        document_id=f"D-{identifier}",
        source=f"{identifier}.md",
        version="1",
        service=service,
        environment="production",
        trust_level=trust,
        section="Runbook",
        content=content,
        position=0,
    )


def test_hybrid_search_filters_service_and_ranks_exact_signature() -> None:
    index = HybridIndex()
    index.add(
        [
            chunk("C1", "checkout-api", "connection pool exhausted after database retry"),
            chunk("C2", "checkout-api", "high CPU utilization response"),
            chunk("C3", "payments-api", "connection pool exhausted"),
        ]
    )

    hits = index.search(
        "connection pool exhausted", service="checkout-api", environment="production"
    )

    assert hits[0].chunk.id == "C1"
    assert all(hit.chunk.service == "checkout-api" for hit in hits)
    assert hits[0].keyword_rank == 1


def test_unrelated_scope_returns_no_hits() -> None:
    index = HybridIndex()
    index.add([chunk("C1", "checkout-api", "database timeout")])
    assert index.search("database timeout", service="unknown-api") == []
