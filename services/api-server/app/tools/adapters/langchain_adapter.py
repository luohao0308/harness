from __future__ import annotations

import importlib.util
from dataclasses import dataclass
from typing import Any

from app.core.config import feature_enabled
from app.tools.adapter_registry import AdapterRegistry, AdapterResult
from app.tools.capabilities import redact_secrets
from app.tools.registry import RiskLevel, ToolMetadata


@dataclass(frozen=True)
class LangChainToolAdapter:
    slug: str = "langchain.invoke_tool"
    method: str = "invoke_tool"
    description: str = "Invoke a configured LangChain tool through the MCP-shaped Harness adapter."
    risk_level: RiskLevel = "low"
    server_label: str = "langchain"
    requires_secret: bool = False
    module_path: str = "app.tools.adapters.langchain_adapter"
    input_schema: dict[str, Any] = None  # type: ignore[assignment]
    output_schema: dict[str, Any] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "input_schema",
            {
                "type": "object",
                "properties": {
                    "tool_name": {"type": "string"},
                    "arguments": {"type": "object"},
                },
                "required": ["tool_name"],
            },
        )
        object.__setattr__(
            self,
            "output_schema",
            {
                "type": "object",
                "properties": {
                    "status": {"type": "string"},
                    "result": {},
                    "error": {"type": ["object", "null"]},
                    "metadata": {"type": "object"},
                },
            },
        )

    def execute(
        self,
        *,
        metadata: ToolMetadata,
        input_json: dict[str, Any],
        config_json: dict[str, Any] | None,
        secret_value: str | None,
        sandbox_workspace_root=None,
        sandbox_command_executor=None,
    ) -> AdapterResult:
        del secret_value, sandbox_workspace_root, sandbox_command_executor
        if metadata.source != "mcp":
            return AdapterResult(
                _envelope(
                    status="error",
                    error_code="invalid_metadata_source",
                    message="LangChain tools must be exposed as ToolMetadata(source='mcp')",
                )
            )
        if not feature_enabled("langchain_adapter_enabled"):
            return AdapterResult(
                _envelope(
                    status="error",
                    error_code="langchain_adapter_disabled",
                    message="LangChain adapter is disabled by feature flag",
                )
            )
        if importlib.util.find_spec("langchain_core") is None:
            return AdapterResult(
                _envelope(
                    status="error",
                    error_code="missing_optional_dependency",
                    message="Optional dependency langchain-core is not installed",
                    metadata={"package": "langchain-core"},
                )
            )
        return AdapterResult(
            _envelope(
                status="ok",
                result={
                    "tool_name": str(input_json.get("tool_name") or metadata.name),
                    "arguments": redact_secrets(input_json.get("arguments", {})),
                },
                metadata={
                    "adapter": self.slug,
                    "source": metadata.source,
                    "configured": bool(config_json),
                    "execution_authority": "toolrunner",
                },
            )
        )

    def health_check(
        self,
        *,
        config_json: dict[str, Any] | None,
        secret_value: str | None,
    ) -> dict[str, Any]:
        del config_json, secret_value
        available = importlib.util.find_spec("langchain_core") is not None
        return {
            "ok": feature_enabled("langchain_adapter_enabled") and available,
            "latency_ms": 0,
            "message": "langchain-core available" if available else "langchain-core is missing",
            "sample": {
                "feature_flag": "langchain_adapter_enabled",
                "optional_dependency": "langchain-core",
                "metadata_source": "mcp",
            },
        }


def register_langchain_adapters(registry: AdapterRegistry) -> None:
    if registry.get("langchain.invoke_tool") is None:
        registry.register(LangChainToolAdapter())


def langchain_tool_metadata(
    *,
    name: str = "langchain.invoke_tool",
    description: str = "LangChain tool exposed through Harness MCP-shaped ToolRunner path.",
) -> ToolMetadata:
    return ToolMetadata(
        name=name,
        description=description,
        category="mcp",
        source="mcp",
        risk_level="low",
        requires_sandbox=False,
        network_policy="none",
        timeout_seconds=30,
        allowed_roles=["admin", "engineer"],
        audit_level="standard",
        idempotent=True,
        input_schema=LangChainToolAdapter().input_schema,
        mcp_server="langchain",
        mcp_method="invoke_tool",
    )


def _envelope(
    *,
    status: str,
    result: Any | None = None,
    error_code: str | None = None,
    message: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "status": status,
        "result": redact_secrets(result) if result is not None else None,
        "error": None
        if error_code is None
        else {"code": error_code, "message": message or error_code},
        "metadata": metadata or {},
    }
