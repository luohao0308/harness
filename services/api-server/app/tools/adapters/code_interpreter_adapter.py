from __future__ import annotations

import ast
import base64
import json
import shlex
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.sandbox.docker_manager import SandboxCommandResult
from app.tools.adapter_registry import AdapterRegistry, AdapterResult
from app.tools.registry import RiskLevel, ToolMetadata

MAX_STDIO_BYTES = 64 * 1024
MAX_FILE_BYTES = 8 * 1024 * 1024
MAX_CODE_CHARS = 100_000
DEFAULT_TIMEOUT_SECONDS = 30
MAX_TIMEOUT_SECONDS = 60
DENIED_IMPORTS = {"socket", "subprocess", "importlib"}
DENIED_IMPORT_MEMBERS = {("os", "system"), ("os", "popen"), ("importlib", "import_module")}
DENIED_CALLS = {
    ("os", "system"),
    ("os", "popen"),
    ("subprocess", "run"),
    ("subprocess", "Popen"),
    ("subprocess", "call"),
    ("subprocess", "check_call"),
    ("subprocess", "check_output"),
}
DENIED_NAMES = {"eval", "exec", "compile", "__import__", "getattr"}


SandboxCommandExecutor = Callable[[str, str, int], SandboxCommandResult]


@dataclass(frozen=True)
class CodeInterpreterAdapter:
    slug: str
    method: str
    description: str
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]
    risk_level: RiskLevel = "high"

    server_label: str = "code_interpreter"
    requires_secret: bool = False
    module_path: str = "app.tools.adapters.code_interpreter_adapter"

    def execute(
        self,
        *,
        metadata: ToolMetadata,
        input_json: dict[str, Any],
        config_json: dict[str, Any] | None,
        secret_value: str | None,
        sandbox_workspace_root: Path | None = None,
        sandbox_command_executor: SandboxCommandExecutor | None = None,
    ) -> AdapterResult:
        del metadata, config_json, secret_value, sandbox_workspace_root
        if sandbox_command_executor is None:
            return AdapterResult(
                {
                    "error": "sandbox_not_ready",
                    "message": "Code Interpreter requires an active sandbox executor",
                }
            )
        if self.method == "run_python":
            return AdapterResult(_run_python(input_json, sandbox_command_executor))
        if self.method == "install_package":
            return AdapterResult(_install_package(input_json, sandbox_command_executor))
        return AdapterResult({"error": "unsupported_method", "message": self.method})

    def health_check(
        self,
        *,
        config_json: dict[str, Any] | None,
        secret_value: str | None,
    ) -> dict[str, Any]:
        del config_json, secret_value
        return {
            "ok": True,
            "latency_ms": 0,
            "message": "Code Interpreter is available when a run sandbox is attached",
            "sample": {
                "requires_sandbox_executor": True,
                "stdout_limit_bytes": MAX_STDIO_BYTES,
                "generated_file_limit_bytes": MAX_FILE_BYTES,
            },
        }


def register_code_interpreter_adapters(registry: AdapterRegistry) -> None:
    for adapter in [
        CodeInterpreterAdapter(
            slug="code_interpreter.run_python",
            method="run_python",
            description="Run bounded Python code inside an Agent sandbox.",
            risk_level="high",
            input_schema={
                "type": "object",
                "properties": {
                    "code": {"type": "string", "minLength": 1},
                    "stdin": {"type": "string"},
                    "files": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "name": {"type": "string"},
                                "content": {"type": "string"},
                                "base64": {"type": "boolean", "default": False},
                            },
                            "required": ["name", "content"],
                        },
                    },
                    "timeout_seconds": {"type": "integer", "default": DEFAULT_TIMEOUT_SECONDS},
                    "idempotency_key": {"type": "string", "minLength": 1},
                },
                "required": ["code", "idempotency_key"],
            },
            output_schema={
                "type": "object",
                "properties": {
                    "stdout": {"type": "string"},
                    "stderr": {"type": "string"},
                    "exit_code": {"type": "integer"},
                    "generated_files": {"type": "array"},
                },
            },
        ),
        CodeInterpreterAdapter(
            slug="code_interpreter.install_package",
            method="install_package",
            description="Install a Python package inside the current sandbox.",
            risk_level="high",
            input_schema={
                "type": "object",
                "properties": {
                    "package": {"type": "string", "minLength": 1},
                    "version": {"type": "string"},
                    "timeout_seconds": {"type": "integer", "default": DEFAULT_TIMEOUT_SECONDS},
                    "idempotency_key": {"type": "string", "minLength": 1},
                },
                "required": ["package", "idempotency_key"],
            },
            output_schema={"type": "object", "properties": {"installed": {"type": "boolean"}}},
        ),
    ]:
        registry.register(adapter)


