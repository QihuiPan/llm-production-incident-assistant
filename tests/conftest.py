from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from api.models import Incident, IncidentCreate


@pytest.fixture
def incident() -> Incident:
    end = datetime.now(UTC)
    payload = IncidentCreate(
        service="checkout-api",
        environment="production",
        alert="HTTP 503 spike with connection pool exhausted errors",
        window_start=end - timedelta(hours=1),
        window_end=end,
    )
    return Incident(**payload.model_dump())
