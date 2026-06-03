from __future__ import annotations

import hashlib
import mimetypes
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.tools.adapter_registry import AdapterRegistry, AdapterResult
from app.tools.registry import RiskLevel, ToolMetadata

DEFAULT_MAX_BYTES = 1_000_000
MAX_BYTES = 8_000_000
DEFAULT_MAX_ENTRIES = 200
MAX_ENTRIES = 1000
MAX_LIST_DEPTH = 3


@dataclass(frozen=True)
class SandboxFileAdapter:
    slug: str
    method: str
    description: str
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]
    risk_level: RiskLevel

    server_label: str = "sandbox"
    requires_secret: bool = False
    module_path: str = "app.tools.adapters.sandbox_file_adapter"

    def execute(
        self,
        *,
        metadata: ToolMetadata,
        input_json: dict[str, Any],
        config_json: dict[str, Any] | None,
        secret_value: str | None,
        sandbox_workspace_root: Path | None = None,
        sandbox_command_executor=None,
    ) -> AdapterResult:
        del metadata, config_json, secret_value, sandbox_command_executor
        if sandbox_workspace_root is None:
            return AdapterResult(
                {"error": "sandbox_not_ready", "message": "Sandbox workspace is required"}
            )
        root = sandbox_workspace_root.resolve()
        if self.method == "read_file":
            output = _read_file(root, input_json)
        elif self.method == "list_files":
            output = _list_files(root, input_json)
        elif self.method == "write_file":
            output = _write_file(root, input_json)
        elif self.method == "delete_file":
            output = _delete_file(root, input_json)
        else:
            output = {"error": "unsupported_method", "message": self.method}
        return AdapterResult(output)

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
            "message": "Sandbox file adapter is available when a run sandbox workspace exists",
            "sample": {"requires_sandbox_workspace": True},
        }


def register_sandbox_file_adapters(registry: AdapterRegistry) -> None:
    for adapter in [
        SandboxFileAdapter(
            slug="sandbox.read_file",
            method="read_file",
            description="Read a file inside the Agent sandbox workspace.",
            risk_level="medium",
            input_schema={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "minLength": 1},
                    "max_bytes": {"type": "integer", "default": DEFAULT_MAX_BYTES},
                },
                "required": ["path"],
            },
            output_schema={"type": "object", "properties": {"content": {"type": "string"}}},
        ),
        SandboxFileAdapter(
            slug="sandbox.list_files",
            method="list_files",
            description="List files inside a sandbox directory.",
            risk_level="medium",
            input_schema={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "default": "."},
                    "pattern": {"type": "string", "default": "*"},
                    "max_entries": {"type": "integer", "default": DEFAULT_MAX_ENTRIES},
                },
            },
            output_schema={"type": "object", "properties": {"entries": {"type": "array"}}},
        ),
        SandboxFileAdapter(
            slug="sandbox.write_file",
            method="write_file",
            description="Write a file inside the sandbox workspace.",
            risk_level="high",
            input_schema={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "minLength": 1},
                    "content": {"type": "string"},
                    "encoding": {"type": "string", "default": "utf-8"},
                },
                "required": ["path", "content"],
            },
            output_schema={"type": "object", "properties": {"bytes_written": {"type": "integer"}}},
        ),
        SandboxFileAdapter(
            slug="sandbox.delete_file",
            method="delete_file",
            description="Delete a file inside the sandbox workspace.",
            risk_level="high",
            input_schema={
                "type": "object",
                "properties": {"path": {"type": "string", "minLength": 1}},
                "required": ["path"],
            },
            output_schema={"type": "object", "properties": {"deleted": {"type": "boolean"}}},
        ),
    ]:
        registry.register(adapter)


def _read_file(root: Path, input_json: dict[str, Any]) -> dict[str, Any]:
    resolved = _resolve_safe_path(root, input_json.get("path"))
    if isinstance(resolved, dict):
        return resolved
    if not resolved.exists():
        return {
            "error": "not_found",
            "message": "file does not exist",
            "path": str(input_json.get("path") or ""),
        }
    if not resolved.is_file():
        return {
            "error": "not_file",
            "message": "path is not a file",
            "path": str(input_json.get("path") or ""),
        }
    max_bytes = _bounded_int(input_json.get("max_bytes"), DEFAULT_MAX_BYTES, 1, MAX_BYTES)
    total_size = resolved.stat().st_size
    raw = resolved.read_bytes()[:max_bytes]
    content = raw.decode("utf-8", errors="replace")
    mime_type, _encoding = mimetypes.guess_type(resolved.name)
    return {
        "path": _relative_path(root, resolved),
        "content": content,
        "size_bytes": len(raw),
        "total_size": total_size,
        "mime_type": mime_type or "application/octet-stream",
        "truncated": total_size > max_bytes,
    }


