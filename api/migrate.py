"""Apply the committed PostgreSQL schema in managed deployment workflows."""

from __future__ import annotations

from pathlib import Path

import psycopg

from api.config import get_settings

PROJECT_ROOT = Path(__file__).resolve().parents[1]
MIGRATION_PATH = PROJECT_ROOT / "infra" / "postgres" / "001_init.sql"


def apply_migration(database_url: str, migration_path: Path = MIGRATION_PATH) -> None:
    """Apply one idempotent, repository-controlled migration transaction."""

    if not database_url:
        raise ValueError("DATABASE_URL is required for database migrations")
    sql = migration_path.read_text(encoding="utf-8")
    with psycopg.connect(database_url) as connection:
        connection.execute(sql, prepare=False)


def main() -> None:
    """Load deployment settings and apply the committed schema."""

    database_url = get_settings().database_url
    if not database_url:
        raise ValueError("DATABASE_URL is required for database migrations")
    apply_migration(database_url)
    print(f"Applied migration: {MIGRATION_PATH.name}")


if __name__ == "__main__":
    main()
