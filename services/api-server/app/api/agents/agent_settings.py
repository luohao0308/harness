"""Agent runtime settings and memory endpoints."""

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
    "/token-optimizer/presets",
    response_model=AgentTokenOptimizerPresetPage,
    summary="查询内置 Token Optimizer 方案",
)
def list_token_optimizer_presets(principal: Principal) -> AgentTokenOptimizerPresetPage:
    require_role(principal, {"admin", "engineer", "operator"})
    return AgentTokenOptimizerPresetPage(
        items=[
            AgentTokenOptimizerPreset(
                preset_id=preset_id,
                display_name=config["display_name"],
                description=config["description"],
                enabled=preset_id != "off",
                priority=TOKEN_OPTIMIZER_PRESET_PRIORITY if preset_id != "off" else None,
            )
            for preset_id, config in TOKEN_OPTIMIZER_PRESETS.items()
        ]
    )


@router.post(
    "/{agent_id}/token-optimizer",
    response_model=AgentTokenOptimizerSelectionResponse,
    summary="选择 Agent 内置 Token Optimizer 方案",
)
def select_agent_token_optimizer(
    agent_id: str,
    request: AgentTokenOptimizerSelectRequest,
    session: DbSession,
    principal: Principal,
) -> AgentTokenOptimizerSelectionResponse:
    require_role(principal, {"admin", "engineer"})
    agent = _get_agent(agent_id=agent_id, session=session, principal=principal)
    if request.preset_id == "off":
        disabled_attachment_id = _disable_agent_token_optimizer_attachments(
            agent=agent,
            session=session,
        )
        agent.updated_at = utc_now()
        session.commit()
        return AgentTokenOptimizerSelectionResponse(
            status="disabled",
            preset_id="off",
            attachment_id=disabled_attachment_id,
            capability_id=None,
            capability_version_id=None,
            enabled=False,
            priority=None,
        )

    capability, version = _ensure_token_optimizer_preset_capability(
        preset_id=request.preset_id,
        session=session,
        principal=principal,
    )
    attachment = _upsert_agent_token_optimizer_attachment(
        agent=agent,
        capability=capability,
        version=version,
        session=session,
        principal=principal,
    )
    agent.updated_at = utc_now()
    session.commit()
    return AgentTokenOptimizerSelectionResponse(
        status="selected",
        preset_id=request.preset_id,
        attachment_id=attachment.id,
        capability_id=capability.id,
        capability_version_id=version.id,
        enabled=attachment.enabled,
        priority=attachment.priority,
    )

@router.get(
    "/{agent_id}/memories",
    response_model=AgentMemoryPage,
    summary="List eligible agent memory records",
)
def list_agent_memories(
    agent_id: str,
    session: DbSession,
    principal: Principal,
    include_inactive: bool = False,
) -> AgentMemoryPage:
    require_role(principal, {"admin", "engineer", "operator"})
    _get_agent(agent_id=agent_id, session=session, principal=principal)
    filters = [
        AgentMemoryRecord.organization_id == principal.organization_id,
        or_(
            AgentMemoryRecord.scope == "org",
            and_(AgentMemoryRecord.scope == "agent", AgentMemoryRecord.agent_id == agent_id),
            and_(
                AgentMemoryRecord.scope == "user",
                AgentMemoryRecord.owner_user_id == principal.user_id,
            ),
        ),
    ]
    if not include_inactive:
        filters.append(AgentMemoryRecord.lifecycle_status == "active")
    items = list(
        session.execute(
            select(AgentMemoryRecord)
            .where(*filters)
            .order_by(AgentMemoryRecord.created_at.desc())
            .limit(100)
        ).scalars()
    )
    return AgentMemoryPage(items=[AgentMemoryResponse.model_validate(item) for item in items])


@router.post(
    "/{agent_id}/memories",
    response_model=AgentMemoryResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create manual agent memory",
)
def create_agent_memory(
    agent_id: str,
    payload: AgentMemoryCreateRequest,
    session: DbSession,
    principal: Principal,
) -> AgentMemoryResponse:
    require_role(principal, {"admin", "engineer"})
    _get_agent(agent_id=agent_id, session=session, principal=principal)
    if payload.scope == "org":
        require_role(principal, {"admin"})
    if payload.source_type != "manual":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="manual memory endpoint only accepts source_type=manual",
        )
    if payload.scope == "run":
        if not payload.run_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="run scope memory requires run_id",
            )
        run = _owned_run(run_id=payload.run_id, session=session, principal=principal)
        if "admin" not in principal.roles and run.created_by != principal.user_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent Run 未找到")
    text = strip_control_chars(payload.text).strip()
    policy_flags = []
    if MEMORY_INJECTION_PATTERN.search(text):
        policy_flags.append("prompt_injection_suspected")
    record = AgentMemoryRecord(
        organization_id=principal.organization_id,
        agent_id=agent_id,
        owner_user_id=principal.user_id if payload.scope == "user" else None,
        run_id=payload.run_id if payload.scope == "run" else None,
        message_id=payload.message_id,
        scope=payload.scope,
        source_type=payload.source_type,
        canonical_text=text,
        content_sha256=hashlib.sha256(text.encode("utf-8")).hexdigest(),
        content_length=len(text),
        score=payload.score,
        policy_flags_json=policy_flags,
        metadata_json=payload.metadata,
        lifecycle_status="active",
        expires_at=payload.expires_at,
        created_by=principal.user_id,
        updated_by=principal.user_id,
        created_at=utc_now(),
        updated_at=utc_now(),
    )
    session.add(record)
    session.commit()
    session.refresh(record)
    return AgentMemoryResponse.model_validate(record)


@router.post(
    "/{agent_id}/memories/{memory_id}/lifecycle",
    response_model=AgentMemoryResponse,
    summary="Update memory lifecycle",
)
def update_agent_memory_lifecycle(
    agent_id: str,
    memory_id: str,
    payload: AgentMemoryActionRequest,
    session: DbSession,
    principal: Principal,
) -> AgentMemoryResponse:
    require_role(principal, {"admin", "engineer"})
    _get_agent(agent_id=agent_id, session=session, principal=principal)
    record = session.execute(
        select(AgentMemoryRecord).where(
            AgentMemoryRecord.id == memory_id,
            AgentMemoryRecord.organization_id == principal.organization_id,
            or_(
                AgentMemoryRecord.scope == "org",
                and_(AgentMemoryRecord.scope == "agent", AgentMemoryRecord.agent_id == agent_id),
                and_(
                    AgentMemoryRecord.scope == "user",
                    AgentMemoryRecord.owner_user_id == principal.user_id,
                ),
                and_(AgentMemoryRecord.scope == "run", AgentMemoryRecord.agent_id == agent_id),
            ),
        )
    ).scalar_one_or_none()
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Memory 未找到")
    if record.scope == "org":
        require_role(principal, {"admin"})
    if record.scope == "run":
        if not record.run_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Memory 未找到")
        run = _owned_run(run_id=record.run_id, session=session, principal=principal)
        if "admin" not in principal.roles and run.created_by != principal.user_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Memory 未找到")
    record.lifecycle_status = {
        "disable": "disabled",
        "archive": "archived",
        "delete": "deleted",
    }[payload.action]
    record.updated_by = principal.user_id
    record.updated_at = utc_now()
    metadata = dict(record.metadata_json or {})
    if payload.reason:
        metadata["lifecycle_reason"] = payload.reason
    record.metadata_json = metadata
    if payload.action == "delete":
        record.deleted_at = utc_now()
    session.commit()
    session.refresh(record)
    return AgentMemoryResponse.model_validate(record)
