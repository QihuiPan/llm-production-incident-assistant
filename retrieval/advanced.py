"""Query planning, multi-query fusion, reranking, and context compression."""

from __future__ import annotations

import re
import time
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal, Protocol

from retrieval.hybrid import tokenize
from retrieval.models import SearchHit

ERROR_SIGNATURE_RE = re.compile(
    r"\b(?:HTTP\s+\d{3}|[A-Z][A-Za-z]+(?:Error|Exception)|[a-z_]+_timeout|[a-z_]+_exhausted)\b",
    re.IGNORECASE,
)


class SearchIndex(Protocol):
    """Minimal search interface shared by memory and PostgreSQL indexes."""

    def search(
        self,
        query: str,
        *,
        service: str | None = None,
        environment: str | None = None,
        limit: int = 10,
    ) -> list[SearchHit]: ...


@dataclass(frozen=True)
class QueryPlan:
    """Incident-specific queries derived from an alert without model access."""

    rewritten: str
    subqueries: tuple[str, ...]
    error_signatures: tuple[str, ...]


class QueryPlanner:
    """Extract operational hints and produce bounded, non-recursive subqueries."""

    def plan(self, alert: str, service: str) -> QueryPlan:
        signatures = tuple(dict.fromkeys(ERROR_SIGNATURE_RE.findall(alert)))
        hints = []
        lowered = alert.lower()
        for term in ("deployment", "database", "queue", "latency", "timeout", "memory", "cpu"):
            if term in lowered:
                hints.append(term)
        rewritten = " ".join([service, *signatures, *hints, alert]).strip()
        subqueries = [rewritten]
        if signatures:
            subqueries.append(f"{service} {' '.join(signatures)} root cause runbook")
        if "deployment" in lowered or "after" in lowered:
            subqueries.append(f"{service} recent deployment regression postmortem")
        if any(term in lowered for term in ("503", "timeout", "downstream")):
            subqueries.append(f"{service} downstream dependency failure")
        return QueryPlan(rewritten, tuple(dict.fromkeys(subqueries[:4])), signatures)


class TrustAwareReranker:
    """Rerank candidates using relevance, provenance, section, and security signals."""

    def rerank(self, query: str, hits: list[SearchHit]) -> list[SearchHit]:
        query_terms = set(tokenize(query))

        def score(hit: SearchHit) -> float:
            chunk_terms = set(tokenize(hit.chunk.content))
            overlap = len(query_terms & chunk_terms) / max(len(query_terms), 1)
            section_bonus = 0.12 if any(
                term in hit.chunk.section.lower()
                for term in ("root cause", "symptom", "recovery", "incident", "database")
            ) else 0.0
            provenance = {"official": 0.15, "reviewed": 0.08, "unverified": 0.0}[
                hit.chunk.trust_level.value
            ]
            security_penalty = 0.5 if hit.chunk.injection_flagged else 0.0
            return hit.score + overlap * 0.5 + section_bonus + provenance - security_penalty

        return sorted(hits, key=score, reverse=True)


class ContextCompressor:
    """Remove near-duplicates and enforce a deterministic context token budget."""

    def __init__(self, token_budget: int = 3200, similarity_threshold: float = 0.82) -> None:
        self.token_budget = token_budget
        self.similarity_threshold = similarity_threshold

    @staticmethod
    def _similarity(left: str, right: str) -> float:
        left_terms = set(tokenize(left))
        right_terms = set(tokenize(right))
        if not left_terms or not right_terms:
            return 0.0
        return len(left_terms & right_terms) / len(left_terms | right_terms)

    def compress(self, hits: list[SearchHit], limit: int) -> list[SearchHit]:
        selected: list[SearchHit] = []
        consumed = 0
        for hit in hits:
            if any(
                self._similarity(hit.chunk.content, existing.chunk.content)
                >= self.similarity_threshold
                for existing in selected
            ):
                continue
            estimated_tokens = max(1, len(hit.chunk.content) // 4)
            if consumed + estimated_tokens > self.token_budget:
                continue
            selected.append(hit)
            consumed += estimated_tokens
            if len(selected) >= limit:
                break
        return selected


class AdvancedRetriever:
    """Support vector-only, hybrid baseline, and decomposed advanced retrieval."""

    def __init__(
        self,
        index: SearchIndex,
        *,
        mode: Literal["vector", "hybrid", "advanced"] = "advanced",
        planner: QueryPlanner | None = None,
        reranker: TrustAwareReranker | None = None,
        compressor: ContextCompressor | None = None,
    ) -> None:
        self.index = index
        self.mode = mode
        self.planner = planner or QueryPlanner()
        self.reranker = reranker or TrustAwareReranker()
        self.compressor = compressor or ContextCompressor()

    def search(
        self,
        alert: str,
        *,
        service: str,
        environment: str,
        limit: int = 10,
        observe: Callable[[str, float, dict[str, object]], None] | None = None,
    ) -> list[SearchHit]:
        plan_started = time.perf_counter()
        plan = self.planner.plan(alert, service)
        if observe:
            observe(
                "planning",
                (time.perf_counter() - plan_started) * 1000,
                {"subqueries": len(plan.subqueries)},
            )
        if self.mode != "advanced":
            search_started = time.perf_counter()
            hits = self.index.search(
                plan.rewritten,
                service=service,
                environment=environment,
                limit=max(limit * 2, 20),
            )
            if observe:
                observe(
                    "candidate_search",
                    (time.perf_counter() - search_started) * 1000,
                    {"candidates": len(hits), "mode": self.mode},
                )
            if self.mode == "vector":
                hits = sorted(
                    hits,
                    key=lambda hit: hit.vector_rank or 1_000_000,
                )
            compression_started = time.perf_counter()
            selected = self.compressor.compress(hits, limit)
            if observe:
                observe(
                    "compression",
                    (time.perf_counter() - compression_started) * 1000,
                    {"selected": len(selected)},
                )
            return selected

        fused_scores: defaultdict[str, float] = defaultdict(float)
        candidates: dict[str, SearchHit] = {}
        search_started = time.perf_counter()
        for subquery in plan.subqueries:
            hits = self.index.search(
                subquery,
                service=service,
                environment=environment,
                limit=max(limit * 2, 20),
            )
            for rank, hit in enumerate(hits, start=1):
                candidates[hit.chunk.id] = hit
                fused_scores[hit.chunk.id] += 1 / (60 + rank)
        if observe:
            observe(
                "candidate_search",
                (time.perf_counter() - search_started) * 1000,
                {"candidates": len(candidates), "mode": self.mode},
            )

        fused = [
            SearchHit(
                chunk=hit.chunk,
                score=hit.score + fused_scores[identifier],
                keyword_rank=hit.keyword_rank,
                vector_rank=hit.vector_rank,
            )
            for identifier, hit in candidates.items()
        ]
        rerank_started = time.perf_counter()
        reranked = self.reranker.rerank(plan.rewritten, fused)
        if observe:
            observe(
                "reranking",
                (time.perf_counter() - rerank_started) * 1000,
                {"candidates": len(reranked)},
            )
        compression_started = time.perf_counter()
        selected = self.compressor.compress(reranked, limit)
        if observe:
            observe(
                "compression",
                (time.perf_counter() - compression_started) * 1000,
                {"selected": len(selected)},
            )
        return selected
