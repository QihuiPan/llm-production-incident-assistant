"""Structured LLM providers, validation repair, cache, fallback, and cost budgets."""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import RLock
from typing import Any, Literal, Protocol

import httpx2 as httpx
import psycopg
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from api.models import Evidence, Hypothesis, Incident, TimelineEvent
from api.security import redact_text

SYSTEM_PROMPT = (Path(__file__).resolve().parents[1] / "prompts" / "system.md").read_text(
    encoding="utf-8"
)


class LLMTimeWindow(BaseModel):
    model_config = ConfigDict(extra="forbid")

    service: str
    environment: Literal["production", "staging", "development"]
    start: datetime
    end: datetime


class LLMSearchLogsArguments(LLMTimeWindow):
    query: str
    limit: int


class LLMGetMetricsArguments(LLMTimeWindow):
    metric: Literal[
        "http_request_rate",
        "http_error_rate",
        "http_latency_p95",
        "cpu_utilization",
        "memory_utilization",
        "queue_depth",
    ]
    step_seconds: int


class LLMGetDeploymentsArguments(LLMTimeWindow):
    pass


class LLMGetDependenciesArguments(BaseModel):
    model_config = ConfigDict(extra="forbid")

    service: str


LLMToolArguments = (
    LLMSearchLogsArguments
    | LLMGetMetricsArguments
    | LLMGetDeploymentsArguments
    | LLMGetDependenciesArguments
)


class QueryDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tool: Literal[
        "search_logs",
        "get_metrics",
        "get_recent_deployments",
        "get_service_dependencies",
    ]
    arguments: LLMToolArguments
    reason: str = Field(min_length=3, max_length=500)

    @model_validator(mode="after")
    def validate_tool_arguments(self) -> QueryDraft:
        expected = {
            "search_logs": LLMSearchLogsArguments,
            "get_metrics": LLMGetMetricsArguments,
            "get_recent_deployments": LLMGetDeploymentsArguments,
            "get_service_dependencies": LLMGetDependenciesArguments,
        }[self.tool]
        if not isinstance(self.arguments, expected):
            raise ValueError("tool and argument schema do not match")
        return self

    def gateway_arguments(self) -> dict[str, Any]:
        arguments = self.arguments.model_dump(mode="json")
        if self.tool == "get_metrics":
            arguments["labels"] = {}
        return arguments


class InvestigationDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    summary: str = Field(min_length=3, max_length=4000)
    timeline: list[TimelineEvent]
    hypotheses: list[Hypothesis]
    next_queries: list[QueryDraft]
    insufficient_evidence: bool


@dataclass(frozen=True)
class LLMUsage:
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0


@dataclass(frozen=True)
class LLMResult:
    draft: InvestigationDraft
    usage: LLMUsage
    provider: str
    model: str
    cache_hit: bool = False
    fallback_used: bool = False
    latency_ms: float = 0.0


class LLMProviderError(RuntimeError):
    """Raised when a provider cannot return a valid, schema-constrained draft."""


class LLMProvider(Protocol):
    def generate(self, incident: Incident, evidence: list[Evidence]) -> LLMResult: ...


class ProviderChain:
    """Try configured external models in order before the service-level safe fallback."""

    def __init__(self, providers: list[LLMProvider]) -> None:
        if not providers:
            raise ValueError("provider chain cannot be empty")
        self.providers = providers
        self.provider_name = "+".join(
            str(getattr(provider, "provider_name", type(provider).__name__))
            for provider in providers
        )
        self.model_name = "+".join(
            str(getattr(provider, "model_name", "unknown")) for provider in providers
        )

    def generate(self, incident: Incident, evidence: list[Evidence]) -> LLMResult:
        failures: list[str] = []
        for position, provider in enumerate(self.providers):
            try:
                result = provider.generate(incident, evidence)
                return replace(result, fallback_used=position > 0)
            except LLMProviderError as exc:
                failures.append(str(exc))
        raise LLMProviderError("all configured providers failed: " + "; ".join(failures))


def _cause_for_context(incident: Incident, evidence: list[Evidence]) -> str:
    combined = " ".join([incident.alert, *(item.excerpt for item in evidence)]).lower()
    if "connection pool" in combined or "pool_acquire" in combined:
        return "Database connection pool exhaustion is the leading hypothesis."
    if "queue" in combined and ("backlog" in combined or "depth" in combined):
        return "A slow or unavailable queue consumer is the leading hypothesis."
    if "503" in combined or "downstream" in combined:
        return "A downstream dependency failure is the leading hypothesis."
    if "latency" in combined or "timeout" in combined:
        return "Downstream latency or timeout propagation is the leading hypothesis."
    return "The available evidence does not identify a specific root cause."


