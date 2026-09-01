from pathlib import Path

import docker
import psycopg
import pytest
from testcontainers.community.postgres import PostgresContainer

from api.orchestrator import IncidentOrchestrator
from api.postgres_store import PostgresStore
from api.tracing import PostgresTraceRecorder
from retrieval.postgres import PostgresHybridIndex
from retrieval.seed import load_demo_documents
from tools.gateway import ToolGateway


def _docker_available() -> bool:
    try:
        client = docker.from_env()
        client.ping()
        client.close()
        return True
    except Exception:
        return False


@pytest.mark.integration
@pytest.mark.skipif(not _docker_available(), reason="Docker daemon is unavailable")
def test_postgres_pgvector_runtime_survives_repository_reconstruction(incident) -> None:
    with PostgresContainer("pgvector/pgvector:pg17") as postgres:
        database_url = postgres.get_connection_url(driver=None)
        migration = Path("infra/postgres/001_init.sql").read_text(encoding="utf-8")
        with psycopg.connect(database_url) as connection:
            connection.execute(migration, prepare=False)

        index = PostgresHybridIndex(database_url)
        load_demo_documents(index)  # type: ignore[arg-type]
        store = PostgresStore(database_url)
        store.add_incident(incident)
        traces = PostgresTraceRecorder(database_url)
        output = IncidentOrchestrator(
            store,
            index,
            ToolGateway(store),
            retrieval_mode="advanced",
            traces=traces,
        ).investigate(incident)
        assert output.evidence
        assert store.get_investigation(incident.id).summary == output.summary
        assert PostgresStore(database_url).get_incident(incident.id).id == incident.id
        assert traces.summary().trace_count >= 3
