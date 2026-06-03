from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

MCP_PROTOCOL_VERSION = "2024-11-05"


class MCPProtocolError(RuntimeError):
    pass


class MCPTransport(Protocol):
    def request(self, payload: dict[str, Any], *, timeout_seconds: int) -> dict[str, Any]: ...

    def close(self) -> None: ...


@dataclass(frozen=True)
class MCPToolMeta:
    name: str
    description: str
    input_schema: dict[str, Any]
    annotations: dict[str, Any]


@dataclass(frozen=True)
class MCPResourceMeta:
    uri: str
    name: str
    description: str
    mime_type: str | None = None


@dataclass(frozen=True)
class MCPToolResult:
    name: str
    content: list[dict[str, Any]]
    structured_content: dict[str, Any]
    is_error: bool = False


class MCPClient:
    def __init__(self, transport: MCPTransport, *, timeout_seconds: int = 30) -> None:
        self.transport = transport
        self.timeout_seconds = max(1, min(int(timeout_seconds), 60))
        self._next_id = 1
        self._initialized = False

    def initialize(self) -> dict[str, Any]:
        result = self._rpc(
            "initialize",
            {
                "protocolVersion": MCP_PROTOCOL_VERSION,
                "capabilities": {"tools": {}, "resources": {}},
                "clientInfo": {"name": "agent-harness", "version": "0.1"},
            },
        )
        self._initialized = True
        try:
            self._notify("notifications/initialized", {})
        except MCPProtocolError:
            pass
        return result

    def list_tools(self) -> list[MCPToolMeta]:
        self._ensure_initialized()
        result = self._rpc("tools/list", {})
        tools = result.get("tools") if isinstance(result, dict) else []
        output: list[MCPToolMeta] = []
        for item in tools if isinstance(tools, list) else []:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name") or "").strip()
            if not name:
                continue
            input_schema = item.get("inputSchema") or item.get("input_schema") or {}
            annotations = (
                item.get("annotations") if isinstance(item.get("annotations"), dict) else {}
            )
            output.append(
                MCPToolMeta(
                    name=name,
                    description=str(item.get("description") or ""),
                    input_schema=input_schema if isinstance(input_schema, dict) else {},
                    annotations=annotations,
                )
            )
        return output

    def call_tool(self, name: str, arguments: dict[str, Any]) -> MCPToolResult:
        self._ensure_initialized()
        result = self._rpc("tools/call", {"name": name, "arguments": arguments})
        content = result.get("content") if isinstance(result, dict) else []
        structured = result.get("structuredContent") if isinstance(result, dict) else {}
        return MCPToolResult(
            name=name,
            content=content if isinstance(content, list) else [],
            structured_content=structured if isinstance(structured, dict) else {},
            is_error=bool(result.get("isError")) if isinstance(result, dict) else False,
        )

    def list_resources(self) -> list[MCPResourceMeta]:
        self._ensure_initialized()
        result = self._rpc("resources/list", {})
        resources = result.get("resources") if isinstance(result, dict) else []
        output: list[MCPResourceMeta] = []
        for item in resources if isinstance(resources, list) else []:
            if not isinstance(item, dict):
                continue
            uri = str(item.get("uri") or "").strip()
            if not uri:
                continue
            output.append(
                MCPResourceMeta(
                    uri=uri,
                    name=str(item.get("name") or uri),
                    description=str(item.get("description") or ""),
                    mime_type=str(item.get("mimeType")) if item.get("mimeType") else None,
                )
            )
        return output

    def close(self) -> None:
        self.transport.close()

    def _ensure_initialized(self) -> None:
        if not self._initialized:
            self.initialize()

    def _rpc(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        request_id = self._next_id
        self._next_id += 1
        response = self.transport.request(
            {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params},
            timeout_seconds=self.timeout_seconds,
        )
        if response.get("jsonrpc") != "2.0":
            raise MCPProtocolError("MCP response missing jsonrpc=2.0")
        if response.get("id") not in {request_id, str(request_id)}:
            raise MCPProtocolError("MCP response id does not match request")
        if response.get("error"):
            raise MCPProtocolError(str(response["error"])[:500])
        result = response.get("result")
        return result if isinstance(result, dict) else {}

    def _notify(self, method: str, params: dict[str, Any]) -> None:
        self.transport.request(
            {"jsonrpc": "2.0", "method": method, "params": params},
            timeout_seconds=self.timeout_seconds,
        )
