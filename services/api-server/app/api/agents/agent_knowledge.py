"""Agent knowledge source and document management endpoints."""

# ruff: noqa: F401,F403,F405,I001,UP037
from .common import *
import app.api.agents as agents_api
from ._capability_helpers import *
from ._grounding_helpers import *
from ._knowledge_helpers import *
from ._plan_helpers import *
from ._session_helpers import *
from ._tool_helpers import *
from ._workspace_chat_helpers import *
from ._workspace_response_helpers import *

@router.get(
    "/{agent_id}/knowledge/sources",
    response_model=KnowledgeSourcePage,
    summary="查询 Agent 知识源",
)
def list_agent_knowledge_sources(
    agent_id: str,
    session: DbSession,
    principal: Principal,
) -> KnowledgeSourcePage:
    require_role(principal, {"admin", "engineer", "operator"})
    _get_agent(agent_id=agent_id, session=session, principal=principal)
    sources = list_knowledge_sources(
        session,
        organization_id=principal.organization_id,
        agent_id=agent_id,
    )
    return KnowledgeSourcePage(
        items=[_knowledge_source_response(session, source) for source in sources]
    )


@router.post(
    "/{agent_id}/knowledge/sources",
    response_model=KnowledgeSourceResponse,
    status_code=status.HTTP_201_CREATED,
    summary="创建 Agent 知识源并索引文档",
)
def create_agent_knowledge_source(
    agent_id: str,
    request: KnowledgeSourceCreateRequest,
    session: DbSession,
    principal: Principal,
) -> KnowledgeSourceResponse:
    require_role(principal, {"admin", "engineer"})
    _get_agent(agent_id=agent_id, session=session, principal=principal)
    if request.scope == "org":
        require_role(principal, {"admin"})
    effective_agent_id = None if request.scope == "org" else agent_id
    source_was_new = (
        _knowledge_source_exists(
            session=session,
            organization_id=principal.organization_id,
            agent_id=effective_agent_id,
            name=request.name,
            idempotency_key=request.idempotency_key,
        )
        is False
    )
    try:
        source, document, chunks, embeddings = agents_api.ingest_knowledge_source(
            session,
            organization_id=principal.organization_id,
            agent_id=effective_agent_id,
            name=request.name,
            description=request.description,
            source_type=request.source_type,
            title=request.title,
            content=request.content,
            uri=request.uri,
            mime_type=request.mime_type,
            created_by=principal.user_id,
            idempotency_key=request.idempotency_key,
            connector_settings_json=request.connector_settings_json,
            create_new_logical_document=True,
        )
    except KnowledgeIngestionError as error:
        _commit_failed_knowledge_ingestion(
            session=session,
            principal=principal,
            action="document_import_failed",
            error=error,
            before=None,
            idempotency_key=request.idempotency_key,
        )
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error)) from error
    before_snapshot = None
    if request.expires_at is not None:
        before_snapshot = knowledge_source_lifecycle_snapshot(source)
        source.expires_at = request.expires_at
        source.updated_at = utc_now()
    if request.connector_secret_value is not None:
        _store_knowledge_connector_secret(
            session=session,
            principal=principal,
            source=source,
            secret_value=request.connector_secret_value,
        )
    _record_knowledge_ingestion_events(
        session=session,
        principal=principal,
        agent_id=agent_id,
        source=source,
        document=document,
        chunks=chunks,
        embeddings=embeddings,
        idempotency_key=request.idempotency_key,
        source_was_new=source_was_new,
    )
    create_knowledge_lifecycle_audit(
        session,
        organization_id=principal.organization_id,
        actor_id=principal.user_id,
        action="created" if source_was_new else "document_indexed",
        source=source,
        before=before_snapshot,
        after=knowledge_source_lifecycle_snapshot(source),
        document_id=document.id,
        idempotency_key=request.idempotency_key,
    )
    session.commit()
    session.refresh(source)
    return _knowledge_source_response(session, source)


