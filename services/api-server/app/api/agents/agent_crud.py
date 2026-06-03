"""Agent CRUD, capability attachment, and session endpoints."""

# ruff: noqa: F401,F403,F405,I001,UP037
from .common import *
from ._capability_helpers import *
from ._grounding_helpers import *
from ._knowledge_helpers import *
from ._plan_helpers import *
from ._session_helpers import *
from ._tool_helpers import *
from ._workspace_chat_helpers import *
from ._workspace_response_helpers import *

@router.get(
    "",
    response_model=AgentPage,
    summary="查询 Agent 注册表",
    description="返回组织内可用的具名 Agent。默认 preset 会自动初始化。",
)
def list_agents(session: DbSession, principal: Principal) -> AgentPage:
    require_role(principal, {"admin", "engineer", "operator"})
    ensure_default_agents(session, principal.organization_id)
    session.commit()
    agents = list(session.execute(select(Agent).order_by(Agent.id.asc())).scalars())
    return AgentPage(items=[_agent_response(agent, session=session) for agent in agents])


@router.post(
    "",
    response_model=AgentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="创建 Agent 定义",
)
def create_agent_definition(
    request: AgentCreateRequest,
    session: DbSession,
    principal: Principal,
) -> AgentResponse:
    require_role(principal, {"admin", "engineer"})
    existing = session.get(Agent, request.id)
    if existing is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Agent already exists")
    now = utc_now()
    agent = Agent(
        id=request.id,
        organization_id=principal.organization_id,
        name=request.name,
        description=request.description,
        role=request.role,
        status="ACTIVE",
        model_provider=request.model_provider,
        model_name=request.model_name,
        system_prompt=request.system_prompt,
        tools_json=list(request.tools_json),
        routing_tags=list(request.routing_tags),
        max_parallel_assignments=request.max_parallel_assignments,
        created_at=now,
        updated_at=now,
    )
    session.add(agent)
    session.commit()
    session.refresh(agent)
    return _agent_response(agent, session=session)


@router.post(
    "/{agent_id}/clone",
    response_model=AgentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="克隆 Agent 定义",
)
def clone_agent_definition(
    agent_id: str,
    request: AgentCloneRequest,
    session: DbSession,
    principal: Principal,
) -> AgentResponse:
    require_role(principal, {"admin", "engineer"})
    source = _get_agent(agent_id=agent_id, session=session, principal=principal)
    if session.get(Agent, request.id) is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Agent already exists")
    now = utc_now()
    clone = Agent(
        id=request.id,
        organization_id=principal.organization_id,
        name=request.name,
        description=source.description,
        role=source.role,
        status="ACTIVE",
        model_provider=source.model_provider,
        model_name=source.model_name,
        system_prompt=source.system_prompt,
        tools_json=list(source.tools_json),
        routing_tags=list(source.routing_tags),
        max_parallel_assignments=source.max_parallel_assignments,
        created_at=now,
        updated_at=now,
    )
    session.add(clone)
    session.commit()
    session.refresh(clone)
    return _agent_response(clone, session=session)


@router.post(
    "/{agent_id}/capabilities/attachments",
    response_model=AgentCapabilityAttachmentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="为 Agent 附加能力",
)
def attach_agent_capability(
    agent_id: str,
    request: AgentCapabilityAttachmentRequest,
    session: DbSession,
    principal: Principal,
) -> AgentCapabilityAttachmentResponse:
    require_role(principal, {"admin", "engineer"})
    agent = _get_agent(agent_id=agent_id, session=session, principal=principal)
    capability, version = _resolve_agent_capability_attachment(
        request=request,
        session=session,
        principal=principal,
    )
    existing = session.execute(
        select(AgentCapabilityAttachment).where(
            AgentCapabilityAttachment.agent_id == agent.id,
            AgentCapabilityAttachment.capability_version_id == version.id,
        )
    ).scalar_one_or_none()
    if existing is None:
        attachment = AgentCapabilityAttachment(
            organization_id=agent.organization_id or principal.organization_id,
            agent_id=agent.id,
            capability_id=capability.id,
            capability_version_id=version.id,
            enabled=request.enabled,
            priority=request.priority,
            attached_by=principal.user_id,
            attached_at=utc_now(),
        )
        session.add(attachment)
    else:
        attachment = existing
        attachment.enabled = request.enabled
        attachment.priority = request.priority
    legacy_tool_name = _legacy_tool_name_for_capability(capability, request.capability_id)
    if legacy_tool_name and legacy_tool_name not in agent.tools_json:
        agent.tools_json = [*agent.tools_json, legacy_tool_name]
    agent.updated_at = utc_now()
    session.commit()
    return AgentCapabilityAttachmentResponse(
        status="attached",
        attachment_id=attachment.id,
        agent_id=attachment.agent_id,
        capability_id=attachment.capability_id,
        capability_version_id=attachment.capability_version_id,
        enabled=attachment.enabled,
        priority=attachment.priority,
    )

@router.get(
    "/{agent_id}/sessions",
    response_model=AgentSessionPage,
    summary="查询 Agent 会话",
)
def list_agent_sessions(
    agent_id: str,
    session: DbSession,
    principal: Principal,
) -> AgentSessionPage:
    require_role(principal, {"admin", "engineer", "operator"})
    _get_agent(agent_id=agent_id, session=session, principal=principal)
    sessions = list(
        session.execute(
            select(AgentSession)
            .where(
                AgentSession.organization_id == principal.organization_id,
                AgentSession.agent_id == agent_id,
            )
            .order_by(AgentSession.updated_at.desc(), AgentSession.id.asc())
        ).scalars()
    )
    return AgentSessionPage(items=sessions)


@router.post(
    "/{agent_id}/sessions",
    response_model=AgentSessionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="创建 Agent 会话",
)
def create_agent_session(
    agent_id: str,
    request: AgentSessionCreateRequest,
    session: DbSession,
    principal: Principal,
) -> AgentSession:
    require_role(principal, {"admin", "engineer"})
    _get_agent(agent_id=agent_id, session=session, principal=principal)
    now = utc_now()
    agent_session = AgentSession(
        organization_id=principal.organization_id,
        agent_id=agent_id,
        created_by=principal.user_id,
        title=request.title or "New Agent Session",
        status="ACTIVE",
        created_at=now,
        updated_at=now,
    )
    session.add(agent_session)
    session.commit()
    session.refresh(agent_session)
    return agent_session
