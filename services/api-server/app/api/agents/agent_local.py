"""Local Agent bridge pairing, connection, and event APIs."""

# ruff: noqa: F401,F403,F405,I001,UP037
import secrets
import sys
from datetime import UTC, datetime, timedelta

from fastapi import Header
from sqlalchemy.exc import IntegrityError

from .common import *
from ._workspace_chat_helpers import _create_workspace_chat_run

LOCAL_AGENT_PROTOCOL_VERSION = "local-agent-v1"
LOCAL_AGENT_SUPPORTED_ADAPTERS = {"fake", "hao", "codex", "claude_code"}
LOCAL_AGENT_DISABLED_ADAPTERS: set[str] = set()
LOCAL_AGENT_DEFAULT_PAIR_ADAPTERS = ["fake", "hao", "codex", "claude_code"]
LOCAL_AGENT_COMMAND = (
    "hao bridge pair "
    "--api {api_url} --pair-token {pair_token} --pair-code {pair_code} --daemon"
)
DEVICE_TOKEN_BYTES = 32
PAIR_TOKEN_BYTES = 32
PAIR_CODE_DIGITS = "0123456789ABCDEFGHJKLMNPQRSTUVWXYZ"
LOCAL_AGENT_OFFLINE_AFTER_SECONDS = 30
LOCAL_AGENT_TOOL_DECISION_TTL_MINUTES = 30
LOCAL_AGENT_TOOL_TERMINAL_STATUSES = {"succeeded", "failed", "cancelled", "denied", "expired"}
LOCAL_AGENT_TOOL_ACTIVE_STATUSES = {"approval_required", "approved", "allowed", "running"}
LOCAL_AGENT_COMMAND_TERMINAL_STATUSES = {"success", "failed", "timeout", "cancelled"}
LOCAL_AGENT_COMMAND_ACTIVE_STATUSES = {"pending", "running"}
LOCAL_AGENT_SIDE_EFFECT_TOOLS = {
    "run_shell",
    "run_tests",
    "write_file",
    "apply_patch",
    "commit_write_file",
    "commit_apply_patch",
    "git",
    "git_commit",
    "network",
    "env_read",
    "secret_read",
    "delete_file",
    "move_file",
}
LOCAL_AGENT_COMMAND_TOOLS = {"run_shell", "run_tests", "git"}
LOCAL_AGENT_PENDING_CHANGE_TERMINAL_STATUSES = {"committed", "denied", "failed"}
LOCAL_AGENT_PENDING_CHANGE_ACTIVE_STATUSES = {
    "previewed",
    "approval_required",
    "approved",
    "allowed",
}
LOCAL_AGENT_PENDING_CHANGE_TOOLS = {
    "write_file",
    "apply_patch",
    "commit_write_file",
    "commit_apply_patch",
}
LOCAL_AGENT_CAPABILITY_TOOL_ALIASES = {
    "apply_patch": "write_file",
    "commit_write_file": "write_file",
    "commit_apply_patch": "write_file",
    "git": "git_command",
    "git_commit": "git_command",
    "network": "network_request",
}
LOCAL_AGENT_SAFE_TOOLS = {"fake.noop", "local_status", "read_metadata"}
LOCAL_AGENT_RESTRICTED_ASSISTANT_ADAPTERS = {"codex", "claude_code"}
LOCAL_AGENT_CODEX_ALLOWED_RISK_CAPABILITIES = {"workspace_read_constrained"}
LOCAL_AGENT_CLAUDE_CODE_ALLOWED_RISK_CAPABILITIES = {
    "workspace_read",
    "host_write_approval_required",
    "shell_approval_required",
    "git_approval_required",
    "pending_change",
    "command_lifecycle",
}
LOCAL_AGENT_CLAUDE_CODE_PERMISSION_BRIDGE = "harness_local_tool_request_v1"
LOCAL_AGENT_CLAUDE_CODE_PERMISSION_BRIDGE_EXECUTION_MODE = (
    "agent_sdk_intent_capture_harness_executor"
)
LOCAL_AGENT_CLAUDE_CODE_LEGACY_PERMISSION_BRIDGE_EXECUTION_MODE = (
    "agent_sdk_permission_bridge"
)
LOCAL_AGENT_CLAUDE_CODE_PERMISSION_BRIDGE_EXECUTOR = "harness_owned_executor"
LOCAL_AGENT_CLAUDE_CODE_V6_SAFETY_FLAGS = {
    "permission_bridge_callback_configured",
    "permission_bridge_pre_tool_hook_configured",
    "permission_bridge_dummy_hook_only",
    "side_effect_tools_preapproval_disabled",
    "forbidden_permission_modes_disabled",
    "unmanaged_settings_disabled",
    "mcp_disabled",
    "plugins_disabled",
    "hooks_disabled",
    "subagents_disabled",
    "browser_disabled",
    "computer_use_disabled",
    "remote_control_disabled",
}
LOCAL_AGENT_CLAUDE_CODE_FORBIDDEN_CAPABILITY_MARKERS = {
    "bypasspermissions",
    "acceptedits",
    "auto",
    "dontask",
    "remote_control",
    "remote-control",
    "mcp",
    "plugin",
    "hook",
    "subagent",
    "browser",
    "computer_use",
    "computer-use",
    "native_resume",
    "background_session",
    "web_session",
    "cloud_session",
}
LOCAL_AGENT_NETWORK_PATTERNS = re.compile(
    r"\b(curl|wget|ssh|scp|git\s+remote|npm\s+install|pip\s+install|pnpm\s+install|yarn\s+add)\b",
    re.IGNORECASE,
)
LOCAL_AGENT_SECRET_PATTERNS = re.compile(
    r"\b(printenv|env|cat\s+\.env|cat\s+.*(secret|token|key)|export\s+\w*(TOKEN|SECRET|KEY))\b",
    re.IGNORECASE,
)
LOCAL_AGENT_CODEX_CONTEXT_MAX_MESSAGES = 8
LOCAL_AGENT_CODEX_CONTEXT_MESSAGE_CHARS = 2000
LOCAL_AGENT_CODEX_CONTEXT_TOTAL_CHARS = 12000


def _sha256_secret(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _as_aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _new_pair_code() -> str:
    return "".join(secrets.choice(PAIR_CODE_DIGITS) for _ in range(6))


def _redact_path(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    if not normalized:
        return None
    parts = normalized.replace("\\", "/").split("/")
    if len(parts) >= 4 and parts[1] in {"Users", "home"}:
        safe_tail = [part for part in parts[3:] if part]
        return f".../{'/'.join(safe_tail[-2:])}" if safe_tail else "..."
    if len(parts) <= 2:
        return normalized
    return f".../{'/'.join(parts[-2:])}"


def _pairing_response(
    token: LocalAgentPairingToken, *, pair_token: str | None = None
) -> LocalAgentPairingResponse:
    command = None
    if pair_token is not None:
        adapter_kind = _pairing_command_adapter(token.scope_json)
        command = LOCAL_AGENT_COMMAND.format(
            api_url="http://127.0.0.1:8000",
            pair_token=pair_token,
            pair_code=token.pair_code,
        )
        if adapter_kind != "hao":
            command = f"{command} --adapter {adapter_kind}"
        permission_bridge = _pairing_command_permission_bridge(token.scope_json)
        if permission_bridge:
            command = f"{command} --permission-bridge {permission_bridge}"
    return LocalAgentPairingResponse(
        id=token.id,
        agent_id=token.agent_id,
        pair_code=token.pair_code,
        pair_token=pair_token,
        command=command,
        status=token.status,
        expires_at=token.expires_at,
        created_at=token.created_at,
    )


def _connection_response(connection: LocalAgentConnection) -> LocalAgentConnectionResponse:
    effective_status = connection.status
    if (
        effective_status in {"online", "busy"}
        and connection.last_seen_at is not None
        and (_as_aware_utc(utc_now()) - _as_aware_utc(connection.last_seen_at)).total_seconds()
        > LOCAL_AGENT_OFFLINE_AFTER_SECONDS
    ):
        effective_status = "offline"
    return LocalAgentConnectionResponse(
        id=connection.id,
        agent_id=connection.agent_id,
        owner_user_id=connection.owner_user_id,
        display_name=connection.display_name,
        adapter_kind=connection.adapter_kind,
        protocol_version=connection.protocol_version,
        bridge_version=connection.bridge_version,
        status=effective_status,
        workspace_root=_redact_path(connection.workspace_root),
        capabilities_json=connection.capabilities_json,
        risk_capabilities_json=connection.risk_capabilities_json,
        last_seen_at=connection.last_seen_at,
        revoked_at=connection.revoked_at,
        created_at=connection.created_at,
        updated_at=connection.updated_at,
    )


def _binding_response(
    binding: LocalAgentConversationBinding,
) -> LocalAgentConversationBindingResponse:
    return LocalAgentConversationBindingResponse(
        id=binding.id,
        connection_id=binding.connection_id,
        agent_id=binding.agent_id,
        agent_session_id=binding.agent_session_id,
        adapter_session_id=binding.adapter_session_id,
        resume_mode=binding.resume_mode,
        status=binding.status,
        created_at=binding.created_at,
        updated_at=binding.updated_at,
    )


def _owned_connection(
    *,
    connection_id: str,
    session: Session,
    principal: Principal,
    executable: bool = False,
) -> LocalAgentConnection:
    connection = session.get(LocalAgentConnection, connection_id)
    if connection is None or connection.organization_id != principal.organization_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Local Agent connection not found"
        )
    if executable and connection.owner_user_id != principal.user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the device owner can execute local Agent messages",
        )
    return connection


def _bridge_connection(
    *,
    session: Session,
    device_token: str | None,
) -> LocalAgentConnection:
    if not device_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing local Agent device token"
        )
    connection = session.execute(
        select(LocalAgentConnection).where(
            LocalAgentConnection.device_token_hash == _sha256_secret(device_token)
        )
    ).scalar_one_or_none()
    if connection is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid local Agent device token"
        )
    if connection.revoked_at is not None or connection.status == "revoked":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Local Agent connection revoked"
        )
    return connection


def _ensure_host_tool_protocol_allowed(connection: LocalAgentConnection) -> None:
    if connection.adapter_kind == "claude_code" and _claude_code_permission_bridge_enabled(
        connection
    ):
        return
    if connection.adapter_kind in LOCAL_AGENT_RESTRICTED_ASSISTANT_ADAPTERS:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"{connection.adapter_kind} adapter cannot use local host tool protocol",
        )


def _claude_code_permission_bridge_enabled(connection: LocalAgentConnection) -> bool:
    capabilities = (
        connection.capabilities_json if isinstance(connection.capabilities_json, dict) else {}
    )
    return (
        connection.adapter_kind == "claude_code"
        and _claude_code_permission_bridge_entitled(connection)
        and capabilities.get("enabled_in_v6") is True
        and capabilities.get("host_tools_authorized") is True
        and capabilities.get("permission_bridge") == LOCAL_AGENT_CLAUDE_CODE_PERMISSION_BRIDGE
        and capabilities.get("execution_mode")
        == LOCAL_AGENT_CLAUDE_CODE_PERMISSION_BRIDGE_EXECUTION_MODE
        and capabilities.get("permission_bridge_execution")
        == LOCAL_AGENT_CLAUDE_CODE_PERMISSION_BRIDGE_EXECUTOR
        and capabilities.get("sdk_native_tool_execution_enabled") is False
    )


def _claude_code_permission_bridge_entitled(connection: LocalAgentConnection) -> bool:
    metadata = connection.metadata_json if isinstance(connection.metadata_json, dict) else {}
    return (
        connection.adapter_kind == "claude_code"
        and metadata.get("server_permission_bridge_entitlement") == "sdk"
    )


def _scope_permission_bridge(scope: dict) -> str | None:
    raw = scope.get("permission_bridge") if isinstance(scope, dict) else None
    if isinstance(raw, list) and len(raw) == 1:
        return str(raw[0])
    if isinstance(raw, str) and raw.strip():
        return raw.strip()
    return None


def _pairing_command_permission_bridge(scope: dict) -> str | None:
    permission_bridge = _scope_permission_bridge(scope)
    if permission_bridge == "sdk":
        return "sdk"
    return None


def _connection_metadata_with_permission_bridge_entitlement(
    metadata: dict,
    *,
    permission_bridge: str | None,
) -> dict:
    safe_metadata = _safe_metadata(metadata)
    safe_metadata["server_permission_bridge_entitlement"] = (
        "sdk" if permission_bridge == "sdk" else "none"
    )
    return safe_metadata


def _get_local_target_agent(
    *,
    agent_id: str,
    session: Session,
    principal: Principal,
) -> Agent:
    agent = session.execute(
        select(Agent).where(
            Agent.id == agent_id,
            or_(
                Agent.organization_id == principal.organization_id,
                Agent.organization_id.is_(None),
            ),
        )
    ).scalar_one_or_none()
    if agent is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found")
    return agent


@router.post(
    "/local-agent/pairing-tokens",
    response_model=LocalAgentPairingResponse,
    status_code=status.HTTP_201_CREATED,
    summary="创建本地 Agent 配对命令",
)
def create_local_agent_pairing_token(
    request: LocalAgentPairingCreateRequest,
    session: DbSession,
    principal: Principal,
) -> LocalAgentPairingResponse:
    require_role(principal, {"admin", "engineer"})
    _get_local_target_agent(agent_id=request.agent_id, session=session, principal=principal)
    pair_token = secrets.token_urlsafe(PAIR_TOKEN_BYTES)
    now = utc_now()
    token = LocalAgentPairingToken(
        organization_id=principal.organization_id,
        user_id=principal.user_id,
        agent_id=request.agent_id,
        token_hash=_sha256_secret(pair_token),
        pair_code=_new_pair_code(),
        scope_json=request.scope
        or {"executable": True, "adapters": LOCAL_AGENT_DEFAULT_PAIR_ADAPTERS},
        status="active",
        expires_at=now + timedelta(minutes=request.ttl_minutes),
        created_at=now,
    )
    session.add(token)
    session.flush()
    _record_local_agent_audit(
        session=session,
        organization_id=principal.organization_id,
        actor_id=principal.user_id,
        action="local_agent.pairing.create",
        resource_type="local_agent_pairing_token",
        resource_id=token.id,
        payload={
            "agent_id": token.agent_id,
            "pair_code": token.pair_code,
            "expires_at": token.expires_at.isoformat(),
        },
    )
    session.commit()
    session.refresh(token)
    return _pairing_response(token, pair_token=pair_token)


@router.post(
    "/local-agent/pairing-tokens/{token_id}/revoke",
    response_model=LocalAgentPairingResponse,
    summary="撤销本地 Agent 配对令牌",
)
def revoke_local_agent_pairing_token(
    token_id: str,
    session: DbSession,
    principal: Principal,
) -> LocalAgentPairingResponse:
    require_role(principal, {"admin", "engineer"})
    token = session.get(LocalAgentPairingToken, token_id)
    if token is None or token.organization_id != principal.organization_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pairing token not found")
    if token.user_id != principal.user_id and "admin" not in principal.roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only creator or admin can revoke pairing token",
        )
    now = utc_now()
    token.status = "revoked"
    token.revoked_at = now
    _record_local_agent_audit(
        session=session,
        organization_id=token.organization_id,
        actor_id=principal.user_id,
        action="local_agent.pairing.revoke",
        resource_type="local_agent_pairing_token",
        resource_id=token.id,
        payload={"agent_id": token.agent_id, "status": token.status},
    )
    session.commit()
    session.refresh(token)
    return _pairing_response(token)


