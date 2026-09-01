"""FastAPI application exposing the incident-assistant contracts."""

from __future__ import annotations

import base64
import hashlib
import json
import time
from pathlib import Path
from typing import Literal

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse

from api.auth import APIKeyAuthenticator, Principal
from api.config import Settings, get_settings
from api.jobs import (
    InlineJobManager,
    MemoryJobRepository,
    PostgresJobRepository,
    RQJobManager,
)
from api.models import (
    BackgroundJob,
    DashboardSummary,
    DocumentIngestResponse,
    EvaluationComparison,
    EvaluationReport,
    EvaluationRequest,
    Evidence,
    FeedbackCreate,
    FeedbackRecord,
    Incident,
    IncidentCreate,
    InvestigationOutput,
    ToolApproval,
    ToolExecutionResult,
    TraceRecord,
    TrustLevel,
)
from api.observability import metrics
from api.orchestrator import IncidentOrchestrator
from api.postmortem import render_postmortem
from api.runtime import build_runtime
from api.security import redact_text
from api.store import NotFoundError
from evals.runner import run_ab_evaluation, run_evaluation
from retrieval.ingest import IngestionError, ingest_bytes
from tools.gateway import ToolPolicyError
from tools.production_adapters import ProductionAdapterError

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATASET_ROOT = PROJECT_ROOT / "evals" / "datasets"


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build an isolated application instance for runtime or tests."""

    settings = settings or get_settings()
    app = FastAPI(
        title="LLM Production Incident Assistant",
        version="2.0.0",
        description=(
            "A cited, evaluated, read-only assistant for production incident investigation."
        ),
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.origins,
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type", "Authorization"],
    )

    runtime = build_runtime(settings)
    store = runtime.store
    index = runtime.index
    gateway = runtime.gateway
    traces = runtime.traces
    authenticator = APIKeyAuthenticator(settings)
    viewer = authenticator.dependency("viewer")
    operator = authenticator.dependency("operator")
    evaluator = authenticator.dependency("evaluator")
    administrator = authenticator.dependency("administrator")
    orchestrator = IncidentOrchestrator(
        store,
        index,
        gateway,
        retrieval_mode=settings.retrieval_mode,
        llm_service=runtime.llm_service,
        traces=traces,
    )
    app.state.store = store
    app.state.index = index
    app.state.gateway = gateway
    app.state.orchestrator = orchestrator
    app.state.traces = traces
    app.state.authenticator = authenticator
    if settings.storage_backend == "postgres":
        if not settings.database_url:
            raise ValueError("DATABASE_URL is required for PostgreSQL jobs")
        job_repository = PostgresJobRepository(settings.database_url)
    else:
        job_repository = MemoryJobRepository()
    if settings.job_backend == "rq":
        if settings.storage_backend != "postgres" or not settings.redis_url:
            raise ValueError("RQ jobs require PostgreSQL storage and REDIS_URL")
        job_manager = RQJobManager(job_repository, settings.redis_url, settings.database_url or "")
    else:
        job_manager = InlineJobManager(job_repository)
    app.state.jobs = job_manager

    @app.middleware("http")
    async def trace_requests(request: Request, call_next):
        started = time.perf_counter()
        status = "ok"
        try:
            response = await call_next(request)
            if response.status_code >= 500:
                status = "error"
            return response
        except Exception:
            status = "error"
            raise
        finally:
            traces.record(
                "http.request",
                (time.perf_counter() - started) * 1000,
                status=status,
                attributes={"method": request.method, "path": request.url.path},
            )

    @app.get("/healthz")
    def health() -> dict[str, object]:
        return {
            "status": "ok",
            "indexed_chunks": len(index.chunks),
            "read_only": True,
            "storage_backend": settings.storage_backend,
            "retrieval_mode": settings.retrieval_mode,
            "tool_backend": settings.tool_backend,
            "auth_enabled": settings.auth_enabled,
        }

    @app.get("/metrics", response_class=PlainTextResponse)
    def prometheus_metrics() -> str:
        return metrics.render_prometheus()

    @app.get("/api/whoami")
    def whoami(principal: Principal = Depends(viewer)) -> dict[str, object]:
        return {"subject": principal.subject, "roles": sorted(principal.roles)}

    @app.get("/api/dashboard", response_model=DashboardSummary)
    def dashboard(_: Principal = Depends(viewer)) -> DashboardSummary:
        return traces.summary()

    @app.get("/api/traces", response_model=list[TraceRecord])
    def list_traces(
        _: Principal = Depends(viewer),
        incident_id: str | None = None,
        limit: int = 100,
    ) -> list[TraceRecord]:
        return traces.list(incident_id=incident_id, limit=min(max(limit, 1), 500))

    def resolve_dataset(dataset: str) -> Path:
        candidate = (PROJECT_ROOT / dataset).resolve()
        if DATASET_ROOT.resolve() not in candidate.parents or candidate.suffix != ".jsonl":
            raise HTTPException(
                status_code=400,
                detail="dataset must be a committed JSONL file under evals/datasets",
            )
        if not candidate.exists():
            raise HTTPException(status_code=404, detail="dataset not found")
        return candidate

    def public_job(job: BackgroundJob) -> BackgroundJob:
        payload = {key: value for key, value in job.payload.items() if key != "payload_base64"}
        return job.model_copy(update={"payload": payload})

    @app.post("/api/documents", response_model=DocumentIngestResponse, status_code=202)
    async def ingest_document(
        file: UploadFile = File(...),
        service: str = Form(
            ..., min_length=2, max_length=80, pattern=r"^[a-zA-Z0-9._-]+$"
        ),
        environment: Literal["production", "staging", "development"] | None = Form(
            default=None
        ),
        version: str = Form(default="1.0.0", min_length=1, max_length=80),
        trust_level: TrustLevel = Form(default=TrustLevel.UNVERIFIED),
        _: Principal = Depends(administrator),
    ) -> DocumentIngestResponse:
        payload = await file.read(settings.max_document_bytes + 1)
        if len(payload) > settings.max_document_bytes:
            raise HTTPException(
                status_code=413, detail="document exceeds the configured size limit"
            )
        try:
            document, chunk_count, flagged = ingest_bytes(
                index,
                filename=file.filename or "document.txt",
                payload=payload,
                service=service,
                environment=environment,
                version=version,
                trust_level=trust_level,
            )
        except IngestionError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        metrics.increment("documents_ingested_total")
        if flagged:
            metrics.increment("prompt_injection_total")
        return DocumentIngestResponse(
            document_id=document.id,
            chunks_created=chunk_count,
            injection_flagged=flagged,
        )

    @app.post("/api/incidents", response_model=Incident, status_code=201)
    def create_incident(
        payload: IncidentCreate, _: Principal = Depends(operator)
    ) -> Incident:
        safe_alert, redactions = redact_text(payload.alert)
        incident = Incident(**payload.model_dump(exclude={"alert"}), alert=safe_alert)
        store.add_incident(incident)
        metrics.increment("incidents_created_total")
        if redactions:
            metrics.increment("incident_redactions_total", redactions)
        return incident

    @app.get("/api/incidents/{incident_id}", response_model=Incident)
    def get_incident(
        incident_id: str, _: Principal = Depends(viewer)
    ) -> Incident:
        try:
            return store.get_incident(incident_id)
        except NotFoundError as exc:
            raise HTTPException(status_code=404, detail="incident not found") from exc

    @app.post("/api/incidents/{incident_id}/investigate", response_model=InvestigationOutput)
    def investigate(
        incident_id: str, _: Principal = Depends(operator)
    ) -> InvestigationOutput:
        try:
            return orchestrator.investigate(store.get_incident(incident_id))
        except NotFoundError as exc:
            raise HTTPException(status_code=404, detail="incident not found") from exc

    @app.get("/api/incidents/{incident_id}/evidence", response_model=list[Evidence])
    def list_evidence(
        incident_id: str, _: Principal = Depends(viewer)
    ) -> list[Evidence]:
        try:
            return store.list_evidence(incident_id)
        except NotFoundError as exc:
            raise HTTPException(status_code=404, detail="incident not found") from exc

    @app.get(
        "/api/incidents/{incident_id}/postmortem",
        response_class=PlainTextResponse,
    )
    def export_postmortem(
        incident_id: str, _: Principal = Depends(viewer)
    ) -> str:
        try:
            incident = store.get_incident(incident_id)
            investigation = store.get_investigation(incident_id)
            return render_postmortem(incident, investigation)
        except NotFoundError as exc:
            raise HTTPException(status_code=404, detail="investigation not found") from exc

    @app.post("/api/tool-calls/{call_id}/approve", response_model=ToolExecutionResult)
    def approve_tool(
        call_id: str,
        payload: ToolApproval,
        principal: Principal = Depends(operator),
    ) -> ToolExecutionResult:
        try:
            approved_by = principal.subject if settings.auth_enabled else payload.approved_by
            result = gateway.approve_and_execute(call_id, approved_by)
            incident_id, _ = store.get_tool_call(call_id)
            serialized = json.dumps(result.result, sort_keys=True, separators=(",", ":"))
            store.add_evidence(
                incident_id,
                Evidence(
                    id=f"T-{call_id}",
                    incident_id=incident_id,
                    source_type="tool",
                    source=result.tool_call.tool,
                    source_version=f"{settings.tool_backend}-v1",
                    trust_level=TrustLevel.REVIEWED,
                    excerpt=serialized[:1000],
                    score=1.0,
                    quote_hash=hashlib.sha256(serialized.encode()).hexdigest(),
                    metadata={"audit_id": result.audit_id, "redactions": result.redactions},
                ),
            )
            return result
        except NotFoundError as exc:
            raise HTTPException(status_code=404, detail="tool call not found") from exc
        except ToolPolicyError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except ProductionAdapterError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

    @app.post(
        "/api/incidents/{incident_id}/feedback", response_model=FeedbackRecord, status_code=201
    )
    def add_feedback(
        incident_id: str,
        payload: FeedbackCreate,
        _: Principal = Depends(viewer),
    ) -> FeedbackRecord:
        try:
            return store.add_feedback(
                FeedbackRecord(incident_id=incident_id, **payload.model_dump())
            )
        except NotFoundError as exc:
            raise HTTPException(status_code=404, detail="incident not found") from exc

    @app.post("/api/jobs/evaluations", response_model=BackgroundJob, status_code=202)
    def queue_evaluation(
        payload: EvaluationRequest, _: Principal = Depends(evaluator)
    ) -> BackgroundJob:
        candidate = resolve_dataset(payload.dataset)
        job_payload = {"dataset": str(candidate), "strict": payload.strict}

        def evaluation_job() -> dict[str, object]:
            report = run_evaluation(candidate, strict=payload.strict)
            store.save_evaluation(report)
            return report.model_dump(mode="json")

        return job_manager.submit(
            "evaluation",
            job_payload,
            evaluation_job,
        )

    @app.post("/api/jobs/documents", response_model=BackgroundJob, status_code=202)
    async def queue_document(
        file: UploadFile = File(...),
        service: str = Form(
            ..., min_length=2, max_length=80, pattern=r"^[a-zA-Z0-9._-]+$"
        ),
        environment: Literal["production", "staging", "development"] | None = Form(
            default=None
        ),
        version: str = Form(default="1.0.0", min_length=1, max_length=80),
        trust_level: TrustLevel = Form(default=TrustLevel.UNVERIFIED),
        _: Principal = Depends(administrator),
    ) -> BackgroundJob:
        payload = await file.read(settings.max_document_bytes + 1)
        if len(payload) > settings.max_document_bytes:
            raise HTTPException(
                status_code=413, detail="document exceeds the configured size limit"
            )
        filename = file.filename or "document.txt"
        job_payload = {
            "filename": filename,
            "payload_base64": base64.b64encode(payload).decode("ascii"),
            "service": service,
            "environment": environment,
            "version": version,
            "trust_level": trust_level.value,
        }

        def ingest_job() -> dict[str, object]:
            document, count, flagged = ingest_bytes(
                index,  # type: ignore[arg-type]
                filename=filename,
                payload=payload,
                service=service,
                environment=environment,
                version=version,
                trust_level=trust_level,
            )
            return {
                "document_id": document.id,
                "chunks_created": count,
                "injection_flagged": flagged,
            }

        return public_job(job_manager.submit("ingestion", job_payload, ingest_job))

    @app.get("/api/jobs/{job_id}", response_model=BackgroundJob)
    def get_job(
        job_id: str, _: Principal = Depends(viewer)
    ) -> BackgroundJob:
        try:
            return public_job(job_repository.get(job_id))
        except NotFoundError as exc:
            raise HTTPException(status_code=404, detail="job not found") from exc

    @app.post("/api/evaluations/run", response_model=EvaluationReport)
    def evaluate(
        payload: EvaluationRequest, _: Principal = Depends(evaluator)
    ) -> EvaluationReport:
        candidate = resolve_dataset(payload.dataset)
        try:
            report = run_evaluation(candidate, strict=payload.strict)
            return store.save_evaluation(report)
        except RuntimeError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.post("/api/evaluations/compare", response_model=EvaluationComparison)
    def compare_evaluations(
        payload: EvaluationRequest, _: Principal = Depends(evaluator)
    ) -> EvaluationComparison:
        candidate = resolve_dataset(payload.dataset)
        try:
            comparison = run_ab_evaluation(candidate, strict=payload.strict)
            store.save_evaluation(comparison.baseline)
            store.save_evaluation(comparison.candidate)
            return comparison
        except RuntimeError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.get("/api/evaluations", response_model=list[EvaluationReport])
    def list_evaluations(_: Principal = Depends(evaluator)) -> list[EvaluationReport]:
        return store.list_evaluations()

    return app


app = create_app()