@router.post(
    "/{agent_id}/knowledge/sources/import",
    response_model=KnowledgeSourceResponse,
    status_code=status.HTTP_201_CREATED,
    summary="通过 multipart 文件创建 Agent 知识源",
)
async def import_agent_knowledge_source_file(
    agent_id: str,
    request: Request,
    session: DbSession,
    principal: Principal,
) -> KnowledgeSourceResponse:
    require_role(principal, {"admin", "engineer"})
    _get_agent(agent_id=agent_id, session=session, principal=principal)
    upload = await _parse_knowledge_multipart_upload(request)
    if upload["scope"] == "org":
        require_role(principal, {"admin"})
    payload = KnowledgeSourceCreateRequest(
        name=upload["name"] or upload["title"],
        description=upload["description"],
        scope=upload["scope"],
        source_type="text" if upload["mime_type"] == "text/plain" else "markdown",
        title=upload["title"],
        content=upload["content"],
        uri=upload["filename"],
        mime_type=upload["mime_type"],
        idempotency_key=upload["idempotency_key"],
    )
    return create_agent_knowledge_source(
        agent_id=agent_id,
        request=payload,
        session=session,
        principal=principal,
    )


@router.patch(
    "/{agent_id}/knowledge/sources/{source_id}",
    response_model=KnowledgeSourceResponse,
    summary="更新知识源普通字段",
)
def update_agent_knowledge_source(
    agent_id: str,
    source_id: str,
    request: KnowledgeSourceUpdateRequest,
    session: DbSession,
    principal: Principal,
) -> KnowledgeSourceResponse:
    require_role(principal, {"admin", "engineer"})
    _get_agent(agent_id=agent_id, session=session, principal=principal)
    source = _visible_knowledge_source_or_404(
        session=session,
        principal=principal,
        agent_id=agent_id,
        source_id=source_id,
    )
    _require_org_source_admin(source=source, principal=principal)
    before = knowledge_source_lifecycle_snapshot(source)
    if request.name is not None:
        source.name = request.name
    if request.description is not None:
        source.description = request.description
    if "expires_at" in request.model_fields_set:
        source.expires_at = request.expires_at
    if request.connector_settings_json is not None:
        if source.source_type != "connector":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    "connector_settings_json can only be updated for connector "
                    "knowledge sources"
                ),
            )
        try:
            source.settings_json = normalize_connector_settings(
                request.connector_settings_json,
                source_type=source.source_type,
            )
        except ValueError as error:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(error),
            ) from error
    if request.connector_secret_value is not None:
        _store_knowledge_connector_secret(
            session=session,
            principal=principal,
            source=source,
            secret_value=request.connector_secret_value,
        )
    source.updated_at = utc_now()
    create_knowledge_lifecycle_audit(
        session,
        organization_id=principal.organization_id,
        actor_id=principal.user_id,
        action="updated",
        source=source,
        before=before,
        after=knowledge_source_lifecycle_snapshot(source),
    )
    session.commit()
    session.refresh(source)
    return _knowledge_source_response(session, source)


@router.post(
    "/{agent_id}/knowledge/sources/{source_id}/disable",
    response_model=KnowledgeSourceResponse,
    summary="停用知识源",
)
def disable_agent_knowledge_source(
    agent_id: str,
    source_id: str,
    request: KnowledgeSourceActionRequest,
    session: DbSession,
    principal: Principal,
) -> KnowledgeSourceResponse:
    return _transition_knowledge_source(
        agent_id=agent_id,
        source_id=source_id,
        request=request,
        session=session,
        principal=principal,
        action="disabled",
        status_value=SOURCE_STATUS_DISABLED,
    )


@router.post(
    "/{agent_id}/knowledge/sources/{source_id}/enable",
    response_model=KnowledgeSourceResponse,
    summary="启用知识源",
)
def enable_agent_knowledge_source(
    agent_id: str,
    source_id: str,
    request: KnowledgeSourceActionRequest,
    session: DbSession,
    principal: Principal,
) -> KnowledgeSourceResponse:
    return _transition_knowledge_source(
        agent_id=agent_id,
        source_id=source_id,
        request=request,
        session=session,
        principal=principal,
        action="enabled",
        status_value=SOURCE_STATUS_ACTIVE,
    )


@router.post(
    "/{agent_id}/knowledge/sources/{source_id}/archive",
    response_model=KnowledgeSourceResponse,
    summary="归档知识源",
)
def archive_agent_knowledge_source(
    agent_id: str,
    source_id: str,
    request: KnowledgeSourceActionRequest,
    session: DbSession,
    principal: Principal,
) -> KnowledgeSourceResponse:
    return _transition_knowledge_source(
        agent_id=agent_id,
        source_id=source_id,
        request=request,
        session=session,
        principal=principal,
        action="archived",
        status_value=SOURCE_STATUS_ARCHIVED,
    )


