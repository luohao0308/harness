from __future__ import annotations

import base64
import json
from collections.abc import Callable
from typing import Any

from app.sandbox.docker_manager import SandboxCommandResult
from app.tools.mcp_protocol.client import MCP_PROTOCOL_VERSION, MCPProtocolError

SandboxCommandExecutor = Callable[[str, str, int], SandboxCommandResult]


class MCPStdioSandboxTransport:
    def __init__(
        self,
        *,
        command: str,
        args: list[str] | None = None,
        sandbox_executor: SandboxCommandExecutor | None,
    ) -> None:
        self.command = command.strip()
        self.args = [str(item) for item in (args or [])]
        self.sandbox_executor = sandbox_executor

    def request(self, payload: dict[str, Any], *, timeout_seconds: int) -> dict[str, Any]:
        if self.sandbox_executor is None:
            raise MCPProtocolError("stdio MCP transport requires a sandbox executor")
        if not self.command:
            raise MCPProtocolError("stdio MCP command is required")
        encoded = base64.b64encode(json.dumps(payload).encode("utf-8")).decode("ascii")
        argv = " ".join([_shell_quote(self.command), *[_shell_quote(arg) for arg in self.args]])
        script = (
            _STDIO_SCRIPT.replace("__MCP_PAYLOAD__", encoded)
            .replace("__MCP_ARGV__", argv)
            .replace("__MCP_PROTOCOL_VERSION__", MCP_PROTOCOL_VERSION)
        )
        result = self.sandbox_executor(script, "/workspace", max(1, min(timeout_seconds, 60)))
        if result.exit_code != 0:
            raise MCPProtocolError(f"stdio MCP command failed: {result.stderr[:300]}")
        marker = "__HARNESS_MCP_RESPONSE__="
        for line in reversed(result.stdout.splitlines()):
            if not line.startswith(marker):
                continue
            try:
                decoded = json.loads(line[len(marker) :])
            except json.JSONDecodeError as exc:
                raise MCPProtocolError("stdio MCP response was not valid JSON") from exc
            if isinstance(decoded, dict):
                return decoded
        raise MCPProtocolError("stdio MCP response marker was not found")

    def close(self) -> None:
        return None


def _shell_quote(value: str) -> str:
    return "'" + value.replace("'", "'\"'\"'") + "'"


_STDIO_SCRIPT = r'''
python - <<'PY'
import base64
import json
import subprocess
import sys

payload = base64.b64decode("__MCP_PAYLOAD__").decode("utf-8")
target = json.loads(payload)
target_id = target.get("id")
requests = []
if target.get("method") not in {"initialize", "notifications/initialized"}:
    requests.append(json.dumps({
        "jsonrpc": "2.0",
        "id": "harness-stdio-initialize",
        "method": "initialize",
        "params": {
            "protocolVersion": "__MCP_PROTOCOL_VERSION__",
            "capabilities": {"tools": {}, "resources": {}},
            "clientInfo": {"name": "agent-harness", "version": "0.1"},
        },
    }))
    requests.append(json.dumps({
        "jsonrpc": "2.0",
        "method": "notifications/initialized",
        "params": {},
    }))
requests.append(payload)
proc = subprocess.run(
    "__MCP_ARGV__",
    input="\n".join(requests) + "\n",
    shell=True,
    text=True,
    capture_output=True,
    timeout=60,
)
if proc.returncode != 0:
    sys.stderr.write(proc.stderr)
    raise SystemExit(proc.returncode)
responses = []
for line in proc.stdout.splitlines():
    line = line.strip()
    if not line:
        continue
    try:
        decoded = json.loads(line)
    except json.JSONDecodeError:
        continue
    if isinstance(decoded, dict):
        responses.append(decoded)
selected = None
for response in responses:
    if target_id is not None and response.get("id") == target_id:
        selected = response
        break
if selected is None:
    for response in reversed(responses):
        if response.get("id") != "harness-stdio-initialize":
            selected = response
            break
print("__HARNESS_MCP_RESPONSE__=" + json.dumps(selected or {}, ensure_ascii=False))
PY
'''
