"""Load versioned demo runbooks and postmortems into the local index."""

from __future__ import annotations

from pathlib import Path

from api.models import TrustLevel
from retrieval.chunking import chunk_document
from retrieval.hybrid import HybridIndex
from retrieval.models import DocumentRecord

DATA_ROOT = Path(__file__).resolve().parents[1] / "data" / "demo"


def load_demo_documents(index: HybridIndex) -> int:
    """Index bundled, non-sensitive documents and return the chunk count."""

    records = [
        ("checkout-api", "production", "official", "checkout-api-runbook.md"),
        ("checkout-api", "production", "reviewed", "checkout-db-pool-postmortem.md"),
        ("payments-api", "production", "official", "payments-api-runbook.md"),
        ("inventory-api", "production", "official", "inventory-api-runbook.md"),
    ]
    count = 0
    for number, (service, environment, trust, filename) in enumerate(records, start=1):
        path = DATA_ROOT / filename
        document = DocumentRecord(
            id=f"DEMO-DOC-{number:03d}",
            source=filename,
            version="1.0.0",
            service=service,
            environment=environment,
            trust_level=TrustLevel(trust),
            content=path.read_text(encoding="utf-8"),
        )
        chunks = chunk_document(document, target_words=160, overlap_words=20)
        index.add(chunks)
        count += len(chunks)
    return count