@router.post(
    "/local-agent/connections/register",
    response_model=LocalAgentConnectionRegisterResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Bridge 使用配对 token 注册本地 Agent 连接",
)
def register_local_agent_connection(
    request: LocalAgentConnectionRegisterRequest,
    session: DbSession,
) -> LocalAgentConnectionRegisterResponse:
    if request.protocol_version != LOCAL_AGENT_PROTOCOL_VERSION:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unsupported local Agent protocol version",
        )
    if request.adapter_kind in LOCAL_AGENT_DISABLED_ADAPTERS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Adapter is not enabled"
        )
    if request.adapter_kind not in LOCAL_AGENT_SUPPORTED_ADAPTERS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported local Agent adapter"
        )
    now = utc_now()
    token = session.execute(
        select(LocalAgentPairingToken).where(
            LocalAgentPairingToken.token_hash == _sha256_secret(request.pair_token),
            LocalAgentPairingToken.pair_code == request.pair_code,
        ).with_for_update()
    ).scalar_one_or_none()
    if token is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid local Agent pairing token"
        )
    if token.status != "active" or token.consumed_at is not None or token.revoked_at is not None:
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="Local Agent pairing token already used or revoked",
        )
    if _as_aware_utc(token.expires_at) < now:
        token.status = "expired"
        _record_local_agent_audit(
            session=session,
            organization_id=token.organization_id,
            actor_id=token.user_id,
            action="local_agent.pairing.expire",
            resource_type="local_agent_pairing_token",
            resource_id=token.id,
            payload={"agent_id": token.agent_id, "pair_code": token.pair_code},
        )
        session.commit()
        raise HTTPException(
            status_code=status.HTTP_410_GONE, detail="Local Agent pairing token expired"
        )
    _validate_pairing_scope_for_adapter(token.scope_json, request.adapter_kind)
    normalized_capabilities = _normalized_capabilities(
        request.adapter_kind,
        request.capabilities,
    )
    normalized_risk_capabilities = _normalized_risk_capabilities(
        request.adapter_kind,
        request.risk_capabilities,
    )
    token_permission_bridge = _scope_permission_bridge(token.scope_json)
    normalized_claude_v6 = _claude_code_capabilities_v6_enabled(normalized_capabilities)
    if token_permission_bridge == "sdk" and not normalized_claude_v6:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "Claude Code SDK permission bridge capability is required "
                "for this pairing token"
            ),
        )
    if normalized_claude_v6 and token_permission_bridge != "sdk":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Claude Code SDK permission bridge requires a scoped pairing token",
        )

    device_token = secrets.token_urlsafe(DEVICE_TOKEN_BYTES)
    connection = LocalAgentConnection(
        organization_id=token.organization_id,
        owner_user_id=token.user_id,
        agent_id=token.agent_id,
        pairing_token_id=token.id,
        device_token_hash=_sha256_secret(device_token),
        display_name=request.display_name or _default_local_agent_name(request.adapter_kind),
        adapter_kind=request.adapter_kind,
        protocol_version=request.protocol_version,
        bridge_version=request.bridge_version,
        status="online",
        workspace_root=_redact_path(request.workspace_root),
        capabilities_json=normalized_capabilities,
        risk_capabilities_json=normalized_risk_capabilities,
        metadata_json=_connection_metadata_with_permission_bridge_entitlement(
            request.metadata,
            permission_bridge=token_permission_bridge if normalized_claude_v6 else None,
        ),
        last_seen_at=now,
        created_at=now,
        updated_at=now,
    )
    token.status = "consumed"
    token.consumed_at = now
    session.add(connection)
    try:
        session.flush()
        _record_local_agent_audit(
            session=session,
            organization_id=token.organization_id,
            actor_id=token.user_id,
            action="local_agent.connection.register",
            resource_type="local_agent_connection",
            resource_id=connection.id,
            payload={
                "agent_id": connection.agent_id,
                "adapter_kind": connection.adapter_kind,
                "pairing_token_id": token.id,
                "workspace_root": _redact_path(connection.workspace_root),
            },
        )
        session.commit()
    except IntegrityError as exc:
        token_id = token.id
        session.rollback()
        existing_connection = session.execute(
            select(LocalAgentConnection).where(LocalAgentConnection.pairing_token_id == token_id)
        ).scalar_one_or_none()
        if existing_connection is not None:
            raise HTTPException(
                status_code=status.HTTP_410_GONE,
                detail="Local Agent pairing token already used or revoked",
            ) from exc
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Local Agent connection token collision"
        ) from exc
    session.refresh(connection)
    return LocalAgentConnectionRegisterResponse(
        connection=_connection_response(connection),
        device_token=device_token,
    )


@router.get(
    "/local-agent/connections",
    response_model=LocalAgentConnectionPage,
    summary="列出本地 Agent 连接",
)
def list_local_agent_connections(
    session: DbSession,
    principal: Principal,
) -> LocalAgentConnectionPage:
    require_role(principal, {"admin", "engineer", "operator"})
    rows = list(
        session.execute(
            select(LocalAgentConnection)
            .where(LocalAgentConnection.organization_id == principal.organization_id)
            .order_by(
                LocalAgentConnection.updated_at.desc(), LocalAgentConnection.created_at.desc()
            )
        ).scalars()
    )
    if "admin" not in principal.roles:
        rows = [row for row in rows if row.owner_user_id == principal.user_id]
    return LocalAgentConnectionPage(items=[_connection_response(row) for row in rows])


@router.post(
    "/local-agent/connections/{connection_id}/heartbeat",
    response_model=LocalAgentHeartbeatResponse,
    summary="Bridge 心跳",
)
def heartbeat_local_agent_connection(
    connection_id: str,
    request: LocalAgentHeartbeatRequest,
    session: DbSession,
    x_local_agent_device_token: str | None = Header(default=None),
) -> LocalAgentHeartbeatResponse:
    connection = _bridge_connection(session=session, device_token=x_local_agent_device_token)
    if connection.id != connection_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Device token does not match connection"
        )
    now = utc_now()
    connection.status = request.status
    connection.protocol_version = request.protocol_version
    connection.bridge_version = request.bridge_version
    if request.capabilities is not None:
        heartbeat_capabilities = _normalized_capabilities(
            connection.adapter_kind,
            request.capabilities,
        )
        if (
            connection.adapter_kind == "claude_code"
            and _claude_code_capabilities_v6_enabled(heartbeat_capabilities)
            and not _claude_code_permission_bridge_entitled(connection)
        ):
            existing_capabilities = (
                connection.capabilities_json
                if isinstance(connection.capabilities_json, dict)
                else {}
            )
            heartbeat_capabilities = _normalized_capabilities(
                connection.adapter_kind,
                {
                    **request.capabilities,
                    "supports_streaming": request.capabilities.get(
                        "supports_streaming",
                        existing_capabilities.get("supports_streaming", True),
                    ),
                    "claude_permission_bridge_v1": False,
                },
            )
        connection.capabilities_json = heartbeat_capabilities
    connection.last_seen_at = now
    connection.updated_at = now
    _record_local_agent_audit(
        session=session,
        organization_id=connection.organization_id,
        actor_id=connection.owner_user_id,
        action="local_agent.connection.heartbeat",
        resource_type="local_agent_connection",
        resource_id=connection.id,
        payload={
            "agent_id": connection.agent_id,
            "adapter_kind": connection.adapter_kind,
            "status": connection.status,
        },
    )
    session.commit()
    session.refresh(connection)
    return LocalAgentHeartbeatResponse(connection=_connection_response(connection))


@router.post(
    "/local-agent/connections/{connection_id}/revoke",
    response_model=LocalAgentConnectionResponse,
    summary="撤销本地 Agent 连接",
)
def revoke_local_agent_connection(
    connection_id: str,
    session: DbSession,
    principal: Principal,
) -> LocalAgentConnectionResponse:
    require_role(principal, {"admin", "engineer"})
    connection = _owned_connection(
        connection_id=connection_id,
        session=session,
        principal=principal,
        executable=False,
    )
    if connection.owner_user_id != principal.user_id and "admin" not in principal.roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only owner or admin can revoke connection",
        )
    now = utc_now()
    connection.status = "revoked"
    connection.revoked_at = now
    connection.updated_at = now
    revoke_reason = "local agent connection revoked"
    active_requests = list(
        session.execute(
            select(LocalAgentToolRequest)
            .where(
                LocalAgentToolRequest.connection_id == connection.id,
                LocalAgentToolRequest.status.in_(LOCAL_AGENT_TOOL_ACTIVE_STATUSES),
            )
            .order_by(LocalAgentToolRequest.created_at.asc(), LocalAgentToolRequest.id.asc())
        ).scalars()
    )
    for local_request in active_requests:
        _terminalize_local_tool_request(
            local_request,
            session=session,
            terminal_status="cancelled",
            tool_status="CANCELLED",
            reason=revoke_reason,
            event_type=EventType.LOCAL_AGENT_COMMAND_CANCELLED,
            actor_type="user",
            actor_id=principal.user_id,
        )
    unfinished_tasks = list(
        session.execute(
            select(LocalAgentBridgeTask)
            .where(
                LocalAgentBridgeTask.connection_id == connection.id,
                ~LocalAgentBridgeTask.status.in_(("completed", "failed", "cancelled")),
            )
            .order_by(LocalAgentBridgeTask.created_at.asc(), LocalAgentBridgeTask.id.asc())
        ).scalars()
    )
    for bridge_task in unfinished_tasks:
        _cancel_local_agent_bridge_task(
            bridge_task=bridge_task,
            session=session,
            reason=revoke_reason,
            actor_type="user",
            actor_id=principal.user_id,
        )
    _record_local_agent_audit(
        session=session,
        organization_id=connection.organization_id,
        actor_id=principal.user_id,
        action="local_agent.connection.revoke",
        resource_type="local_agent_connection",
        resource_id=connection.id,
        payload={
            "agent_id": connection.agent_id,
            "adapter_kind": connection.adapter_kind,
            "owner_user_id": connection.owner_user_id,
        },
    )
    session.commit()
    session.refresh(connection)
    return _connection_response(connection)


@router.post(
    "/local-agent/connections/{connection_id}/bindings",
    response_model=LocalAgentConversationBindingResponse,
    status_code=status.HTTP_201_CREATED,
    summary="绑定本地 Agent 与 Harness AgentSession",
)
def bind_local_agent_conversation(
    connection_id: str,
    request: LocalAgentConversationBindRequest,
    session: DbSession,
    principal: Principal,
) -> LocalAgentConversationBindingResponse:
    require_role(principal, {"admin", "engineer"})
    connection = _owned_connection(
        connection_id=connection_id,
        session=session,
        principal=principal,
        executable=True,
    )
    agent_session = _resolve_or_create_agent_session(
        connection=connection,
        request=request,
        session=session,
        principal=principal,
    )
    existing = session.execute(
        select(LocalAgentConversationBinding).where(
            LocalAgentConversationBinding.connection_id == connection.id,
            LocalAgentConversationBinding.agent_session_id == agent_session.id,
        )
    ).scalar_one_or_none()
    if existing is not None:
        resume_mode = _normalized_resume_mode(
            connection=connection,
            requested_resume_mode=request.resume_mode,
        )
        existing.status = "active"
        existing.adapter_session_id = request.adapter_session_id or existing.adapter_session_id
        existing.resume_mode = resume_mode
        existing.updated_at = utc_now()
        session.commit()
        session.refresh(existing)
        return _binding_response(existing)

    now = utc_now()
    resume_mode = _normalized_resume_mode(
        connection=connection,
        requested_resume_mode=request.resume_mode,
    )
    binding = LocalAgentConversationBinding(
        organization_id=principal.organization_id,
        owner_user_id=principal.user_id,
        connection_id=connection.id,
        agent_id=connection.agent_id,
        agent_session_id=agent_session.id,
        adapter_session_id=request.adapter_session_id,
        resume_mode=resume_mode,
        status="active",
        metadata_json={
            "adapter_kind": connection.adapter_kind,
            "supports_resume": bool(connection.capabilities_json.get("supports_resume", True)),
            "workspace_identity_hash": (connection.metadata_json or {}).get(
                "workspace_identity_hash"
            ),
        },
        created_at=now,
        updated_at=now,
    )
    session.add(binding)
    session.commit()
    session.refresh(binding)
    return _binding_response(binding)


@router.get(
    "/local-agent/connections/{connection_id}/bindings",
    response_model=LocalAgentConversationBindingPage,
    summary="列出本地 Agent 连接的会话绑定",
)
def list_local_agent_conversation_bindings(
    connection_id: str,
    session: DbSession,
    principal: Principal,
) -> LocalAgentConversationBindingPage:
    require_role(principal, {"admin", "engineer", "operator"})
    connection = _owned_connection(
        connection_id=connection_id,
        session=session,
        principal=principal,
        executable=False,
    )
    if "admin" not in principal.roles and connection.owner_user_id != principal.user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only owner or admin can list local Agent bindings",
        )
    rows = list(
        session.execute(
            select(LocalAgentConversationBinding)
            .where(
                LocalAgentConversationBinding.connection_id == connection.id,
                LocalAgentConversationBinding.organization_id == principal.organization_id,
            )
            .order_by(
                LocalAgentConversationBinding.updated_at.desc(),
                LocalAgentConversationBinding.created_at.desc(),
            )
        ).scalars()
    )
    return LocalAgentConversationBindingPage(items=[_binding_response(row) for row in rows])


@router.post(
    "/local-agent/bindings/{binding_id}/messages",
    response_model=LocalAgentSendMessageResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="通过 Harness 向本地 Agent 发送消息",
)
def send_local_agent_message(
    binding_id: str,
    request: LocalAgentSendMessageRequest,
    session: DbSession,
    principal: Principal,
) -> LocalAgentSendMessageResponse:
    require_role(principal, {"admin", "engineer"})
    binding = session.get(LocalAgentConversationBinding, binding_id)
    if binding is None or binding.organization_id != principal.organization_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Local Agent binding not found"
        )
    connection = _owned_connection(
        connection_id=binding.connection_id,
        session=session,
        principal=principal,
        executable=True,
    )
    if connection.status == "revoked" or connection.revoked_at is not None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Local Agent connection revoked"
        )
    existing = session.execute(
        select(LocalAgentBridgeTask).where(
            LocalAgentBridgeTask.binding_id == binding.id,
            LocalAgentBridgeTask.client_message_id == request.client_message_id,
        )
    ).scalar_one_or_none()
    if existing is not None:
        return LocalAgentSendMessageResponse(
            bridge_task_id=existing.id,
            run_id=existing.task_id,
            agent_session_id=existing.agent_session_id,
            user_message_id=existing.user_message_id,
            status=existing.status,
        )

    agent_session = session.get(AgentSession, binding.agent_session_id)
    if agent_session is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent Session not found")
    now = utc_now()
    conversation_context = (
        _codex_conversation_context(
            agent_session_id=agent_session.id,
            session=session,
        )
        if connection.adapter_kind in LOCAL_AGENT_RESTRICTED_ASSISTANT_ADAPTERS
        else []
    )
    user_message = AgentMessage(
        session_id=agent_session.id,
        agent_id=binding.agent_id,
        role="user",
        content=request.content,
        metadata_json={
            "source": "local_agent",
            "connection_id": connection.id,
            "binding_id": binding.id,
            "client_message_id": request.client_message_id,
        },
        created_at=now,
    )
    session.add(user_message)
    session.flush()
    run = _create_workspace_chat_run(
        agent_id=binding.agent_id,
        goal=request.content,
        session=session,
        principal=principal,
        mode="cli_agent" if connection.adapter_kind == "hao" else "chat",
        max_subagents=0,
        commit=False,
    )
    bridge_payload = {
        "protocol_version": LOCAL_AGENT_PROTOCOL_VERSION,
        "adapter_kind": connection.adapter_kind,
        "adapter_session_id": binding.adapter_session_id,
        "resume_mode": binding.resume_mode,
        "message": request.content,
        "agent_id": binding.agent_id,
        "agent_session_id": agent_session.id,
        "run_id": run.id,
        "workspace_root": connection.workspace_root,
        "capabilities": connection.capabilities_json,
        "workspace_identity_hash": (connection.metadata_json or {}).get("workspace_identity_hash"),
    }
    if conversation_context:
        bridge_payload["conversation_context"] = conversation_context
    bridge_task = LocalAgentBridgeTask(
        organization_id=principal.organization_id,
        owner_user_id=principal.user_id,
        connection_id=connection.id,
        binding_id=binding.id,
        agent_session_id=agent_session.id,
        task_id=run.id,
        user_message_id=user_message.id,
        client_message_id=request.client_message_id,
        status="pending",
        payload_json=bridge_payload,
        created_at=now,
        updated_at=now,
    )
    session.add(bridge_task)
    agent_session.updated_at = now
    EventStore(session).append(
        task_id=run.id,
        event_type=EventType.LOCAL_AGENT_MESSAGE_QUEUED,
        payload_json={
            "connection_id": connection.id,
            "binding_id": binding.id,
            "bridge_task_id": bridge_task.id,
            "agent_session_id": agent_session.id,
            "client_message_id": request.client_message_id,
            "adapter_kind": connection.adapter_kind,
        },
        actor_type="user",
        actor_id=principal.user_id,
    )
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        return _existing_bridge_task_response(
            binding=binding,
            client_message_id=request.client_message_id,
            session=session,
            conflict=exc,
        )
    return LocalAgentSendMessageResponse(
        bridge_task_id=bridge_task.id,
        run_id=run.id,
        agent_session_id=agent_session.id,
        user_message_id=user_message.id,
        status=bridge_task.status,
    )


