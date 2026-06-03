from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .api_client import HarnessApiClient


@dataclass(frozen=True)
class SandboxToolResult:
    status: str
    tool_call_id: str | None
    output_json: dict[str, Any]
    duration_ms: int
    error_message: str | None = None


def execute_sandbox_tool(
    api_client: HarnessApiClient,
    *,
    run_id: str,
    tool_name: str,
    input_json: dict[str, Any],
) -> SandboxToolResult:
    response = api_client.execute_sandbox_tool(run_id, tool_name, input_json)
    tool_call = response.get("tool_call") if isinstance(response, dict) else {}
    if not isinstance(tool_call, dict):
        tool_call = {}
    output = response.get("output") if isinstance(response, dict) else {}
    if not isinstance(output, dict):
        output = {"value": output}
    return SandboxToolResult(
        status=str(tool_call.get("status") or "UNKNOWN"),
        tool_call_id=str(tool_call.get("id")) if tool_call.get("id") else None,
        output_json=output,
        duration_ms=int(tool_call.get("duration_ms") or 0),
        error_message=(
            str(tool_call.get("error_message"))
            if tool_call.get("error_message") is not None
            else None
        ),
    )
