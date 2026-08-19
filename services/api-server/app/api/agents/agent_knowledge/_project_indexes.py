"""Desktop project Knowledge index binding lifecycle endpoints."""

# ruff: noqa: F401,F403,F405,I001,UP037
from ..common import *
from .._session_helpers import *


@router.get(
    "/{agent_id}/knowledge/project-indexes",
    response_model=ProjectKnowledgeIndexPage,
    summary="查询 Desktop 项目知识索引",
)
def list_agent_project_knowledge_indexes(
    agent_id: str,
    session: DbSession,
    principal: Principal,
) -> ProjectKnowledgeIndexPage:
    require_role(principal, {"admin", "engineer", "operator"})
    _get_agent(agent_id=agent_id, session=session, principal=principal)
    indexes = list_project_knowledge_indexes(
        session,
        organization_id=principal.organization_id,
        agent_id=agent_id,
    )
    return ProjectKnowledgeIndexPage(
        items=[_project_knowledge_index_response(session, index) for index in indexes]
    )


@router.get(
    "/{agent_id}/knowledge/project-indexes/{index_id}",
    response_model=ProjectKnowledgeIndexResponse,
    summary="查询 Desktop 项目知识索引详情",
)
def get_agent_project_knowledge_index(
    agent_id: str,
    index_id: str,
    session: DbSession,
    principal: Principal,
) -> ProjectKnowledgeIndexResponse:
    require_role(principal, {"admin", "engineer", "operator"})
    _get_agent(agent_id=agent_id, session=session, principal=principal)
    index = _project_knowledge_index_or_404(
        session=session,
        principal=principal,
        agent_id=agent_id,
        index_id=index_id,
    )
    return _project_knowledge_index_response(session, index)


@router.post(
    "/{agent_id}/knowledge/project-indexes",
    response_model=ProjectKnowledgeIndexResponse,
    status_code=status.HTTP_201_CREATED,
    summary="绑定 Desktop 项目知识索引",
)
def create_agent_project_knowledge_index(
    agent_id: str,
    request: ProjectKnowledgeIndexCreateRequest,
    session: DbSession,
    principal: Principal,
) -> ProjectKnowledgeIndexResponse:
    require_role(principal, {"admin", "engineer"})
    _get_agent(agent_id=agent_id, session=session, principal=principal)
    try:
        index, _created = create_project_knowledge_index(
            session,
            organization_id=principal.organization_id,
            agent_id=agent_id,
            desktop_profile_id=request.desktop_profile_id,
            root_identity=request.root_identity,
            name=request.name,
            description=request.description,
            ignore_patterns=request.ignore_patterns,
            created_by=principal.user_id,
            idempotency_key=request.idempotency_key,
        )
        session.commit()
    except ProjectKnowledgeIndexConflict as error:
        session.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error
    except IntegrityError as error:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Project root is already bound",
        ) from error
    session.refresh(index)
    return _project_knowledge_index_response(session, index)


@router.post(
    "/{agent_id}/knowledge/project-indexes/{index_id}/sync",
    response_model=ProjectKnowledgeIndexResponse,
    summary="同步 Desktop 项目知识完整快照",
)
def sync_agent_project_knowledge_index(
    agent_id: str,
    index_id: str,
    request: ProjectKnowledgeSyncRequest,
    session: DbSession,
    principal: Principal,
) -> ProjectKnowledgeIndexResponse:
    require_role(principal, {"admin", "engineer"})
    _get_agent(agent_id=agent_id, session=session, principal=principal)
    index = _project_knowledge_index_or_404(
        session=session,
        principal=principal,
        agent_id=agent_id,
        index_id=index_id,
    )
    if (
        request.desktop_profile_id != index.desktop_profile_id
        or request.root_identity != index.root_identity
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Desktop profile or project root identity does not match the binding",
        )
    try:
        sync_project_knowledge_snapshot(
            session,
            index=index,
            snapshot_cursor=request.snapshot_cursor,
            snapshot_generation=request.snapshot_generation,
            complete=request.complete,
            files=[item.model_dump() for item in request.files],
            snapshot_started_at=request.started_at,
            snapshot_completed_at=request.completed_at,
            scan_errors=[item.model_dump() for item in request.errors],
            actor_id=principal.user_id,
        )
        session.commit()
    except ProjectKnowledgeIndexConflict as error:
        session.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error
    session.refresh(index)
    return _project_knowledge_index_response(session, index)


