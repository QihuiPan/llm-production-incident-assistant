"""Environment-backed application settings."""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Validated settings with conservative safety defaults."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "development"
    log_level: str = "INFO"
    allowed_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    max_document_bytes: int = Field(default=5 * 1024 * 1024, ge=1024)
    max_tool_calls_per_run: int = Field(default=3, ge=1, le=10)
    max_query_window_hours: int = Field(default=24, ge=1, le=168)
    max_tool_rows: int = Field(default=200, ge=1, le=1000)
    daily_cost_budget_usd: float = Field(default=5.0, gt=0)
    database_url: str | None = None
    storage_backend: Literal["memory", "postgres"] = "memory"
    retrieval_mode: Literal["vector", "hybrid", "advanced"] = "advanced"
    tool_backend: Literal["simulator", "production"] = "simulator"
    auth_enabled: bool = False
    api_keys_json: str = "{}"
    llm_provider: Literal["deterministic", "openai_compatible"] = "deterministic"
    llm_api_url: str | None = None
    llm_api_key: SecretStr | None = None
    llm_model: str | None = None
    llm_fallback_model: str | None = None
    llm_timeout_seconds: float = Field(default=20.0, gt=0, le=120)
    llm_max_output_tokens: int = Field(default=1200, ge=100, le=16_000)
    llm_cache_ttl_seconds: int = Field(default=900, ge=0, le=86_400)
    llm_input_cost_per_million: float = Field(default=0.0, ge=0)
    llm_output_cost_per_million: float = Field(default=0.0, ge=0)
    redis_url: str | None = "redis://localhost:6379/0"
    job_backend: Literal["inline", "rq"] = "inline"
    opensearch_url: str | None = None
    opensearch_index: str = "logs-*"
    prometheus_url: str | None = None
    deployment_api_url: str | None = None
    service_catalog_url: str | None = None
    telemetry_bearer_token: SecretStr | None = None

    @property
    def origins(self) -> list[str]:
        """Return normalized browser origins for CORS configuration."""

        return [origin.strip() for origin in self.allowed_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    """Load settings once per process."""

    return Settings()
