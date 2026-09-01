"""Environment-backed application settings."""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field
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

    @property
    def origins(self) -> list[str]:
        """Return normalized browser origins for CORS configuration."""

        return [origin.strip() for origin in self.allowed_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    """Load settings once per process."""

    return Settings()