@router.post(
    "/{agent_id}/knowledge/project-indexes/{index_id}/pause",
    response_model=ProjectKnowledgeIndexResponse,
    summary="暂停 Desktop 项目知识索引",
)
def pause_agent_project_knowledge_index(
    agent_id: str,
    index_id: str,
    request: ProjectKnowledgeIndexActionRequest,
    session: DbSession,
    principal: Principal,
) -> ProjectKnowledgeIndexResponse:
    return _change_project_knowledge_index_state(
        agent_id=agent_id,
        index_id=index_id,
        request=request,
        session=session,
        principal=principal,
        transition=pause_project_knowledge_index,
    )


@router.post(
    "/{agent_id}/knowledge/project-indexes/{index_id}/resume",
    response_model=ProjectKnowledgeIndexResponse,
    summary="恢复 Desktop 项目知识索引",
)
def resume_agent_project_knowledge_index(
    agent_id: str,
    index_id: str,
    request: ProjectKnowledgeIndexActionRequest,
    session: DbSession,
    principal: Principal,
) -> ProjectKnowledgeIndexResponse:
    return _change_project_knowledge_index_state(
        agent_id=agent_id,
        index_id=index_id,
        request=request,
        session=session,
        principal=principal,
        transition=resume_project_knowledge_index,
    )


@router.post(
    "/{agent_id}/knowledge/project-indexes/{index_id}/unbind",
    response_model=ProjectKnowledgeIndexResponse,
    summary="解绑 Desktop 项目知识索引并归档来源",
)
def unbind_agent_project_knowledge_index(
    agent_id: str,
    index_id: str,
    request: ProjectKnowledgeIndexActionRequest,
    session: DbSession,
    principal: Principal,
) -> ProjectKnowledgeIndexResponse:
    return _change_project_knowledge_index_state(
        agent_id=agent_id,
        index_id=index_id,
        request=request,
        session=session,
        principal=principal,
        transition=unbind_project_knowledge_index,
    )


def _change_project_knowledge_index_state(
    *,
    agent_id: str,
    index_id: str,
    request: ProjectKnowledgeIndexActionRequest,
    session: Session,
    principal: Principal,
    transition,
) -> ProjectKnowledgeIndexResponse:
    require_role(principal, {"admin", "engineer"})
    _get_agent(agent_id=agent_id, session=session, principal=principal)
    index = _project_knowledge_index_or_404(
        session=session,
        principal=principal,
        agent_id=agent_id,
        index_id=index_id,
    )
    try:
        transition(
            session,
            index=index,
            actor_id=principal.user_id,
            reason=request.reason,
        )
        session.commit()
    except ProjectKnowledgeIndexConflict as error:
        session.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error
    session.refresh(index)
    return _project_knowledge_index_response(session, index)


def _project_knowledge_index_or_404(
    *,
    session: Session,
    principal: Principal,
    agent_id: str,
    index_id: str,
) -> ProjectKnowledgeIndex:
    index = get_project_knowledge_index(
        session,
        organization_id=principal.organization_id,
        agent_id=agent_id,
        index_id=index_id,
    )
    if index is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project knowledge index not found",
        )
    return index


def _project_knowledge_index_response(
    session: Session,
    index: ProjectKnowledgeIndex,
) -> ProjectKnowledgeIndexResponse:
    counts = project_knowledge_file_counts(session, index_id=index.id)
    return ProjectKnowledgeIndexResponse(
        id=index.id,
        organization_id=index.organization_id,
        agent_id=index.agent_id,
        knowledge_source_id=index.knowledge_source_id,
        desktop_profile_id=index.desktop_profile_id,
        root_identity=index.root_identity,
        name=index.name,
        description=index.description,
        status=index.status,
        ignore_patterns=(
            list(index.ignore_patterns_json) if isinstance(index.ignore_patterns_json, list) else []
        ),
        snapshot_generation=index.snapshot_generation,
        snapshot_cursor=index.snapshot_cursor,
        last_snapshot_at=index.last_snapshot_at,
        last_sync_at=index.last_sync_at,
        last_error=index.last_error,
        unbound_at=index.unbound_at,
        created_at=index.created_at,
        updated_at=index.updated_at,
        **counts,
    )


__all__ = [name for name in globals() if not name.startswith("__") and name != "annotations"]
