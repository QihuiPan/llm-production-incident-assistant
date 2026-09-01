from pathlib import Path
from unittest.mock import MagicMock

import yaml
from fastapi.testclient import TestClient

from api import migrate
from api.config import Settings
from api.main import create_app


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


def test_render_blueprint_uses_only_free_resources() -> None:
    blueprint = yaml.safe_load(Path("render.yaml").read_text(encoding="utf-8"))
    services = {service["name"]: service for service in blueprint["services"]}

    web = services["llm-incident-assistant"]
    database = blueprint["databases"][0]
    web_env = {entry["key"]: entry for entry in web["envVars"]}

    assert blueprint["version"] == "1"
    assert web["type"] == "web"
    assert web["plan"] == "free"
    assert web["dockerfilePath"] == "./Dockerfile.render-free"
    assert web_env["JOB_BACKEND"]["value"] == "inline"
    assert web_env["API_KEYS_JSON"] == {"key": "API_KEYS_JSON", "sync": False}
    assert web_env["DATABASE_URL"]["fromDatabase"]["property"] == "connectionString"
    assert "REDIS_URL" not in web_env
    assert database["plan"] == "free"
    assert database["ipAllowList"] == []
    assert database["postgresMajorVersion"] == "17"
    assert "diskSizeGB" not in database


def test_combined_runtime_serves_workspace_and_api(tmp_path: Path) -> None:
    (tmp_path / "index.html").write_text("<h1>Incident Assistant</h1>", encoding="utf-8")
    app = create_app(Settings(web_dist_dir=str(tmp_path)))
    client = TestClient(app)

    assert client.get("/").text == "<h1>Incident Assistant</h1>"
    assert client.get("/healthz").json()["status"] == "ok"


def test_nginx_proxies_only_application_api_routes() -> None:
    config = Path("web/nginx.conf").read_text(encoding="utf-8")
    assert "location /api/" in config
    assert "proxy_pass http://${API_UPSTREAM_HOSTPORT};" in config
    assert "location /metrics" not in config
