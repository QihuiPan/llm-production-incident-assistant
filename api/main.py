"""FastAPI application exposing the incident-assistant contracts."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse

from api.config import get_settings
from api.models import (
    DocumentIngestResponse,
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
    TrustLevel,
)
from api.observability import metrics
from api.orchestrator import IncidentOrchestrator
from api.postmortem import render_postmortem
from api.store import MemoryStore, NotFoundError
from evals.runner import run_evaluation
from retrieval.hybrid import HybridIndex
from retrieval.ingest import IngestionError, ingest_bytes
from retrieval.seed import load_demo_documents
from tools.gateway import ToolGateway, ToolPolicyError

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATASET_ROOT = PROJECT_ROOT / "evals" / "datasets"


def create_app() -> FastAPI:
    """Build an isolated application instance for runtime or tests."""

    settings = get_settings()
    app = FastAPI(
        title="LLM Production Incident Assistant",
        version="1.0.0",
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

    store = MemoryStore()
    index = HybridIndex()
    load_demo_documents(index)
    gateway = ToolGateway(
        store,
        max_calls_per_incident=settings.max_tool_calls_per_run,
        max_window_hours=settings.max_query_window_hours,
        max_rows=settings.max_tool_rows,
    )
    orchestrator = IncidentOrchestrator(store, index, gateway)
    app.state.store = store
    app.state.index = index
    app.state.gateway = gateway
    app.state.orchestrator = orchestrator

    @app.get("/healthz")
    def health() -> dict[str, object]:
        return {"status": "ok", "indexed_chunks": len(index.chunks), "read_only": True}

    @app.get("/metrics", response_class=PlainTextResponse)
    def prometheus_metrics() -> str:
        return metrics.render_prometheus()

    @app.post("/api/documents", response_model=DocumentIngestResponse, status_code=202)
    async def ingest_document(
        file: UploadFile = File(...),
        service: str = Form(...),
        environment: str | None = Form(default=None),
        version: str = Form(default="1.0.0"),
        trust_level: TrustLevel = Form(default=TrustLevel.UNVERIFIED),
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
    def create_incident(payload: IncidentCreate) -> Incident:
        incident = Incident(**payload.model_dump())
        store.add_incident(incident)
        metrics.increment("incidents_created_total")
        return incident

    @app.get("/api/incidents/{incident_id}", response_model=Incident)
    def get_incident(incident_id: str) -> Incident:
        try:
            return store.get_incident(incident_id)
        except NotFoundError as exc:
            raise HTTPException(status_code=404, detail="incident not found") from exc

    @app.post("/api/incidents/{incident_id}/investigate", response_model=InvestigationOutput)
    def investigate(incident_id: str) -> InvestigationOutput:
        try:
            return orchestrator.investigate(store.get_incident(incident_id))
        except NotFoundError as exc:
            raise HTTPException(status_code=404, detail="incident not found") from exc

    @app.get("/api/incidents/{incident_id}/evidence", response_model=list[Evidence])
    def list_evidence(incident_id: str) -> list[Evidence]:
        try:
            return store.list_evidence(incident_id)
        except NotFoundError as exc:
            raise HTTPException(status_code=404, detail="incident not found") from exc

    @app.get(
        "/api/incidents/{incident_id}/postmortem",
        response_class=PlainTextResponse,
    )
    def export_postmortem(incident_id: str) -> str:
        try:
            incident = store.get_incident(incident_id)
            investigation = store.get_investigation(incident_id)
            return render_postmortem(incident, investigation)
        except NotFoundError as exc:
            raise HTTPException(status_code=404, detail="investigation not found") from exc

    @app.post("/api/tool-calls/{call_id}/approve", response_model=ToolExecutionResult)
    def approve_tool(call_id: str, payload: ToolApproval) -> ToolExecutionResult:
        try:
            result = gateway.approve_and_execute(call_id, payload.approved_by)
            incident_id, _ = store.get_tool_call(call_id)
            serialized = json.dumps(result.result, sort_keys=True, separators=(",", ":"))
            store.add_evidence(
                incident_id,
                Evidence(
                    id=f"T-{call_id}",
                    incident_id=incident_id,
                    source_type="tool",
                    source=result.tool_call.tool,
                    source_version="simulator-v1",
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

    @app.post(
        "/api/incidents/{incident_id}/feedback", response_model=FeedbackRecord, status_code=201
    )
    def add_feedback(incident_id: str, payload: FeedbackCreate) -> FeedbackRecord:
        try:
            return store.add_feedback(
                FeedbackRecord(incident_id=incident_id, **payload.model_dump())
            )
        except NotFoundError as exc:
            raise HTTPException(status_code=404, detail="incident not found") from exc

    @app.post("/api/evaluations/run", response_model=EvaluationReport)
    def evaluate(payload: EvaluationRequest) -> EvaluationReport:
        candidate = (PROJECT_ROOT / payload.dataset).resolve()
        if DATASET_ROOT.resolve() not in candidate.parents or candidate.suffix != ".jsonl":
            raise HTTPException(
                status_code=400,
                detail="dataset must be a committed JSONL file under evals/datasets",
            )
        if not candidate.exists():
            raise HTTPException(status_code=404, detail="dataset not found")
        try:
            return run_evaluation(candidate, strict=payload.strict)
        except RuntimeError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    return app


app = create_app()
