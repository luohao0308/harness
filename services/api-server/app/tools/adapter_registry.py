from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, cast

from app.tools.registry import RiskLevel, ToolMetadata

ADAPTER_VERSION = "v1-2026-05-29"


@dataclass(frozen=True)
class AdapterResult:
    output_json: dict[str, Any]


class ToolAdapter(Protocol):
    slug: str
    server_label: str
    method: str
    description: str
    requires_secret: bool
    risk_level: RiskLevel
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]
    module_path: str

    def execute(
        self,
        *,
        metadata: ToolMetadata,
        input_json: dict[str, Any],
        config_json: dict[str, Any] | None,
        secret_value: str | None,
        sandbox_workspace_root: Path | None = None,
    ) -> AdapterResult: ...

    def health_check(
        self,
        *,
        config_json: dict[str, Any] | None,
        secret_value: str | None,
    ) -> dict[str, Any]: ...


class AdapterRegistry:
    def __init__(self) -> None:
        self._adapters: dict[str, ToolAdapter] = {}

    def register(self, adapter: ToolAdapter) -> None:
        if adapter.slug in self._adapters:
            raise ValueError(f"adapter slug already registered: {adapter.slug}")
        self._adapters[adapter.slug] = adapter

    def get(self, slug: str) -> ToolAdapter | None:
        return self._adapters.get(slug)

    def list_for_server(self, server: str) -> list[ToolAdapter]:
        normalized = server.strip().lower()
        return [
            adapter
            for adapter in self._adapters.values()
            if adapter.server_label.lower() == normalized
        ]

    def list_all(self) -> list[ToolAdapter]:
        return sorted(self._adapters.values(), key=lambda adapter: adapter.slug)

    def clear(self) -> None:
        self._adapters.clear()


REGISTRY = AdapterRegistry()


def adapter_snapshot(adapter: ToolAdapter) -> dict[str, Any]:
    return {
        "slug": adapter.slug,
        "server_label": adapter.server_label,
        "method": adapter.method,
        "version": ADAPTER_VERSION,
        "adapter_module": adapter.module_path,
        "adapter_sha256": adapter_source_sha256(adapter),
        "input_schema_sha256": _stable_json_sha256(adapter.input_schema),
        "output_schema_sha256": _stable_json_sha256(adapter.output_schema),
    }


def adapter_source_sha256(adapter: ToolAdapter) -> str:
    cached = getattr(adapter, "_adapter_source_sha256", None)
    if isinstance(cached, str) and cached:
        return cached
    try:
        module = __import__(adapter.module_path, fromlist=["__file__"])
        file_path = Path(str(module.__file__ or "")).resolve()
        raw = file_path.read_bytes()
    except Exception:
        raw = adapter.module_path.encode("utf-8")
    digest = hashlib.sha256(raw).hexdigest()
    try:
        cast(Any, adapter)._adapter_source_sha256 = digest
    except Exception:
        pass
    return digest


def adapter_metadata(adapter: ToolAdapter) -> dict[str, Any]:
    snapshot = adapter_snapshot(adapter)
    return {
        **snapshot,
        "description": adapter.description,
        "requires_secret": adapter.requires_secret,
        "risk_level": adapter.risk_level,
        "input_schema": adapter.input_schema,
        "output_schema": adapter.output_schema,
    }


def timed_health_result(
    probe,
    *,
    success_message: str,
    failure_prefix: str,
) -> dict[str, Any]:
    started_at = time.monotonic()
    try:
        sample = probe()
    except Exception as exc:
        return {
            "ok": False,
            "latency_ms": int((time.monotonic() - started_at) * 1000),
            "message": f"{failure_prefix}: {str(exc)[:240]}",
            "sample": {},
        }
    return {
        "ok": True,
        "latency_ms": int((time.monotonic() - started_at) * 1000),
        "message": success_message,
        "sample": sample if isinstance(sample, dict) else {},
    }


def _stable_json_sha256(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )
    return hashlib.sha256(raw).hexdigest()