def _run_python(
    input_json: dict[str, Any],
    executor: SandboxCommandExecutor,
) -> dict[str, Any]:
    code = str(input_json.get("code") or "")
    if not code.strip():
        return {"error": "invalid_input", "message": "code is required"}
    if len(code) > MAX_CODE_CHARS:
        return {"error": "invalid_input", "message": "code is too large"}
    violations = _policy_violations(code)
    if violations:
        return {"error": "policy_denied", "message": "; ".join(violations[:5])}
    file_errors = _validate_files(input_json.get("files"))
    if file_errors:
        return {"error": "invalid_input", "message": "; ".join(file_errors)}
    timeout = _timeout(input_json.get("timeout_seconds"))
    payload = {
        "code": code,
        "stdin": str(input_json.get("stdin") or ""),
        "files": input_json.get("files") if isinstance(input_json.get("files"), list) else [],
        "max_stdio_bytes": MAX_STDIO_BYTES,
        "max_file_bytes": MAX_FILE_BYTES,
    }
    encoded = base64.b64encode(json.dumps(payload).encode("utf-8")).decode("ascii")
    command = "python - <<'PY'\n" + _RUNNER_SCRIPT + f"\nrun({encoded!r})\nPY"
    result = executor(command, "/workspace", timeout)
    output = _decode_runner_output(result.stdout)
    if output is None:
        output = {
            "stdout": result.stdout[:MAX_STDIO_BYTES],
            "stderr": result.stderr[:MAX_STDIO_BYTES],
            "exit_code": result.exit_code,
            "generated_files": [],
        }
    output["duration_ms"] = result.duration_ms
    return output


def _install_package(
    input_json: dict[str, Any],
    executor: SandboxCommandExecutor,
) -> dict[str, Any]:
    package = str(input_json.get("package") or "").strip()
    version = str(input_json.get("version") or "").strip()
    if not _valid_package_name(package):
        return {"error": "invalid_input", "message": "package must be a Python package name"}
    if version and not _valid_version(version):
        return {"error": "invalid_input", "message": "version contains unsupported characters"}
    requirement = f"{package}=={version}" if version else package
    timeout = _timeout(input_json.get("timeout_seconds"))
    command = "python -m pip install --disable-pip-version-check " + shlex.quote(requirement)
    result = executor(command, "/workspace", timeout)
    return {
        "installed": result.exit_code == 0,
        "package": package,
        "version": version or None,
        "exit_code": result.exit_code,
        "stdout": result.stdout[:MAX_STDIO_BYTES],
        "stderr": result.stderr[:MAX_STDIO_BYTES],
        "duration_ms": result.duration_ms,
    }


def _policy_violations(code: str) -> list[str]:
    try:
        tree = ast.parse(code)
    except SyntaxError as exc:
        return [f"syntax error: {exc.msg}"]
    violations: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            modules = []
            if isinstance(node, ast.Import):
                modules = [alias.name.split(".", 1)[0] for alias in node.names]
            elif node.module:
                modules = [node.module.split(".", 1)[0]]
            for module in modules:
                if module in DENIED_IMPORTS:
                    violations.append(f"import {module} is blocked")
            if isinstance(node, ast.ImportFrom) and node.module:
                module = node.module.split(".", 1)[0]
                for alias in node.names:
                    if (module, alias.name) in DENIED_IMPORT_MEMBERS:
                        violations.append(f"from {module} import {alias.name} is blocked")
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id in DENIED_NAMES:
                violations.append(f"call {node.func.id} is blocked")
            if isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name):
                pair = (node.func.value.id, node.func.attr)
                if pair in DENIED_CALLS:
                    violations.append(f"call {pair[0]}.{pair[1]} is blocked")
    return violations


