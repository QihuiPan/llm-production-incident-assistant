"""Bounded incident investigation orchestration with grounded citations."""

from __future__ import annotations

import hashlib
import time
from typing import Literal

from api.llm import DeterministicLLMProvider, LLMService
from api.models import (
    Evidence,
    Incident,
    InvestigationOutput,
    RunMetrics,
    TrustLevel,
)
from api.observability import metrics
from api.repositories import Store
from api.security import redact_text, scan_prompt_injection
from api.tracing import MemoryTraceRecorder, TraceRecorder
from retrieval.advanced import AdvancedRetriever, SearchIndex
from tools.gateway import ToolGateway, ToolPolicyError

CONFIG_VERSION = "flagship-advanced-v2"


def _evidence_id(position: int) -> str:
    return f"E{position:03d}"


def _quote_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def validate_citations(output: InvestigationOutput) -> None:
    """Reject any generated identifier that does not map to stored evidence."""

    allowed = {item.id for item in output.evidence}
    cited: list[str] = []
    for event in output.timeline:
        cited.extend(event.evidence_ids)
    for hypothesis in output.hypotheses:
        cited.extend(hypothesis.supporting_evidence)
        cited.extend(hypothesis.contradictions)
    invalid = sorted(set(cited) - allowed)
    if invalid:
        metrics.increment("citation_validation_failure_total")
        raise ValueError(f"invalid evidence identifiers: {', '.join(invalid)}")


class IncidentOrchestrator:
    """Coordinate retrieval, grounded composition, and approval-gated tool proposals."""

    def __init__(
        self,
        store: Store,
        index: SearchIndex,
        gateway: ToolGateway,
        *,
        retrieval_mode: Literal["vector", "hybrid", "advanced"] = "advanced",
        llm_service: LLMService | None = None,
        traces: TraceRecorder | None = None,
    ) -> None:
        self.store = store
        self.index = index
        self.gateway = gateway
        self.retriever = AdvancedRetriever(index, mode=retrieval_mode)
        self.llm_service = llm_service or LLMService(DeterministicLLMProvider())
        self.traces = traces or MemoryTraceRecorder()

    def investigate(self, incident: Incident) -> InvestigationOutput:
        started = time.perf_counter()
        query = f"{incident.service} {incident.environment} {incident.alert}"
        retrieval_started = time.perf_counter()

        def record_retrieval_stage(
            name: str, duration_ms: float, attributes: dict[str, object]
        ) -> None:
            self.traces.record(
                f"retrieval.{name}",
                duration_ms,
                incident_id=incident.id,
                attributes=attributes,
            )

        hits = self.retriever.search(
            incident.alert,
            service=incident.service,
            environment=incident.environment,
            limit=10,
            observe=record_retrieval_stage,
        )
        retrieval_ms = (time.perf_counter() - retrieval_started) * 1000
        metrics.observe("retrieval_latency_ms", retrieval_ms)
        self.traces.record(
            "retrieval",
            retrieval_ms,
            incident_id=incident.id,
            attributes={"mode": self.retriever.mode, "hit_count": len(hits)},
        )

        evidence: list[Evidence] = []
        security_events: list[str] = []
        for position, hit in enumerate(hits, start=1):
            raw_excerpt = hit.chunk.content[:1000]
            scan = scan_prompt_injection(raw_excerpt)
            excerpt, redactions = redact_text(raw_excerpt)
            if scan.flagged:
                security_events.append(f"Prompt injection pattern isolated in {hit.chunk.source}.")
                metrics.increment("prompt_injection_total")
            if redactions:
                security_events.append(
                    f"Sensitive values were redacted from {hit.chunk.source}."
                )
                metrics.increment("retrieval_redactions_total", redactions)
            evidence.append(
                Evidence(
                    id=_evidence_id(position),
                    incident_id=incident.id,
                    source_type="document",
                    source=hit.chunk.source,
                    source_version=hit.chunk.version,
                    trust_level=TrustLevel(hit.chunk.trust_level),
                    excerpt=excerpt,
                    score=hit.score,
                    quote_hash=_quote_hash(excerpt),
                    metadata={
                        "chunk_id": hit.chunk.id,
                        "section": hit.chunk.section,
                        "keyword_rank": hit.keyword_rank,
                        "vector_rank": hit.vector_rank,
                        "injection_flagged": scan.flagged,
                        "redactions": redactions,
                    },
                )
            )

        composition_started = time.perf_counter()
        llm_result = self.llm_service.generate(incident, evidence)
        self.traces.record(
            "llm.generate",
            llm_result.latency_ms,
            incident_id=incident.id,
            attributes={
                "provider": llm_result.provider,
                "model": llm_result.model,
                "input_tokens": llm_result.usage.input_tokens,
                "output_tokens": llm_result.usage.output_tokens,
                "cost_usd": llm_result.usage.cost_usd,
                "cache_hit": llm_result.cache_hit,
                "fallback_used": llm_result.fallback_used,
            },
        )
        draft = llm_result.draft
        if draft.insufficient_evidence:
            metrics.increment("low_score_retrieval_total")
        if llm_result.cache_hit:
            metrics.increment("llm_cache_hit_total")
        if llm_result.fallback_used:
            metrics.increment("llm_fallback_total")

        proposals = []
        for query_draft in draft.next_queries:
            try:
                proposals.append(
                    self.gateway.propose(
                        incident,
                        query_draft.tool,
                        query_draft.gateway_arguments(),
                        query_draft.reason,
                    )
                )
            except ToolPolicyError as exc:
                security_events.append(f"Tool proposal blocked: {exc}")

        composition_ms = (time.perf_counter() - composition_started) * 1000
        total_ms = (time.perf_counter() - started) * 1000
        estimated_tokens = max(1, (len(query) + sum(len(item.excerpt) for item in evidence)) // 4)
        output = InvestigationOutput(
            incident_id=incident.id,
            summary=draft.summary,
            timeline=draft.timeline,
            hypotheses=draft.hypotheses,
            next_queries=proposals,
            evidence=evidence,
            security_events=security_events,
            insufficient_evidence=draft.insufficient_evidence,
            metrics=RunMetrics(
                retrieval_ms=retrieval_ms,
                composition_ms=composition_ms,
                total_ms=total_ms,
                estimated_tokens=estimated_tokens,
                estimated_cost_usd=llm_result.usage.cost_usd,
                config_version=CONFIG_VERSION,
                llm_ms=llm_result.latency_ms,
                input_tokens=llm_result.usage.input_tokens,
                output_tokens=llm_result.usage.output_tokens,
                provider=llm_result.provider,
                model=llm_result.model,
                cache_hit=llm_result.cache_hit,
                fallback_used=llm_result.fallback_used,
            ),
        )
        validate_citations(output)
        metrics.increment("investigations_total")
        metrics.observe("investigation_latency_ms", total_ms)
        self.traces.record(
            "investigation",
            total_ms,
            incident_id=incident.id,
            attributes={
                "evidence_count": len(evidence),
                "tool_proposals": len(proposals),
                "security_events": len(security_events),
            },
        )
        return self.store.save_investigation(output)
