from dataclasses import dataclass
from urllib.parse import urlparse

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import SystemSetting, Task

DEFAULT_SANDBOX_IMAGE = "agent-runtime:latest"
DEFAULT_SANDBOX_MEMORY = "1024m"
DEFAULT_SANDBOX_MEMORY_MB = 1024
DEFAULT_SANDBOX_CPUS = "1.0"
DEFAULT_SANDBOX_NANO_CPUS = 1_000_000_000
DEFAULT_WORKSPACE_QUOTA_MB = 1024
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
    "sandbox": {
        "default_network": False,
        "default_timeout_seconds": 60,
        "memory_mb": DEFAULT_SANDBOX_MEMORY_MB,
        "cpus": DEFAULT_SANDBOX_CPUS,
        "workspace_quota_mb": DEFAULT_WORKSPACE_QUOTA_MB,
        "network_allowlist": [],
    },
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
    workspace_quota_mb: int = DEFAULT_WORKSPACE_QUOTA_MB
    network_allowlist: tuple[str, ...] = ()
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

    def evaluate_network_request(self, *, task_id: str, url: str) -> SandboxPolicyDecision:
        settings = self._settings_for_task(task_id)
        sandbox = settings.get("sandbox", {})
        if not bool(sandbox.get("default_network", False)):
            return SandboxPolicyDecision(
                allowed=False,
                reason="network is disabled by sandbox policy",
                policy_id="network-enabled",
                audit_level="critical",
                requires_sandbox=True,
            )
        host = _hostname_from_url(url)
        if host is None:
            return SandboxPolicyDecision(
                allowed=False,
                reason="network url host is invalid",
                policy_id="network-url-valid",
                audit_level="critical",
                requires_sandbox=True,
            )
        allowlist = _network_allowlist(sandbox)
        if not _host_allowed(host=host, allowlist=allowlist):
            return SandboxPolicyDecision(
                allowed=False,
                reason="network host is not in allowlist",
                policy_id="network-allowlist",
                audit_level="critical",
                requires_sandbox=True,
            )
        return SandboxPolicyDecision(
            allowed=True,
            reason="network host accepted",
            policy_id="network-allowlist",
            audit_level="critical",
            requires_sandbox=True,
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
        memory_mb = _positive_int(
            sandbox.get("memory_mb"),
            default=DEFAULT_SANDBOX_MEMORY_MB,
        )
        cpus = _positive_float_string(sandbox.get("cpus"), default=DEFAULT_SANDBOX_CPUS)
        workspace_quota_mb = _positive_int(
            sandbox.get("workspace_quota_mb"),
            default=DEFAULT_WORKSPACE_QUOTA_MB,
        )
        return SandboxRuntimePolicy(
            network_mode="bridge" if network_enabled else DEFAULT_SANDBOX_NETWORK,
            network_enabled=network_enabled,
            timeout_seconds=timeout_seconds,
            memory=f"{memory_mb}m",
            memory_mb=memory_mb,
            cpus=cpus,
            nano_cpus=int(float(cpus) * 1_000_000_000),
            workspace_quota_mb=workspace_quota_mb,
            network_allowlist=tuple(_network_allowlist(sandbox)),
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


def _positive_int(value: object, *, default: int) -> int:
    try:
        parsed = int(str(value))
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default


def _positive_float_string(value: object, *, default: str) -> str:
    try:
        parsed = float(str(value))
    except (TypeError, ValueError):
        return default
    if parsed <= 0:
        return default
    if parsed.is_integer():
        return f"{parsed:.1f}"
    return f"{parsed:.3f}".rstrip("0").rstrip(".")


def _network_allowlist(sandbox: dict) -> list[str]:
    raw_allowlist = sandbox.get("network_allowlist", [])
    if not isinstance(raw_allowlist, list):
        return []
    return [str(item).lower().strip() for item in raw_allowlist if str(item).strip()]


def _hostname_from_url(url: str) -> str | None:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or parsed.hostname is None:
        return None
    return parsed.hostname.lower()


def _host_allowed(*, host: str, allowlist: list[str]) -> bool:
    for entry in allowlist:
        if entry == "*":
            return True
        if entry.startswith("*.") or entry.startswith("."):
            suffix = entry.removeprefix("*.").removeprefix(".")
            if host == suffix or host.endswith(f".{suffix}"):
                return True
            continue
        if host == entry:
            return True
    return False