@router.delete(
    "/{agent_id}/knowledge/sources/{source_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="永久删除知识源",
)
def delete_agent_knowledge_source(
    agent_id: str,
    source_id: str,
    session: DbSession,
    principal: Principal,
) -> None:
    require_role(principal, {"admin", "engineer"})
    _get_agent(agent_id=agent_id, session=session, principal=principal)
    source = _visible_knowledge_source_or_404(
        session=session,
        principal=principal,
        agent_id=agent_id,
        source_id=source_id,
    )
    _require_org_source_admin(source=source, principal=principal)
    _delete_knowledge_source(
        source=source,
        session=session,
        principal=principal,
    )


@router.post(
    "/{agent_id}/knowledge/sources/{source_id}/scope",
    response_model=KnowledgeSourceResponse,
    summary="变更知识源作用域",
)
def change_agent_knowledge_source_scope(
    agent_id: str,
    source_id: str,
    request: KnowledgeSourceScopeRequest,
    session: DbSession,
    principal: Principal,
) -> KnowledgeSourceResponse:
    require_role(principal, {"admin"})
    _get_agent(agent_id=agent_id, session=session, principal=principal)
    source = _visible_knowledge_source_or_404(
        session=session,
        principal=principal,
        agent_id=agent_id,
        source_id=source_id,
    )
    before = knowledge_source_lifecycle_snapshot(source)
    next_agent_id = None if request.scope == "org" else agent_id
    source.agent_id = next_agent_id
    source.updated_at = utc_now()
    _set_knowledge_source_scope_rows(
        session=session,
        source_id=source.id,
        agent_id=next_agent_id,
    )
    create_knowledge_lifecycle_audit(
        session,
        organization_id=principal.organization_id,
        actor_id=principal.user_id,
        action="scope_changed",
        source=source,
        before=before,
        after={
            **knowledge_source_lifecycle_snapshot(source),
            "reason": request.reason,
        },
    )
    session.commit()
    session.refresh(source)
    return _knowledge_source_response(session, source)


@router.get(
    "/{agent_id}/knowledge/sources/{source_id}/documents",
    response_model=list[KnowledgeDocumentResponse],
    summary="查询知识源文档版本",
)
def list_agent_knowledge_documents(
    agent_id: str,
    source_id: str,
    session: DbSession,
    principal: Principal,
) -> list[KnowledgeDocumentResponse]:
    require_role(principal, {"admin", "engineer", "operator"})
    _get_agent(agent_id=agent_id, session=session, principal=principal)
    source = _visible_knowledge_source_or_404(
        session=session,
        principal=principal,
        agent_id=agent_id,
        source_id=source_id,
    )
    return _knowledge_document_responses(session, source)


@router.post(
    "/{agent_id}/knowledge/sources/{source_id}/documents",
    response_model=KnowledgeSourceResponse,
    status_code=status.HTTP_201_CREATED,
    summary="向知识源添加文档",
)
def create_agent_knowledge_document(
    agent_id: str,
    source_id: str,
    request: KnowledgeDocumentCreateRequest,
    session: DbSession,
    principal: Principal,
) -> KnowledgeSourceResponse:
    require_role(principal, {"admin", "engineer"})
    _get_agent(agent_id=agent_id, session=session, principal=principal)
    source = _active_knowledge_source_or_409(
        session=session,
        principal=principal,
        agent_id=agent_id,
        source_id=source_id,
    )
    before = knowledge_source_lifecycle_snapshot(source)
    try:
        source, document, chunks, embeddings = agents_api.ingest_knowledge_source(
            session,
            organization_id=principal.organization_id,
            agent_id=source.agent_id,
            source_id=source.id,
            name=source.name,
            description=source.description,
            source_type=source.source_type,
            title=request.title,
            content=request.content,
            uri=request.uri,
            mime_type=request.mime_type,
            created_by=principal.user_id,
            idempotency_key=request.idempotency_key,
            create_new_logical_document=True,
        )
    except KnowledgeIngestionError as error:
        _commit_failed_knowledge_ingestion(
            session=session,
            principal=principal,
            action="document_import_failed",
            error=error,
            before=before,
            idempotency_key=request.idempotency_key,
        )
    _record_knowledge_ingestion_events(
        session=session,
        principal=principal,
        agent_id=agent_id,
        source=source,
        document=document,
        chunks=chunks,
        embeddings=embeddings,
        idempotency_key=request.idempotency_key,
        source_was_new=False,
    )
    create_knowledge_lifecycle_audit(
        session,
        organization_id=principal.organization_id,
        actor_id=principal.user_id,
        action="document_indexed",
        source=source,
        before=before,
        after=knowledge_source_lifecycle_snapshot(source),
        document_id=document.id,
        idempotency_key=request.idempotency_key,
    )
    session.commit()
    session.refresh(source)
    return _knowledge_source_response(session, source)


