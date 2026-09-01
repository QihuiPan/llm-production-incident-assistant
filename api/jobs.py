"""Inspectable background-job repositories and queue dispatchers."""

from __future__ import annotations

import json
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from threading import RLock
from typing import Any, Protocol
from uuid import uuid4

import psycopg
from psycopg.rows import dict_row
from redis import Redis
from rq import Queue

from api.models import BackgroundJob, utc_now
from api.security import redact_text
from api.store import NotFoundError


class JobRepository(Protocol):
    def create(self, job: BackgroundJob) -> BackgroundJob: ...

    def get(self, job_id: str) -> BackgroundJob: ...

    def update(self, job: BackgroundJob) -> BackgroundJob: ...


class MemoryJobRepository:
    def __init__(self) -> None:
        self._jobs: dict[str, BackgroundJob] = {}
        self._lock = RLock()

    def create(self, job: BackgroundJob) -> BackgroundJob:
        with self._lock:
            self._jobs[job.id] = job
        return job

    def get(self, job_id: str) -> BackgroundJob:
        with self._lock:
            try:
                return self._jobs[job_id]
            except KeyError as exc:
                raise NotFoundError(job_id) from exc

    def update(self, job: BackgroundJob) -> BackgroundJob:
        with self._lock:
            self._jobs[job.id] = job
        return job


class PostgresJobRepository:
    def __init__(self, database_url: str) -> None:
        self.database_url = database_url

    def create(self, job: BackgroundJob) -> BackgroundJob:
        with psycopg.connect(self.database_url) as connection:
            connection.execute(
                """
                INSERT INTO background_jobs (id, queue, kind, status, payload, created_at)
                VALUES (%s, %s, %s, %s, %s::jsonb, %s)
                """,
                (
                    job.id,
                    job.queue,
                    job.kind,
                    job.status,
                    json.dumps(job.payload),
                    job.created_at,
                ),
            )
        return job

    def get(self, job_id: str) -> BackgroundJob:
        with psycopg.connect(self.database_url, row_factory=dict_row) as connection:
            row = connection.execute(
                "SELECT * FROM background_jobs WHERE id = %s", (job_id,)
            ).fetchone()
        if row is None:
            raise NotFoundError(job_id)
        return BackgroundJob.model_validate(row)

    def update(self, job: BackgroundJob) -> BackgroundJob:
        with psycopg.connect(self.database_url) as connection:
            result = connection.execute(
                """
                UPDATE background_jobs SET status = %s, result = %s::jsonb, error = %s,
                    started_at = %s, finished_at = %s
                WHERE id = %s
                """,
                (
                    job.status,
                    json.dumps(job.result) if job.result is not None else None,
                    job.error,
                    job.started_at,
                    job.finished_at,
                    job.id,
                ),
            )
        if result.rowcount == 0:
            raise NotFoundError(job.id)
        return job


class JobManager(Protocol):
    repository: JobRepository

    def submit(
        self,
        kind: str,
        payload: dict[str, Any],
        runner: Callable[[], dict[str, Any]],
    ) -> BackgroundJob: ...


class InlineJobManager:
    """Run jobs in a bounded local thread pool while preserving the queue contract."""

    def __init__(self, repository: JobRepository, max_workers: int = 2) -> None:
        self.repository = repository
        self._executor = ThreadPoolExecutor(
            max_workers=max_workers, thread_name_prefix="incident-job"
        )

    def submit(
        self,
        kind: str,
        payload: dict[str, Any],
        runner: Callable[[], dict[str, Any]],
    ) -> BackgroundJob:
        job = BackgroundJob(
            id=f"JOB-{uuid4().hex[:12].upper()}",
            queue="inline",
            kind=kind,
            status="QUEUED",
            payload=payload,
        )
        self.repository.create(job)

        def execute() -> None:
            running = job.model_copy(update={"status": "RUNNING", "started_at": utc_now()})
            self.repository.update(running)
            try:
                result = runner()
                completed = running.model_copy(
                    update={"status": "SUCCEEDED", "result": result, "finished_at": utc_now()}
                )
            except Exception as exc:
                clean_error, _ = redact_text(str(exc))
                completed = running.model_copy(
                    update={
                        "status": "FAILED",
                        "error": clean_error[:2000],
                        "finished_at": utc_now(),
                    }
                )
            self.repository.update(completed)

        self._executor.submit(execute)
        return job


class RQJobManager:
    """Dispatch durable jobs to Redis Queue; workers persist lifecycle state in PostgreSQL."""

    def __init__(self, repository: JobRepository, redis_url: str, database_url: str) -> None:
        self.repository = repository
        self.database_url = database_url
        self.queue = Queue("incident-assistant", connection=Redis.from_url(redis_url))

    def submit(
        self,
        kind: str,
        payload: dict[str, Any],
        runner: Callable[[], dict[str, Any]],
    ) -> BackgroundJob:
        del runner
        job = BackgroundJob(
            id=f"JOB-{uuid4().hex[:12].upper()}",
            queue="incident-assistant",
            kind=kind,
            status="QUEUED",
            payload=payload,
        )
        self.repository.create(job)
        try:
            self.queue.enqueue(
                "workers.tasks.execute_job",
                job.id,
                self.database_url,
                job_timeout=1800,
                result_ttl=86_400,
                failure_ttl=604_800,
            )
        except Exception as exc:
            clean_error, _ = redact_text(str(exc))
            self.repository.update(
                job.model_copy(
                    update={
                        "status": "FAILED",
                        "error": clean_error[:2000],
                        "finished_at": utc_now(),
                    }
                )
            )
            raise
        return job
