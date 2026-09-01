"""Background evaluation worker entry point."""

from __future__ import annotations

from pathlib import Path

from api.models import EvaluationReport
from evals.runner import run_evaluation


def run_job(dataset: Path, *, strict: bool = True) -> EvaluationReport:
    """Run a versioned offline benchmark as a queue-safe job."""

    return run_evaluation(dataset, strict=strict)