class DeterministicLLMProvider:
    """Credential-free grounded fallback that exercises the production contract."""

    provider_name = "deterministic"
    model_name = "local-baseline-v2"

    def generate(self, incident: Incident, evidence: list[Evidence]) -> LLMResult:
        started = time.perf_counter()
        supporting = [
            item.id for item in evidence[:3] if not item.metadata.get("injection_flagged", False)
        ]
        common_window = {
            "service": incident.service,
            "environment": incident.environment,
            "start": incident.window_start.isoformat(),
            "end": incident.window_end.isoformat(),
        }
        queries = [
            QueryDraft(
                tool="get_recent_deployments",
                arguments=common_window,
                reason="Correlate the alert with recent code changes.",
            ),
            QueryDraft(
                tool="search_logs",
                arguments={**common_window, "query": incident.alert[:300], "limit": 100},
                reason="Collect bounded service errors matching the alert signature.",
            ),
            QueryDraft(
                tool="get_metrics",
                arguments={
                    **common_window,
                    "metric": "http_error_rate",
                    "step_seconds": 60,
                },
                reason="Confirm the error-rate trend during the incident window.",
            ),
        ]
        if not supporting:
            draft = InvestigationDraft(
                summary=(
                    "Insufficient evidence. Approve the proposed read-only queries to gather "
                    "incident-specific signals."
                ),
                timeline=[],
                hypotheses=[],
                next_queries=queries,
                insufficient_evidence=True,
            )
        else:
            cause = _cause_for_context(incident, evidence)
            draft = InvestigationDraft(
                summary=(
                    f"{cause} This is a grounded preliminary assessment; "
                    "tool evidence is still pending."
                ),
                timeline=[
                    TimelineEvent(
                        at=incident.window_start.isoformat(),
                        event=f"Alert opened for {incident.service}: {incident.alert[:180]}",
                        evidence_ids=supporting[:1],
                    )
                ],
                hypotheses=[
                    Hypothesis(
                        cause=cause,
                        confidence=min(0.88, 0.48 + 0.1 * len(supporting)),
                        supporting_evidence=supporting[:2],
                        contradictions=supporting[2:3],
                    )
                ],
                next_queries=queries,
                insufficient_evidence=False,
            )
        estimated_input = max(
            1,
            (len(incident.alert) + sum(len(item.excerpt) for item in evidence)) // 4,
        )
        return LLMResult(
            draft=draft,
            usage=LLMUsage(
                input_tokens=estimated_input,
                output_tokens=len(draft.model_dump_json()) // 4,
            ),
            provider=self.provider_name,
            model=self.model_name,
            latency_ms=(time.perf_counter() - started) * 1000,
        )


