#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
API_DIR = ROOT / "docs/contracts/api-reference"
OPENAPI_PATH = API_DIR / "openapi.json"
INDEX_PATH = API_DIR / "README.md"
CANONICAL_API_DIR = ROOT / "docs/contracts/api"
WEBSITE_API_DIR = ROOT / "apps/web-site/public"


def resolve_api_python() -> str:
    venv_python = ROOT / "services/api-server/.venv/bin/python"
    configured = os.environ.get("HARNESS_API_PYTHON")
    if configured:
        return configured
    return str(venv_python) if venv_python.is_file() else sys.executable


def load_openapi() -> dict:
    code = (
        "import json;"
        "from app.main import app;"
        "print(json.dumps(app.openapi(), ensure_ascii=False, sort_keys=True))"
    )
    result = subprocess.run(
        [resolve_api_python(), "-c", code],
        cwd=ROOT / "services/api-server",
        check=True,
        text=True,
        stdout=subprocess.PIPE,
    )
    return json.loads(result.stdout)


def render_yaml(schema: dict) -> str:
    result = subprocess.run(
        [
            resolve_api_python(),
            "-c",
            (
                "import json,sys,yaml;"
                "print(yaml.safe_dump(json.load(sys.stdin), sort_keys=False, allow_unicode=True), end='')"
            ),
        ],
        cwd=ROOT / "services/api-server",
        check=True,
        input=json.dumps(schema, ensure_ascii=False),
        text=True,
        stdout=subprocess.PIPE,
    )
    return result.stdout


def main() -> None:
    schema = load_openapi()
    API_DIR.mkdir(parents=True, exist_ok=True)
    CANONICAL_API_DIR.mkdir(parents=True, exist_ok=True)
    WEBSITE_API_DIR.mkdir(parents=True, exist_ok=True)
    json_payload = json.dumps(schema, indent=2, ensure_ascii=False) + "\n"
    yaml_payload = render_yaml(schema)
    json_targets = (
        OPENAPI_PATH,
        CANONICAL_API_DIR / "openapi.json",
        WEBSITE_API_DIR / "openapi.json",
    )
    yaml_targets = (
        CANONICAL_API_DIR / "openapi.yaml",
        WEBSITE_API_DIR / "openapi.yaml",
    )
    for target in json_targets:
        target.write_text(json_payload, encoding="utf-8")
    for target in yaml_targets:
        target.write_text(yaml_payload, encoding="utf-8")
    lines = [
        "# Harness API Reference",
        "",
        f"Title: {schema.get('info', {}).get('title', 'Harness API')}",
        f"Version: {schema.get('info', {}).get('version', 'unknown')}",
        "",
        "Generated from FastAPI OpenAPI metadata.",
        "",
        "## Endpoints",
        "",
    ]
    paths = schema.get("paths", {})
    for path in sorted(paths):
        operations = paths[path]
        for method in sorted(operations):
            if method.startswith("x-"):
                continue
            operation = operations[method]
            tags = ", ".join(operation.get("tags", [])) or "untagged"
            summary = operation.get("summary") or operation.get("operationId") or ""
            lines.append(f"### `{method.upper()} {path}`")
            lines.append("")
            lines.append(f"- Tags: {tags}")
            lines.append(f"- Summary: {summary}")
            responses = operation.get("responses", {})
            if responses:
                lines.append(f"- Responses: {', '.join(sorted(responses.keys()))}")
            lines.append("")
    INDEX_PATH.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    targets = (INDEX_PATH, *json_targets, *yaml_targets)
    print("wrote " + ", ".join(str(target.relative_to(ROOT)) for target in targets))


if __name__ == "__main__":
    main()
