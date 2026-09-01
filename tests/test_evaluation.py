from pathlib import Path

from evals.runner import run_evaluation


def test_committed_dataset_passes_regression_gate() -> None:
    path = Path("evals/datasets/synthetic_incidents.jsonl")
    report = run_evaluation(path, strict=True)
    assert report.cases == 50
    assert report.passed
    assert report.citation_precision == 1.0