@router.get(
    "/local-agent/bindings/{binding_id}/tasks",
    response_model=LocalAgentBindingTaskPage,
    summary="查询本地 Agent 会话未完成任务",
)
def list_local_agent_binding_tasks(
    binding_id: str,
    session: DbSession,
    principal: Principal,
) -> LocalAgentBindingTaskPage:
    require_role(principal, {"admin", "engineer", "operator"})
    binding = session.get(LocalAgentConversationBinding, binding_id)
    if binding is None or binding.organization_id != principal.organization_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Local Agent binding not found"
        )
    connection = _owned_connection(
        connection_id=binding.connection_id,
        session=session,
        principal=principal,
        executable=False,
    )
    if "admin" not in principal.roles and connection.owner_user_id != principal.user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only owner or admin can list local Agent tasks",
        )
    rows = list(
        session.execute(
            select(LocalAgentBridgeTask)
            .where(
                LocalAgentBridgeTask.binding_id == binding.id,
                LocalAgentBridgeTask.status.in_(("pending", "leased", "running")),
            )
            .order_by(LocalAgentBridgeTask.created_at.asc(), LocalAgentBridgeTask.id.asc())
        ).scalars()
    )
    return LocalAgentBindingTaskPage(items=[_binding_task_response(row) for row in rows])


@router.get(
    "/local-agent/bridge/tasks",
    response_model=LocalAgentBridgeTaskPage,
    summary="Bridge 拉取待执行任务",
)
def pull_local_agent_bridge_tasks(
    session: DbSession,
    x_local_agent_device_token: str | None = Header(default=None),
) -> LocalAgentBridgeTaskPage:
    connection = _bridge_connection(session=session, device_token=x_local_agent_device_token)
    now = utc_now()
    tasks = list(
        session.execute(
            select(LocalAgentBridgeTask)
            .where(
                LocalAgentBridgeTask.connection_id == connection.id,
                LocalAgentBridgeTask.status == "pending",
            )
            .with_for_update(skip_locked=True)
            .order_by(LocalAgentBridgeTask.created_at.asc(), LocalAgentBridgeTask.id.asc())
            .limit(10)
        ).scalars()
    )
    for task in tasks:
        if task.status == "pending":
            task.status = "leased"
            task.leased_at = now
            task.updated_at = now
            EventStore(session).append(
                task_id=task.task_id,
                event_type=EventType.LOCAL_AGENT_TASK_LEASED,
                payload_json={
                    "connection_id": connection.id,
                    "bridge_task_id": task.id,
                    "adapter_kind": connection.adapter_kind,
                },
                actor_type="local_agent",
                actor_id=connection.id,
            )
    connection.last_seen_at = now
    connection.status = "online"
    connection.updated_at = now
    session.commit()
    return LocalAgentBridgeTaskPage(items=[_bridge_task_response(task) for task in tasks])


@router.post(
    "/local-agent/bridge/tasks/{bridge_task_id}/ack",
    response_model=LocalAgentBridgeTaskResponse,
    summary="Bridge ack 待执行任务",
)
def ack_local_agent_bridge_task(
    bridge_task_id: str,
    request: LocalAgentBridgeAckRequest,
    session: DbSession,
    x_local_agent_device_token: str | None = Header(default=None),
) -> LocalAgentBridgeTaskResponse:
    connection = _bridge_connection(session=session, device_token=x_local_agent_device_token)
    bridge_task = _owned_bridge_task(
        bridge_task_id=bridge_task_id,
        connection=connection,
        session=session,
    )
    now = utc_now()
    if bridge_task.status in {"completed", "failed", "cancelled"}:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Local Agent bridge task is already terminal",
        )
    if request.status in {"leased", "running"}:
        if bridge_task.status not in {"pending", "leased", "running"}:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Local Agent bridge task cannot be acked as running",
            )
        bridge_task.status = "running"
    else:
        bridge_task.status = "failed"
    bridge_task.acked_at = now
    bridge_task.updated_at = now
    EventStore(session).append(
        task_id=bridge_task.task_id,
        event_type=EventType.LOCAL_AGENT_TASK_ACKED,
        payload_json={
            "connection_id": connection.id,
            "bridge_task_id": bridge_task.id,
            "adapter_kind": connection.adapter_kind,
            "status": bridge_task.status,
            "error_message": request.error_message,
        },
        actor_type="local_agent",
        actor_id=connection.id,
    )
    session.commit()
    session.refresh(bridge_task)
    return _bridge_task_response(bridge_task)


@router.post(
    "/local-agent/bridge/events",
    response_model=LocalAgentBridgeEventResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Bridge 上报本地 Agent 事件",
)
def record_local_agent_bridge_event(
    request: LocalAgentBridgeEventRequest,
    session: DbSession,
    x_local_agent_device_token: str | None = Header(default=None),
) -> LocalAgentBridgeEventResponse:
    connection = _bridge_connection(session=session, device_token=x_local_agent_device_token)
    existing = session.execute(
        select(LocalAgentBridgeEventReceipt).where(
            LocalAgentBridgeEventReceipt.connection_id == connection.id,
            LocalAgentBridgeEventReceipt.event_id == request.event_id,
        )
    ).scalar_one_or_none()
    if existing is not None:
        event_sequence = None
        if existing.agent_event_id:
            agent_event = session.get(AgentEvent, existing.agent_event_id)
            event_sequence = agent_event.sequence if agent_event else None
        return LocalAgentBridgeEventResponse(
            receipt_id=existing.id,
            duplicate=True,
            event_sequence=event_sequence,
            tool_call_id=existing.tool_call_id,
        )
    bridge_task = _owned_bridge_task(
        bridge_task_id=request.bridge_task_id,
        connection=connection,
        session=session,
    )
    if bridge_task.status in {"completed", "failed", "cancelled"}:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Local Agent bridge task is already terminal",
        )
    agent_event, tool_call = _apply_bridge_event(
        connection=connection,
        bridge_task=bridge_task,
        request=request,
        session=session,
    )
    receipt = LocalAgentBridgeEventReceipt(
        organization_id=connection.organization_id,
        connection_id=connection.id,
        bridge_task_id=bridge_task.id,
        task_id=bridge_task.task_id,
        event_id=request.event_id,
        sequence=request.sequence,
        event_type=request.event_type,
        payload_json=_safe_bridge_payload(request),
        agent_event_id=agent_event.id if agent_event else None,
        tool_call_id=tool_call.id if tool_call else None,
        created_at=utc_now(),
    )
    session.add(receipt)
    session.commit()
    return LocalAgentBridgeEventResponse(
        receipt_id=receipt.id,
        duplicate=False,
        event_sequence=agent_event.sequence if agent_event else None,
        tool_call_id=tool_call.id if tool_call else None,
    )


@router.post(
    "/local-agent/bridge/tool-requests",
    response_model=LocalAgentToolDecisionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Bridge 申请本地工具执行授权",
)
def create_local_agent_tool_request(
    request: LocalAgentToolRequestCreateRequest,
    session: DbSession,
    x_local_agent_device_token: str | None = Header(default=None),
) -> LocalAgentToolDecisionResponse:
    connection = _bridge_connection(session=session, device_token=x_local_agent_device_token)
    _ensure_host_tool_protocol_allowed(connection)
    existing = session.execute(
        select(LocalAgentToolRequest).where(
            LocalAgentToolRequest.connection_id == connection.id,
            LocalAgentToolRequest.tool_request_id == request.tool_request_id,
        )
    ).scalar_one_or_none()
    if existing is not None:
        return _local_tool_decision_response(existing, session=session)
    bridge_task = _owned_bridge_task(
        bridge_task_id=request.bridge_task_id,
        connection=connection,
        session=session,
    )
    if bridge_task.status in {"completed", "failed", "cancelled"}:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Local Agent bridge task is already terminal",
        )
    classification = _classify_local_tool_request(request)
    resolved_tool = None
    capability_snapshot = {
        "source": "local_agent_bridge",
        "server_execution": False,
        "connection_id": connection.id,
        "bridge_task_id": bridge_task.id,
        "adapter_kind": connection.adapter_kind,
        "workspace_root": _redact_path(connection.workspace_root),
        "execution_target": request.execution_target,
        "server_risk": classification["risk_level"],
        "bridge_risk": request.risk_level,
        "permission_mode": request.permission_mode,
    }
    capability_tool_name = _capability_tool_name(request.tool_name)
    if (
        classification["decision"] != "denied"
        and _local_tool_requires_capability(request.tool_name)
    ):
        try:
            resolved_tool = CapabilityRegistry(
                session,
                connection.organization_id,
            ).resolve_tool(
                agent_id=connection.agent_id,
                tool_name=capability_tool_name,
                task_id=bridge_task.task_id,
                source="local_agent_bridge",
            )
        except CapabilityResolutionError as exc:
            classification = {
                **classification,
                "decision": "denied",
                "risk_level": "unknown",
                "reason": f"local tool capability is not attached: {exc}",
                "capability_attached": False,
            }
            capability_snapshot["capability_attached"] = False
        else:
            capability_snapshot = {
                **capability_snapshot,
                **resolved_tool.snapshot_json,
                "source": "local_agent_bridge",
                "server_execution": False,
                "connection_id": connection.id,
                "bridge_task_id": bridge_task.id,
                "adapter_kind": connection.adapter_kind,
                "workspace_root": _redact_path(connection.workspace_root),
                "execution_target": request.execution_target,
                "local_tool_name": request.tool_name,
                "capability_tool_name": capability_tool_name,
                "server_risk": classification["risk_level"],
                "bridge_risk": request.risk_level,
                "permission_mode": request.permission_mode,
                "capability_attached": True,
            }
            classification = {
                **classification,
                "capability_attached": True,
                "capability_id": resolved_tool.capability.id,
                "capability_version_id": resolved_tool.version.id,
                "capability_type": resolved_tool.version.type,
            }
    now = utc_now()
    safe_input = _redact_mapping(request.input_json)
    safe_preview = (
        _redact_mapping(request.pending_change_preview)
        if isinstance(request.pending_change_preview, dict)
        else {}
    )
    safe_metadata = _safe_metadata(request.metadata)
    executable_input_sha256 = _executable_input_sha256(safe_input)
    initial_status = {
        "allowed": "APPROVED",
        "approval_required": "PENDING_APPROVAL",
        "denied": "DENIED",
    }[classification["decision"]]
    tool_call = ToolCall(
        task_id=bridge_task.task_id,
        agent_run_id=None,
        tool_name=request.tool_name,
        status=initial_status,
        risk_level=classification["risk_level"],
        capability_id=resolved_tool.capability.id if resolved_tool is not None else None,
        capability_version_id=resolved_tool.version.id if resolved_tool is not None else None,
        capability_type=resolved_tool.version.type if resolved_tool is not None else None,
        capability_content_sha256=resolved_tool.version.content_sha256
        if resolved_tool is not None
        else None,
        capability_config_sha256=resolved_tool.version.config_sha256
        if resolved_tool is not None
        else None,
        capability_schema_version=resolved_tool.version.schema_version
        if resolved_tool is not None
        else None,
        capability_snapshot_json=capability_snapshot,
        requires_sandbox=False,
        duration_ms=0,
        input_json=safe_input,
        output_json={},
        error_message=classification["reason"] if classification["decision"] == "denied" else None,
        created_at=now,
    )
    session.add(tool_call)
    session.flush()
    approval: ToolApproval | None = None
    expires_at = now + timedelta(minutes=LOCAL_AGENT_TOOL_DECISION_TTL_MINUTES)
    decision_json = {
        "decision": classification["decision"],
        "reason": classification["reason"],
        "server_execution": False,
        "auto_allowed": classification["decision"] == "allowed",
        "input_json": safe_input,
        "executable_input_sha256": executable_input_sha256,
        "metadata": safe_metadata,
        "pending_change_preview": safe_preview,
        "cwd": _redact_path(request.cwd),
        "expires_at": expires_at.isoformat(),
    }
    local_status = classification["decision"]
    if classification["decision"] == "approval_required":
        approval = ToolApproval(
            task_id=bridge_task.task_id,
            tool_call_id=tool_call.id,
            organization_id=connection.organization_id,
            requested_by=connection.owner_user_id,
            status="PENDING",
            risk_level=classification["risk_level"],
            reason=classification["reason"],
            request_json={
                "source": "local_agent_bridge",
                "server_execution": False,
                "tool_request_id": request.tool_request_id,
                "bridge_task_id": bridge_task.id,
                "connection_id": connection.id,
                "tool_name": request.tool_name,
                "input_json": safe_input,
                "executable_input_sha256": executable_input_sha256,
                "metadata": safe_metadata,
                "pending_change_preview": safe_preview,
                "cwd": _redact_path(request.cwd),
                "policy_decision": classification,
            },
            decision_json={},
            created_at=now,
        )
        session.add(approval)
        session.flush()
        decision_json["approval_id"] = approval.id
        run = session.get(Task, bridge_task.task_id)
        if run is not None:
            run.status = "WAITING_APPROVAL"
            run.updated_at = now
    elif classification["decision"] == "denied":
        tool_call.output_json = {"denied": True, "reason": classification["reason"]}
    local_request = LocalAgentToolRequest(
        organization_id=connection.organization_id,
        connection_id=connection.id,
        binding_id=bridge_task.binding_id,
        bridge_task_id=bridge_task.id,
        task_id=bridge_task.task_id,
        tool_request_id=request.tool_request_id,
        tool_call_id=tool_call.id,
        approval_id=approval.id if approval is not None else None,
        tool_name=request.tool_name,
        execution_target=request.execution_target,
        risk_level=classification["risk_level"],
        permission_mode=request.permission_mode,
        status=local_status,
        input_json=safe_input,
        policy_decision_json=classification,
        decision_json=decision_json,
        result_json={},
        decision_expires_at=expires_at
        if classification["decision"] in {"allowed", "approval_required"}
        else None,
        created_at=now,
        updated_at=now,
    )
    session.add(local_request)
    session.flush()
    if safe_preview:
        _record_pending_change_preview(
            local_request=local_request,
            approval=approval,
            request=request,
            preview=safe_preview,
            status="approval_required"
            if classification["decision"] == "approval_required"
            else classification["decision"],
            session=session,
        )
    _append_local_tool_request_events(
        connection=connection,
        bridge_task=bridge_task,
        local_request=local_request,
        approval=approval,
        classification=classification,
        session=session,
    )
    session.commit()
    session.refresh(local_request)
    return _local_tool_decision_response(local_request, session=session)