def _list_files(root: Path, input_json: dict[str, Any]) -> dict[str, Any]:
    resolved = _resolve_safe_path(root, input_json.get("path") or ".")
    if isinstance(resolved, dict):
        return resolved
    if not resolved.exists():
        return {
            "error": "not_found",
            "message": "directory does not exist",
            "path": str(input_json.get("path") or "."),
        }
    if not resolved.is_dir():
        return {
            "error": "not_directory",
            "message": "path is not a directory",
            "path": str(input_json.get("path") or "."),
        }
    relative_parts = resolved.relative_to(root).parts
    if len(relative_parts) > MAX_LIST_DEPTH:
        return {"error": "depth_exceeded", "message": "directory depth exceeds limit"}
    pattern = str(input_json.get("pattern") or "*")
    max_entries = _bounded_int(input_json.get("max_entries"), DEFAULT_MAX_ENTRIES, 1, MAX_ENTRIES)
    entries = []
    for path in sorted(resolved.glob(pattern)):
        if not _is_inside(root, path.resolve()):
            continue
        rel_depth = len(path.resolve().relative_to(root).parts)
        if rel_depth > MAX_LIST_DEPTH + 1:
            continue
        stat = path.stat()
        entries.append(
            {
                "name": path.name,
                "path": _relative_path(root, path.resolve()),
                "type": "directory" if path.is_dir() else "file",
                "size_bytes": stat.st_size if path.is_file() else 0,
                "modified_at": datetime.fromtimestamp(stat.st_mtime, UTC).isoformat(),
            }
        )
        if len(entries) >= max_entries:
            break
    return {
        "path": _relative_path(root, resolved),
        "entries": entries,
        "truncated": len(entries) >= max_entries,
    }


def _write_file(root: Path, input_json: dict[str, Any]) -> dict[str, Any]:
    resolved = _resolve_safe_path(root, input_json.get("path"))
    if isinstance(resolved, dict):
        return resolved
    encoding = str(input_json.get("encoding") or "utf-8")
    if encoding.lower().replace("_", "-") != "utf-8":
        return {"error": "unsupported_encoding", "message": "only utf-8 is supported in v1"}
    content = str(input_json.get("content") or "")
    raw = content.encode("utf-8")
    if len(raw) > MAX_BYTES:
        return {"error": "file_too_large", "message": f"write limit is {MAX_BYTES} bytes"}
    resolved.parent.mkdir(parents=True, exist_ok=True)
    resolved.write_bytes(raw)
    return {
        "path": _relative_path(root, resolved),
        "bytes_written": len(raw),
        "sha256": hashlib.sha256(raw).hexdigest(),
    }


def _delete_file(root: Path, input_json: dict[str, Any]) -> dict[str, Any]:
    resolved = _resolve_safe_path(root, input_json.get("path"))
    if isinstance(resolved, dict):
        return resolved
    if not resolved.exists():
        return {
            "error": "not_found",
            "message": "file does not exist",
            "path": str(input_json.get("path") or ""),
        }
    if not resolved.is_file():
        return {
            "error": "not_file",
            "message": "only files can be deleted",
            "path": _relative_path(root, resolved),
        }
    resolved.unlink()
    return {"path": _relative_path(root, resolved), "deleted": True}


def _resolve_safe_path(root: Path, raw_path: Any) -> Path | dict[str, Any]:
    path_text = str(raw_path or "").strip()
    if not path_text:
        return {"error": "invalid_input", "message": "path is required"}
    candidate = Path(path_text)
    if candidate.is_absolute() or ".." in candidate.parts:
        return {"error": "path_traversal", "message": "path must stay inside sandbox workspace"}
    resolved = (root / candidate).resolve()
    if not _is_inside(root, resolved):
        return {"error": "path_traversal", "message": "path must stay inside sandbox workspace"}
    return resolved


def _is_inside(root: Path, path: Path) -> bool:
    return path == root or root in path.parents


def _relative_path(root: Path, path: Path) -> str:
    value = str(path.relative_to(root))
    return "." if value == "." else value


def _bounded_int(value: Any, default: int, minimum: int, maximum: int) -> int:
    try:
        return max(minimum, min(int(value), maximum))
    except (TypeError, ValueError):
        return default
