"""Deterministic hybrid retrieval with reciprocal rank fusion."""

from __future__ import annotations

import hashlib
import math
import re
from collections import Counter

from retrieval.models import ChunkRecord, SearchHit

TOKEN_RE = re.compile(r"[A-Za-z0-9_.:/-]+")
TRUST_WEIGHTS = {"official": 1.15, "reviewed": 1.05, "unverified": 0.9}


def tokenize(text: str) -> list[str]:
    """Tokenize operational text while preserving common error-signature punctuation."""

    return [token.lower() for token in TOKEN_RE.findall(text)]


def hashed_embedding(text: str, dimensions: int = 768) -> list[float]:
    """Create a local deterministic embedding suitable for a zero-secret demo."""

    vector = [0.0] * dimensions
    for token in tokenize(text):
        digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
        index = int.from_bytes(digest[:4], "big") % dimensions
        sign = -1.0 if digest[4] & 1 else 1.0
        vector[index] += sign
    norm = math.sqrt(sum(item * item for item in vector)) or 1.0
    return [item / norm for item in vector]


def cosine(left: list[float], right: list[float]) -> float:
    return sum(a * b for a, b in zip(left, right, strict=True))


class HybridIndex:
    """In-memory baseline mirroring PostgreSQL FTS plus pgvector behavior."""

    def __init__(self) -> None:
        self._chunks: list[ChunkRecord] = []
        self._embeddings: dict[str, list[float]] = {}

    @property
    def chunks(self) -> tuple[ChunkRecord, ...]:
        return tuple(self._chunks)

    def add(self, chunks: list[ChunkRecord]) -> None:
        for chunk in chunks:
            self._chunks = [item for item in self._chunks if item.id != chunk.id]
            self._chunks.append(chunk)
            self._embeddings[chunk.id] = hashed_embedding(chunk.content)

    def search(
        self,
        query: str,
        *,
        service: str | None = None,
        environment: str | None = None,
        limit: int = 10,
    ) -> list[SearchHit]:
        """Fuse keyword and vector rankings, then apply provenance-aware reranking."""

        candidates = [
            chunk
            for chunk in self._chunks
            if (service is None or chunk.service == service)
            and (environment is None or chunk.environment in (None, environment))
        ]
        if not candidates:
            return []

        query_terms = Counter(tokenize(query))
        doc_frequency = Counter()
        tokenized: dict[str, list[str]] = {}
        for chunk in candidates:
            terms = tokenize(chunk.content)
            tokenized[chunk.id] = terms
            doc_frequency.update(set(terms))

        keyword_scores: dict[str, float] = {}
        average_length = sum(len(value) for value in tokenized.values()) / len(tokenized)
        for chunk in candidates:
            term_counts = Counter(tokenized[chunk.id])
            length = len(tokenized[chunk.id]) or 1
            score = 0.0
            for term, query_count in query_terms.items():
                frequency = term_counts[term]
                if not frequency:
                    continue
                inverse_frequency = math.log(
                    1 + (len(candidates) - doc_frequency[term] + 0.5) / (doc_frequency[term] + 0.5)
                )
                normalized = (
                    frequency * 2.2 / (frequency + 1.2 * (0.25 + 0.75 * length / average_length))
                )
                score += inverse_frequency * normalized * query_count
            keyword_scores[chunk.id] = score

        query_embedding = hashed_embedding(query)
        vector_scores = {
            chunk.id: cosine(query_embedding, self._embeddings[chunk.id]) for chunk in candidates
        }
        keyword_order = sorted(candidates, key=lambda item: keyword_scores[item.id], reverse=True)
        vector_order = sorted(candidates, key=lambda item: vector_scores[item.id], reverse=True)
        keyword_ranks = {item.id: rank for rank, item in enumerate(keyword_order, start=1)}
        vector_ranks = {item.id: rank for rank, item in enumerate(vector_order, start=1)}

        hits: list[SearchHit] = []
        for chunk in candidates:
            keyword_rank = keyword_ranks[chunk.id]
            vector_rank = vector_ranks[chunk.id]
            fused = 1 / (60 + keyword_rank) + 1 / (60 + vector_rank)
            if keyword_scores[chunk.id] <= 0 and vector_scores[chunk.id] <= 0:
                continue
            trust = TRUST_WEIGHTS[chunk.trust_level.value]
            injection_penalty = 0.35 if chunk.injection_flagged else 1.0
            score = fused * trust * injection_penalty
            hits.append(SearchHit(chunk, score, keyword_rank, vector_rank))

        return sorted(hits, key=lambda item: item.score, reverse=True)[:limit]