@router.get(
    "/local-agent/bridge/tool-requests/{tool_request_id}/decision",
    response_model=LocalAgentToolDecisionResponse,
    summary="Bridge 查询本地工具授权决定",
)
def get_local_agent_tool_decision(
    tool_request_id: str,
    session: DbSession,
    x_local_agent_device_token: str | None = Header(default=None),
) -> LocalAgentToolDecisionResponse:
    connection = _bridge_connection(session=session, device_token=x_local_agent_device_token)
    _ensure_host_tool_protocol_allowed(connection)
    local_request = _owned_local_tool_request(
        tool_request_id=tool_request_id,
        connection=connection,
        session=session,
    )
    _expire_local_tool_request_if_needed(local_request, session=session)
    session.commit()
    session.refresh(local_request)
    return _local_tool_decision_response(local_request, session=session)


@router.post(
    "/local-agent/bridge/tool-requests/{tool_request_id}/pending-change-refresh",
    response_model=LocalAgentToolDecisionResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Bridge 用批准后的输入刷新 pending change 预览",
)
def refresh_local_agent_pending_change(
    tool_request_id: str,
    request: LocalAgentPendingChangeRefreshRequest,
    session: DbSession,
    x_local_agent_device_token: str | None = Header(default=None),
) -> LocalAgentToolDecisionResponse:
    connection = _bridge_connection(session=session, device_token=x_local_agent_device_token)
    _ensure_host_tool_protocol_allowed(connection)
    local_request = _owned_local_tool_request(
        tool_request_id=tool_request_id,
        connection=connection,
        session=session,
    )
    _require_executable_local_tool_request(
        local_request,
        session=session,
        detail="Local Agent pending change is not authorized",
    )
    if local_request.tool_name not in LOCAL_AGENT_PENDING_CHANGE_TOOLS:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Local Agent pending change refresh is only valid for write/apply_patch tools",
        )
    approved_input = _approved_input_for_request(local_request)
    if request.input_json != approved_input:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Local Agent pending change refresh must use the approved executable input",
        )
    preview = _validated_pending_change_refresh_preview(
        local_request=local_request,
        refresh=request,
    )
    pending_change = session.execute(
        select(LocalAgentPendingChange)
        .where(
            LocalAgentPendingChange.local_agent_tool_request_id == local_request.id,
            LocalAgentPendingChange.status.in_(LOCAL_AGENT_PENDING_CHANGE_ACTIVE_STATUSES),
        )
        .order_by(LocalAgentPendingChange.updated_at.desc(), LocalAgentPendingChange.id.desc())
    ).scalar_one_or_none()
    if pending_change is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Local Agent pending change refresh requires an active preview",
        )
    now = utc_now()
    pending_change.change_id = str(preview["change_id"])
    pending_change.target_paths_json = [str(path) for path in request.target_paths]
    pending_change.diff_sha256 = str(preview["diff_sha256"])
    pending_change.preview_json = preview
    pending_change.status = (
        "approved" if local_request.status == "approved" else local_request.status
    )
    pending_change.command_id = None
    pending_change.committed_at = None
    pending_change.denied_at = None
    pending_change.error_message = None
    pending_change.updated_at = now
    decision_json = (
        local_request.decision_json if isinstance(local_request.decision_json, dict) else {}
    )
    local_request.decision_json = {
        **decision_json,
        "input_json": approved_input,
        "executable_input_sha256": _executable_input_sha256(approved_input),
        "pending_change_preview": preview,
    }
    local_request.updated_at = now
    approval = (
        session.get(ToolApproval, local_request.approval_id)
        if local_request.approval_id
        else None
    )
    if approval is not None:
        approval_request_json = (
            approval.request_json if isinstance(approval.request_json, dict) else {}
        )
        approval.request_json = {
            **approval_request_json,
            "input_json": approved_input,
            "executable_input_sha256": _executable_input_sha256(approved_input),
            "pending_change_preview": preview,
        }
    EventStore(session).append(
        task_id=local_request.task_id,
        event_type=EventType.LOCAL_AGENT_PENDING_CHANGE_PREVIEWED,
        payload_json={
            "source": "local_agent_bridge",
            "tool_request_id": local_request.tool_request_id,
            "change_id": pending_change.change_id,
            "target_paths": pending_change.target_paths_json,
            "diff_sha256": pending_change.diff_sha256,
            "status": pending_change.status,
            "refreshed": True,
        },
        actor_type="local_agent",
        actor_id=connection.id,
    )
    session.commit()
    session.refresh(local_request)
    return _local_tool_decision_response(local_request, session=session)


@router.get(
    "/local-agent/bridge/tool-requests/pending",
    response_model=LocalAgentPendingToolRequestPage,
    summary="Bridge 查询服务端未决本地工具请求",
)
def list_pending_local_agent_tool_requests(
    session: DbSession,
    x_local_agent_device_token: str | None = Header(default=None),
) -> LocalAgentPendingToolRequestPage:
    connection = _bridge_connection(session=session, device_token=x_local_agent_device_token)
    _ensure_host_tool_protocol_allowed(connection)
    rows = list(
        session.execute(
            select(LocalAgentToolRequest)
            .where(
                LocalAgentToolRequest.connection_id == connection.id,
                LocalAgentToolRequest.status.in_(("approval_required", "approved", "allowed")),
            )
            .order_by(
                LocalAgentToolRequest.created_at.asc(),
                LocalAgentToolRequest.id.asc(),
            )
        ).scalars()
    )
    for row in rows:
        _expire_local_tool_request_if_needed(row, session=session)
    session.commit()
    live_rows = [row for row in rows if row.status in {"approval_required", "approved", "allowed"}]
    return LocalAgentPendingToolRequestPage(
        items=[_local_tool_decision_response(row, session=session) for row in live_rows]
    )


@router.post(
    "/local-agent/bridge/tool-requests/{tool_request_id}/result",
    response_model=LocalAgentToolDecisionResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Bridge 上报已授权本地工具结果",
)
def record_local_agent_tool_result(
    tool_request_id: str,
    request: LocalAgentToolResultRequest,
    session: DbSession,
    x_local_agent_device_token: str | None = Header(default=None),
) -> LocalAgentToolDecisionResponse:
    connection = _bridge_connection(session=session, device_token=x_local_agent_device_token)
    _ensure_host_tool_protocol_allowed(connection)
    existing_receipt = session.execute(
        select(LocalAgentBridgeEventReceipt).where(
            LocalAgentBridgeEventReceipt.connection_id == connection.id,
            LocalAgentBridgeEventReceipt.event_id == request.event_id,
        )
    ).scalar_one_or_none()
    local_request = _owned_local_tool_request(
        tool_request_id=tool_request_id,
        connection=connection,
        session=session,
    )
    if existing_receipt is not None:
        return _local_tool_decision_response(local_request, session=session)
    _require_executable_local_tool_request(
        local_request,
        session=session,
        detail="Local Agent tool request is not executable",
    )
    now = utc_now()
    result_status = _normalized_tool_status(request.status)
    terminal_status = {
        "SUCCESS": "succeeded",
        "FAILED": "failed",
        "TIMEOUT": "failed",
        "DENIED": "denied",
        "CANCELLED": "cancelled",
    }.get(request.status, "failed")
    tool_call = session.get(ToolCall, local_request.tool_call_id)
    if tool_call is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="ToolCall not found")
    command = _validated_result_command(
        local_request=local_request,
        command_id=request.command_id,
        result_status=request.status,
        session=session,
    )
    try:
        pending_change = _validate_pending_change_result(
            local_request=local_request,
            request=request,
            session=session,
        )
    except HTTPException:
        session.commit()
        raise
    result_change_id = pending_change.change_id if pending_change is not None else request.change_id
    safe_output = _redact_mapping(request.output_json)
    tool_call.status = result_status
    tool_call.output_json = safe_output
    tool_call.duration_ms = request.duration_ms
    tool_call.error_message = _bounded_text(request.error_message)
    local_request.status = terminal_status
    local_request.result_json = {
        "event_id": request.event_id,
        "status": request.status,
        "output_json": safe_output,
        "duration_ms": request.duration_ms,
        "command_id": command.command_id if command is not None else None,
        "change_id": result_change_id,
        "diff_sha256": request.diff_sha256,
        "metadata": _redact_mapping(request.metadata),
    }
    local_request.completed_at = now
    local_request.updated_at = now
    event_type = {
        "SUCCESS": EventType.TOOL_RESULT_RECEIVED,
        "FAILED": EventType.TOOL_FAILED,
        "TIMEOUT": EventType.TOOL_TIMEOUT,
        "DENIED": EventType.TOOL_DENIED_BY_POLICY,
        "CANCELLED": EventType.LOCAL_AGENT_COMMAND_CANCELLED,
    }.get(request.status, EventType.TOOL_FAILED)
    agent_event = EventStore(session).append(
        task_id=local_request.task_id,
        event_type=event_type,
        payload_json={
            "source": "local_agent_bridge",
            "connection_id": connection.id,
            "bridge_task_id": local_request.bridge_task_id,
            "tool_request_id": local_request.tool_request_id,
            "tool_call_id": tool_call.id,
            "tool_name": tool_call.tool_name,
            "status": tool_call.status,
            "server_execution": False,
            "command_id": command.command_id if command is not None else None,
            "change_id": result_change_id,
        },
        actor_type="local_agent",
        actor_id=connection.id,
    )
    session.add(
        LocalAgentBridgeEventReceipt(
            organization_id=connection.organization_id,
            connection_id=connection.id,
            bridge_task_id=local_request.bridge_task_id,
            task_id=local_request.task_id,
            event_id=request.event_id,
            sequence=None,
            event_type="tool_result",
            payload_json={
                "tool_request_id": local_request.tool_request_id,
                "status": request.status,
                "metadata": _redact_mapping(request.metadata),
            },
            agent_event_id=agent_event.id,
            tool_call_id=tool_call.id,
            created_at=now,
        )
    )
    session.commit()
    session.refresh(local_request)
    return _local_tool_decision_response(local_request, session=session)


@router.post(
    "/local-agent/bridge/commands/{command_id}/events",
    response_model=LocalAgentCommandResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Bridge 上报本地命令生命周期",
)
def record_local_agent_command_event(
    command_id: str,
    request: LocalAgentCommandEventRequest,
    session: DbSession,
    x_local_agent_device_token: str | None = Header(default=None),
) -> LocalAgentCommandResponse:
    connection = _bridge_connection(session=session, device_token=x_local_agent_device_token)
    _ensure_host_tool_protocol_allowed(connection)
    local_request = _owned_local_tool_request(
        tool_request_id=request.tool_request_id,
        connection=connection,
        session=session,
    )
    _require_executable_local_tool_request(
        local_request,
        session=session,
        detail="Local Agent command is not authorized",
    )
    command = session.execute(
        select(LocalAgentCommand).where(
            LocalAgentCommand.connection_id == connection.id,
            LocalAgentCommand.command_id == command_id,
        )
    ).scalar_one_or_none()
    now = utc_now()
    if command is not None and command.local_agent_tool_request_id != local_request.id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Local Agent command does not belong to tool request",
        )
    if command is None:
        if request.event_type != "started":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Local Agent command must start before output or terminal events",
            )
        if not request.command:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Local Agent command start requires command text",
            )
        expected_command = _approved_command_for_request(local_request)
        _validate_command_start_payload(
            local_request=local_request,
            request=request,
            expected_command=expected_command,
        )
        command = LocalAgentCommand(
            organization_id=connection.organization_id,
            connection_id=connection.id,
            binding_id=local_request.binding_id,
            bridge_task_id=local_request.bridge_task_id,
            task_id=local_request.task_id,
            local_agent_tool_request_id=local_request.id,
            tool_request_id=local_request.tool_request_id,
            command_id=command_id,
            tool_name=local_request.tool_name,
            command=expected_command,
            status="pending",
            retry_of_command_id=request.retry_of_command_id,
            output_summary_json={},
            event_receipts_json={},
            created_at=now,
            updated_at=now,
        )
        session.add(command)
        session.flush()
    else:
        _validate_existing_command_against_request(
            local_request=local_request,
            command=command,
            request=request,
        )
        if request.event_type == "started":
            expected_command = _approved_command_for_request(local_request)
            _validate_command_start_payload(
                local_request=local_request,
                request=request,
                expected_command=expected_command,
            )
    receipts = command.event_receipts_json if isinstance(command.event_receipts_json, dict) else {}
    if request.event_id in receipts:
        return _local_command_response(command)
    if command.status in LOCAL_AGENT_COMMAND_TERMINAL_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Local Agent command is already terminal",
        )
    if request.event_type == "started" and command.started_at is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Local Agent command already started",
        )
    if request.event_type in {"output", "finished", "timeout", "cancelled"} and (
        command.status != "running" or command.started_at is None
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Local Agent command must be running before output or terminal events",
        )
    receipts[request.event_id] = request.event_type
    command.event_receipts_json = receipts
    event_type = EventType.LOCAL_AGENT_COMMAND_OUTPUT
    if request.event_type == "started":
        command.status = "running"
        command.started_at = command.started_at or now
        local_request.status = "running"
        local_request.started_at = local_request.started_at or now
        event_type = EventType.LOCAL_AGENT_COMMAND_STARTED
    elif request.event_type == "output":
        command.status = "running"
        summary = (
            command.output_summary_json if isinstance(command.output_summary_json, dict) else {}
        )
        summary["stdout_tail"] = _bounded_text(request.stdout, limit=2000)
        summary["stderr_tail"] = _bounded_text(request.stderr, limit=2000)
        command.output_summary_json = summary
    else:
        command.status = {
            "finished": request.status or "success",
            "timeout": "timeout",
            "cancelled": "cancelled",
        }.get(request.event_type, "failed")
        if command.status not in LOCAL_AGENT_COMMAND_TERMINAL_STATUSES:
            command.status = "failed"
        command.finished_at = now
        command.exit_code = request.exit_code
        command.duration_ms = request.duration_ms
        command.error_message = _bounded_text(request.error_message)
        event_type = (
            EventType.LOCAL_AGENT_COMMAND_CANCELLED
            if command.status == "cancelled"
            else EventType.LOCAL_AGENT_COMMAND_FINISHED
        )
    command.updated_at = now
    local_request.updated_at = now
    EventStore(session).append(
        task_id=local_request.task_id,
        event_type=event_type,
        payload_json={
            "source": "local_agent_bridge",
            "connection_id": connection.id,
            "bridge_task_id": local_request.bridge_task_id,
            "tool_request_id": local_request.tool_request_id,
            "command_id": command.command_id,
            "status": command.status,
            "stdout_tail": _bounded_text(request.stdout, limit=2000),
            "stderr_tail": _bounded_text(request.stderr, limit=2000),
            "exit_code": request.exit_code,
        },
        actor_type="local_agent",
        actor_id=connection.id,
    )
    session.commit()
    session.refresh(command)
    return _local_command_response(command)


@router.get(
    "/local-agent/bridge/commands/{command_id}",
    response_model=LocalAgentCommandResponse,
    summary="Bridge 查询本地命令状态",
)
def get_local_agent_command_status(
    command_id: str,
    session: DbSession,
    x_local_agent_device_token: str | None = Header(default=None),
) -> LocalAgentCommandResponse:
    connection = _bridge_connection(session=session, device_token=x_local_agent_device_token)
    _ensure_host_tool_protocol_allowed(connection)
    command = _owned_local_agent_command(
        command_id=command_id,
        connection=connection,
        session=session,
    )
    return _local_command_response(command)


