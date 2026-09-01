from pathlib import Path

from evals.runner import run_ab_evaluation, run_evaluation


def test_committed_dataset_passes_regression_gate() -> None:
    path = Path("evals/datasets/synthetic_incidents.jsonl")
    report = run_evaluation(path, strict=True)
    assert report.cases == 100
    assert report.passed
    assert report.citation_precision == 1.0
    assert report.split_metrics["heldout"]["cases"] == 20


def test_advanced_candidate_passes_vector_ab_gate() -> None:
    comparison = run_ab_evaluation(
        Path("evals/datasets/synthetic_incidents.jsonl"), strict=True
    )
    assert comparison.candidate.cases == 100
    assert comparison.passed
