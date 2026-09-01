import json
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

from fastapi.testclient import TestClient

from api.config import Settings
from api.jobs import InlineJobManager, MemoryJobRepository
from api.main import create_app


def incident_payload() -> dict[str, str]:
    end = datetime.now(UTC)
    return {
        "service": "checkout-api",
        "environment": "production",
        "alert": "HTTP 503 spike with connection pool exhausted errors",
        "window_start": (end - timedelta(hours=1)).isoformat(),
        "window_end": end.isoformat(),
    }


def _settings() -> Settings:
    return Settings(
        auth_enabled=True,
        api_keys_json=json.dumps(
            {
                "viewer-secret": {"subject": "reviewer", "roles": ["viewer"]},
                "operator-secret": {"subject": "on-call", "roles": ["operator"]},
                "evaluator-secret": {"subject": "quality", "roles": ["evaluator"]},
            }
        ),
        redis_url=None,
    )


def _authorization(key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {key}"}


def test_api_key_role_matrix_is_enforced_server_side() -> None:
    client = TestClient(create_app(_settings()))
    assert client.get("/healthz").status_code == 200
    assert client.post("/api/incidents", json=incident_payload()).status_code == 401
    assert (
        client.post(
            "/api/incidents",
            json=incident_payload(),
            headers=_authorization("viewer-secret"),
        ).status_code
        == 403
    )
    created = client.post(
        "/api/incidents",
        json=incident_payload(),
        headers=_authorization("operator-secret"),
    )
    assert created.status_code == 201
    assert (
        client.get("/api/whoami", headers=_authorization("viewer-secret")).json()["subject"]
        == "reviewer"
    )
    assert (
        client.post(
            "/api/evaluations/run",
            json={"strict": False},
            headers=_authorization("operator-secret"),
        ).status_code
        == 403
    )


def test_inline_jobs_expose_inspectable_lifecycle() -> None:
    repository = MemoryJobRepository()
    manager = InlineJobManager(repository, max_workers=1)
    queued = manager.submit("evaluation", {"dataset": "sample"}, lambda: {"passed": True})
    deadline = time.monotonic() + 2
    current = repository.get(queued.id)
    while current.status not in {"SUCCEEDED", "FAILED"} and time.monotonic() < deadline:
        time.sleep(0.01)
        current = repository.get(queued.id)
    assert current.status == "SUCCEEDED"
    assert current.result == {"passed": True}


def test_queued_evaluation_api_returns_job() -> None:
    client = TestClient(create_app(_settings()))
    response = client.post(
        "/api/jobs/evaluations",
        json={"dataset": "evals/datasets/synthetic_incidents.jsonl", "strict": False},
        headers=_authorization("evaluator-secret"),
    )
    assert response.status_code == 202
    assert response.json()["kind"] == "evaluation"
    assert Path("evals/datasets/synthetic_incidents.jsonl").exists()