def _validate_files(value: Any) -> list[str]:
    if value in (None, []):
        return []
    if not isinstance(value, list):
        return ["files must be a list"]
    errors: list[str] = []
    for index, item in enumerate(value[:20]):
        if not isinstance(item, dict):
            errors.append(f"files[{index}] must be an object")
            continue
        name = str(item.get("name") or "")
        if not _safe_relative_path(name):
            errors.append(f"files[{index}].name must be a safe relative path")
        content = str(item.get("content") or "")
        size = len(content.encode("utf-8"))
        if bool(item.get("base64")):
            try:
                size = len(base64.b64decode(content.encode("ascii"), validate=True))
            except Exception:
                errors.append(f"files[{index}].content is not valid base64")
        if size > MAX_FILE_BYTES:
            errors.append(f"files[{index}] exceeds {MAX_FILE_BYTES} bytes")
    if len(value) > 20:
        errors.append("at most 20 input files are allowed")
    return errors


def _safe_relative_path(value: str) -> bool:
    if not value or value.startswith("/"):
        return False
    path = Path(value)
    return ".." not in path.parts


def _timeout(value: Any) -> int:
    try:
        return max(1, min(int(value), MAX_TIMEOUT_SECONDS))
    except (TypeError, ValueError):
        return DEFAULT_TIMEOUT_SECONDS


def _valid_package_name(value: str) -> bool:
    if not value or len(value) > 120:
        return False
    return all(char.isalnum() or char in {"_", "-", "."} for char in value)


def _valid_version(value: str) -> bool:
    if not value or len(value) > 80:
        return False
    return all(char.isalnum() or char in {"_", "-", ".", "+", "!", "~"} for char in value)


def _decode_runner_output(stdout: str) -> dict[str, Any] | None:
    marker = "__HARNESS_CODE_RESULT__="
    for line in reversed(stdout.splitlines()):
        if not line.startswith(marker):
            continue
        try:
            value = json.loads(line[len(marker) :])
        except json.JSONDecodeError:
            return None
        return value if isinstance(value, dict) else None
    return None


_RUNNER_SCRIPT = r'''
import base64
import contextlib
import hashlib
import io
import json
import os
import pathlib
import sys
import time

def run(encoded):
    payload = json.loads(base64.b64decode(encoded).decode("utf-8"))
    workspace = pathlib.Path("/workspace").resolve()
    generated_root = (workspace / "output" / "code-interpreter").resolve()
    generated_root.mkdir(parents=True, exist_ok=True)
    for item in payload.get("files", []):
        target = (workspace / str(item.get("name", ""))).resolve()
        if workspace != target and workspace not in target.parents:
            raise SystemExit("input file escapes workspace")
        target.parent.mkdir(parents=True, exist_ok=True)
        content = str(item.get("content", ""))
        raw = base64.b64decode(content) if item.get("base64") else content.encode("utf-8")
        if len(raw) > int(payload["max_file_bytes"]):
            raise SystemExit("input file too large")
        target.write_bytes(raw)
    stdin = io.StringIO(str(payload.get("stdin", "")))
    stdout = io.StringIO()
    stderr = io.StringIO()
    old_stdin = sys.stdin
    started = time.monotonic()
    exit_code = 0
    try:
        sys.stdin = stdin
        namespace = {"__name__": "__main__"}
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            compiled = compile(
                str(payload.get("code", "")),
                "<harness-code-interpreter>",
                "exec",
            )
            exec(compiled, namespace)
    except SystemExit as exc:
        exit_code = int(exc.code) if isinstance(exc.code, int) else 1
    except Exception as exc:
        exit_code = 1
        stderr.write(f"{type(exc).__name__}: {exc}\n")
    finally:
        sys.stdin = old_stdin
    generated = []
    for path in sorted(generated_root.rglob("*")):
        if not path.is_file():
            continue
        stat = path.stat()
        if stat.st_size > int(payload["max_file_bytes"]):
            continue
        raw = path.read_bytes()
        generated.append({
            "name": str(path.relative_to(generated_root)),
            "size": stat.st_size,
            "sha256": hashlib.sha256(raw).hexdigest(),
            "content_preview": raw[:1000].decode("utf-8", errors="replace"),
        })
        if len(generated) >= 20:
            break
    result = {
        "stdout": stdout.getvalue()[: int(payload["max_stdio_bytes"])],
        "stderr": stderr.getvalue()[: int(payload["max_stdio_bytes"])],
        "exit_code": exit_code,
        "generated_files": generated,
        "duration_ms": int((time.monotonic() - started) * 1000),
    }
    print("__HARNESS_CODE_RESULT__=" + json.dumps(result, ensure_ascii=False, sort_keys=True))
'''
