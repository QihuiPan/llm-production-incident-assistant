"""Retrieval-domain records."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from api.models import TrustLevel


@dataclass(frozen=True)
class DocumentRecord:
    id: str
    source: str
    version: str
    service: str
    environment: str | None
    trust_level: TrustLevel
    content: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ChunkRecord:
    id: str
    document_id: str
    source: str
    version: str
    service: str
    environment: str | None
    trust_level: TrustLevel
    section: str
    content: str
    position: int
    injection_flagged: bool = False


@dataclass(frozen=True)
class SearchHit:
    chunk: ChunkRecord
    score: float
    keyword_rank: int | None
    vector_rank: int | None
