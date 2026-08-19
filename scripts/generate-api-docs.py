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


def load_openapi() -> dict:
    venv_python = ROOT / "services/api-server/.venv/bin/python"
    api_python = os.environ.get("HARNESS_API_PYTHON")
    if not api_python:
        api_python = str(venv_python) if venv_python.is_file() else sys.executable
    code = (
        "import json;"
        "from app.main import app;"
        "print(json.dumps(app.openapi(), ensure_ascii=False, sort_keys=True))"
    )
    result = subprocess.run(
        [api_python, "-c", code],
        cwd=ROOT / "services/api-server",
        check=True,
        text=True,
        stdout=subprocess.PIPE,
    )
    return json.loads(result.stdout)


def main() -> None:
    schema = load_openapi()
    API_DIR.mkdir(parents=True, exist_ok=True)
    OPENAPI_PATH.write_text(json.dumps(schema, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    lines = [
        "# Forge Harness API Reference",
        "",
        f"Title: {schema.get('info', {}).get('title', 'Forge Harness API')}",
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
    print(f"wrote {INDEX_PATH.relative_to(ROOT)} and {OPENAPI_PATH.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