@router.post(
    "/local-agent/bridge/commands/{command_id}/cancel-ack",
    response_model=LocalAgentCommandResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Bridge 确认本地命令取消",
)
def ack_local_agent_command_cancel(
    command_id: str,
    request: LocalAgentCommandCancelAckRequest,
    session: DbSession,
    x_local_agent_device_token: str | None = Header(default=None),
) -> LocalAgentCommandResponse:
    connection = _bridge_connection(session=session, device_token=x_local_agent_device_token)
    _ensure_host_tool_protocol_allowed(connection)
    command = _owned_local_agent_command(
        command_id=command_id,
        connection=connection,
        session=session,
    )
    if command.status in LOCAL_AGENT_COMMAND_TERMINAL_STATUSES:
        if command.cancel_requested_at is not None and command.status == request.status:
            return _local_command_response(command)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Local Agent command is already terminal",
        )
    if command.cancel_requested_at is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Local Agent command cancellation was not requested",
        )
    local_request = session.get(LocalAgentToolRequest, command.local_agent_tool_request_id)
    if local_request is None or local_request.connection_id != connection.id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Local Agent command parent request is invalid",
        )
    now = utc_now()
    command.status = request.status
    command.finished_at = now
    command.error_message = _bounded_text(request.error_message or request.status)
    command.updated_at = now
    local_request.status = "cancelled" if request.status == "cancelled" else "failed"
    local_request.completed_at = now
    local_request.updated_at = now
    tool_call = session.get(ToolCall, local_request.tool_call_id)
    if tool_call is not None:
        tool_call.status = "CANCELLED" if request.status == "cancelled" else "FAILED"
        tool_call.error_message = command.error_message
        tool_call.output_json = {
            "cancelled": request.status == "cancelled",
            "command_id": command.command_id,
            "error": command.error_message,
        }
    EventStore(session).append(
        task_id=local_request.task_id,
        event_type=EventType.LOCAL_AGENT_COMMAND_CANCELLED,
        payload_json={
            "source": "local_agent_bridge",
            "connection_id": connection.id,
            "bridge_task_id": local_request.bridge_task_id,
            "tool_request_id": local_request.tool_request_id,
            "command_id": command.command_id,
            "status": command.status,
        },
        actor_type="local_agent",
        actor_id=connection.id,
    )
    session.commit()
    session.refresh(command)
    return _local_command_response(command)


@router.post(
    "/local-agent/bindings/{binding_id}/commands/{command_id}/cancel",
    response_model=LocalAgentCommandResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="请求取消本地命令",
)
def cancel_local_agent_command(
    binding_id: str,
    command_id: str,
    session: DbSession,
    principal: Principal,
) -> LocalAgentCommandResponse:
    require_role(principal, {"admin", "engineer"})
    binding = session.get(LocalAgentConversationBinding, binding_id)
    if binding is None or binding.organization_id != principal.organization_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Local Agent binding not found",
        )
    if binding.owner_user_id != principal.user_id and "admin" not in principal.roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only owner or admin can cancel",
        )
    connection = session.get(LocalAgentConnection, binding.connection_id)
    if connection is not None:
        _ensure_host_tool_protocol_allowed(connection)
    command = session.execute(
        select(LocalAgentCommand).where(
            LocalAgentCommand.binding_id == binding.id,
            LocalAgentCommand.command_id == command_id,
        )
    ).scalar_one_or_none()
    if command is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Local Agent command not found",
        )
    if command.status in LOCAL_AGENT_COMMAND_TERMINAL_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Local Agent command is terminal",
        )
    command.cancel_requested_at = utc_now()
    command.updated_at = utc_now()
    session.commit()
    session.refresh(command)
    return _local_command_response(command)


@router.post(
    "/local-agent/bindings/{binding_id}/commands/{command_id}/retry",
    response_model=LocalAgentCommandResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="请求重试本地命令",
)
def retry_local_agent_command(
    binding_id: str,
    command_id: str,
    session: DbSession,
    principal: Principal,
) -> LocalAgentCommandResponse:
    require_role(principal, {"admin", "engineer"})
    binding = session.get(LocalAgentConversationBinding, binding_id)
    if binding is None or binding.organization_id != principal.organization_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Local Agent binding not found",
        )
    if binding.owner_user_id != principal.user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only owner can retry local commands",
        )
    connection = session.get(LocalAgentConnection, binding.connection_id)
    if connection is not None:
        _ensure_host_tool_protocol_allowed(connection)
    command = session.execute(
        select(LocalAgentCommand).where(
            LocalAgentCommand.binding_id == binding.id,
            LocalAgentCommand.command_id == command_id,
        )
    ).scalar_one_or_none()
    if command is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Local Agent command not found",
        )
    if command.status not in {"failed", "timeout", "cancelled"}:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Local Agent command retry requires failed, timeout, or cancelled status",
        )
    local_request = session.get(LocalAgentToolRequest, command.local_agent_tool_request_id)
    if local_request is None or local_request.binding_id != binding.id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Local Agent command parent request is invalid",
        )
    if local_request.tool_name not in LOCAL_AGENT_COMMAND_TOOLS:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Local Agent command retry is only valid for command tools",
        )
    if local_request.status in {"denied", "expired", "succeeded"}:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Local Agent command parent request is not retryable",
        )
    terminal_status = "cancelled" if command.status == "cancelled" else "failed"
    tool_status = {
        "cancelled": "CANCELLED",
        "timeout": "TIMEOUT",
        "failed": "FAILED",
    }[command.status]
    event_type = {
        "cancelled": EventType.LOCAL_AGENT_COMMAND_CANCELLED,
        "timeout": EventType.TOOL_TIMEOUT,
        "failed": EventType.TOOL_FAILED,
    }[command.status]
    _terminalize_local_tool_request(
        local_request,
        session=session,
        terminal_status=terminal_status,
        tool_status=tool_status,
        reason="local command retry requested",
        event_type=event_type,
        actor_type="user",
        actor_id=principal.user_id,
    )
    retry_request, retry_command = _create_retry_local_tool_request(
        original_request=local_request,
        original_command=command,
        session=session,
        actor_id=principal.user_id,
    )
    EventStore(session).append(
        task_id=retry_request.task_id,
        event_type=EventType.LOCAL_AGENT_TOOL_DECISION_READY,
        payload_json={
            "source": "local_agent_bridge",
            "tool_request_id": retry_request.tool_request_id,
            "tool_call_id": retry_request.tool_call_id,
            "command_id": retry_command.command_id,
            "retry_of_command_id": command.command_id,
            "retry_of_tool_request_id": local_request.tool_request_id,
            "decision": retry_request.status,
            "server_execution": False,
        },
        actor_type="user",
        actor_id=principal.user_id,
    )
    session.commit()
    session.refresh(retry_command)
    return _local_command_response(retry_command)


def _resolve_or_create_agent_session(
    *,
    connection: LocalAgentConnection,
    request: LocalAgentConversationBindRequest,
    session: Session,
    principal: Principal,
) -> AgentSession:
    if request.agent_session_id:
        agent_session = session.get(AgentSession, request.agent_session_id)
        if (
            agent_session is None
            or agent_session.organization_id != principal.organization_id
            or agent_session.agent_id != connection.agent_id
        ):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Agent Session not found"
            )
        if agent_session.created_by != principal.user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only the session owner can bind local Agent execution",
            )
        return agent_session
    now = utc_now()
    agent_session = AgentSession(
        organization_id=principal.organization_id,
        agent_id=connection.agent_id,
        created_by=principal.user_id,
        title=request.title or f"{connection.display_name} local session",
        status="ACTIVE",
        created_at=now,
        updated_at=now,
    )
    session.add(agent_session)
    session.flush()
    return agent_session


def _owned_bridge_task(
    *,
    bridge_task_id: str,
    connection: LocalAgentConnection,
    session: Session,
) -> LocalAgentBridgeTask:
    bridge_task = session.get(LocalAgentBridgeTask, bridge_task_id)
    if bridge_task is None or bridge_task.connection_id != connection.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Local Agent bridge task not found"
        )
    return bridge_task


def _owned_local_tool_request(
    *,
    tool_request_id: str,
    connection: LocalAgentConnection,
    session: Session,
) -> LocalAgentToolRequest:
    local_request = session.execute(
        select(LocalAgentToolRequest).where(
            LocalAgentToolRequest.connection_id == connection.id,
            LocalAgentToolRequest.tool_request_id == tool_request_id,
        )
    ).scalar_one_or_none()
    if local_request is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Local Agent tool request not found",
        )
    return local_request


def _owned_local_agent_command(
    *,
    command_id: str,
    connection: LocalAgentConnection,
    session: Session,
) -> LocalAgentCommand:
    command = session.execute(
        select(LocalAgentCommand).where(
            LocalAgentCommand.connection_id == connection.id,
            LocalAgentCommand.command_id == command_id,
        )
    ).scalar_one_or_none()
    if command is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Local Agent command not found",
        )
    return command


def _terminalize_local_tool_request(
    local_request: LocalAgentToolRequest,
    *,
    session: Session,
    terminal_status: str,
    tool_status: str,
    reason: str,
    event_type: EventType,
    actor_type: str,
    actor_id: str | None,
) -> bool:
    if local_request.status in LOCAL_AGENT_TOOL_TERMINAL_STATUSES:
        return False
    now = utc_now()
    safe_reason = _bounded_text(reason)
    local_request.status = terminal_status
    local_request.completed_at = local_request.completed_at or now
    local_request.updated_at = now
    decision_json = (
        local_request.decision_json if isinstance(local_request.decision_json, dict) else {}
    )
    local_request.decision_json = {
        **decision_json,
        "terminal_status": terminal_status,
        "terminal_reason": safe_reason,
        "terminalized_at": now.isoformat(),
        "server_execution": False,
    }
    local_request.result_json = {
        "status": tool_status,
        "reason": safe_reason,
        "server_execution": False,
    }
    tool_call = session.get(ToolCall, local_request.tool_call_id)
    if tool_call is not None and tool_call.status not in {
        "SUCCESS",
        "FAILED",
        "TIMEOUT",
        "DENIED",
        "CANCELLED",
    }:
        tool_call.status = tool_status
        tool_call.error_message = safe_reason
        tool_call.output_json = {
            "status": tool_status,
            "reason": safe_reason,
            "server_execution": False,
            "tool_request_id": local_request.tool_request_id,
        }
    approval = (
        session.get(ToolApproval, local_request.approval_id)
        if local_request.approval_id
        else None
    )
    if approval is not None and approval.status == "PENDING":
        approval.status = "EXPIRED" if terminal_status == "expired" else "DENIED"
        approval.decided_by = actor_id
        approval.decided_at = now
        approval.decision_json = {
            "decision": approval.status,
            "reason": safe_reason,
            "server_execution": False,
        }
    pending_changes = list(
        session.execute(
            select(LocalAgentPendingChange).where(
                LocalAgentPendingChange.local_agent_tool_request_id == local_request.id,
                LocalAgentPendingChange.status.in_(LOCAL_AGENT_PENDING_CHANGE_ACTIVE_STATUSES),
            )
        ).scalars()
    )
    for change in pending_changes:
        if terminal_status == "failed":
            change.status = "failed"
            change.error_message = safe_reason
        else:
            change.status = "denied"
            change.denied_at = now
            change.error_message = safe_reason if terminal_status == "expired" else None
        change.updated_at = now
    active_commands = list(
        session.execute(
            select(LocalAgentCommand).where(
                LocalAgentCommand.local_agent_tool_request_id == local_request.id,
                LocalAgentCommand.status.in_(LOCAL_AGENT_COMMAND_ACTIVE_STATUSES),
            )
        ).scalars()
    )
    for command in active_commands:
        if terminal_status == "cancelled":
            command.status = "cancelled"
        elif tool_status == "TIMEOUT":
            command.status = "timeout"
        else:
            command.status = "failed"
        command.finished_at = command.finished_at or now
        command.error_message = safe_reason
        command.updated_at = now
    _refresh_waiting_local_task(
        task_id=local_request.task_id,
        session=session,
        now=now,
    )
    EventStore(session).append(
        task_id=local_request.task_id,
        event_type=event_type,
        payload_json={
            "source": "local_agent_bridge",
            "connection_id": local_request.connection_id,
            "bridge_task_id": local_request.bridge_task_id,
            "tool_request_id": local_request.tool_request_id,
            "tool_call_id": local_request.tool_call_id,
            "tool_name": local_request.tool_name,
            "status": tool_status,
            "terminal_status": terminal_status,
            "reason": safe_reason,
            "server_execution": False,
        },
        actor_type=actor_type,
        actor_id=actor_id,
    )
    return True


def _refresh_waiting_local_task(
    *,
    task_id: str,
    session: Session,
    now: datetime,
) -> None:
    task = session.get(Task, task_id)
    if task is None or task.status != "WAITING_APPROVAL":
        return
    pending_approvals = session.execute(
        select(func.count(ToolApproval.id)).where(
            ToolApproval.task_id == task.id,
            ToolApproval.status == "PENDING",
        )
    ).scalar_one()
    if pending_approvals:
        return
    task.status = "RUNNING"
    task.completed_at = None
    task.updated_at = now


def _cancel_local_agent_bridge_task(
    *,
    bridge_task: LocalAgentBridgeTask,
    session: Session,
    reason: str,
    actor_type: str,
    actor_id: str | None,
) -> bool:
    if bridge_task.status in {"completed", "failed", "cancelled"}:
        return False
    now = utc_now()
    safe_reason = _bounded_text(reason)
    bridge_task.status = "cancelled"
    bridge_task.completed_at = bridge_task.completed_at or now
    bridge_task.updated_at = now
    run = session.get(Task, bridge_task.task_id)
    if run is not None and run.status not in {"COMPLETED", "FAILED", "CANCELLED"}:
        run.status = "CANCELLED"
        run.completed_at = run.completed_at or now
        run.updated_at = now
    EventStore(session).append(
        task_id=bridge_task.task_id,
        event_type=EventType.TASK_CANCELLED,
        payload_json={
            "source": "local_agent_bridge",
            "connection_id": bridge_task.connection_id,
            "bridge_task_id": bridge_task.id,
            "reason": safe_reason,
        },
        actor_type=actor_type,
        actor_id=actor_id,
    )
    return True


def _retry_identifier(prefix: str) -> str:
    suffix = secrets.token_hex(4)
    return f"{prefix[:120]}:retry:{suffix}"


