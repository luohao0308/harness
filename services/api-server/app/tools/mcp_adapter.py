from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

from app.tools.adapter_registry import REGISTRY
from app.tools.adapters import ensure_builtin_adapters_registered
from app.tools.registry import ToolMetadata


@dataclass(frozen=True)
class MCPToolResult:
    server: str
    method: str
    output_json: dict


class MCPAdapter:
    """Deterministic MCP-shaped adapter used by the harness runtime.

    The first slice keeps transport local while preserving the same ToolCall,
    policy, trace, and audit contract that remote MCP tools will use.
    """

    def execute(
        self,
        *,
        metadata: ToolMetadata,
        input_json: dict,
        config_json: dict | None = None,
        secret_value: str | None = None,
        sandbox_workspace_root: Path | None = None,
    ) -> MCPToolResult:
        server = metadata.mcp_server or "local"
        method = metadata.mcp_method or metadata.name
        config = config_json if isinstance(config_json, dict) else {}
        ensure_builtin_adapters_registered(REGISTRY)
        adapter = REGISTRY.get(metadata.name)
        if adapter is not None:
            result = adapter.execute(
                metadata=metadata,
                input_json=input_json,
                config_json=config,
                secret_value=secret_value,
                sandbox_workspace_root=sandbox_workspace_root,
            )
            return MCPToolResult(
                server=adapter.server_label,
                method=adapter.method,
                output_json=result.output_json,
            )
        runtime = config.get("runtime") if isinstance(config.get("runtime"), dict) else {}
        runtime_evidence = _runtime_evidence(runtime=runtime, secret_ref=config.get("secret_ref"))
        if metadata.name == "mcp_context_search":
            query = str(input_json.get("query", ""))
            limit = max(1, min(int(input_json.get("limit", 5)), 20))
            return MCPToolResult(
                server=server,
                method=method,
                output_json={
                    "items": [
                        {
                            "id": f"context-{index + 1}",
                            "title": f"Context match {index + 1}",
                            "snippet": query[:160],
                        }
                        for index in range(limit)
                    ],
                    "source": "mcp-adapter",
                    "runtime": runtime_evidence,
                },
            )
        if metadata.name == "mcp_artifact_put":
            return MCPToolResult(
                server=server,
                method=method,
                output_json={
                    "artifact": {
                        "name": str(input_json.get("name", "artifact")),
                        "size_bytes": len(str(input_json.get("content", "")).encode("utf-8")),
                    },
                    "source": "mcp-adapter",
                    "runtime": runtime_evidence,
                },
            )
        if metadata.name == "brave" and runtime_evidence["configured"] and secret_value:
            return MCPToolResult(
                server=server,
                method=method,
                output_json=_execute_brave_search(
                    endpoint_url=str(runtime.get("endpoint_url") or ""),
                    api_key=secret_value,
                    input_json=input_json,
                    timeout_seconds=int(runtime.get("timeout_seconds") or metadata.timeout_seconds),
                    runtime_evidence=runtime_evidence,
                ),
            )
        query = str(input_json.get("query", ""))
        limit = max(1, min(int(input_json.get("limit", 5)), 20))
        return MCPToolResult(
            server=server,
            method=method,
            output_json={
                "items": [
                    {
                        "id": f"{metadata.name}-result-{index + 1}",
                        "title": f"{metadata.name} MCP result {index + 1}",
                        "snippet": query[:160],
                        "server": server,
                    }
                    for index in range(limit)
                ],
                "source": "mcp-marketplace-adapter",
                "tool": metadata.name,
                "runtime": runtime_evidence,
                "note": (
                    "Harness smoke result; save a runtime endpoint and server-side credential "
                    "to call a live external provider."
                ),
            },
        )


def _runtime_evidence(*, runtime: dict, secret_ref: Any) -> dict:
    transport = str(runtime.get("transport") or "http")
    endpoint_configured = bool(str(runtime.get("endpoint_url") or "").strip())
    command_configured = bool(str(runtime.get("command") or "").strip())
    configured = (transport in {"http", "sse"} and endpoint_configured) or (
        transport == "stdio" and command_configured
    )
    return {
        "configured": configured,
        "transport": transport,
        "endpoint_configured": endpoint_configured,
        "command_configured": command_configured,
        "secret_ref_configured": bool(str(secret_ref or "").strip()),
    }


def _execute_brave_search(
    *,
    endpoint_url: str,
    api_key: str,
    input_json: dict,
    timeout_seconds: int,
    runtime_evidence: dict,
) -> dict:
    query = str(input_json.get("query", "")).strip()
    if not query:
        raise ValueError("query is required")
    limit = max(1, min(int(input_json.get("limit", 5)), 20))
    response = httpx.get(
        endpoint_url,
        params={"q": query[:400], "count": limit},
        headers={
            "Accept": "application/json",
            "X-Subscription-Token": api_key,
        },
        timeout=min(max(timeout_seconds, 1), 30),
    )
    if response.status_code >= 400:
        raise RuntimeError(
            "Brave Search API request failed with HTTP "
            f"{response.status_code}: {response.text[:300]}"
        )
    payload = response.json()
    web = payload.get("web") if isinstance(payload, dict) else {}
    results = web.get("results") if isinstance(web, dict) else []
    items: list[dict[str, str]] = []
    if isinstance(results, list):
        for index, result in enumerate(results[:limit], start=1):
            if not isinstance(result, dict):
                continue
            items.append(
                {
                    "id": str(result.get("url") or f"brave-result-{index}"),
                    "title": str(
                        result.get("title") or result.get("url") or f"Brave result {index}"
                    ),
                    "url": str(result.get("url") or ""),
                    "snippet": str(result.get("description") or ""),
                    "server": "brave",
                }
            )
    return {
        "items": items,
        "source": "brave-search-api",
        "tool": "brave",
        "live_provider": True,
        "runtime": {**runtime_evidence, "secret_available": True},
        "query": query,
    }
