"""Agent knowledge source and document management endpoints."""

# ruff: noqa: F401,F403,F405,I001,UP037
from ..common import *
import app.api.agents as agents_api
from .._capability_helpers import *
from .._grounding_helpers import *
from .._knowledge_helpers import *
from .._plan_helpers import *
from .._session_helpers import *
from .._tool_helpers import *
from .._workspace_chat_helpers import *


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