def _create_retry_local_tool_request(
    *,
    original_request: LocalAgentToolRequest,
    original_command: LocalAgentCommand,
    session: Session,
    actor_id: str | None,
) -> tuple[LocalAgentToolRequest, LocalAgentCommand]:
    original_tool_call = session.get(ToolCall, original_request.tool_call_id)
    if original_tool_call is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="ToolCall not found")
    now = utc_now()
    expires_at = now + timedelta(minutes=LOCAL_AGENT_TOOL_DECISION_TTL_MINUTES)
    retry_tool_request_id = _retry_identifier(original_request.tool_request_id)
    retry_command_id = _retry_identifier(original_command.command_id)
    retry_input = _approved_input_for_request(original_request)
    retry_input_sha256 = _executable_input_sha256(retry_input)
    original_snapshot = (
        original_tool_call.capability_snapshot_json
        if isinstance(original_tool_call.capability_snapshot_json, dict)
        else {}
    )
    tool_call = ToolCall(
        task_id=original_request.task_id,
        agent_run_id=original_tool_call.agent_run_id,
        tool_name=original_request.tool_name,
        status="APPROVED",
        risk_level=original_request.risk_level,
        capability_id=original_tool_call.capability_id,
        capability_version_id=original_tool_call.capability_version_id,
        capability_type=original_tool_call.capability_type,
        capability_content_sha256=original_tool_call.capability_content_sha256,
        capability_config_sha256=original_tool_call.capability_config_sha256,
        capability_schema_version=original_tool_call.capability_schema_version,
        capability_snapshot_json={
            **original_snapshot,
            "source": "local_agent_bridge",
            "server_execution": False,
            "retry": True,
            "retry_of_tool_request_id": original_request.tool_request_id,
            "retry_of_command_id": original_command.command_id,
            "retry_requested_by": actor_id,
        },
        requires_sandbox=False,
        duration_ms=0,
        input_json=retry_input,
        output_json={},
        error_message=None,
        created_at=now,
    )
    session.add(tool_call)
    session.flush()
    decision_json = (
        original_request.decision_json
        if isinstance(original_request.decision_json, dict)
        else {}
    )
    retry_decision_json = {
        key: value
        for key, value in decision_json.items()
        if key not in {"terminal_status", "terminal_reason", "terminalized_at"}
    }
    retry_request = LocalAgentToolRequest(
        organization_id=original_request.organization_id,
        connection_id=original_request.connection_id,
        binding_id=original_request.binding_id,
        bridge_task_id=original_request.bridge_task_id,
        task_id=original_request.task_id,
        tool_request_id=retry_tool_request_id,
        tool_call_id=tool_call.id,
        approval_id=None,
        tool_name=original_request.tool_name,
        execution_target=original_request.execution_target,
        risk_level=original_request.risk_level,
        permission_mode=original_request.permission_mode,
        status="approved",
        input_json=retry_input,
        policy_decision_json=original_request.policy_decision_json,
        decision_json={
            **retry_decision_json,
            "decision": "approved",
            "reason": "local command retry requested",
            "server_execution": False,
            "input_json": retry_input,
            "executable_input_sha256": retry_input_sha256,
            "retry": True,
            "retry_of_tool_request_id": original_request.tool_request_id,
            "retry_of_tool_call_id": original_request.tool_call_id,
            "retry_of_command_id": original_command.command_id,
            "retry_requested_by": actor_id,
            "retry_requested_at": now.isoformat(),
            "expires_at": expires_at.isoformat(),
        },
        result_json={},
        decision_expires_at=expires_at,
        created_at=now,
        updated_at=now,
    )
    session.add(retry_request)
    session.flush()
    retry_command = LocalAgentCommand(
        organization_id=original_command.organization_id,
        connection_id=original_command.connection_id,
        binding_id=original_command.binding_id,
        bridge_task_id=original_command.bridge_task_id,
        task_id=original_command.task_id,
        local_agent_tool_request_id=retry_request.id,
        tool_request_id=retry_request.tool_request_id,
        command_id=retry_command_id,
        tool_name=original_command.tool_name,
        command=_approved_command_for_request(retry_request),
        status="pending",
        retry_of_command_id=original_command.command_id,
        output_summary_json={},
        event_receipts_json={},
        created_at=now,
        updated_at=now,
    )
    session.add(retry_command)
    session.flush()
    EventStore(session).append(
        task_id=retry_request.task_id,
        event_type=EventType.TOOL_CALLED,
        payload_json={
            "source": "local_agent_bridge",
            "connection_id": retry_request.connection_id,
            "bridge_task_id": retry_request.bridge_task_id,
            "tool_request_id": retry_request.tool_request_id,
            "tool_call_id": retry_request.tool_call_id,
            "tool_name": retry_request.tool_name,
            "status": retry_request.status,
            "retry": True,
            "retry_of_tool_request_id": original_request.tool_request_id,
            "retry_of_command_id": original_command.command_id,
            "server_execution": False,
        },
        actor_type="user",
        actor_id=actor_id,
    )
    return retry_request, retry_command


def _classify_local_tool_request(request: LocalAgentToolRequestCreateRequest) -> dict:
    tool_name = request.tool_name.strip()
    command = ""
    if isinstance(request.input_json, dict):
        command = str(request.input_json.get("command") or "")
    target_paths = [str(path) for path in request.target_paths if str(path).strip()]
    bridge_risk = request.risk_level
    server_risk = "low"
    decision = "allowed"
    reason = "safe-listed local metadata request"
    if request.execution_target != "host":
        return {
            "decision": "denied",
            "risk_level": "high",
            "reason": "local bridge may only request host execution in V3",
            "bridge_risk": bridge_risk,
        }
    if tool_name in LOCAL_AGENT_SAFE_TOOLS:
        server_risk = "low"
        decision = "allowed"
    elif tool_name in LOCAL_AGENT_SIDE_EFFECT_TOOLS or tool_name.startswith(
        ("run_", "write_", "commit_")
    ):
        server_risk = "high"
        decision = "approval_required"
        reason = "local host side-effect tools require Harness approval"
    elif tool_name in {"read_file", "search_files", "list_files"}:
        server_risk = "medium"
        decision = "approval_required"
        reason = "local filesystem reads require Harness approval in V3"
    else:
        server_risk = "unknown"
        decision = "denied"
        reason = "unknown local tool is denied by default"
    if command and LOCAL_AGENT_NETWORK_PATTERNS.search(command):
        server_risk = "critical"
        decision = "approval_required"
        reason = "network or package-install command requires approval"
    if command and LOCAL_AGENT_SECRET_PATTERNS.search(command):
        server_risk = "critical"
        decision = "approval_required"
        reason = "secret/env read command requires approval"
    if request.requires_network or request.requires_secret_read:
        server_risk = "critical"
        if decision != "denied":
            decision = "approval_required"
        reason = "network or secret access requires approval"
    if target_paths and any(path.startswith(("~", "/")) for path in target_paths):
        if decision != "denied":
            decision = "approval_required"
        server_risk = "high" if server_risk not in {"critical"} else server_risk
        reason = "absolute or home target paths require approval"
    return {
        "decision": decision,
        "risk_level": server_risk,
        "reason": reason,
        "bridge_risk": bridge_risk,
        "bridge_permission_mode": request.permission_mode,
        "target_paths": [_redact_path(path) for path in target_paths],
        "requires_network": request.requires_network,
        "requires_secret_read": request.requires_secret_read,
    }


def _capability_tool_name(tool_name: str) -> str:
    return LOCAL_AGENT_CAPABILITY_TOOL_ALIASES.get(tool_name, tool_name)


def _local_tool_requires_capability(tool_name: str) -> bool:
    return tool_name not in LOCAL_AGENT_SAFE_TOOLS


def _local_tool_decision_response(
    local_request: LocalAgentToolRequest,
    *,
    session: Session,
) -> LocalAgentToolDecisionResponse:
    decision_json = (
        local_request.decision_json if isinstance(local_request.decision_json, dict) else {}
    )
    input_json = decision_json.get("input_json")
    if not isinstance(input_json, dict):
        input_json = local_request.input_json
    executable = local_request.status in {"allowed", "approved"}
    if local_request.decision_expires_at is not None and _as_aware_utc(
        local_request.decision_expires_at
    ) < _as_aware_utc(utc_now()):
        executable = False
    if local_request.status in {"denied", "expired", "succeeded", "failed", "cancelled"}:
        executable = False
    approval = (
        session.get(ToolApproval, local_request.approval_id)
        if local_request.approval_id
        else None
    )
    decision = local_request.status
    if (
        approval is not None
        and approval.status == "PENDING"
        and local_request.status == "approval_required"
    ):
        decision = "approval_required"
    return LocalAgentToolDecisionResponse(
        tool_request_id=local_request.tool_request_id,
        bridge_task_id=local_request.bridge_task_id,
        tool_call_id=local_request.tool_call_id,
        approval_id=local_request.approval_id,
        decision=decision,
        status=local_request.status,
        executable=executable,
        server_execution=False,
        tool_name=local_request.tool_name,
        input_json=input_json,
        reason=str(decision_json.get("reason") or ""),
        decision_json=decision_json,
        expires_at=local_request.decision_expires_at,
    )


def _require_executable_local_tool_request(
    local_request: LocalAgentToolRequest,
    *,
    session: Session,
    detail: str,
) -> None:
    _expire_local_tool_request_if_needed(local_request, session=session)
    if local_request.status in LOCAL_AGENT_TOOL_TERMINAL_STATUSES:
        if local_request.status == "expired":
            session.commit()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Local Agent tool request is already terminal",
        )
    if local_request.status not in {"allowed", "approved", "running"}:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail)
    if local_request.decision_expires_at is not None and _as_aware_utc(
        local_request.decision_expires_at
    ) < _as_aware_utc(utc_now()):
        _terminalize_local_tool_request(
            local_request,
            session=session,
            terminal_status="expired",
            tool_status="DENIED",
            reason="local tool decision expired",
            event_type=EventType.TOOL_DENIED_BY_POLICY,
            actor_type="system",
            actor_id=None,
        )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Local Agent tool decision expired",
        )


def _expire_local_tool_request_if_needed(
    local_request: LocalAgentToolRequest,
    *,
    session: Session,
) -> None:
    if local_request.status in LOCAL_AGENT_TOOL_TERMINAL_STATUSES:
        return
    if local_request.decision_expires_at is None:
        return
    if _as_aware_utc(local_request.decision_expires_at) >= _as_aware_utc(utc_now()):
        return
    _terminalize_local_tool_request(
        local_request,
        session=session,
        terminal_status="expired",
        tool_status="DENIED",
        reason="local tool decision expired",
        event_type=EventType.TOOL_DENIED_BY_POLICY,
        actor_type="system",
        actor_id=None,
    )


def _append_local_tool_request_events(
    *,
    connection: LocalAgentConnection,
    bridge_task: LocalAgentBridgeTask,
    local_request: LocalAgentToolRequest,
    approval: ToolApproval | None,
    classification: dict,
    session: Session,
) -> None:
    event_store = EventStore(session)
    base_payload = {
        "source": "local_agent_bridge",
        "connection_id": connection.id,
        "bridge_task_id": bridge_task.id,
        "tool_request_id": local_request.tool_request_id,
        "tool_call_id": local_request.tool_call_id,
        "tool_name": local_request.tool_name,
        "server_execution": False,
    }
    event_store.append(
        task_id=bridge_task.task_id,
        event_type=EventType.TOOL_CALLED,
        payload_json={
            **base_payload,
            "status": local_request.status,
            "risk_level": local_request.risk_level,
            "input_json": local_request.input_json,
        },
        actor_type="local_agent",
        actor_id=connection.id,
    )
    event_store.append(
        task_id=bridge_task.task_id,
        event_type=EventType.POLICY_CHECKED,
        payload_json={
            **base_payload,
            "decision": classification["decision"],
            "server_risk": classification["risk_level"],
            "bridge_risk": classification.get("bridge_risk"),
            "reason": classification["reason"],
            "policy_id": "local_agent_tool_safety_v3",
        },
        actor_type="local_agent",
        actor_id=connection.id,
    )
    if approval is not None:
        event_store.append(
            task_id=bridge_task.task_id,
            event_type=EventType.TOOL_APPROVAL_REQUESTED,
            payload_json={
                **base_payload,
                "approval_id": approval.id,
                "risk_level": approval.risk_level,
                "reason": approval.reason,
            },
            actor_type="local_agent",
            actor_id=connection.id,
        )
    elif classification["decision"] == "denied":
        event_store.append(
            task_id=bridge_task.task_id,
            event_type=EventType.TOOL_DENIED_BY_POLICY,
            payload_json={**base_payload, "reason": classification["reason"]},
            actor_type="local_agent",
            actor_id=connection.id,
        )


def _record_pending_change_preview(
    *,
    local_request: LocalAgentToolRequest,
    approval: ToolApproval | None,
    request: LocalAgentToolRequestCreateRequest,
    preview: dict,
    status: str,
    session: Session,
) -> None:
    change_id = str(preview.get("change_id") or request.tool_request_id)
    target_paths = request.target_paths or preview.get("target_paths") or []
    if not isinstance(target_paths, list):
        target_paths = []
    diff_sha256 = str(preview.get("diff_sha256") or preview.get("diff_hash") or "")
    row = LocalAgentPendingChange(
        organization_id=local_request.organization_id,
        connection_id=local_request.connection_id,
        binding_id=local_request.binding_id,
        bridge_task_id=local_request.bridge_task_id,
        task_id=local_request.task_id,
        local_agent_tool_request_id=local_request.id,
        tool_request_id=local_request.tool_request_id,
        approval_id=approval.id if approval is not None else None,
        change_id=change_id,
        target_paths_json=[_redact_path(str(path)) for path in target_paths],
        diff_sha256=diff_sha256,
        preview_json=preview,
        status=status if status in {"approval_required", "allowed", "denied"} else "previewed",
        created_at=utc_now(),
        updated_at=utc_now(),
    )
    session.add(row)
    EventStore(session).append(
        task_id=local_request.task_id,
        event_type=EventType.LOCAL_AGENT_PENDING_CHANGE_PREVIEWED,
        payload_json={
            "source": "local_agent_bridge",
            "tool_request_id": local_request.tool_request_id,
            "change_id": change_id,
            "target_paths": row.target_paths_json,
            "diff_sha256": diff_sha256,
            "status": row.status,
        },
        actor_type="local_agent",
        actor_id=local_request.connection_id,
    )


def _validated_pending_change_refresh_preview(
    *,
    local_request: LocalAgentToolRequest,
    refresh: LocalAgentPendingChangeRefreshRequest,
) -> dict:
    preview = (
        refresh.pending_change_preview
        if isinstance(refresh.pending_change_preview, dict)
        else {}
    )
    change_id = str(preview.get("change_id") or "").strip()
    if not change_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Local Agent pending change refresh requires change_id",
        )
    target_paths = [str(path).strip() for path in refresh.target_paths if str(path).strip()]
    if not target_paths:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Local Agent pending change refresh requires target paths",
        )
    preview_target_paths = preview.get("target_paths")
    if isinstance(preview_target_paths, list):
        normalized_preview_paths = [
            str(path).strip() for path in preview_target_paths if str(path).strip()
        ]
        if normalized_preview_paths != target_paths:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Local Agent pending change refresh target paths do not match preview",
            )
    expected_target_paths = _approved_pending_change_target_paths(local_request, refresh.input_json)
    if expected_target_paths != target_paths:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Local Agent pending change refresh target paths do not match approved input",
        )
    diff_sha256 = str(preview.get("diff_sha256") or preview.get("diff_hash") or "").strip()
    if not diff_sha256:
        diff_text = str(preview.get("diff") or "")
        if not diff_text:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Local Agent pending change refresh requires diff or diff hash",
            )
        diff_sha256 = hashlib.sha256(
            diff_text.encode("utf-8", errors="replace")
        ).hexdigest()
    return {
        **preview,
        "change_id": change_id,
        "target_paths": target_paths,
        "diff_sha256": diff_sha256,
    }


def _approved_pending_change_target_paths(
    local_request: LocalAgentToolRequest,
    input_json: dict,
) -> list[str]:
    if local_request.tool_name == "write_file":
        path = str(input_json.get("path") or "").strip()
        return [path] if path else []
    if local_request.tool_name == "apply_patch":
        return _patch_target_paths_from_preview_text(str(input_json.get("patch") or ""))
    return []


def _patch_target_paths_from_preview_text(patch: str) -> list[str]:
    paths: list[str] = []
    for line in patch.splitlines():
        if not line.startswith(("--- ", "+++ ")):
            continue
        raw = line[4:].strip()
        if raw == "/dev/null":
            continue
        if raw.startswith(("a/", "b/")):
            raw = raw[2:]
        path = raw.split("\t", 1)[0].strip()
        if path and path not in paths:
            paths.append(path)
    return paths


