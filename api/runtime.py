"""Configuration-driven construction of production and local runtime services."""

from __future__ import annotations

from dataclasses import dataclass

from api.config import Settings
from api.llm import (
    DeterministicLLMProvider,
    LLMService,
    MemoryBudgetLedger,
    MemoryLLMCache,
    OpenAIResponsesProvider,
    PostgresBudgetLedger,
    PostgresLLMCache,
    ProviderChain,
)
from api.postgres_store import PostgresStore
from api.repositories import Store
from api.store import MemoryStore
from api.tracing import MemoryTraceRecorder, PostgresTraceRecorder, TraceRecorder
from retrieval.advanced import SearchIndex
from retrieval.hybrid import HybridIndex
from retrieval.postgres import PostgresHybridIndex
from retrieval.seed import load_demo_documents
from tools.adapters import ADAPTERS
from tools.gateway import ToolGateway
from tools.production_adapters import ProductionAdapters


@dataclass(frozen=True)
class Runtime:
    store: Store
    index: SearchIndex
    gateway: ToolGateway
    llm_service: LLMService
    traces: TraceRecorder


def _database_url(settings: Settings) -> str:
    if not settings.database_url:
        raise ValueError("DATABASE_URL is required when PostgreSQL storage is enabled")
    return settings.database_url


def _llm_service(settings: Settings) -> LLMService:
    fallback = DeterministicLLMProvider()
    if settings.llm_provider == "deterministic":
        provider = fallback
    else:
        if not settings.llm_api_url or not settings.llm_api_key or not settings.llm_model:
            raise ValueError(
                "LLM_API_URL, LLM_API_KEY, and LLM_MODEL are required for openai_compatible"
            )
        provider_options = {
            "endpoint": settings.llm_api_url,
            "api_key": settings.llm_api_key.get_secret_value(),
            "timeout_seconds": settings.llm_timeout_seconds,
            "max_output_tokens": settings.llm_max_output_tokens,
            "input_cost_per_million": settings.llm_input_cost_per_million,
            "output_cost_per_million": settings.llm_output_cost_per_million,
        }
        providers = [OpenAIResponsesProvider(model=settings.llm_model, **provider_options)]
        if settings.llm_fallback_model:
            providers.append(
                OpenAIResponsesProvider(model=settings.llm_fallback_model, **provider_options)
            )
        provider = ProviderChain(providers)

    if settings.storage_backend == "postgres":
        database_url = _database_url(settings)
        cache = PostgresLLMCache(database_url)
        ledger = PostgresBudgetLedger(database_url)
    else:
        cache = MemoryLLMCache()
        ledger = MemoryBudgetLedger()
    return LLMService(
        provider,
        fallback=fallback,
        cache=cache,
        ledger=ledger,
        cache_ttl_seconds=settings.llm_cache_ttl_seconds,
        daily_budget_usd=settings.daily_cost_budget_usd,
    )


def build_runtime(settings: Settings) -> Runtime:
    """Construct a complete runtime without hidden process-global dependencies."""

    if settings.storage_backend == "postgres":
        database_url = _database_url(settings)
        store: Store = PostgresStore(database_url)
        index: SearchIndex = PostgresHybridIndex(database_url)
        traces: TraceRecorder = PostgresTraceRecorder(database_url)
    else:
        store = MemoryStore()
        index = HybridIndex()
        traces = MemoryTraceRecorder()
    load_demo_documents(index)  # type: ignore[arg-type]

    adapters = (
        ProductionAdapters(settings).mapping if settings.tool_backend == "production" else ADAPTERS
    )
    gateway = ToolGateway(
        store,
        adapters=adapters,
        traces=traces,
        max_calls_per_incident=settings.max_tool_calls_per_run,
        max_window_hours=settings.max_query_window_hours,
        max_rows=settings.max_tool_rows,
    )
    return Runtime(store, index, gateway, _llm_service(settings), traces)
