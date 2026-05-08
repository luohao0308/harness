from typing import Literal

from pydantic import BaseModel, Field

RiskLevel = Literal["low", "medium", "high", "critical"]


class ToolMetadata(BaseModel):
    name: str
    description: str
    category: str
    source: Literal["builtin", "mcp"] = "builtin"
    risk_level: RiskLevel
    requires_sandbox: bool
    network_policy: str = "none"
    timeout_seconds: int = Field(default=60, ge=1)
    allowed_roles: list[str] = Field(default_factory=lambda: ["admin", "engineer"])
    audit_level: str = "standard"
    idempotent: bool = True
    input_schema: dict = Field(default_factory=dict)
    mcp_server: str | None = None
    mcp_method: str | None = None


class ToolRegistry(BaseModel):
    tools: dict[str, ToolMetadata]

    @classmethod
    def default(cls) -> "ToolRegistry":
        tools = [
            ToolMetadata(
                name="read_file",
                description="读取工作区文件。",
                category="filesystem",
                risk_level="low",
                requires_sandbox=False,
                network_policy="none",
                timeout_seconds=10,
                audit_level="standard",
                idempotent=True,
            ),
            ToolMetadata(
                name="list_files",
                description="列出工作区文件。",
                category="filesystem",
                risk_level="low",
                requires_sandbox=False,
                network_policy="none",
                timeout_seconds=10,
                audit_level="standard",
                idempotent=True,
            ),
            ToolMetadata(
                name="write_file",
                description="在任务工作区写入任务产物。",
                category="filesystem",
                risk_level="high",
                requires_sandbox=True,
                network_policy="none",
                timeout_seconds=30,
                audit_level="elevated",
                idempotent=False,
            ),
            ToolMetadata(
                name="run_shell",
                description="在 Docker 沙箱内运行 Shell 命令。",
                category="shell",
                risk_level="high",
                requires_sandbox=True,
                network_policy="none",
                timeout_seconds=60,
                audit_level="elevated",
                idempotent=False,
            ),
            ToolMetadata(
                name="run_tests",
                description="在 Docker 沙箱内运行测试。",
                category="shell",
                risk_level="high",
                requires_sandbox=True,
                network_policy="none",
                timeout_seconds=300,
                audit_level="elevated",
                idempotent=True,
            ),
            ToolMetadata(
                name="network_request",
                description="在 Docker 沙箱内执行受控网络请求。",
                category="network",
                risk_level="high",
                requires_sandbox=True,
                network_policy="restricted",
                timeout_seconds=30,
                allowed_roles=["admin"],
                audit_level="critical",
                idempotent=False,
            ),
            ToolMetadata(
                name="git_command",
                description="在 Docker 沙箱内运行 Git 命令。",
                category="git",
                risk_level="high",
                requires_sandbox=True,
                network_policy="restricted",
                timeout_seconds=120,
                audit_level="elevated",
                idempotent=False,
            ),
            ToolMetadata(
                name="mcp_context_search",
                description="通过 MCP Adapter 查询外部上下文。",
                category="mcp",
                source="mcp",
                risk_level="low",
                requires_sandbox=False,
                network_policy="restricted",
                timeout_seconds=30,
                audit_level="standard",
                idempotent=True,
                input_schema={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"},
                        "limit": {"type": "integer", "default": 5},
                    },
                    "required": ["query"],
                },
                mcp_server="local-context",
                mcp_method="context.search",
            ),
            ToolMetadata(
                name="mcp_artifact_put",
                description="通过 MCP Adapter 写入任务 Artifact 记录。",
                category="mcp",
                source="mcp",
                risk_level="medium",
                requires_sandbox=False,
                network_policy="none",
                timeout_seconds=30,
                audit_level="elevated",
                idempotent=False,
                input_schema={
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "content": {"type": "string"},
                    },
                    "required": ["name", "content"],
                },
                mcp_server="local-artifacts",
                mcp_method="artifact.put",
            ),
        ]
        return cls(tools={tool.name: tool for tool in tools})

    def list_tools(self) -> list[ToolMetadata]:
        return list(self.tools.values())
