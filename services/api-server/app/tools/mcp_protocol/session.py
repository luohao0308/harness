from __future__ import annotations

from dataclasses import dataclass, field

from app.tools.mcp_protocol.client import MCPClient, MCPResourceMeta, MCPToolMeta, MCPToolResult


@dataclass
class MCPSession:
    client: MCPClient
    initialized: bool = False
    tools: list[MCPToolMeta] = field(default_factory=list)
    resources: list[MCPResourceMeta] = field(default_factory=list)

    def refresh(self) -> MCPSession:
        self.client.initialize()
        self.initialized = True
        self.tools = self.client.list_tools()
        try:
            self.resources = self.client.list_resources()
        except Exception:
            self.resources = []
        return self

    def call_tool(self, name: str, arguments: dict) -> MCPToolResult:
        if not self.initialized:
            self.refresh()
        return self.client.call_tool(name, arguments)

    def close(self) -> None:
        self.client.close()