class OpenAIResponsesProvider:
    """Call an OpenAI Responses endpoint with strict JSON-schema output."""

    def __init__(
        self,
        *,
        endpoint: str,
        api_key: str,
        model: str,
        timeout_seconds: float = 20.0,
        max_output_tokens: int = 1200,
        input_cost_per_million: float = 0.0,
        output_cost_per_million: float = 0.0,
        requester: Any | None = None,
    ) -> None:
        self.endpoint = endpoint
        self.api_key = api_key
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.max_output_tokens = max_output_tokens
        self.input_cost_per_million = input_cost_per_million
        self.output_cost_per_million = output_cost_per_million
        self.requester = requester
        self.provider_name = "openai_responses"
        self.model_name = model

    @staticmethod
    def _evidence_payload(evidence: list[Evidence]) -> list[dict[str, Any]]:
        return [
            {
                "id": item.id,
                "source": item.source,
                "version": item.source_version,
                "trust_level": item.trust_level.value,
                "excerpt": item.excerpt,
            }
            for item in evidence
        ]

    def _request(self, payload: dict[str, Any]) -> dict[str, Any]:
        if self.requester is not None:
            return self.requester(payload)
        with httpx.Client(timeout=self.timeout_seconds) as client:
            response = client.post(
                self.endpoint,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            response.raise_for_status()
            return response.json()

    def generate(self, incident: Incident, evidence: list[Evidence]) -> LLMResult:
        started = time.perf_counter()
        safe_alert, _ = redact_text(incident.alert)
        user_payload = {
            "incident": incident.model_copy(update={"alert": safe_alert}).model_dump(mode="json"),
            "untrusted_evidence": self._evidence_payload(evidence),
        }
        input_items = [
            {
                "role": "user",
                "content": json.dumps(user_payload, separators=(",", ":")),
            }
        ]
        last_error = "unknown validation error"
        for attempt in range(2):
            request = {
                "model": self.model,
                "instructions": SYSTEM_PROMPT,
                "input": input_items,
                "max_output_tokens": self.max_output_tokens,
                "store": False,
                "text": {
                    "format": {
                        "type": "json_schema",
                        "name": "incident_investigation",
                        "strict": True,
                        "schema": InvestigationDraft.model_json_schema(),
                    }
                },
            }
            try:
                response = self._request(request)
                content = self._output_text(response)
                raw = json.loads(content) if isinstance(content, str) else content
                draft = InvestigationDraft.model_validate(raw)
                usage = response.get("usage", {})
                input_tokens = int(usage.get("input_tokens", 0))
                output_tokens = int(usage.get("output_tokens", 0))
                cost = (
                    input_tokens * self.input_cost_per_million
                    + output_tokens * self.output_cost_per_million
                ) / 1_000_000
                return LLMResult(
                    draft=draft,
                    usage=LLMUsage(input_tokens, output_tokens, cost),
                    provider=self.provider_name,
                    model=self.model,
                    latency_ms=(time.perf_counter() - started) * 1000,
                )
            except (KeyError, TypeError, json.JSONDecodeError, ValidationError) as exc:
                last_error = str(exc)
                if attempt == 0:
                    input_items.append(
                        {
                            "role": "user",
                            "content": (
                                "The previous response failed schema validation. Return only a "
                                "corrected "
                                f"JSON object. Validation error: {last_error[:1000]}"
                            ),
                        }
                    )
                    continue
                break
            except Exception as exc:
                raise LLMProviderError(f"provider request failed: {exc}") from exc
        raise LLMProviderError(f"provider returned invalid structured output: {last_error}")

    @staticmethod
    def _output_text(response: dict[str, Any]) -> str:
        direct = response.get("output_text")
        if isinstance(direct, str):
            return direct
        for item in response.get("output", []):
            for content in item.get("content", []):
                if content.get("type") == "output_text" and isinstance(content.get("text"), str):
                    return content["text"]
        raise KeyError("response did not contain output_text")


OpenAICompatibleProvider = OpenAIResponsesProvider


class LLMCache(Protocol):
    def get(self, key: str) -> LLMResult | None: ...

    def put(self, key: str, result: LLMResult, ttl_seconds: int) -> None: ...


class MemoryLLMCache:
    def __init__(self) -> None:
        self._lock = RLock()
        self._values: dict[str, tuple[datetime, LLMResult]] = {}

    def get(self, key: str) -> LLMResult | None:
        with self._lock:
            record = self._values.get(key)
            if record is None:
                return None
            expires_at, result = record
            if expires_at <= datetime.now(UTC):
                self._values.pop(key, None)
                return None
            return result

    def put(self, key: str, result: LLMResult, ttl_seconds: int) -> None:
        with self._lock:
            self._values[key] = (datetime.now(UTC) + timedelta(seconds=ttl_seconds), result)


class PostgresLLMCache:
    def __init__(self, database_url: str) -> None:
        self.database_url = database_url

    def get(self, key: str) -> LLMResult | None:
        with psycopg.connect(self.database_url) as connection:
            row = connection.execute(
                """
                SELECT response, provider, model, input_tokens, output_tokens,
                       cost_usd, fallback_used
                FROM llm_cache WHERE cache_key = %s AND expires_at > now()
                """,
                (key,),
            ).fetchone()
        if row is None:
            return None
        return LLMResult(
            draft=InvestigationDraft.model_validate(row[0]),
            usage=LLMUsage(row[3], row[4], float(row[5])),
            provider=row[1],
            model=row[2],
            cache_hit=True,
            fallback_used=bool(row[6]),
        )

    def put(self, key: str, result: LLMResult, ttl_seconds: int) -> None:
        with psycopg.connect(self.database_url) as connection:
            connection.execute(
                """
                INSERT INTO llm_cache
                    (cache_key, provider, model, response, input_tokens,
                     output_tokens, cost_usd, fallback_used, expires_at)
                VALUES (%s, %s, %s, %s::jsonb, %s, %s, %s, %s,
                        now() + %s * interval '1 second')
                ON CONFLICT (cache_key) DO UPDATE SET
                    response = EXCLUDED.response,
                    input_tokens = EXCLUDED.input_tokens,
                    output_tokens = EXCLUDED.output_tokens,
                    cost_usd = EXCLUDED.cost_usd,
                    fallback_used = EXCLUDED.fallback_used,
                    expires_at = EXCLUDED.expires_at
                """,
                (
                    key,
                    result.provider,
                    result.model,
                    result.draft.model_dump_json(),
                    result.usage.input_tokens,
                    result.usage.output_tokens,
                    result.usage.cost_usd,
                    result.fallback_used,
                    ttl_seconds,
                ),
            )


class BudgetLedger(Protocol):
    def spent_today(self) -> float: ...

    def record(self, usage: LLMUsage) -> None: ...


class MemoryBudgetLedger:
    def __init__(self) -> None:
        self._day = datetime.now(UTC).date()
        self._cost = 0.0
        self._lock = RLock()

    def spent_today(self) -> float:
        with self._lock:
            current_day = datetime.now(UTC).date()
            if self._day != current_day:
                self._day = current_day
                self._cost = 0.0
            return self._cost

    def record(self, usage: LLMUsage) -> None:
        with self._lock:
            self.spent_today()
            self._cost += usage.cost_usd


class PostgresBudgetLedger:
    """Atomically aggregate model usage across API and worker processes."""

    def __init__(self, database_url: str) -> None:
        self.database_url = database_url

    def spent_today(self) -> float:
        with psycopg.connect(self.database_url) as connection:
            row = connection.execute(
                "SELECT cost_usd FROM daily_costs WHERE usage_date = CURRENT_DATE"
            ).fetchone()
        return float(row[0]) if row else 0.0

    def record(self, usage: LLMUsage) -> None:
        with psycopg.connect(self.database_url) as connection:
            connection.execute(
                """
                INSERT INTO daily_costs (usage_date, cost_usd, input_tokens, output_tokens)
                VALUES (CURRENT_DATE, %s, %s, %s)
                ON CONFLICT (usage_date) DO UPDATE SET
                    cost_usd = daily_costs.cost_usd + EXCLUDED.cost_usd,
                    input_tokens = daily_costs.input_tokens + EXCLUDED.input_tokens,
                    output_tokens = daily_costs.output_tokens + EXCLUDED.output_tokens,
                    updated_at = now()
                """,
                (usage.cost_usd, usage.input_tokens, usage.output_tokens),
            )


class LLMService:
    """Apply cache, cost budget, provider fallback, and deterministic degradation."""

    def __init__(
        self,
        provider: LLMProvider,
        *,
        fallback: LLMProvider | None = None,
        cache: LLMCache | None = None,
        ledger: BudgetLedger | None = None,
        cache_ttl_seconds: int = 900,
        daily_budget_usd: float = 5.0,
    ) -> None:
        self.provider = provider
        self.fallback = fallback or DeterministicLLMProvider()
        self.cache = cache or MemoryLLMCache()
        self.ledger = ledger or MemoryBudgetLedger()
        self.cache_ttl_seconds = cache_ttl_seconds
        self.daily_budget_usd = daily_budget_usd

    def _key(self, incident: Incident, evidence: list[Evidence]) -> str:
        payload = {
            "incident": incident.model_dump(mode="json"),
            "evidence": [(item.id, item.quote_hash) for item in evidence],
            "provider": getattr(self.provider, "provider_name", type(self.provider).__name__),
            "model": getattr(self.provider, "model_name", "unknown"),
        }
        return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()

    def generate(self, incident: Incident, evidence: list[Evidence]) -> LLMResult:
        key = self._key(incident, evidence)
        cached = self.cache.get(key)
        if cached is not None:
            return LLMResult(
                draft=cached.draft,
                usage=cached.usage,
                provider=cached.provider,
                model=cached.model,
                cache_hit=True,
                fallback_used=cached.fallback_used,
                latency_ms=0.0,
            )
        if self.ledger.spent_today() >= self.daily_budget_usd:
            result = self.fallback.generate(incident, evidence)
            return replace(result, fallback_used=True)
        try:
            result = self.provider.generate(incident, evidence)
        except LLMProviderError:
            fallback = self.fallback.generate(incident, evidence)
            result = replace(fallback, fallback_used=True)
        self.ledger.record(result.usage)
        if self.cache_ttl_seconds:
            self.cache.put(key, result, self.cache_ttl_seconds)
        return result
