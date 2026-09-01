from pathlib import Path
from unittest.mock import MagicMock

import yaml

from api import migrate


def test_apply_migration_uses_committed_sql(monkeypatch) -> None:
    connection = MagicMock()
    context = MagicMock()
    context.__enter__.return_value = connection
    monkeypatch.setattr(migrate.psycopg, "connect", MagicMock(return_value=context))

    migrate.apply_migration("postgresql://example", Path("infra/postgres/001_init.sql"))

    migrate.psycopg.connect.assert_called_once_with("postgresql://example")
    sql = connection.execute.call_args.args[0]
    assert "CREATE EXTENSION IF NOT EXISTS vector" in sql
    assert connection.execute.call_args.kwargs == {"prepare": False}


def test_render_blueprint_keeps_data_and_api_private() -> None:
    blueprint = yaml.safe_load(Path("render.yaml").read_text(encoding="utf-8"))
    services = {service["name"]: service for service in blueprint["services"]}

    api = services["llm-incident-assistant-api"]
    web = services["llm-incident-assistant-web"]
    queue = services["llm-incident-assistant-queue"]
    database = blueprint["databases"][0]
    api_env = {entry["key"]: entry for entry in api["envVars"]}
    web_env = {entry["key"]: entry for entry in web["envVars"]}

    assert blueprint["version"] == "1"
    assert api["type"] == "pserv"
    assert web["type"] == "web"
    assert web_env["API_UPSTREAM_HOSTPORT"]["fromService"]["type"] == "pserv"
    assert api_env["API_KEYS_JSON"] == {"key": "API_KEYS_JSON", "sync": False}
    assert api_env["DATABASE_URL"]["fromDatabase"]["property"] == "connectionString"
    assert queue["ipAllowList"] == []
    assert queue["persistenceMode"] == "journal-snapshot"
    assert database["ipAllowList"] == []
    assert database["postgresMajorVersion"] == "17"


def test_nginx_proxies_only_application_api_routes() -> None:
    config = Path("web/nginx.conf").read_text(encoding="utf-8")
    assert "location /api/" in config
    assert "proxy_pass http://${API_UPSTREAM_HOSTPORT};" in config
    assert "location /metrics" not in config
