from __future__ import annotations

from dataclasses import dataclass

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

    def execute(self, *, metadata: ToolMetadata, input_json: dict) -> MCPToolResult:
        server = metadata.mcp_server or "local"
        method = metadata.mcp_method or metadata.name
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
                },
            )
        raise ValueError(f"unsupported MCP tool: {metadata.name}")