@router.post(
    "/{agent_id}/knowledge/sources/{source_id}/documents/import",
    response_model=KnowledgeSourceResponse,
    status_code=status.HTTP_201_CREATED,
    summary="通过 multipart 文件添加知识源文档",
)
async def import_agent_knowledge_document_file(
    agent_id: str,
    source_id: str,
    request: Request,
    session: DbSession,
    principal: Principal,
) -> KnowledgeSourceResponse:
    _active_knowledge_source_or_409(
        session=session,
        principal=principal,
        agent_id=agent_id,
        source_id=source_id,
    )
    upload = await _parse_knowledge_multipart_upload(request)
    payload = KnowledgeDocumentCreateRequest(
        title=upload["title"],
        content=upload["content"],
        uri=upload["filename"],
        mime_type=upload["mime_type"],
        idempotency_key=upload["idempotency_key"],
    )
    return create_agent_knowledge_document(
        agent_id=agent_id,
        source_id=source_id,
        request=payload,
        session=session,
        principal=principal,
    )


@router.post(
    "/{agent_id}/knowledge/sources/{source_id}/documents/{document_id}/versions",
    response_model=KnowledgeSourceResponse,
    status_code=status.HTTP_201_CREATED,
    summary="为文档创建新版本",
)
def create_agent_knowledge_document_version(
    agent_id: str,
    source_id: str,
    document_id: str,
    request: KnowledgeDocumentCreateRequest,
    session: DbSession,
    principal: Principal,
) -> KnowledgeSourceResponse:
    source = _active_knowledge_source_or_409(
        session=session,
        principal=principal,
        agent_id=agent_id,
        source_id=source_id,
    )
    document = session.get(KnowledgeDocument, document_id)
    if document is None or document.source_id != source.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    before = knowledge_source_lifecycle_snapshot(source)
    try:
        source, new_document, chunks, embeddings = agents_api.ingest_knowledge_source(
            session,
            organization_id=principal.organization_id,
            agent_id=source.agent_id,
            source_id=source.id,
            name=source.name,
            description=source.description,
            source_type=source.source_type,
            title=request.title,
            content=request.content,
            uri=request.uri,
            mime_type=request.mime_type,
            created_by=principal.user_id,
            idempotency_key=request.idempotency_key,
            reingest_document_id=document.id,
        )
    except KnowledgeIngestionError as error:
        _commit_failed_knowledge_ingestion(
            session=session,
            principal=principal,
            action="document_reingest_failed",
            error=error,
            before=before,
            idempotency_key=request.idempotency_key,
        )
    _record_knowledge_ingestion_events(
        session=session,
        principal=principal,
        agent_id=agent_id,
        source=source,
        document=new_document,
        chunks=chunks,
        embeddings=embeddings,
        idempotency_key=request.idempotency_key,
        source_was_new=False,
    )
    create_knowledge_lifecycle_audit(
        session,
        organization_id=principal.organization_id,
        actor_id=principal.user_id,
        action="document_versioned",
        source=source,
        before=before,
        after=knowledge_source_lifecycle_snapshot(source),
        document_id=new_document.id,
        idempotency_key=request.idempotency_key,
    )
    session.commit()
    session.refresh(source)
    return _knowledge_source_response(session, source)


@router.post(
    "/{agent_id}/knowledge/sources/{source_id}/documents/{document_id}/versions/import",
    response_model=KnowledgeSourceResponse,
    status_code=status.HTTP_201_CREATED,
    summary="通过 multipart 文件创建文档新版本",
)
async def import_agent_knowledge_document_version_file(
    agent_id: str,
    source_id: str,
    document_id: str,
    request: Request,
    session: DbSession,
    principal: Principal,
) -> KnowledgeSourceResponse:
    source = _active_knowledge_source_or_409(
        session=session,
        principal=principal,
        agent_id=agent_id,
        source_id=source_id,
    )
    document = session.get(KnowledgeDocument, document_id)
    if document is None or document.source_id != source.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    upload = await _parse_knowledge_multipart_upload(request)
    payload = KnowledgeDocumentCreateRequest(
        title=upload["title"],
        content=upload["content"],
        uri=upload["filename"],
        mime_type=upload["mime_type"],
        idempotency_key=upload["idempotency_key"],
    )
    return create_agent_knowledge_document_version(
        agent_id=agent_id,
        source_id=source_id,
        document_id=document_id,
        request=payload,
        session=session,
        principal=principal,
    )
