"""CLI-compatible ingestion worker boundary for queue integration."""

from __future__ import annotations

from dataclasses import dataclass

from api.models import TrustLevel
from retrieval.hybrid import HybridIndex
from retrieval.ingest import ingest_bytes


@dataclass(frozen=True)
class IngestionJob:
    filename: str
    payload: bytes
    service: str
    environment: str | None
    version: str
    trust_level: TrustLevel


def run_job(index: HybridIndex, job: IngestionJob) -> tuple[str, int, bool]:
    """Run the same validated ingestion path used by the HTTP API."""

    document, count, flagged = ingest_bytes(
        index,
        filename=job.filename,
        payload=job.payload,
        service=job.service,
        environment=job.environment,
        version=job.version,
        trust_level=job.trust_level,
    )
    return document.id, count, flagged
