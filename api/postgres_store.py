"""PostgreSQL persistence for incidents, evidence, tools, feedback, and outputs."""

from __future__ import annotations

import json
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import psycopg
from psycopg.rows import dict_row

from api.models import (
    EvaluationReport,
    Evidence,
    FeedbackRecord,
    Incident,
    InvestigationOutput,
    ToolProposal,
)
from api.store import NotFoundError


class PostgresStore:
    """Durable repository with one short transaction per domain operation."""

    def __init__(self, database_url: str) -> None:
        if not database_url:
            raise ValueError("database_url is required for PostgreSQL storage")
        self.database_url = database_url

    @contextmanager
    def _connection(self) -> Iterator[psycopg.Connection[dict[str, Any]]]:
        with psycopg.connect(self.database_url, row_factory=dict_row) as connection:
            yield connection

    def ping(self) -> None:
        with self._connection() as connection:
            connection.execute("SELECT 1")

    def add_incident(self, incident: Incident) -> Incident:
        with self._connection() as connection:
            connection.execute(
                """
                INSERT INTO incidents
                    (id, service, environment, alert, window_start, window_end, status, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (id) DO UPDATE SET
                    service = EXCLUDED.service,
                    environment = EXCLUDED.environment,
                    alert = EXCLUDED.alert,
                    window_start = EXCLUDED.window_start,
                    window_end = EXCLUDED.window_end,
                    status = EXCLUDED.status
                """,
                (
                    incident.id,
                    incident.service,
                    incident.environment,
                    incident.alert,
                    incident.window_start,
                    incident.window_end,
                    incident.status.value,
                    incident.created_at,
                ),
            )
        return incident

    def get_incident(self, incident_id: str) -> Incident:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT * FROM incidents WHERE id = %s",
                (incident_id,),
            ).fetchone()
        if row is None:
            raise NotFoundError(incident_id)
        return Incident(
            id=row["id"],
            service=row["service"],
            environment=row["environment"],
            alert=row["alert"],
            window_start=row["window_start"],
            window_end=row["window_end"],
            status=row["status"],
            created_at=row["created_at"],
        )

    def save_investigation(self, output: InvestigationOutput) -> InvestigationOutput:
        payload = output.model_dump(mode="json")
        with self._connection() as connection:
            connection.execute(
                "UPDATE incidents SET status = 'INVESTIGATING' WHERE id = %s",
                (output.incident_id,),
            )
            connection.execute(
                """
                INSERT INTO messages (incident_id, role, content, model_info)
                VALUES (%s, 'assistant', %s::jsonb, %s::jsonb)
                """,
                (
                    output.incident_id,
                    json.dumps(payload),
                    json.dumps(output.metrics.model_dump(mode="json")),
                ),
            )
            for evidence in output.evidence:
                self._upsert_evidence(connection, output.incident_id, evidence)
            for proposal in output.next_queries:
                connection.execute(
                    """
                    INSERT INTO tool_calls (id, incident_id, tool, reason, arguments, status)
                    VALUES (%s, %s, %s, %s, %s::jsonb, %s)
                    ON CONFLICT (id) DO UPDATE SET
                        reason = EXCLUDED.reason,
                        arguments = EXCLUDED.arguments,
                        status = EXCLUDED.status
                    """,
                    (
                        proposal.id,
                        output.incident_id,
                        proposal.tool,
                        proposal.reason,
                        json.dumps(proposal.arguments),
                        proposal.status,
                    ),
                )
        return output

    def get_investigation(self, incident_id: str) -> InvestigationOutput:
        with self._connection() as connection:
            row = connection.execute(
                """
                SELECT content FROM messages
                WHERE incident_id = %s AND role = 'assistant'
                ORDER BY id DESC LIMIT 1
                """,
                (incident_id,),
            ).fetchone()
        if row is None:
            raise NotFoundError(incident_id)
        return InvestigationOutput.model_validate(row["content"])

    def list_evidence(self, incident_id: str) -> list[Evidence]:
        self.get_incident(incident_id)
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT metadata FROM evidence WHERE incident_id = %s ORDER BY id",
                (incident_id,),
            ).fetchall()
        return [Evidence.model_validate(row["metadata"]["payload"]) for row in rows]

    def _upsert_evidence(
        self,
        connection: psycopg.Connection[dict[str, Any]],
        incident_id: str,
        evidence: Evidence,
    ) -> None:
        chunk_id = evidence.metadata.get("chunk_id") if evidence.source_type == "document" else None
        tool_call_id = None
        if evidence.source_type == "tool":
            tool_call_id = evidence.metadata.get("tool_call_id") or evidence.id.removeprefix("T-")
        connection.execute(
            """
            INSERT INTO evidence
                (id, incident_id, chunk_id, tool_call_id, quote_hash, metadata)
            VALUES (%s, %s, %s, %s, %s, %s::jsonb)
            ON CONFLICT (incident_id, id) DO UPDATE SET
                quote_hash = EXCLUDED.quote_hash,
                metadata = EXCLUDED.metadata
            """,
            (
                evidence.id,
                incident_id,
                chunk_id,
                tool_call_id,
                evidence.quote_hash,
                json.dumps({"payload": evidence.model_dump(mode="json")}),
            ),
        )

    def add_evidence(self, incident_id: str, evidence: Evidence) -> Evidence:
        self.get_incident(incident_id)
        with self._connection() as connection:
            self._upsert_evidence(connection, incident_id, evidence)
        return evidence

    def get_tool_call(self, call_id: str) -> tuple[str, ToolProposal]:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT * FROM tool_calls WHERE id = %s",
                (call_id,),
            ).fetchone()
        if row is None:
            raise NotFoundError(call_id)
        return row["incident_id"], ToolProposal(
            id=row["id"],
            tool=row["tool"],
            arguments=row["arguments"],
            reason=row["reason"],
            status=row["status"],
        )

    def update_tool_call(self, incident_id: str, proposal: ToolProposal) -> None:
        with self._connection() as connection:
            result = connection.execute(
                """
                UPDATE tool_calls SET reason = %s, arguments = %s::jsonb, status = %s,
                    executed_at = CASE WHEN %s = 'EXECUTED' THEN now() ELSE executed_at END
                WHERE id = %s AND incident_id = %s
                """,
                (
                    proposal.reason,
                    json.dumps(proposal.arguments),
                    proposal.status,
                    proposal.status,
                    proposal.id,
                    incident_id,
                ),
            )
            if result.rowcount == 0:
                connection.execute(
                    """
                    INSERT INTO tool_calls (id, incident_id, tool, reason, arguments, status)
                    VALUES (%s, %s, %s, %s, %s::jsonb, %s)
                    """,
                    (
                        proposal.id,
                        incident_id,
                        proposal.tool,
                        proposal.reason,
                        json.dumps(proposal.arguments),
                        proposal.status,
                    ),
                )

    def record_approval(self, call_id: str, approved_by: str) -> None:
        with self._connection() as connection:
            connection.execute(
                "UPDATE tool_calls SET approved_by = %s WHERE id = %s",
                (approved_by, call_id),
            )

    def add_feedback(self, feedback: FeedbackRecord) -> FeedbackRecord:
        self.get_incident(feedback.incident_id)
        with self._connection() as connection:
            connection.execute(
                """
                INSERT INTO feedback
                    (incident_id, correctness, citation_quality, helpfulness,
                     label, correction, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    feedback.incident_id,
                    feedback.correctness,
                    feedback.citation_quality,
                    feedback.helpfulness,
                    feedback.label,
                    feedback.correction,
                    feedback.created_at,
                ),
            )
        return feedback

    def save_evaluation(self, report: EvaluationReport) -> EvaluationReport:
        payload = report.model_dump(mode="json")
        with self._connection() as connection:
            connection.execute(
                """
                INSERT INTO evaluations (case_id, config_version, metrics, output)
                VALUES ('aggregate', %s, %s::jsonb, %s::jsonb)
                ON CONFLICT (case_id, config_version) DO UPDATE SET
                    metrics = EXCLUDED.metrics,
                    output = EXCLUDED.output,
                    created_at = now()
                """,
                (report.config_version, json.dumps(payload), json.dumps(payload)),
            )
        return report

    def list_evaluations(self) -> list[EvaluationReport]:
        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT output FROM evaluations
                WHERE case_id = 'aggregate'
                ORDER BY created_at DESC
                """
            ).fetchall()
        return [EvaluationReport.model_validate(row["output"]) for row in rows]
