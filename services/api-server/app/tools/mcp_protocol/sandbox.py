from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MCPSandboxLaunchPolicy:
    cpu_limit: str = "0.5"
    memory_limit_mb: int = 512
    timeout_seconds: int = 60
    network_mode: str = "none"
    host_process_allowed: bool = False


DEFAULT_MCP_SANDBOX_POLICY = MCPSandboxLaunchPolicy()
