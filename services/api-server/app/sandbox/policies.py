from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import SystemSetting, Task

DEFAULT_SANDBOX_IMAGE = "agent-runtime:latest"
DEFAULT_SANDBOX_MEMORY = "1024m"
DEFAULT_SANDBOX_MEMORY_MB = 1024
DEFAULT_SANDBOX_CPUS = "1.0"
DEFAULT_SANDBOX_NANO_CPUS = 1_000_000_000
DEFAULT_SANDBOX_NETWORK = "none"
DEFAULT_SANDBOX_USER = "non-root"
DEFAULT_WORKSPACE_MOUNT = "/workspace"
POLICY_SETTINGS_KEY = "settings.policies"
DEFAULT_SANDBOX_TIMEOUT_SECONDS = 60

DEFAULT_POLICY_SETTINGS = {
    "risk_levels": [
        {"name": "low", "requires_sandbox": False, "approval": "auto"},
        {"name": "medium", "requires_sandbox": True, "approval": "auto"},
        {"name": "high", "requires_sandbox": True, "approval": "admin"},
        {"name": "critical", "requires_sandbox": True, "approval": "admin"},
    ],
    "approvals": {"manual_review": True, "deny_on_missing_policy": True},
    "sandbox": {"default_network": False, "default_timeout_seconds": 60},
    "audit": {"model_calls": True, "tool_calls": True, "policy_actions": True},
}


@dataclass(frozen=True)
class SandboxPolicyDecision:
    allowed: bool
    reason: str
    policy_id: str
    audit_level: str
    requires_sandbox: bool | None = None


@dataclass(frozen=True)
class SandboxRuntimePolicy:
    network_mode: str
    network_enabled: bool
    timeout_seconds: int
    memory: str = DEFAULT_SANDBOX_MEMORY
    memory_mb: int = DEFAULT_SANDBOX_MEMORY_MB
    cpus: str = DEFAULT_SANDBOX_CPUS
    nano_cpus: int = DEFAULT_SANDBOX_NANO_CPUS
    user: str = DEFAULT_SANDBOX_USER


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


class PolicyEngine:
    def __init__(self, session: Session) -> None:
        self.session = session

    def evaluate_tool(
        self,
        *,
        task_id: str,
        metadata,
        roles: list[str],
        sandbox_present: bool,
    ) -> SandboxPolicyDecision:
        settings = self._settings_for_task(task_id)
        risk_policy = self._risk_policy(settings=settings, risk_level=metadata.risk_level)
        if risk_policy is None:
            if settings.get("approvals", {}).get("deny_on_missing_policy", True):
                return SandboxPolicyDecision(
                    allowed=False,
                    reason="risk policy is missing",
                    policy_id="risk-policy-required",
                    audit_level=metadata.audit_level,
                    requires_sandbox=metadata.requires_sandbox,
                )
            requires_sandbox = metadata.requires_sandbox
            approval = "auto"
            allowed_roles = metadata.allowed_roles
        else:
            requires_sandbox = bool(
                risk_policy.get("requires_sandbox", metadata.requires_sandbox)
            )
            approval = str(risk_policy.get("approval", "auto"))
            allowed_roles = list(risk_policy.get("allowed_roles", metadata.allowed_roles))

        if not set(roles).intersection(allowed_roles):
            return SandboxPolicyDecision(
                allowed=False,
                reason="role is not allowed to run tool",
                policy_id="tool-role-allowed",
                audit_level=metadata.audit_level,
                requires_sandbox=requires_sandbox,
            )
        if approval == "admin" and "admin" not in roles:
            return SandboxPolicyDecision(
                allowed=False,
                reason="tool requires admin approval",
                policy_id="tool-approval-required",
                audit_level=metadata.audit_level,
                requires_sandbox=requires_sandbox,
            )
        if requires_sandbox and not sandbox_present:
            return SandboxPolicyDecision(
                allowed=False,
                reason="sandbox is required for tool",
                policy_id="tool-sandbox-required",
                audit_level=metadata.audit_level,
                requires_sandbox=requires_sandbox,
            )
        return SandboxPolicyDecision(
            allowed=True,
            reason="tool policy accepted",
            policy_id="tool-policy",
            audit_level=metadata.audit_level,
            requires_sandbox=requires_sandbox,
        )

    def _settings_for_task(self, task_id: str) -> dict:
        task = self.session.get(Task, task_id)
        if task is None or task.organization_id is None:
            return DEFAULT_POLICY_SETTINGS
        setting = self.session.execute(
            select(SystemSetting).where(
                SystemSetting.organization_id == task.organization_id,
                SystemSetting.key == POLICY_SETTINGS_KEY,
            )
        ).scalar_one_or_none()
        if setting is None:
            return DEFAULT_POLICY_SETTINGS
        return setting.value_json

    def _risk_policy(self, *, settings: dict, risk_level: str) -> dict | None:
        for policy in settings.get("risk_levels", []):
            if policy.get("name") == risk_level:
                return policy
        return None


class SandboxPolicyResolver:
    def __init__(self, session: Session) -> None:
        self.session = session

    def runtime_for_task(self, task_id: str | None) -> SandboxRuntimePolicy:
        settings = self._settings_for_task(task_id)
        sandbox = settings.get("sandbox", {})
        network_enabled = bool(sandbox.get("default_network", False))
        timeout_seconds = int(
            sandbox.get("default_timeout_seconds") or DEFAULT_SANDBOX_TIMEOUT_SECONDS
        )
        return SandboxRuntimePolicy(
            network_mode="bridge" if network_enabled else DEFAULT_SANDBOX_NETWORK,
            network_enabled=network_enabled,
            timeout_seconds=timeout_seconds,
        )

    def _settings_for_task(self, task_id: str | None) -> dict:
        if task_id is None:
            return DEFAULT_POLICY_SETTINGS
        task = self.session.get(Task, task_id)
        if task is None or task.organization_id is None:
            return DEFAULT_POLICY_SETTINGS
        setting = self.session.execute(
            select(SystemSetting).where(
                SystemSetting.organization_id == task.organization_id,
                SystemSetting.key == POLICY_SETTINGS_KEY,
            )
        ).scalar_one_or_none()
        if setting is None:
            return DEFAULT_POLICY_SETTINGS
        return setting.value_json
