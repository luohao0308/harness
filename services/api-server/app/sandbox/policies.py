from dataclasses import dataclass

DEFAULT_SANDBOX_IMAGE = "agent-runtime:latest"
DEFAULT_SANDBOX_MEMORY = "1024m"
DEFAULT_SANDBOX_MEMORY_MB = 1024
DEFAULT_SANDBOX_CPUS = "1.0"
DEFAULT_SANDBOX_NANO_CPUS = 1_000_000_000
DEFAULT_SANDBOX_NETWORK = "none"
DEFAULT_SANDBOX_USER = "non-root"
DEFAULT_WORKSPACE_MOUNT = "/workspace"


@dataclass(frozen=True)
class SandboxPolicyDecision:
    allowed: bool
    reason: str
    policy_id: str
    audit_level: str


def require_command_timeout(timeout_seconds: int | None) -> SandboxPolicyDecision:
    if timeout_seconds is None or timeout_seconds <= 0:
        return SandboxPolicyDecision(
            allowed=False,
            reason="command timeout is required",
            policy_id="command-timeout-required",
            audit_level="elevated",
        )
    return SandboxPolicyDecision(
        allowed=True,
        reason="command timeout accepted",
        policy_id="command-timeout-required",
        audit_level="elevated",
    )


def network_enabled_from_mode(network_mode: str = DEFAULT_SANDBOX_NETWORK) -> bool:
    return network_mode != "none"
