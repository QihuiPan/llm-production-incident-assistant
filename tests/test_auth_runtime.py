import json
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
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


def test_public_demo_is_keyless_but_protected_routes_remain_private() -> None:
    settings = _settings().model_copy(
        update={
            "public_demo_enabled": True,
            "public_demo_rate_limit_requests": 2,
            "public_demo_global_limit_requests": 2,
        }
    )
    client = TestClient(create_app(settings))

    status = client.get("/api/demo/status")
    assert status.json() == {
        "enabled": True,
        "services": ["checkout-api", "payments-api", "inventory-api"],
        "synthetic_data_only": True,
        "api_key_required": False,
    }
    investigated = client.post("/api/demo/investigate", json=incident_payload())
    assert investigated.status_code == 200
    assert investigated.headers["cache-control"] == "no-store"
    assert investigated.json()["evidence"]
    assert all(item["status"] == "PENDING" for item in investigated.json()["next_queries"])
    assert client.get("/api/dashboard").status_code == 401
    assert client.post("/api/incidents", json=incident_payload()).status_code == 401


def test_public_demo_restricts_services_and_rate() -> None:
    settings = _settings().model_copy(
        update={
            "public_demo_enabled": True,
            "public_demo_rate_limit_requests": 1,
            "public_demo_global_limit_requests": 2,
        }
    )
    client = TestClient(create_app(settings))
    unknown = incident_payload() | {"service": "private-service"}
    assert client.post("/api/demo/investigate", json=unknown).status_code == 422
    assert client.post("/api/demo/investigate", json=incident_payload()).status_code == 200
    limited = client.post("/api/demo/investigate", json=incident_payload())
    assert limited.status_code == 429
    assert int(limited.headers["retry-after"]) > 0


def test_public_demo_rejects_billable_or_production_backends() -> None:
    unsafe_model = _settings().model_copy(
        update={"public_demo_enabled": True, "llm_provider": "openai_compatible"}
    )
    with pytest.raises(ValueError, match="LLM_PROVIDER=deterministic"):
        create_app(unsafe_model)

    unsafe_tools = _settings().model_copy(
        update={"public_demo_enabled": True, "tool_backend": "production"}
    )
    with pytest.raises(ValueError, match="TOOL_BACKEND=simulator"):
        create_app(unsafe_tools)


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