def _validate_pending_change_result(
    *,
    local_request: LocalAgentToolRequest,
    request: LocalAgentToolResultRequest,
    session: Session,
) -> LocalAgentPendingChange | None:
    change: LocalAgentPendingChange | None = None
    if request.change_id:
        change = session.execute(
            select(LocalAgentPendingChange).where(
                LocalAgentPendingChange.connection_id == local_request.connection_id,
                LocalAgentPendingChange.change_id == request.change_id,
            )
        ).scalar_one_or_none()
        if change is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Unknown pending change",
            )
    elif local_request.tool_name in LOCAL_AGENT_PENDING_CHANGE_TOOLS:
        change = session.execute(
            select(LocalAgentPendingChange)
            .where(LocalAgentPendingChange.local_agent_tool_request_id == local_request.id)
            .order_by(LocalAgentPendingChange.created_at.asc(), LocalAgentPendingChange.id.asc())
        ).scalar_one_or_none()
        if change is None and request.status == "SUCCESS":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Pending change evidence is required for local write result",
            )
    if change is None:
        return None
    if change.local_agent_tool_request_id != local_request.id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Pending change does not belong to tool request",
        )
    if change.status in LOCAL_AGENT_PENDING_CHANGE_TERMINAL_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Pending change is already terminal",
        )
    now = utc_now()
    if request.status == "SUCCESS" and local_request.tool_name in LOCAL_AGENT_PENDING_CHANGE_TOOLS:
        if not request.diff_sha256 or not change.diff_sha256:
            _fail_pending_change_result(
                local_request=local_request,
                change=change,
                reason="pending change diff hash is required",
                session=session,
            )
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Pending change diff hash is required",
            )
        if request.diff_sha256 != change.diff_sha256:
            _fail_pending_change_result(
                local_request=local_request,
                change=change,
                reason="pending change diff hash mismatch",
                session=session,
            )
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Pending change diff hash mismatch",
            )
    elif request.diff_sha256 and change.diff_sha256 and request.diff_sha256 != change.diff_sha256:
        _fail_pending_change_result(
            local_request=local_request,
            change=change,
            reason="pending change diff hash mismatch",
            session=session,
        )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Pending change diff hash mismatch",
        )
    if request.status == "SUCCESS":
        change.status = "committed"
        change.committed_at = now
    elif request.status in {"DENIED", "CANCELLED"}:
        change.status = "denied"
        change.denied_at = now
    else:
        change.status = "failed"
        change.error_message = _bounded_text(request.error_message)
    change.updated_at = now
    return change


def _fail_pending_change_result(
    *,
    local_request: LocalAgentToolRequest,
    change: LocalAgentPendingChange,
    reason: str,
    session: Session,
) -> None:
    now = utc_now()
    change.status = "failed"
    change.error_message = reason
    change.updated_at = now
    local_request.status = "failed"
    local_request.completed_at = now
    local_request.updated_at = now
    local_request.result_json = {
        "status": "FAILED",
        "change_id": change.change_id,
        "error": reason,
    }
    tool_call = session.get(ToolCall, local_request.tool_call_id)
    if tool_call is not None:
        tool_call.status = "FAILED"
        tool_call.error_message = reason
        tool_call.output_json = {
            "failed": True,
            "change_id": change.change_id,
            "error": reason,
        }
    EventStore(session).append(
        task_id=local_request.task_id,
        event_type=EventType.TOOL_FAILED,
        payload_json={
            "source": "local_agent_bridge",
            "tool_request_id": local_request.tool_request_id,
            "tool_call_id": local_request.tool_call_id,
            "change_id": change.change_id,
            "status": "FAILED",
            "reason": reason,
            "server_execution": False,
        },
        actor_type="local_agent",
        actor_id=local_request.connection_id,
    )


def _validated_result_command(
    *,
    local_request: LocalAgentToolRequest,
    command_id: str | None,
    result_status: str,
    session: Session,
) -> LocalAgentCommand | None:
    if local_request.tool_name not in LOCAL_AGENT_COMMAND_TOOLS:
        if command_id is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Local Agent non-command tool result cannot include command_id",
            )
        return None
    if not command_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Local Agent command result requires command_id",
        )
    command = session.execute(
        select(LocalAgentCommand).where(
            LocalAgentCommand.connection_id == local_request.connection_id,
            LocalAgentCommand.command_id == command_id,
        )
    ).scalar_one_or_none()
    if command is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Local Agent command not found for result",
        )
    if command.local_agent_tool_request_id != local_request.id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Local Agent result command does not belong to tool request",
        )
    if (
        command.task_id != local_request.task_id
        or command.binding_id != local_request.binding_id
        or command.bridge_task_id != local_request.bridge_task_id
        or command.connection_id != local_request.connection_id
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Local Agent result command ownership chain mismatch",
        )
    _validate_existing_command_against_request(
        local_request=local_request,
        command=command,
        request=None,
    )
    if command.status not in LOCAL_AGENT_COMMAND_TERMINAL_STATUSES or command.finished_at is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Local Agent result command is not terminal",
        )
    if result_status == "SUCCESS" and command.status != "success":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Successful local tool result requires successful terminal command",
        )
    if result_status == "CANCELLED" and command.status != "cancelled":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cancelled local tool result requires cancelled terminal command",
        )
    if result_status == "TIMEOUT" and command.status != "timeout":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Timeout local tool result requires timed-out terminal command",
        )
    if result_status == "FAILED" and command.status == "success":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Failed local tool result cannot bind a successful command",
        )
    return command


def _approved_input_for_request(local_request: LocalAgentToolRequest) -> dict:
    decision_json = (
        local_request.decision_json if isinstance(local_request.decision_json, dict) else {}
    )
    input_json = decision_json.get("input_json")
    if not isinstance(input_json, dict):
        input_json = local_request.input_json
    return input_json if isinstance(input_json, dict) else {}


def _executable_input_sha256(input_json: dict) -> str:
    return stable_json_sha256(input_json if isinstance(input_json, dict) else {})


def _approved_command_for_request(local_request: LocalAgentToolRequest) -> str:
    if local_request.tool_name not in LOCAL_AGENT_COMMAND_TOOLS:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Local Agent command events are only valid for command tools",
        )
    input_json = _approved_input_for_request(local_request)
    command = str(input_json.get("command") or input_json.get("cmd") or "").strip()
    if local_request.tool_name == "run_tests":
        command = command or "pytest"
        command = _normalize_local_agent_shell_command(command)
    if local_request.tool_name == "git":
        if not command:
            args = input_json.get("args") if isinstance(input_json.get("args"), list) else []
            command = f"git {' '.join(map(str, args))}".strip()
        if command and not command.startswith("git"):
            command = f"git {command}"
    if local_request.tool_name == "run_shell":
        command = _normalize_local_agent_shell_command(command)
    if not command:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Local Agent approved command input is missing command",
        )
    return _bounded_text(command)


def _normalize_local_agent_shell_command(command: str) -> str:
    if command == "python":
        return sys.executable
    if command.startswith("python "):
        return f"{sys.executable} {command.removeprefix('python ')}"
    return command


def _validate_command_start_payload(
    *,
    local_request: LocalAgentToolRequest,
    request: LocalAgentCommandEventRequest,
    expected_command: str,
) -> None:
    if request.tool_name is not None and request.tool_name != local_request.tool_name:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Local Agent command tool_name does not match approved tool request",
        )
    if _bounded_text(request.command) != expected_command:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Local Agent command does not match approved executable input",
        )
    decision_json = (
        local_request.decision_json if isinstance(local_request.decision_json, dict) else {}
    )
    expected_hash = decision_json.get("executable_input_sha256")
    if expected_hash and expected_hash != _executable_input_sha256(
        _approved_input_for_request(local_request)
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Local Agent executable input hash mismatch",
        )


def _validate_existing_command_against_request(
    *,
    local_request: LocalAgentToolRequest,
    command: LocalAgentCommand,
    request: LocalAgentCommandEventRequest | None = None,
) -> None:
    if local_request.tool_name not in LOCAL_AGENT_COMMAND_TOOLS:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Local Agent command is not valid for non-command tool request",
        )
    expected_command = _approved_command_for_request(local_request)
    if command.tool_name != local_request.tool_name or command.command != expected_command:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Local Agent command no longer matches approved executable input",
        )
    if (
        request is not None
        and request.retry_of_command_id is not None
        and command.retry_of_command_id != request.retry_of_command_id
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Local Agent retry source does not match command record",
        )


def _local_command_response(command: LocalAgentCommand) -> LocalAgentCommandResponse:
    return LocalAgentCommandResponse(
        command_id=command.command_id,
        tool_request_id=command.tool_request_id,
        status=command.status,
        cancel_requested=command.cancel_requested_at is not None,
    )


def _has_unresolved_local_tool_state(
    *,
    bridge_task: LocalAgentBridgeTask,
    session: Session,
) -> bool:
    count = session.execute(
        select(func.count(LocalAgentToolRequest.id)).where(
            LocalAgentToolRequest.bridge_task_id == bridge_task.id,
            LocalAgentToolRequest.status.in_(
                ("approval_required", "approved", "allowed", "running")
            ),
        )
    ).scalar_one()
    return bool(count)


def _existing_bridge_task_response(
    *,
    binding: LocalAgentConversationBinding,
    client_message_id: str,
    session: Session,
    conflict: IntegrityError,
) -> LocalAgentSendMessageResponse:
    existing = session.execute(
        select(LocalAgentBridgeTask).where(
            LocalAgentBridgeTask.binding_id == binding.id,
            LocalAgentBridgeTask.client_message_id == client_message_id,
        )
    ).scalar_one_or_none()
    if existing is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Local Agent message idempotency conflict",
        ) from conflict
    return LocalAgentSendMessageResponse(
        bridge_task_id=existing.id,
        run_id=existing.task_id,
        agent_session_id=existing.agent_session_id,
        user_message_id=existing.user_message_id,
        status=existing.status,
    )


def _record_local_agent_audit(
    *,
    session: Session,
    organization_id: str | None,
    actor_id: str | None,
    action: str,
    resource_type: str,
    resource_id: str,
    payload: dict,
) -> None:
    session.add(
        AdminAuditEvent(
            organization_id=organization_id,
            actor_id=actor_id,
            event_type="LOCAL_AGENT_LIFECYCLE",
            resource_type=resource_type,
            resource_id=resource_id,
            action=action,
            payload_json=_redact_mapping(payload, max_items=30),
            created_at=utc_now(),
        )
    )


def _bridge_task_response(task: LocalAgentBridgeTask) -> LocalAgentBridgeTaskResponse:
    return LocalAgentBridgeTaskResponse(
        id=task.id,
        connection_id=task.connection_id,
        binding_id=task.binding_id,
        agent_session_id=task.agent_session_id,
        run_id=task.task_id,
        client_message_id=task.client_message_id,
        status=task.status,
        payload=task.payload_json,
    )


def _binding_task_response(task: LocalAgentBridgeTask) -> LocalAgentBindingTaskResponse:
    return LocalAgentBindingTaskResponse(
        id=task.id,
        connection_id=task.connection_id,
        binding_id=task.binding_id,
        agent_session_id=task.agent_session_id,
        run_id=task.task_id,
        user_message_id=task.user_message_id,
        client_message_id=task.client_message_id,
        status=task.status,
        created_at=task.created_at,
        updated_at=task.updated_at,
    )


def _apply_bridge_event(
    *,
    connection: LocalAgentConnection,
    bridge_task: LocalAgentBridgeTask,
    request: LocalAgentBridgeEventRequest,
    session: Session,
) -> tuple[AgentEvent | None, ToolCall | None]:
    now = utc_now()
    agent_event: AgentEvent | None = None
    tool_call: ToolCall | None = None
    if request.event_type == "adapter_started":
        agent_event = EventStore(session).append(
            task_id=bridge_task.task_id,
            event_type=EventType.LOCAL_AGENT_ADAPTER_STARTED,
            payload_json={
                "connection_id": connection.id,
                "bridge_task_id": bridge_task.id,
                "adapter_kind": connection.adapter_kind,
                "sequence": request.sequence,
                "metadata": _safe_metadata(request.metadata),
            },
            actor_type="local_agent",
            actor_id=connection.id,
        )
    elif request.event_type == "assistant_delta":
        agent_event = EventStore(session).append(
            task_id=bridge_task.task_id,
            event_type=EventType.LOCAL_AGENT_DELTA_RECEIVED,
            payload_json={
                "connection_id": connection.id,
                "bridge_task_id": bridge_task.id,
                "adapter_kind": connection.adapter_kind,
                "content": _bounded_text(request.content),
                "sequence": request.sequence,
                "metadata": _safe_metadata(request.metadata),
            },
            actor_type="local_agent",
            actor_id=connection.id,
        )
    elif request.event_type == "assistant_done":
        if connection.adapter_kind == "claude_code":
            _ensure_claude_code_assistant_done_safety_proof(connection, request)
        if _has_unresolved_local_tool_state(bridge_task=bridge_task, session=session):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Local Agent assistant_done cannot bypass unresolved local tool state",
            )
        assistant = AgentMessage(
            session_id=bridge_task.agent_session_id,
            agent_id=connection.agent_id,
            role="assistant",
            content=_bounded_text(request.content),
            metadata_json={
                "source": "local_agent",
                "connection_id": connection.id,
                "bridge_task_id": bridge_task.id,
                "adapter_kind": connection.adapter_kind,
                "event_id": request.event_id,
                "resume_mode": bridge_task.payload_json.get("resume_mode"),
            },
            created_at=now,
        )
        session.add(assistant)
        bridge_task.status = "completed"
        bridge_task.completed_at = now
        bridge_task.updated_at = now
        run = session.get(Task, bridge_task.task_id)
        if run is not None:
            run.status = "COMPLETED"
            run.completed_at = now
            run.updated_at = now
        agent_session = session.get(AgentSession, bridge_task.agent_session_id)
        if agent_session is not None:
            agent_session.updated_at = now
        agent_event = EventStore(session).append(
            task_id=bridge_task.task_id,
            event_type=EventType.LOCAL_AGENT_MESSAGE_COMPLETED,
            payload_json={
                "connection_id": connection.id,
                "bridge_task_id": bridge_task.id,
                "assistant_message_id": assistant.id,
                "adapter_kind": connection.adapter_kind,
                "sequence": request.sequence,
                "metadata": _safe_metadata(request.metadata),
            },
            actor_type="local_agent",
            actor_id=connection.id,
        )
    elif request.event_type == "assistant_error":
        if _has_unresolved_local_tool_state(bridge_task=bridge_task, session=session):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Local Agent assistant_error cannot bypass unresolved local tool state",
            )
        bridge_task.status = "failed"
        bridge_task.completed_at = now
        bridge_task.updated_at = now
        run = session.get(Task, bridge_task.task_id)
        if run is not None:
            run.status = "FAILED"
            run.updated_at = now
        agent_event = EventStore(session).append(
            task_id=bridge_task.task_id,
            event_type=EventType.LOCAL_AGENT_MESSAGE_FAILED,
            payload_json={
                "connection_id": connection.id,
                "bridge_task_id": bridge_task.id,
                "adapter_kind": connection.adapter_kind,
                "error_message": _bounded_text(request.error_message),
                "sequence": request.sequence,
                "metadata": _safe_metadata(request.metadata),
            },
            actor_type="local_agent",
            actor_id=connection.id,
        )
    elif request.event_type == "tool_result":
        if connection.adapter_kind in LOCAL_AGENT_RESTRICTED_ASSISTANT_ADAPTERS:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"{connection.adapter_kind} adapter cannot report legacy tool_result events",
            )
        if _legacy_tool_result_requires_authorization(request):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Local Agent side-effect tool results require an authorized tool request",
            )
        tool_call = ToolCall(
            task_id=bridge_task.task_id,
            agent_run_id=None,
            tool_name=request.tool_name or "local_agent.tool",
            status="DENIED"
            if _normalized_tool_status(request.status) == "SUCCESS"
            else _normalized_tool_status(request.status),
            risk_level="low" if request.risk_level == "unknown" else request.risk_level,
            capability_snapshot_json={
                "source": "local_agent_bridge",
                "authorized": False,
                "connection_id": connection.id,
                "bridge_task_id": bridge_task.id,
                "adapter_kind": connection.adapter_kind,
                "workspace_root": _redact_path(connection.workspace_root),
            },
            requires_sandbox=False,
            duration_ms=request.duration_ms,
            input_json=_redact_mapping(request.input_json),
            output_json=_redact_mapping(request.output_json),
            error_message=_bounded_text(request.error_message),
            created_at=now,
        )
        session.add(tool_call)
        session.flush()
        agent_event = EventStore(session).append(
            task_id=bridge_task.task_id,
            event_type=EventType.TOOL_RESULT_RECEIVED
            if tool_call.status == "SUCCESS"
            else EventType.TOOL_FAILED,
            payload_json={
                "connection_id": connection.id,
                "bridge_task_id": bridge_task.id,
                "tool_call_id": tool_call.id,
                "tool_name": tool_call.tool_name,
                "status": tool_call.status,
                "risk_level": tool_call.risk_level,
            },
            actor_type="local_agent",
            actor_id=connection.id,
        )
    session.flush()
    return agent_event, tool_call


