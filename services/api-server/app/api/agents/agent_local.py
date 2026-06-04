"""Local Agent bridge pairing, connection, and event APIs."""

# ruff: noqa: F401,F403,F405,I001,UP037
import secrets
from datetime import UTC, datetime, timedelta

from fastapi import Header
from sqlalchemy.exc import IntegrityError

from .common import *
from ._workspace_chat_helpers import _create_workspace_chat_run

LOCAL_AGENT_PROTOCOL_VERSION = "local-agent-v1"
LOCAL_AGENT_SUPPORTED_ADAPTERS = {"fake", "hao"}
LOCAL_AGENT_DISABLED_ADAPTERS = {"codex", "claude_code"}
LOCAL_AGENT_COMMAND = (
    "hao bridge pair "
    "--api {api_url} --pair-token {pair_token} --pair-code {pair_code} --daemon"
)
DEVICE_TOKEN_BYTES = 32
PAIR_TOKEN_BYTES = 32
PAIR_CODE_DIGITS = "0123456789ABCDEFGHJKLMNPQRSTUVWXYZ"
LOCAL_AGENT_OFFLINE_AFTER_SECONDS = 30


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
    if len(parts) <= 2:
        return normalized
    return f".../{'/'.join(parts[-2:])}"


def _pairing_response(
    token: LocalAgentPairingToken, *, pair_token: str | None = None
) -> LocalAgentPairingResponse:
    command = None
    if pair_token is not None:
        command = LOCAL_AGENT_COMMAND.format(
            api_url="http://127.0.0.1:8000",
            pair_token=pair_token,
            pair_code=token.pair_code,
        )
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
        scope_json=request.scope or {"executable": True, "adapters": ["fake", "hao"]},
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
            status_code=status.HTTP_400_BAD_REQUEST, detail="Adapter is not enabled in v1"
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
        workspace_root=request.workspace_root,
        capabilities_json=_normalized_capabilities(request),
        risk_capabilities_json=list(request.risk_capabilities),
        metadata_json=_safe_metadata(request.metadata),
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
        connection.capabilities_json = request.capabilities
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
        existing.status = "active"
        existing.adapter_session_id = request.adapter_session_id or existing.adapter_session_id
        existing.resume_mode = request.resume_mode
        existing.updated_at = utc_now()
        session.commit()
        session.refresh(existing)
        return _binding_response(existing)

    now = utc_now()
    binding = LocalAgentConversationBinding(
        organization_id=principal.organization_id,
        owner_user_id=principal.user_id,
        connection_id=connection.id,
        agent_id=connection.agent_id,
        agent_session_id=agent_session.id,
        adapter_session_id=request.adapter_session_id,
        resume_mode=request.resume_mode,
        status="active",
        metadata_json={
            "adapter_kind": connection.adapter_kind,
            "supports_resume": bool(connection.capabilities_json.get("supports_resume", True)),
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
        payload_json={
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
        },
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
    if request.event_type == "assistant_delta":
        agent_event = EventStore(session).append(
            task_id=bridge_task.task_id,
            event_type=EventType.LOCAL_AGENT_DELTA_RECEIVED,
            payload_json={
                "connection_id": connection.id,
                "bridge_task_id": bridge_task.id,
                "content": _bounded_text(request.content),
                "sequence": request.sequence,
            },
            actor_type="local_agent",
            actor_id=connection.id,
        )
    elif request.event_type == "assistant_done":
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
            },
            actor_type="local_agent",
            actor_id=connection.id,
        )
    elif request.event_type == "assistant_error":
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
                "error_message": _bounded_text(request.error_message),
                "sequence": request.sequence,
            },
            actor_type="local_agent",
            actor_id=connection.id,
        )
    elif request.event_type == "tool_result":
        tool_call = ToolCall(
            task_id=bridge_task.task_id,
            agent_run_id=None,
            tool_name=request.tool_name or "local_agent.tool",
            status=_normalized_tool_status(request.status),
            risk_level=request.risk_level,
            capability_snapshot_json={
                "source": "local_agent_bridge",
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


def _default_local_agent_name(adapter_kind: str) -> str:
    return {
        "fake": "Fake Local Agent",
        "hao": "hao Local Agent",
        "codex": "Codex CLI",
        "claude_code": "Claude Code",
    }.get(adapter_kind, adapter_kind)


def _normalized_capabilities(request: LocalAgentConnectionRegisterRequest) -> dict:
    capabilities = dict(request.capabilities or {})
    capabilities.setdefault("supports_streaming", True)
    capabilities.setdefault("supports_resume", request.adapter_kind == "hao")
    capabilities.setdefault("supports_cancel", request.adapter_kind == "hao")
    capabilities.setdefault("enabled_in_v1", request.adapter_kind in LOCAL_AGENT_SUPPORTED_ADAPTERS)
    return capabilities


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
        "metadata": _redact_mapping(request.metadata, max_items=20),
    }


def _bounded_text(value: str | None, limit: int = 4000) -> str:
    if not value:
        return ""
    redacted = _redact_secret_text(value)
    return redacted[:limit] + ("...[truncated]" if len(redacted) > limit else "")


def _redact_mapping(value: dict, *, max_items: int = 50) -> dict:
    output: dict = {}
    for index, (key, item) in enumerate((value or {}).items()):
        if index >= max_items:
            output["[truncated]"] = True
            break
        key_text = str(key)
        if _looks_secret_key(key_text):
            output[key_text] = "[REDACTED]"
        elif isinstance(item, str):
            output[key_text] = _bounded_text(item)
        elif isinstance(item, dict):
            output[key_text] = _redact_mapping(item, max_items=max_items)
        else:
            output[key_text] = item
    return output


def _looks_secret_key(value: str) -> bool:
    lowered = value.lower()
    return any(
        marker in lowered
        for marker in ("secret", "token", "api_key", "apikey", "password", "authorization", "env")
    )


def _redact_secret_text(value: str) -> str:
    redacted = re.sub(r"(sk|hk|pat|sat)[_-][A-Za-z0-9_\-]{8,}", "[REDACTED]", value)
    redacted = re.sub(r"(?i)(api[_-]?key|token|secret|password)=\S+", r"\1=[REDACTED]", redacted)
    return redacted


def _normalized_tool_status(value: str | None) -> str:
    normalized = (value or "SUCCESS").upper()
    if normalized in {"SUCCESS", "FAILED", "TIMEOUT", "DENIED", "PENDING_APPROVAL"}:
        return normalized
    return "FAILED"
