from typing import Literal

from pydantic import BaseModel, Field

RiskLevel = Literal["low", "medium", "high", "critical"]


class ToolMetadata(BaseModel):
    name: str
    description: str
    risk_level: RiskLevel
    requires_sandbox: bool
    timeout_seconds: int = Field(default=60, ge=1)


class ToolRegistry(BaseModel):
    tools: dict[str, ToolMetadata]

    @classmethod
    def default(cls) -> "ToolRegistry":
        tools = [
            ToolMetadata(
                name="read_file",
                description="读取工作区文件。",
                risk_level="low",
                requires_sandbox=False,
                timeout_seconds=10,
            ),
            ToolMetadata(
                name="list_files",
                description="列出工作区文件。",
                risk_level="low",
                requires_sandbox=False,
                timeout_seconds=10,
            ),
            ToolMetadata(
                name="write_file",
                description="在任务工作区写入任务产物。",
                risk_level="high",
                requires_sandbox=True,
                timeout_seconds=30,
            ),
            ToolMetadata(
                name="run_shell",
                description="在 Docker 沙箱内运行 Shell 命令。",
                risk_level="high",
                requires_sandbox=True,
                timeout_seconds=60,
            ),
            ToolMetadata(
                name="run_tests",
                description="在 Docker 沙箱内运行测试。",
                risk_level="high",
                requires_sandbox=True,
                timeout_seconds=300,
            ),
            ToolMetadata(
                name="network_request",
                description="在 Docker 沙箱内执行受控网络请求。",
                risk_level="high",
                requires_sandbox=True,
                timeout_seconds=30,
            ),
            ToolMetadata(
                name="git_command",
                description="在 Docker 沙箱内运行 Git 命令。",
                risk_level="high",
                requires_sandbox=True,
                timeout_seconds=120,
            ),
        ]
        return cls(tools={tool.name: tool for tool in tools})

    def list_tools(self) -> list[ToolMetadata]:
        return list(self.tools.values())
