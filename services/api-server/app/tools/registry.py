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
                name="read_project",
                description="Read project files inside the task workspace.",
                risk_level="medium",
                requires_sandbox=True,
                timeout_seconds=60,
            ),
            ToolMetadata(
                name="write_artifact",
                description="Write task artifacts inside the task workspace.",
                risk_level="high",
                requires_sandbox=True,
                timeout_seconds=60,
            ),
            ToolMetadata(
                name="summarize_context",
                description="Summarize already available task context.",
                risk_level="low",
                requires_sandbox=False,
                timeout_seconds=30,
            ),
        ]
        return cls(tools={tool.name: tool for tool in tools})

    def list_tools(self) -> list[ToolMetadata]:
        return list(self.tools.values())
