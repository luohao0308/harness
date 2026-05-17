import hashlib
import ipaddress
import socket
from dataclasses import dataclass
from urllib.parse import quote, unquote, urlparse, urlsplit, urlunsplit

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
    "web_research": {
        "enabled": False,
        "require_allowlist": True,
        "allow_domains": [],
        "deny_domains": [],
        "max_results": 2,
        "timeout_seconds": 8,
        "max_content_bytes": 1200,
        "max_calls_per_run": 1,
    },
}


@dataclass(frozen=True)
class SandboxPolicyDecision:
    allowed: bool
    reason: str
    policy_id: str
    audit_level: str
    requires_sandbox: bool | None = None


@dataclass(frozen=True)
class WebResearchPolicyDecision:
    allowed: bool
    reason: str
    policy_id: str
    audit_level: str = "critical"
    snapshot: dict | None = None
    normalized_url: str | None = None
    normalized_url_sha256: str | None = None
    hostname: str | None = None


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

    def evaluate_web_research_pre_call(
        self,
        *,
        organization_id: str | None,
        provider: str,
        api_key_present: bool,
        query: str,
        max_results: int,
        timeout_seconds: int,
        calls_used: int = 0,
        query_has_secret: bool = False,
    ) -> WebResearchPolicyDecision:
        settings = self._settings_for_organization(organization_id)
        web = _web_research_settings(settings)
        snapshot = _web_policy_snapshot(
            provider=provider,
            web=web,
            reason="pre_call",
            query_length=len(query),
        )
        if provider == "disabled":
            return WebResearchPolicyDecision(
                allowed=False,
                reason="web research provider is disabled",
                policy_id="web-research-provider-enabled",
                snapshot=snapshot,
            )
        if not bool(web.get("enabled", False)):
            return WebResearchPolicyDecision(
                allowed=False,
                reason="web research is disabled by organization policy",
                policy_id="web-research-enabled",
                snapshot=snapshot,
            )
        if provider != "fake" and not api_key_present:
            return WebResearchPolicyDecision(
                allowed=False,
                reason="web research provider api key is missing",
                policy_id="web-research-api-key",
                snapshot=snapshot,
            )
        if not query or len(query) > 500:
            return WebResearchPolicyDecision(
                allowed=False,
                reason="web research query length is invalid",
                policy_id="web-research-query-valid",
                snapshot=snapshot,
            )
        if query_has_secret:
            return WebResearchPolicyDecision(
                allowed=False,
                reason="web research query appears to contain a secret",
                policy_id="web-research-query-privacy",
                snapshot=snapshot,
            )
        if max_results < 1 or max_results > int(web.get("max_results", 2)):
            return WebResearchPolicyDecision(
                allowed=False,
                reason="web research max results exceeds organization policy",
                policy_id="web-research-result-limit",
                snapshot=snapshot,
            )
        if timeout_seconds < 1 or timeout_seconds > int(web.get("timeout_seconds", 8)):
            return WebResearchPolicyDecision(
                allowed=False,
                reason="web research timeout exceeds organization policy",
                policy_id="web-research-timeout-limit",
                snapshot=snapshot,
            )
        if calls_used >= int(web.get("max_calls_per_run", 1)):
            return WebResearchPolicyDecision(
                allowed=False,
                reason="web research call limit is exhausted for this run",
                policy_id="web-research-call-limit",
                snapshot={**snapshot, "calls_used": calls_used},
            )
        allowlist = _domain_list(web, "allow_domains")
        if bool(web.get("require_allowlist", True)) and not allowlist:
            return WebResearchPolicyDecision(
                allowed=False,
                reason="web research domain allowlist is required",
                policy_id="web-research-allowlist-required",
                snapshot=snapshot,
            )
        return WebResearchPolicyDecision(
            allowed=True,
            reason="web research pre-call policy accepted",
            policy_id="web-research-pre-call",
            snapshot=snapshot,
        )

    def evaluate_web_research_result(
        self,
        *,
        organization_id: str | None,
        provider: str,
        url: str,
        seen_url_hashes: set[str] | None = None,
    ) -> WebResearchPolicyDecision:
        settings = self._settings_for_organization(organization_id)
        web = _web_research_settings(settings)
        snapshot = _web_policy_snapshot(provider=provider, web=web, reason="post_result")
        normalized = _normalize_web_research_url(url)
        if normalized.error:
            return WebResearchPolicyDecision(
                allowed=False,
                reason=normalized.error,
                policy_id="web-research-url-valid",
                snapshot={**snapshot, **normalized.snapshot},
                hostname=normalized.hostname,
            )
        url_hash = _sha256(normalized.url or "")
        if seen_url_hashes is not None and url_hash in seen_url_hashes:
            return WebResearchPolicyDecision(
                allowed=False,
                reason="web research url is duplicate in retrieval session",
                policy_id="web-research-url-dedupe",
                snapshot={**snapshot, **normalized.snapshot},
                normalized_url=normalized.url,
                normalized_url_sha256=url_hash,
                hostname=normalized.hostname,
            )
        host = normalized.hostname or ""
        denylist = _domain_list(web, "deny_domains")
        if _host_allowed(host=host, allowlist=denylist):
            return WebResearchPolicyDecision(
                allowed=False,
                reason="web research host is denied by organization policy",
                policy_id="web-research-denylist",
                snapshot={**snapshot, **normalized.snapshot},
                normalized_url=normalized.url,
                normalized_url_sha256=url_hash,
                hostname=host,
            )
        allowlist = _domain_list(web, "allow_domains")
        if bool(web.get("require_allowlist", True)) and not _host_allowed(
            host=host,
            allowlist=allowlist,
        ):
            return WebResearchPolicyDecision(
                allowed=False,
                reason="web research host is not in organization allowlist",
                policy_id="web-research-allowlist",
                snapshot={**snapshot, **normalized.snapshot},
                normalized_url=normalized.url,
                normalized_url_sha256=url_hash,
                hostname=host,
            )
        if _metadata_hostname(host):
            return WebResearchPolicyDecision(
                allowed=False,
                reason="web research host is metadata or local-only",
                policy_id="web-research-metadata-host",
                snapshot={**snapshot, **normalized.snapshot},
                normalized_url=normalized.url,
                normalized_url_sha256=url_hash,
                hostname=host,
            )
        addresses = _resolve_host_addresses(host)
        blocked = [str(address) for address in addresses if _blocked_address(address)]
        if blocked:
            return WebResearchPolicyDecision(
                allowed=False,
                reason="web research host resolves to a blocked address",
                policy_id="web-research-resolved-address",
                snapshot={
                    **snapshot,
                    **normalized.snapshot,
                    "resolved_ip_classification": "blocked",
                    "blocked_resolved_addresses": blocked,
                },
                normalized_url=normalized.url,
                normalized_url_sha256=url_hash,
                hostname=host,
            )
        return WebResearchPolicyDecision(
            allowed=True,
            reason="web research result policy accepted",
            policy_id="web-research-result",
            snapshot={
                **snapshot,
                **normalized.snapshot,
                "resolved_ip_classification": "public_or_unresolved",
            },
            normalized_url=normalized.url,
            normalized_url_sha256=url_hash,
            hostname=host,
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

    def _settings_for_organization(self, organization_id: str | None) -> dict:
        if organization_id is None:
            return DEFAULT_POLICY_SETTINGS
        setting = self.session.execute(
            select(SystemSetting).where(
                SystemSetting.organization_id == organization_id,
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


@dataclass(frozen=True)
class _NormalizedWebUrl:
    url: str | None
    hostname: str | None
    error: str | None
    snapshot: dict


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _web_research_settings(settings: dict) -> dict:
    raw = settings.get("web_research", {})
    if not isinstance(raw, dict):
        raw = {}
    merged = dict(DEFAULT_POLICY_SETTINGS["web_research"])
    merged.update(raw)
    merged["max_results"] = _positive_int(merged.get("max_results"), default=2)
    merged["timeout_seconds"] = _positive_int(merged.get("timeout_seconds"), default=8)
    merged["max_content_bytes"] = _positive_int(
        merged.get("max_content_bytes"),
        default=1200,
    )
    merged["max_calls_per_run"] = _positive_int(
        merged.get("max_calls_per_run"),
        default=1,
    )
    return merged


def _domain_list(settings: dict, key: str) -> list[str]:
    raw = settings.get(key, [])
    if not isinstance(raw, list):
        return []
    return [_normalize_domain_pattern(item) for item in raw if _normalize_domain_pattern(item)]


def _normalize_domain_pattern(value: object) -> str:
    text = str(value).strip().lower()
    if not text:
        return ""
    if text == "*":
        return text
    prefix = "*." if text.startswith("*.") else "." if text.startswith(".") else ""
    core = text.removeprefix("*.").removeprefix(".")
    try:
        core = core.encode("idna").decode("ascii")
    except UnicodeError:
        return ""
    return f"{prefix}{core}"


def _web_policy_snapshot(*, provider: str, web: dict, reason: str, **extra: object) -> dict:
    return {
        "schema_version": "web-research-policy-snapshot-v1",
        "provider": provider,
        "reason": reason,
        "enabled": bool(web.get("enabled", False)),
        "allow_domains": _domain_list(web, "allow_domains"),
        "deny_domains": _domain_list(web, "deny_domains"),
        "require_allowlist": bool(web.get("require_allowlist", True)),
        "max_results": int(web.get("max_results", 2)),
        "timeout_seconds": int(web.get("timeout_seconds", 8)),
        "max_content_bytes": int(web.get("max_content_bytes", 1200)),
        "max_calls_per_run": int(web.get("max_calls_per_run", 1)),
        "provider_domain_filters_advisory_only": True,
        "authoritative_enforcement": "post_result_policy_before_persistence",
        "evaluator_version": "web-research-policy-v1",
        **extra,
    }


def _normalize_web_research_url(url: str) -> _NormalizedWebUrl:
    raw = str(url or "").strip()
    try:
        parsed = urlsplit(raw)
    except ValueError as exc:
        return _NormalizedWebUrl(
            url=None,
            hostname=None,
            error="web research url is invalid",
            snapshot={"url_error": str(exc)},
        )
    if parsed.scheme.lower() not in {"http", "https"}:
        return _NormalizedWebUrl(
            url=None,
            hostname=None,
            error="web research url scheme is not allowed",
            snapshot={"scheme": parsed.scheme.lower()},
        )
    if parsed.username is not None or parsed.password is not None:
        return _NormalizedWebUrl(
            url=None,
            hostname=parsed.hostname,
            error="web research url must not contain credentials",
            snapshot={"credentials_present": True},
        )
    host = parsed.hostname or ""
    if not host:
        return _NormalizedWebUrl(
            url=None,
            hostname=None,
            error="web research url host is invalid",
            snapshot={},
        )
    host = host.rstrip(".").lower()
    if not _looks_like_ip_literal(host):
        try:
            host = host.encode("idna").decode("ascii")
        except UnicodeError:
            return _NormalizedWebUrl(
                url=None,
                hostname=host,
                error="web research url host idna normalization failed",
                snapshot={"hostname": host},
            )
    literal = _parse_ip_literal(host)
    if literal is not None and _blocked_address(literal):
        return _NormalizedWebUrl(
            url=None,
            hostname=host,
            error="web research url host is a blocked address",
            snapshot={
                "normalized_hostname": host,
                "resolved_ip_classification": "blocked_literal",
            },
        )
    try:
        port = parsed.port
    except ValueError:
        return _NormalizedWebUrl(
            url=None,
            hostname=host,
            error="web research url port is invalid",
            snapshot={"normalized_hostname": host},
        )
    netloc = host
    if ":" in host and not host.startswith("["):
        netloc = f"[{host}]"
    if port and not (
        (parsed.scheme.lower() == "http" and port == 80)
        or (parsed.scheme.lower() == "https" and port == 443)
    ):
        netloc = f"{netloc}:{port}"
    path = quote(unquote(parsed.path or "/"), safe="/:@")
    normalized = urlunsplit((parsed.scheme.lower(), netloc, path, parsed.query, ""))
    return _NormalizedWebUrl(
        url=normalized,
        hostname=host,
        error=None,
        snapshot={"normalized_hostname": host},
    )


def _looks_like_ip_literal(host: str) -> bool:
    return ":" in host or all(char.isdigit() or char == "." for char in host)


def _parse_ip_literal(host: str) -> ipaddress._BaseAddress | None:
    try:
        return ipaddress.ip_address(host.strip("[]"))
    except ValueError:
        pass
    if ":" in host:
        return None
    try:
        packed = socket.inet_aton(host)
    except OSError:
        return None
    return ipaddress.IPv4Address(packed)


def _metadata_hostname(host: str) -> bool:
    return host in {"localhost", "metadata.google.internal"} or host.endswith(".local")


def _resolve_host_addresses(host: str) -> list[ipaddress._BaseAddress]:
    literal = _parse_ip_literal(host)
    if literal is not None:
        return [literal]
    try:
        infos = socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
    except OSError:
        return []
    addresses: list[ipaddress._BaseAddress] = []
    for info in infos:
        sockaddr = info[4]
        if not sockaddr:
            continue
        try:
            addresses.append(ipaddress.ip_address(str(sockaddr[0])))
        except ValueError:
            continue
    return addresses


def _blocked_address(address: ipaddress._BaseAddress) -> bool:
    return (
        address.is_loopback
        or address.is_link_local
        or address.is_private
        or address.is_reserved
        or address.is_multicast
        or address.is_unspecified
    )


def is_safe_web_research_url(url: str) -> bool:
    normalized = _normalize_web_research_url(url)
    if normalized.error or not normalized.hostname:
        return False
    if _metadata_hostname(normalized.hostname):
        return False
    return not any(
        _blocked_address(address)
        for address in _resolve_host_addresses(normalized.hostname)
    )
