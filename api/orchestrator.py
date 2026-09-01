"""Bounded incident investigation orchestration with grounded citations."""

from __future__ import annotations

import hashlib
import time
from collections.abc import Iterable

from api.models import (
    Evidence,
    Hypothesis,
    Incident,
    InvestigationOutput,
    RunMetrics,
    TimelineEvent,
    TrustLevel,
)
from api.observability import metrics
from api.security import scan_prompt_injection
from api.store import MemoryStore
from retrieval.hybrid import HybridIndex
from retrieval.models import SearchHit
from tools.gateway import ToolGateway, ToolPolicyError

CONFIG_VERSION = "baseline-hybrid-v1"


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


def _cause_for_alert(alert: str, hits: Iterable[SearchHit]) -> str:
    combined = " ".join([alert, *(hit.chunk.content for hit in hits)]).lower()
    if "connection pool" in combined or "pool_acquire" in combined:
        return "Database connection pool exhaustion is the leading hypothesis."
    if "queue" in combined and ("backlog" in combined or "depth" in combined):
        return "A slow or unavailable queue consumer is the leading hypothesis."
    if "503" in combined or "downstream" in combined:
        return "A downstream dependency failure is the leading hypothesis."
    if "latency" in combined or "timeout" in combined:
        return "Downstream latency or timeout propagation is the leading hypothesis."
    return "The available evidence does not identify a specific root cause."


class IncidentOrchestrator:
    """Coordinate retrieval, grounded composition, and approval-gated tool proposals."""

    def __init__(self, store: MemoryStore, index: HybridIndex, gateway: ToolGateway) -> None:
        self.store = store
        self.index = index
        self.gateway = gateway

    def investigate(self, incident: Incident) -> InvestigationOutput:
        started = time.perf_counter()
        query = f"{incident.service} {incident.environment} {incident.alert}"
        retrieval_started = time.perf_counter()
        hits = self.index.search(
            query,
            service=incident.service,
            environment=incident.environment,
            limit=10,
        )
        retrieval_ms = (time.perf_counter() - retrieval_started) * 1000
        metrics.observe("retrieval_latency_ms", retrieval_ms)

        evidence: list[Evidence] = []
        security_events: list[str] = []
        for position, hit in enumerate(hits, start=1):
            excerpt = hit.chunk.content[:1000]
            scan = scan_prompt_injection(excerpt)
            if scan.flagged:
                security_events.append(f"Prompt injection pattern isolated in {hit.chunk.source}.")
                metrics.increment("prompt_injection_total")
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
                    },
                )
            )

        composition_started = time.perf_counter()
        supporting = [item.id for item in evidence[:3] if not item.metadata["injection_flagged"]]
        insufficient = not supporting
        if insufficient:
            summary = (
                "Insufficient evidence. Approve the proposed read-only queries to gather "
                "incident-specific signals."
            )
            hypotheses: list[Hypothesis] = []
            timeline: list[TimelineEvent] = []
            metrics.increment("low_score_retrieval_total")
        else:
            cause = _cause_for_alert(incident.alert, hits)
            confidence = min(0.88, 0.48 + 0.1 * len(supporting))
            hypotheses = [
                Hypothesis(
                    cause=cause,
                    confidence=confidence,
                    supporting_evidence=supporting[:2],
                    contradictions=supporting[2:3],
                )
            ]
            timeline = [
                TimelineEvent(
                    at=incident.window_start.isoformat(),
                    event=f"Alert opened for {incident.service}: {incident.alert[:180]}",
                    evidence_ids=supporting[:1],
                )
            ]
            summary = (
                f"{cause} This is a grounded preliminary assessment; "
                "tool evidence is still pending."
            )

        proposals = []
        common_window = {
            "service": incident.service,
            "environment": incident.environment,
            "start": incident.window_start,
            "end": incident.window_end,
        }
        proposal_specs = [
            (
                "get_recent_deployments",
                common_window,
                "Correlate the alert with recent code changes.",
            ),
            (
                "search_logs",
                {**common_window, "query": incident.alert[:300], "limit": 100},
                "Collect bounded service errors matching the alert signature.",
            ),
            (
                "get_metrics",
                {**common_window, "metric": "http_error_rate", "labels": {}, "step_seconds": 60},
                "Confirm the error-rate trend during the incident window.",
            ),
        ]
        for tool, arguments, reason in proposal_specs:
            try:
                proposals.append(self.gateway.propose(incident, tool, arguments, reason))
            except ToolPolicyError as exc:
                security_events.append(f"Tool proposal blocked: {exc}")

        composition_ms = (time.perf_counter() - composition_started) * 1000
        total_ms = (time.perf_counter() - started) * 1000
        estimated_tokens = max(1, (len(query) + sum(len(item.excerpt) for item in evidence)) // 4)
        output = InvestigationOutput(
            incident_id=incident.id,
            summary=summary,
            timeline=timeline,
            hypotheses=hypotheses,
            next_queries=proposals,
            evidence=evidence,
            security_events=security_events,
            insufficient_evidence=insufficient,
            metrics=RunMetrics(
                retrieval_ms=retrieval_ms,
                composition_ms=composition_ms,
                total_ms=total_ms,
                estimated_tokens=estimated_tokens,
                estimated_cost_usd=0.0,
                config_version=CONFIG_VERSION,
            ),
        )
        validate_citations(output)
        metrics.increment("investigations_total")
        metrics.observe("investigation_latency_ms", total_ms)
        return self.store.save_investigation(output)
