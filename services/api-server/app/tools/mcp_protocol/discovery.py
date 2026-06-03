from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.tools.mcp_protocol.client import MCPClient, MCPProtocolError, MCPToolMeta
from app.tools.mcp_protocol.session import MCPSession
from app.tools.mcp_protocol.transports.http_transport import MCPHTTPTransport
from app.tools.mcp_protocol.transports.streamable_http import MCPStreamableHTTPTransport


@dataclass(frozen=True)
class MCPDiscoveryResult:
    server_slug: str
    transport: str
    ok: bool
    tools: list[MCPToolMeta]
    resources_count: int
    message: str


def discover_tools(
    *,
    server_slug: str,
    runtime: dict[str, Any],
    secret_value: str | None = None,
) -> MCPDiscoveryResult:
    transport_name = str(runtime.get("transport") or "http")
    timeout = int(runtime.get("timeout_seconds") or 30)
    if transport_name == "stdio":
        return MCPDiscoveryResult(
            server_slug=server_slug,
            transport=transport_name,
            ok=False,
            tools=[],
            resources_count=0,
            message="stdio discovery requires a run sandbox and is not available from admin API",
        )
    endpoint_url = str(runtime.get("endpoint_url") or "").strip()
    if not endpoint_url:
        return MCPDiscoveryResult(
            server_slug=server_slug,
            transport=transport_name,
            ok=False,
            tools=[],
            resources_count=0,
            message="endpoint_url is required for MCP discovery",
        )
    transport = (
        MCPStreamableHTTPTransport(endpoint_url=endpoint_url, secret_value=secret_value)
        if transport_name == "sse"
        else MCPHTTPTransport(endpoint_url=endpoint_url, secret_value=secret_value)
    )
    client = MCPClient(transport, timeout_seconds=timeout)
    session = MCPSession(client)
    try:
        session.refresh()
    except MCPProtocolError as exc:
        return MCPDiscoveryResult(
            server_slug=server_slug,
            transport=transport_name,
            ok=False,
            tools=[],
            resources_count=0,
            message=str(exc)[:300],
        )
    finally:
        session.close()
    return MCPDiscoveryResult(
        server_slug=server_slug,
        transport=transport_name,
        ok=True,
        tools=session.tools,
        resources_count=len(session.resources),
        message=f"discovered {len(session.tools)} MCP tools",
    )
