"""Redis Queue entry points that update durable job lifecycle records."""

from __future__ import annotations

import base64
from pathlib import Path

from api.jobs import PostgresJobRepository
from api.models import TrustLevel, utc_now
from api.postgres_store import PostgresStore
from api.security import redact_text
from evals.runner import run_evaluation
from retrieval.ingest import ingest_bytes
from retrieval.postgres import PostgresHybridIndex


def execute_job(job_id: str, database_url: str) -> None:
    """Execute one validated queued ingestion or evaluation job."""

    repository = PostgresJobRepository(database_url)
    job = repository.get(job_id)
    running = job.model_copy(update={"status": "RUNNING", "started_at": utc_now()})
    repository.update(running)
    try:
        if job.kind == "evaluation":
            report = run_evaluation(Path(job.payload["dataset"]), strict=job.payload["strict"])
            PostgresStore(database_url).save_evaluation(report)
            result = report.model_dump(mode="json")
        elif job.kind == "ingestion":
            document, count, flagged = ingest_bytes(
                PostgresHybridIndex(database_url),  # type: ignore[arg-type]
                filename=job.payload["filename"],
                payload=base64.b64decode(job.payload["payload_base64"]),
                service=job.payload["service"],
                environment=job.payload.get("environment"),
                version=job.payload["version"],
                trust_level=TrustLevel(job.payload["trust_level"]),
            )
            result = {
                "document_id": document.id,
                "chunks_created": count,
                "injection_flagged": flagged,
            }
        else:
            raise ValueError(f"unsupported job kind: {job.kind}")
        repository.update(
            running.model_copy(
                update={"status": "SUCCEEDED", "result": result, "finished_at": utc_now()}
            )
        )
    except Exception as exc:
        clean_error, _ = redact_text(str(exc))
        repository.update(
            running.model_copy(
                update={
                    "status": "FAILED",
                    "error": clean_error[:2000],
                    "finished_at": utc_now(),
                }
            )
        )
        raise