def _legacy_tool_result_requires_authorization(request: LocalAgentBridgeEventRequest) -> bool:
    tool_name = (request.tool_name or "").strip()
    normalized_status = _normalized_tool_status(request.status)
    if normalized_status == "SUCCESS" and tool_name not in LOCAL_AGENT_SAFE_TOOLS:
        return True
    if tool_name in LOCAL_AGENT_SIDE_EFFECT_TOOLS:
        return True
    if tool_name in {"read_file", "search_files", "list_files"}:
        return True
    command = ""
    if isinstance(request.input_json, dict):
        command = str(request.input_json.get("command") or "")
    return bool(
        command
        and (
            LOCAL_AGENT_NETWORK_PATTERNS.search(command)
            or LOCAL_AGENT_SECRET_PATTERNS.search(command)
        )
    )


def _ensure_claude_code_assistant_done_safety_proof(
    connection: LocalAgentConnection,
    request: LocalAgentBridgeEventRequest,
) -> None:
    if _claude_code_permission_bridge_enabled(connection):
        _ensure_claude_code_permission_bridge_done_safety_proof(request)
        return
    _ensure_claude_code_v5_empty_tool_safety_proof(request)


def _ensure_claude_code_v5_empty_tool_safety_proof(
    request: LocalAgentBridgeEventRequest,
) -> None:
    metadata = request.metadata if isinstance(request.metadata, dict) else {}
    system_init_safe = metadata.get("system_init_safe")
    if system_init_safe is not True:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Claude Code assistant_done requires empty-tool system/init safety proof",
        )
    for key in ("tools_count", "mcp_servers_count"):
        value = metadata.get(key)
        if isinstance(value, bool) or not isinstance(value, int) or value != 0:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Claude Code assistant_done requires empty-tool system/init safety proof",
            )


def _ensure_claude_code_permission_bridge_done_safety_proof(
    request: LocalAgentBridgeEventRequest,
) -> None:
    metadata = request.metadata if isinstance(request.metadata, dict) else {}
    if (
        metadata.get("permission_bridge_active") is not True
        or metadata.get("permission_bridge_version") != LOCAL_AGENT_CLAUDE_CODE_PERMISSION_BRIDGE
        or metadata.get("permission_bridge_execution")
        != LOCAL_AGENT_CLAUDE_CODE_PERMISSION_BRIDGE_EXECUTOR
        or metadata.get("sdk_native_tool_execution_enabled") is not False
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Claude Code assistant_done requires active permission bridge proof",
        )
    safety = metadata.get("safety") if isinstance(metadata.get("safety"), dict) else metadata
    for key in LOCAL_AGENT_CLAUDE_CODE_V6_SAFETY_FLAGS:
        if safety.get(key) is not True:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Claude Code permission bridge safety proof missing: {key}",
            )
    forbidden_mode = str(
        safety.get("permission_mode") or metadata.get("permission_mode") or ""
    ).strip()
    if forbidden_mode and forbidden_mode != "default":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Claude Code permission bridge used forbidden permission mode",
        )
    forbidden_surfaces = safety.get("forbidden_surfaces")
    if isinstance(forbidden_surfaces, list) and forbidden_surfaces:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Claude Code permission bridge loaded forbidden capability surface",
        )
    allowed_tools = safety.get("allowed_tools")
    if isinstance(allowed_tools, list) and allowed_tools:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Claude Code permission bridge cannot pre-approve SDK tools",
        )


def _default_local_agent_name(adapter_kind: str) -> str:
    return {
        "fake": "Fake Local Agent",
        "hao": "hao Local Agent",
        "codex": "Codex CLI",
        "claude_code": "Claude Code",
    }.get(adapter_kind, adapter_kind)


def _validate_pairing_scope_for_adapter(scope: dict, adapter_kind: str) -> None:
    adapters = scope.get("adapters") if isinstance(scope, dict) else None
    if adapters is None:
        if isinstance(scope, dict) and scope:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Local Agent pairing token requires explicit adapter scope",
            )
        return
    if not isinstance(adapters, list) or adapter_kind not in {str(item) for item in adapters}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Local Agent pairing token is not scoped for this adapter",
        )
    permission_bridge = _scope_permission_bridge(scope)
    if permission_bridge is None:
        return
    if adapter_kind != "claude_code" or permission_bridge != "sdk":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Local Agent pairing token permission bridge is not scoped for this adapter",
        )


def _pairing_command_adapter(scope: dict) -> str:
    adapters = scope.get("adapters") if isinstance(scope, dict) else None
    if isinstance(adapters, list) and len(adapters) == 1:
        adapter = str(adapters[0])
        if adapter in LOCAL_AGENT_SUPPORTED_ADAPTERS:
            return adapter
    return "hao"


def _normalized_resume_mode(
    *,
    connection: LocalAgentConnection,
    requested_resume_mode: str,
) -> str:
    if connection.adapter_kind in LOCAL_AGENT_RESTRICTED_ASSISTANT_ADAPTERS:
        return "context_replay_new_session"
    return requested_resume_mode


def _normalized_capabilities(adapter_kind: str, reported: dict | None) -> dict:
    capabilities = dict(reported or {})
    if adapter_kind == "codex":
        return {
            **capabilities,
            "adapter_kind": "codex",
            "supports_streaming": bool(capabilities.get("supports_streaming", True)),
            "supports_resume": False,
            "supports_cancel": False,
            "enabled_in_v1": True,
            "enabled_in_v4": True,
            "host_tools_authorized": False,
            "resume_mode": "context_replay_new_session",
        }
    if adapter_kind == "claude_code":
        v6_enabled = _claude_code_reported_v6_capabilities_allowed(capabilities)
        normalized = {
            **capabilities,
            "adapter_kind": "claude_code",
            "supports_streaming": bool(capabilities.get("supports_streaming", True)),
            "supports_resume": False,
            "enabled_in_v1": True,
            "enabled_in_v5": True,
            "resume_mode": "context_replay_new_session",
            "permission_defer_supported": False,
        }
        if v6_enabled:
            normalized.update(
                {
                    "enabled_in_v6": True,
                    "supports_cancel": True,
                    "host_tools_authorized": True,
                    "claude_permission_bridge_v1": True,
                    "permission_bridge": LOCAL_AGENT_CLAUDE_CODE_PERMISSION_BRIDGE,
                    "execution_mode": LOCAL_AGENT_CLAUDE_CODE_PERMISSION_BRIDGE_EXECUTION_MODE,
                    "permission_bridge_execution": (
                        LOCAL_AGENT_CLAUDE_CODE_PERMISSION_BRIDGE_EXECUTOR
                    ),
                    "sdk_native_tool_execution_enabled": False,
                    "permission_bridge_mode": "sdk",
                    "sdk_allowed_tools_preapproved": False,
                }
            )
        else:
            normalized.update(
                {
                    "enabled_in_v6": False,
                    "supports_cancel": False,
                    "host_tools_authorized": False,
                    "permission_bridge": None,
                    "execution_mode": "headless_bare_no_session_no_tools",
                    "permission_bridge_mode": "none",
                }
            )
        return normalized
    capabilities.setdefault("adapter_kind", adapter_kind)
    capabilities.setdefault("supports_streaming", True)
    capabilities.setdefault("supports_resume", adapter_kind == "hao")
    capabilities.setdefault("supports_cancel", adapter_kind == "hao")
    capabilities.setdefault("enabled_in_v1", adapter_kind in LOCAL_AGENT_SUPPORTED_ADAPTERS)
    return capabilities


def _claude_code_capabilities_v6_enabled(capabilities: dict) -> bool:
    return (
        capabilities.get("enabled_in_v6") is True
        and capabilities.get("host_tools_authorized") is True
        and capabilities.get("permission_bridge") == LOCAL_AGENT_CLAUDE_CODE_PERMISSION_BRIDGE
        and capabilities.get("execution_mode")
        == LOCAL_AGENT_CLAUDE_CODE_PERMISSION_BRIDGE_EXECUTION_MODE
        and capabilities.get("permission_bridge_execution")
        == LOCAL_AGENT_CLAUDE_CODE_PERMISSION_BRIDGE_EXECUTOR
        and capabilities.get("sdk_native_tool_execution_enabled") is False
    )


def _claude_code_reported_v6_capabilities_allowed(capabilities: dict) -> bool:
    if capabilities.get("claude_permission_bridge_v1") is not True:
        return False
    if str(capabilities.get("permission_bridge_mode") or "").strip() != "sdk":
        return False
    if capabilities.get("permission_bridge") not in {
        LOCAL_AGENT_CLAUDE_CODE_PERMISSION_BRIDGE,
        "sdk",
    }:
        return False
    execution_mode = str(capabilities.get("execution_mode") or "").strip()
    if execution_mode != LOCAL_AGENT_CLAUDE_CODE_PERMISSION_BRIDGE_EXECUTION_MODE:
        return False
    permission_bridge_execution = str(
        capabilities.get("permission_bridge_execution") or ""
    ).strip()
    if permission_bridge_execution != LOCAL_AGENT_CLAUDE_CODE_PERMISSION_BRIDGE_EXECUTOR:
        return False
    if capabilities.get("sdk_native_tool_execution_enabled") is not False:
        return False
    if capabilities.get("permission_bridge_callback_configured") is not True:
        return False
    if capabilities.get("permission_bridge_pre_tool_hook_configured") is not True:
        return False
    if capabilities.get("permission_bridge_dummy_hook_only") is not True:
        return False
    if capabilities.get("side_effect_tools_preapproval_disabled") is not True:
        return False
    if capabilities.get("forbidden_permission_modes_disabled") is not True:
        return False
    if capabilities.get("unmanaged_settings_disabled") is not True:
        return False
    if capabilities.get("sdk_allowed_tools_preapproved") is True:
        return False
    if capabilities.get("allowed_tools") not in (None, [], ()):
        return False
    for key in (
        "remote_control_enabled",
        "mcp_enabled",
        "plugins_enabled",
        "hooks_enabled",
        "subagents_enabled",
        "browser_enabled",
        "computer_use_enabled",
        "native_resume_enabled",
        "background_sessions_enabled",
        "web_sessions_enabled",
        "cloud_sessions_enabled",
    ):
        if capabilities.get(key) is True:
            return False
    return True


def _normalized_risk_capabilities(adapter_kind: str, reported: list[str]) -> list[str]:
    if adapter_kind == "codex":
        return [
            str(capability)
            for capability in reported
            if str(capability) in LOCAL_AGENT_CODEX_ALLOWED_RISK_CAPABILITIES
        ]
    if adapter_kind == "claude_code":
        return [
            str(capability)
            for capability in reported
            if str(capability) in LOCAL_AGENT_CLAUDE_CODE_ALLOWED_RISK_CAPABILITIES
        ]
    return list(reported)


def _safe_metadata(value: dict) -> dict:
    return _redact_mapping(value, max_items=20)


def _safe_bridge_payload(request: LocalAgentBridgeEventRequest) -> dict:
    return {
        "event_type": request.event_type,
        "bridge_task_id": request.bridge_task_id,
        "sequence": request.sequence,
        "content": _bounded_text(request.content),
        "tool_name": request.tool_name,
        "status": request.status,
        "risk_level": request.risk_level,
        "error_message": _bounded_text(request.error_message),
        "metadata": _redact_mapping(request.metadata, max_items=20),
    }


def _bounded_text(value: str | None, limit: int = 4000) -> str:
    if not value:
        return ""
    redacted = _redact_secret_text(value)
    return redacted[:limit] + ("...[truncated]" if len(redacted) > limit else "")


def _codex_conversation_context(
    *,
    agent_session_id: str,
    session: Session,
) -> list[dict[str, str]]:
    rows = list(
        session.execute(
            select(AgentMessage)
            .where(
                AgentMessage.session_id == agent_session_id,
                AgentMessage.role.in_(("user", "assistant")),
            )
            .order_by(AgentMessage.created_at.desc(), AgentMessage.id.desc())
            .limit(LOCAL_AGENT_CODEX_CONTEXT_MAX_MESSAGES)
        ).scalars()
    )
    context: list[dict[str, str]] = []
    total_chars = 0
    for message in reversed(rows):
        content = _bounded_text(message.content, limit=LOCAL_AGENT_CODEX_CONTEXT_MESSAGE_CHARS)
        if not content:
            continue
        remaining = LOCAL_AGENT_CODEX_CONTEXT_TOTAL_CHARS - total_chars
        if remaining <= 0:
            break
        if len(content) > remaining:
            content = content[:remaining] + "...[truncated]"
        context.append({"role": message.role, "content": content})
        total_chars += len(content)
    return context


def _redact_mapping(value: dict, *, max_items: int = 50) -> dict:
    redacted = _redact_value(value if isinstance(value, dict) else {}, max_items=max_items)
    return redacted if isinstance(redacted, dict) else {}


def _redact_value(value, *, max_items: int = 50, key: str | None = None):
    if key is not None and _looks_secret_key(key):
        return "[REDACTED]"
    if isinstance(value, dict):
        output: dict = {}
        for index, (item_key, item) in enumerate(value.items()):
            if index >= max_items:
                output["[truncated]"] = True
                break
            key_text = str(item_key)
            output[key_text] = _redact_value(item, max_items=max_items, key=key_text)
        return output
    if isinstance(value, list):
        output = []
        for index, item in enumerate(value):
            if index >= max_items:
                output.append("[truncated]")
                break
            output.append(_redact_value(item, max_items=max_items, key=key))
        return output
    if isinstance(value, str):
        if key is not None and _looks_path_key(key):
            return _redact_path(value)
        return _bounded_text(value)
    return value


def _looks_secret_key(value: str) -> bool:
    lowered = value.lower()
    return any(
        marker in lowered
        for marker in ("secret", "token", "api_key", "apikey", "password", "authorization", "env")
    )


def _looks_path_key(value: str) -> bool:
    lowered = value.lower()
    normalized = lowered.replace("-", "_")
    return any(
        marker in normalized
        for marker in (
            "cwd",
            "workspace_root",
            "path",
            "paths",
            "target_path",
            "target_paths",
        )
    )


def _redact_secret_text(value: str) -> str:
    redacted = re.sub(r"(sk|hk|pat|sat)[_-][A-Za-z0-9_\-]{8,}", "[REDACTED]", value)
    redacted = re.sub(r"(?i)(api[_-]?key|token|secret|password)=\S+", r"\1=[REDACTED]", redacted)
    redacted = re.sub(
        r"(?i)\b([A-Z0-9_]*(?:TOKEN|SECRET|PASSWORD|API[_-]?KEY)[A-Z0-9_]*\s*=\s*)"
        r"(?:'[^']*'|\"[^\"]*\"|[^\s;,&|]+)",
        r"\1[REDACTED]",
        redacted,
    )
    redacted = re.sub(
        r"(?i)\b(authorization\s*:\s*bearer\s+)[A-Za-z0-9._~+/=\-]+",
        r"\1[REDACTED]",
        redacted,
    )
    redacted = re.sub(
        r"(?i)\b(bearer\s+)[A-Za-z0-9._~+/=\-]{8,}",
        r"\1[REDACTED]",
        redacted,
    )
    redacted = re.sub(
        r"(?<!\.)/(?:Users|home)/[^\s'\";:&|`]+",
        lambda match: _redact_path(match.group(0)) or "[REDACTED_PATH]",
        redacted,
    )
    return redacted


def _normalized_tool_status(value: str | None) -> str:
    normalized = (value or "SUCCESS").upper()
    if normalized in {"SUCCESS", "FAILED", "TIMEOUT", "DENIED", "PENDING_APPROVAL", "CANCELLED"}:
        return normalized
    return "FAILED"
