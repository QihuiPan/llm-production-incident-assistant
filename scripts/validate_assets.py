"""Validate committed JSON, YAML, and generated OpenAPI delivery contracts."""

from __future__ import annotations

import json
from pathlib import Path

import yaml

from api.main import create_app


def main() -> None:
    json_files = [Path("prompts/investigation.schema.json")]
    yaml_files = [
        *Path(".github/workflows").glob("*.yml"),
        *Path("infra/k8s").glob("*.yaml"),
        Path("docker-compose.yml"),
        Path("infra/prometheus.yml"),
        Path("render.yaml"),
    ]
    for path in json_files:
        json.loads(path.read_text(encoding="utf-8"))
    for path in yaml_files:
        list(yaml.safe_load_all(path.read_text(encoding="utf-8")))
    schema = create_app().openapi()
    if schema["info"]["version"] != "2.1.0":
        raise RuntimeError("OpenAPI release version does not match v2.1")
    print(
        f"Validated {len(json_files)} JSON files, {len(yaml_files)} YAML files, "
        f"and {len(schema['paths'])} OpenAPI paths."
    )


if __name__ == "__main__":
    main()
