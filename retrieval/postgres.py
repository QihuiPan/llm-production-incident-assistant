"""PostgreSQL full-text and pgvector hybrid index."""

from __future__ import annotations

import json
from typing import Any

import psycopg
from pgvector import Vector
from pgvector.psycopg import register_vector
from psycopg.rows import dict_row

from api.models import TrustLevel
from retrieval.hybrid import hashed_embedding
from retrieval.models import ChunkRecord, SearchHit


class PostgresHybridIndex:
    """Durable hybrid index using PostgreSQL FTS, pgvector, and SQL-side RRF."""

    def __init__(self, database_url: str) -> None:
        self.database_url = database_url

    def _connect(self) -> psycopg.Connection[dict[str, Any]]:
        connection = psycopg.connect(self.database_url, row_factory=dict_row)
        register_vector(connection)
        return connection

    @property
    def chunks(self) -> tuple[ChunkRecord, ...]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT c.*, d.source, d.version, d.service, d.environment, d.trust_level
                FROM chunks c JOIN documents d ON d.id = c.document_id
                ORDER BY c.id
                """
            ).fetchall()
        return tuple(self._row_to_chunk(row) for row in rows)

    def add(self, chunks: list[ChunkRecord]) -> None:
        with self._connect() as connection:
            for chunk in chunks:
                connection.execute(
                    """
                    INSERT INTO documents (id, source, version, service, environment, trust_level)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    ON CONFLICT (id) DO UPDATE SET
                        source = EXCLUDED.source,
                        version = EXCLUDED.version,
                        service = EXCLUDED.service,
                        environment = EXCLUDED.environment,
                        trust_level = EXCLUDED.trust_level
                    """,
                    (
                        chunk.document_id,
                        chunk.source,
                        chunk.version,
                        chunk.service,
                        chunk.environment,
                        chunk.trust_level.value,
                    ),
                )
                metadata = {
                    "position": chunk.position,
                    "injection_flagged": chunk.injection_flagged,
                }
                connection.execute(
                    """
                    INSERT INTO chunks (id, document_id, section, content, embedding, metadata)
                    VALUES (%s, %s, %s, %s, %s, %s::jsonb)
                    ON CONFLICT (id) DO UPDATE SET
                        section = EXCLUDED.section,
                        content = EXCLUDED.content,
                        embedding = EXCLUDED.embedding,
                        metadata = EXCLUDED.metadata
                    """,
                    (
                        chunk.id,
                        chunk.document_id,
                        chunk.section,
                        chunk.content,
                        Vector(hashed_embedding(chunk.content, dimensions=768)),
                        json.dumps(metadata),
                    ),
                )

    def search(
        self,
        query: str,
        *,
        service: str | None = None,
        environment: str | None = None,
        limit: int = 10,
    ) -> list[SearchHit]:
        query_vector = Vector(hashed_embedding(query, dimensions=768))
        with self._connect() as connection:
            rows = connection.execute(
                """
                WITH candidates AS (
                    SELECT c.*, d.source, d.version, d.service, d.environment, d.trust_level,
                        ts_rank_cd(
                            c.search_vector,
                            websearch_to_tsquery('english', %(query)s)
                        ) AS keyword_score,
                        1 - (c.embedding <=> %(embedding)s) AS vector_score
                    FROM chunks c JOIN documents d ON d.id = c.document_id
                    WHERE (%(service)s IS NULL OR d.service = %(service)s)
                      AND (
                        %(environment)s IS NULL OR d.environment IS NULL
                        OR d.environment = %(environment)s
                      )
                ), ranked AS (
                    SELECT *,
                        row_number() OVER (ORDER BY keyword_score DESC, id) AS keyword_rank,
                        row_number() OVER (ORDER BY vector_score DESC, id) AS vector_rank
                    FROM candidates
                )
                SELECT *,
                    (1.0 / (60 + keyword_rank) + 1.0 / (60 + vector_rank))
                    * CASE trust_level
                        WHEN 'official' THEN 1.15
                        WHEN 'reviewed' THEN 1.05 ELSE 0.9
                      END
                    * CASE WHEN COALESCE(
                        (metadata->>'injection_flagged')::boolean, false
                      ) THEN 0.35 ELSE 1 END
                    AS fused_score
                FROM ranked
                WHERE keyword_score > 0 OR vector_score > 0
                ORDER BY fused_score DESC
                LIMIT %(limit)s
                """,
                {
                    "query": query,
                    "embedding": query_vector,
                    "service": service,
                    "environment": environment,
                    "limit": limit,
                },
            ).fetchall()
        return [
            SearchHit(
                chunk=self._row_to_chunk(row),
                score=float(row["fused_score"]),
                keyword_rank=int(row["keyword_rank"]),
                vector_rank=int(row["vector_rank"]),
            )
            for row in rows
        ]

    @staticmethod
    def _row_to_chunk(row: dict[str, Any]) -> ChunkRecord:
        metadata = row.get("metadata") or {}
        return ChunkRecord(
            id=row["id"],
            document_id=row["document_id"],
            source=row["source"],
            version=row["version"],
            service=row["service"],
            environment=row["environment"],
            trust_level=TrustLevel(row["trust_level"]),
            section=row["section"],
            content=row["content"],
            position=int(metadata.get("position", 0)),
            injection_flagged=bool(metadata.get("injection_flagged", False)),
        )
