"""Reproducible offline benchmark for retrieval, grounding, and tool selection."""

from __future__ import annotations

import argparse
import json
import math
from datetime import datetime
from pathlib import Path
from statistics import quantiles
from typing import Any

from api.models import EvaluationComparison, EvaluationReport, Incident, IncidentCreate
from api.orchestrator import CONFIG_VERSION, IncidentOrchestrator, validate_citations
from api.store import MemoryStore
from retrieval.hybrid import HybridIndex
from retrieval.seed import load_demo_documents
from tools.gateway import ToolGateway

THRESHOLDS = {
    "root_cause_accuracy": 0.80,
    "evidence_recall_at_10": 0.90,
    "citation_precision": 0.95,
    "unsupported_claim_rate": 0.05,
    "tool_selection_accuracy": 0.85,
    "p95_latency_ms": 12_000.0,
}


def _percentile_95(values: list[float]) -> float:
    if not values:
        return 0.0
    if len(values) < 20:
        ordered = sorted(values)
        return ordered[min(len(ordered) - 1, math.ceil(len(ordered) * 0.95) - 1)]
    return quantiles(values, n=100, method="inclusive")[94]


def _load_cases(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def run_evaluation(
    path: Path, *, strict: bool = True, retrieval_mode: str = "advanced"
) -> EvaluationReport:
    """Run every labelled case against a clean, versioned baseline configuration."""

    cases = _load_cases(path)
    if not cases:
        raise ValueError("evaluation dataset is empty")

    root_matches = 0
    evidence_matches = 0
    valid_citations = 0
    citation_checks = 0
    unsupported_claims = 0
    claims = 0
    tool_matches = 0
    tool_checks = 0
    latencies: list[float] = []

    index = HybridIndex()
    load_demo_documents(index)
    store = MemoryStore()
    gateway = ToolGateway(store)
    orchestrator = IncidentOrchestrator(store, index, gateway, retrieval_mode=retrieval_mode)  # type: ignore[arg-type]
    failure_counts = {
        "root_cause": 0,
        "evidence": 0,
        "citation": 0,
        "unsupported_claim": 0,
        "tool_selection": 0,
    }
    split_totals: dict[str, int] = {}
    split_root_matches: dict[str, int] = {}
    split_evidence_matches: dict[str, int] = {}

    for case in cases:
        incident = Incident(
            **IncidentCreate(
                service=case["service"],
                environment=case["environment"],
                alert=case["alert"],
                window_start=datetime.fromisoformat(case["window_start"]),
                window_end=datetime.fromisoformat(case["window_end"]),
            ).model_dump()
        )
        store.add_incident(incident)
        output = orchestrator.investigate(incident)
        latencies.append(output.metrics.total_ms)

        cause = output.hypotheses[0].cause.lower() if output.hypotheses else ""
        split = str(case.get("split", "unassigned"))
        split_totals[split] = split_totals.get(split, 0) + 1
        root_match = int(any(term.lower() in cause for term in case["gold_root_cause_terms"]))
        root_matches += root_match
        split_root_matches[split] = split_root_matches.get(split, 0) + root_match
        failure_counts["root_cause"] += 1 - root_match
        sources = {item.source for item in output.evidence[:10]}
        evidence_match = int(any(source in sources for source in case["gold_evidence_sources"]))
        evidence_matches += evidence_match
        split_evidence_matches[split] = split_evidence_matches.get(split, 0) + evidence_match
        failure_counts["evidence"] += 1 - evidence_match

        try:
            validate_citations(output)
            valid_citations += 1
        except ValueError:
            failure_counts["citation"] += 1
        citation_checks += 1
        unsupported = int(bool(output.hypotheses) and not output.hypotheses[0].supporting_evidence)
        unsupported_claims += unsupported
        failure_counts["unsupported_claim"] += unsupported
        claims += int(bool(output.hypotheses))

        proposed = {item.tool for item in output.next_queries}
        expected = set(case["expected_tools"])
        tool_matches += len(proposed & expected)
        tool_checks += len(expected)
        failure_counts["tool_selection"] += len(expected - proposed)

    split_metrics = {
        split: {
            "cases": float(total),
            "root_cause_accuracy": split_root_matches.get(split, 0) / total,
            "evidence_recall_at_10": split_evidence_matches.get(split, 0) / total,
        }
        for split, total in sorted(split_totals.items())
    }

    report_values = {
        "cases": len(cases),
        "root_cause_accuracy": root_matches / len(cases),
        "evidence_recall_at_10": evidence_matches / len(cases),
        "citation_precision": valid_citations / citation_checks,
        "unsupported_claim_rate": unsupported_claims / max(claims, 1),
        "tool_selection_accuracy": tool_matches / max(tool_checks, 1),
        "p95_latency_ms": _percentile_95(latencies),
    }
    passed = (
        report_values["root_cause_accuracy"] >= THRESHOLDS["root_cause_accuracy"]
        and report_values["evidence_recall_at_10"] >= THRESHOLDS["evidence_recall_at_10"]
        and report_values["citation_precision"] >= THRESHOLDS["citation_precision"]
        and report_values["unsupported_claim_rate"] <= THRESHOLDS["unsupported_claim_rate"]
        and report_values["tool_selection_accuracy"] >= THRESHOLDS["tool_selection_accuracy"]
        and report_values["p95_latency_ms"] < THRESHOLDS["p95_latency_ms"]
    )
    report = EvaluationReport(
        **report_values,
        passed=passed,
        config_version=f"{CONFIG_VERSION}:{retrieval_mode}",
        failure_counts=failure_counts,
        split_metrics=split_metrics,
    )
    if strict and not passed:
        raise RuntimeError(f"evaluation regression: {report.model_dump_json()}")
    return report


def run_ab_evaluation(path: Path, *, strict: bool = True) -> EvaluationComparison:
    """Compare vector-only retrieval with the advanced candidate on identical cases."""

    baseline = run_evaluation(path, strict=False, retrieval_mode="vector")
    candidate = run_evaluation(path, strict=False, retrieval_mode="advanced")
    metrics = (
        "root_cause_accuracy",
        "evidence_recall_at_10",
        "citation_precision",
        "unsupported_claim_rate",
        "tool_selection_accuracy",
        "p95_latency_ms",
    )
    deltas = {
        name: float(getattr(candidate, name) - getattr(baseline, name)) for name in metrics
    }
    passed = candidate.passed and (
        candidate.evidence_recall_at_10 >= baseline.evidence_recall_at_10
        and candidate.root_cause_accuracy >= baseline.root_cause_accuracy
    )
    comparison = EvaluationComparison(
        baseline=baseline,
        candidate=candidate,
        deltas=deltas,
        passed=passed,
    )
    if strict and not passed:
        raise RuntimeError(f"A/B evaluation regression: {comparison.model_dump_json()}")
    return comparison


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--strict", action="store_true")
    parser.add_argument(
        "--mode", choices=("vector", "hybrid", "advanced"), default="advanced"
    )
    parser.add_argument("--compare", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = (
        run_ab_evaluation(args.dataset, strict=args.strict)
        if args.compare
        else run_evaluation(args.dataset, strict=args.strict, retrieval_mode=args.mode)
    )
    rendered = json.dumps(report.model_dump(), indent=2)
    print(rendered)
    if args.output:
        args.output.write_text(rendered + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
