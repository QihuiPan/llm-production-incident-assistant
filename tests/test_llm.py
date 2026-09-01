from dataclasses import replace

from api.llm import (
    DeterministicLLMProvider,
    LLMProviderError,
    LLMService,
    OpenAIResponsesProvider,
)
from api.models import Evidence, TrustLevel


def _evidence(incident_id: str) -> list[Evidence]:
    return [
        Evidence(
            id="E001",
            incident_id=incident_id,
            source_type="document",
            source="runbook.md",
            source_version="1",
            trust_level=TrustLevel.OFFICIAL,
            excerpt="The database connection pool is exhausted.",
            score=1,
            quote_hash="abc",
        )
    ]


def _draft() -> dict[str, object]:
    return {
        "summary": "Connection pool exhaustion is likely.",
        "timeline": [{"at": "now", "event": "Alert fired", "evidence_ids": ["E001"]}],
        "hypotheses": [
            {
                "cause": "Database connection pool exhaustion.",
                "confidence": 0.8,
                "supporting_evidence": ["E001"],
                "contradictions": [],
            }
        ],
        "next_queries": [],
        "insufficient_evidence": False,
    }


def test_responses_provider_uses_strict_schema_and_repairs_once(incident) -> None:
    requests: list[dict[str, object]] = []

    def requester(payload):
        requests.append(payload)
        if len(requests) == 1:
            return {"output_text": "not json", "usage": {}}
        return {
            "output_text": __import__("json").dumps(_draft()),
            "usage": {"input_tokens": 120, "output_tokens": 40},
        }

    provider = OpenAIResponsesProvider(
        endpoint="https://api.example.test/v1/responses",
        api_key="test-key",
        model="test-model",
        requester=requester,
    )
    result = provider.generate(incident, _evidence(incident.id))
    assert len(requests) == 2
    assert requests[0]["text"]["format"]["strict"] is True
    assert requests[0]["store"] is False
    assert result.usage.input_tokens == 120
    assert result.draft.hypotheses[0].supporting_evidence == ["E001"]


def test_service_falls_back_when_external_provider_fails(incident) -> None:
    class BrokenProvider:
        provider_name = "broken"
        model_name = "broken-model"

        def generate(self, incident, evidence):
            raise LLMProviderError("unavailable")

    service = LLMService(BrokenProvider(), fallback=DeterministicLLMProvider())
    result = service.generate(incident, _evidence(incident.id))
    assert result.fallback_used
    assert result.provider == "deterministic"


def test_cached_result_does_not_repeat_provider_request(incident) -> None:
    provider = DeterministicLLMProvider()
    service = LLMService(provider)
    first = service.generate(incident, _evidence(incident.id))
    second = service.generate(incident, _evidence(incident.id))
    assert not first.cache_hit
    assert second.cache_hit
    assert replace(first, cache_hit=True, latency_ms=0) == second
