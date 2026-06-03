"""Knowledge source lifecycle helpers for Agent API endpoints."""

# ruff: noqa: F401,F403,F405,I001,UP037
from .common import *
from ._session_helpers import *

def _knowledge_source_exists(
    *,
    session: Session,
    organization_id: str | None,
    agent_id: str | None,
    name: str,
    idempotency_key: str | None,
) -> bool:
    statement = select(KnowledgeSource).where(
        KnowledgeSource.organization_id == organization_id,
        KnowledgeSource.agent_id == agent_id,
    )
    if idempotency_key:
        statement = statement.where(KnowledgeSource.idempotency_key == idempotency_key)
    else:
        statement = statement.where(KnowledgeSource.name == name)
    return session.execute(statement.limit(1)).scalar_one_or_none() is not None


def _visible_knowledge_source_or_404(
    *,
    session: Session,
    principal: Principal,
    agent_id: str,
    source_id: str,
) -> KnowledgeSource:
    source = get_visible_knowledge_source(
        session,
        organization_id=principal.organization_id,
        agent_id=agent_id,
        source_id=source_id,
    )
    if source is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Knowledge source not found",
        )
    return source


def _store_knowledge_connector_secret(
    *,
    session: Session,
    principal: Principal,
    source: KnowledgeSource,
    secret_value: str,
) -> None:
    settings = source.settings_json if isinstance(source.settings_json, dict) else {}
    provider = connector_provider_key(settings, source_type=source.source_type)
    secret_ref = str(settings.get("secret_ref") or settings.get("auth_secret_ref") or "").strip()
    try:
        store_connector_secret_ref(
            session,
            organization_id=principal.organization_id,
            actor_id=principal.user_id,
            secret_ref=secret_ref,
            provider=provider,
            secret_value=secret_value,
        )
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error)) from error
    session.add(
        AdminAuditEvent(
            organization_id=principal.organization_id,
            actor_id=principal.user_id,
            event_type="knowledge_connector.secret_saved",
            resource_type="knowledge_source",
            resource_id=source.id,
            action="connector_secret_saved",
            payload_json={
                "schema_version": "knowledge-connector-secret-v1",
                "source_id": source.id,
                "provider": provider,
                "secret_ref": secret_ref,
                "secret_configured": True,
                "secret_value_present": bool(secret_value.strip()),
            },
            created_at=utc_now(),
        )
    )


def _active_knowledge_source_or_409(
    *,
    session: Session,
    principal: Principal,
    agent_id: str,
    source_id: str,
) -> KnowledgeSource:
    require_role(principal, {"admin", "engineer"})
    _get_agent(agent_id=agent_id, session=session, principal=principal)
    source = _visible_knowledge_source_or_404(
        session=session,
        principal=principal,
        agent_id=agent_id,
        source_id=source_id,
    )
    if source.status != SOURCE_STATUS_ACTIVE:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Knowledge source is not active",
        )
    _require_org_source_admin(source=source, principal=principal)
    return source


def _require_org_source_admin(*, source: KnowledgeSource, principal: Principal) -> None:
    if source.agent_id is None:
        require_role(principal, {"admin"})


async def _parse_knowledge_multipart_upload(request: Request) -> dict[str, str | None]:
    content_type = request.headers.get("content-type", "")
    if "multipart/form-data" not in content_type:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Expected multipart/form-data",
        )
    content_length = request.headers.get("content-length")
    if content_length is not None:
        try:
            declared_length = int(content_length)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid Content-Length",
            ) from exc
        if declared_length > KNOWLEDGE_UPLOAD_MAX_MULTIPART_BYTES:
            raise HTTPException(
                status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                detail="Multipart upload too large",
            )
    body_parts: list[bytes] = []
    body_size = 0
    async for chunk in request.stream():
        body_size += len(chunk)
        if body_size > KNOWLEDGE_UPLOAD_MAX_MULTIPART_BYTES:
            raise HTTPException(
                status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                detail="Multipart upload too large",
            )
        body_parts.append(chunk)
    body = b"".join(body_parts)
    message = BytesParser(policy=email_default_policy).parsebytes(
        b"Content-Type: " + content_type.encode("utf-8") + b"\r\nMIME-Version: 1.0\r\n\r\n" + body
    )
    fields: dict[str, str] = {}
    file_payload: bytes | None = None
    filename: str | None = None
    mime_type: str | None = None
    for part in message.iter_parts():
        name = part.get_param("name", header="content-disposition")
        if not name:
            continue
        part_filename = part.get_filename()
        payload = part.get_payload(decode=True) or b""
        if part_filename:
            filename = part_filename
            mime_type = part.get_content_type()
            file_payload = payload
        else:
            fields[name] = payload.decode("utf-8", errors="replace")

    if file_payload is None or filename is None or mime_type is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="File is required")
    suffix = Path(filename).suffix.lower()
    if suffix not in KNOWLEDGE_UPLOAD_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only .txt/.md files are supported",
        )
    normalized_mime_type = "text/plain" if suffix == ".txt" else "text/markdown"
    if len(file_payload) > KNOWLEDGE_UPLOAD_MAX_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail="File too large",
        )
    try:
        content = file_payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File must be valid UTF-8 text",
        ) from exc
    if not content.strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="File is empty")
    title = fields.get("title") or Path(filename).stem or filename
    scope = fields.get("scope") or "agent"
    if scope not in {"agent", "org"}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid scope")
    return {
        "name": fields.get("name"),
        "description": fields.get("description", ""),
        "scope": scope,
        "title": title,
        "content": content,
        "filename": filename,
        "mime_type": normalized_mime_type,
        "idempotency_key": fields.get("idempotency_key") or None,
    }


def _set_knowledge_source_scope_rows(
    *,
    session: Session,
    source_id: str,
    agent_id: str | None,
) -> None:
    session.execute(
        update(KnowledgeDocument)
        .where(KnowledgeDocument.source_id == source_id)
        .values(agent_id=agent_id, updated_at=utc_now())
    )
    session.execute(
        update(KnowledgeChunk)
        .where(KnowledgeChunk.source_id == source_id)
        .values(agent_id=agent_id)
    )
    session.execute(
        update(KnowledgeEmbedding)
        .where(
            KnowledgeEmbedding.chunk_id.in_(
                select(KnowledgeChunk.id).where(KnowledgeChunk.source_id == source_id)
            )
        )
        .values(agent_id=agent_id, updated_at=utc_now())
    )


def _transition_knowledge_source(
    *,
    agent_id: str,
    source_id: str,
    request: KnowledgeSourceActionRequest,
    session: Session,
    principal: Principal,
    action: str,
    status_value: str,
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
    if source.status == SOURCE_STATUS_ARCHIVED and status_value != SOURCE_STATUS_ARCHIVED:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Archived knowledge source cannot be re-enabled in P2",
        )
    before = knowledge_source_lifecycle_snapshot(source)
    now = utc_now()
    source.status = status_value
    source.updated_at = now
    if status_value == SOURCE_STATUS_DISABLED:
        source.disabled_at = now
    elif status_value == SOURCE_STATUS_ACTIVE:
        source.disabled_at = None
        source.health_status = SOURCE_HEALTH_HEALTHY
    elif status_value == SOURCE_STATUS_ARCHIVED:
        source.archived_at = now
    create_knowledge_lifecycle_audit(
        session,
        organization_id=principal.organization_id,
        actor_id=principal.user_id,
        action=action,
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


def _delete_knowledge_source(
    *,
    source: KnowledgeSource,
    session: Session,
    principal: Principal,
) -> None:
    before = knowledge_source_lifecycle_snapshot(source)
    document_ids = list(
        session.execute(
            select(KnowledgeDocument.id).where(KnowledgeDocument.source_id == source.id)
        ).scalars()
    )
    chunk_ids = list(
        session.execute(
            select(KnowledgeChunk.id).where(KnowledgeChunk.source_id == source.id)
        ).scalars()
    )
    create_knowledge_lifecycle_audit(
        session,
        organization_id=principal.organization_id,
        actor_id=principal.user_id,
        action="deleted",
        source=source,
        before=before,
        after={
            "status": "DELETED",
            "agent_id": source.agent_id,
            "reason": "permanent_delete",
            "deleted_document_count": len(document_ids),
            "deleted_chunk_count": len(chunk_ids),
        },
    )
    if chunk_ids:
        session.execute(
            update(CitationRecord)
            .where(CitationRecord.chunk_id.in_(chunk_ids))
            .values(chunk_id=None)
        )
        session.execute(
            update(RetrievalHit)
            .where(RetrievalHit.chunk_id.in_(chunk_ids))
            .values(chunk_id=None)
        )
    if document_ids:
        session.execute(
            update(RetrievalHit)
            .where(RetrievalHit.document_id.in_(document_ids))
            .values(document_id=None)
        )
    session.execute(
        update(WorkspaceContextCache)
        .where(
            WorkspaceContextCache.organization_id == principal.organization_id,
            WorkspaceContextCache.cache_source == "rag_retrieval",
            WorkspaceContextCache.status == "active",
        )
        .values(
            status="stale",
            metadata_json={
                "reason": "knowledge_source_deleted",
                "source_id": source.id,
            },
            updated_at=utc_now(),
        )
    )
    session.execute(
        delete(KnowledgeEmbedding).where(
            KnowledgeEmbedding.chunk_id.in_(
                select(KnowledgeChunk.id).where(KnowledgeChunk.source_id == source.id)
            )
        )
    )
    session.execute(delete(KnowledgeChunk).where(KnowledgeChunk.source_id == source.id))
    if document_ids:
        session.execute(
            update(KnowledgeDocument)
            .where(KnowledgeDocument.supersedes_document_id.in_(document_ids))
            .values(supersedes_document_id=None)
        )
    session.execute(delete(KnowledgeDocument).where(KnowledgeDocument.source_id == source.id))
    session.delete(source)
    session.commit()


def _commit_failed_knowledge_ingestion(
    *,
    session: Session,
    principal: Principal,
    action: str,
    error: KnowledgeIngestionError,
    before: dict | None,
    idempotency_key: str | None,
) -> None:
    create_knowledge_lifecycle_audit(
        session,
        organization_id=principal.organization_id,
        actor_id=principal.user_id,
        action=action,
        source=error.source,
        before=before,
        after={
            **knowledge_source_lifecycle_snapshot(error.source),
            "error": str(error),
        },
        document_id=error.document.id,
        idempotency_key=idempotency_key,
    )
    session.commit()
    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error))


def _record_knowledge_ingestion_events(
    *,
    session: Session,
    principal: Principal,
    agent_id: str,
    source: KnowledgeSource,
    document: KnowledgeDocument,
    chunks: list[KnowledgeChunk],
    embeddings: list[KnowledgeEmbedding],
    idempotency_key: str | None,
    source_was_new: bool,
) -> None:
    now = utc_now()
    audit_task = Task(
        organization_id=principal.organization_id,
        agent_id=agent_id,
        created_by=principal.user_id,
        title=f"Knowledge ingestion: {source.name}",
        goal=f"Index knowledge document {document.title}",
        status="COMPLETED",
        model_provider="system",
        model_name="knowledge-harness",
        max_runtime_seconds=0,
        max_subagents=0,
        enable_sandbox=False,
        enable_network=False,
        created_at=now,
        updated_at=now,
        completed_at=now,
    )
    session.add(audit_task)
    session.flush()
    event_store = EventStore(session)
    base_payload = {
        "schema_version": "knowledge-grounding-v1",
        "org_id": principal.organization_id,
        "agent_id": agent_id,
        "run_id": audit_task.id,
        "correlation_id": audit_task.id,
        "causation_id": audit_task.id,
        "idempotency_key": idempotency_key,
        "source_id": source.id,
        "document_id": document.id,
    }
    if source_was_new:
        event_store.append(
            task_id=audit_task.id,
            event_type=EventType.KNOWLEDGE_SOURCE_CREATED,
            payload_json={
                **base_payload,
                "source_type": source.source_type,
                "source_version": source.version,
            },
            actor_type="user",
            actor_id=principal.user_id,
        )
    event_store.append(
        task_id=audit_task.id,
        event_type=EventType.KNOWLEDGE_DOCUMENT_INDEXED,
        payload_json={
            **base_payload,
            "document_version": document.version,
            "chunk_ids": [chunk.id for chunk in chunks],
            "chunk_count": len(chunks),
            "embedding_ids": [embedding.id for embedding in embeddings],
        },
        actor_type="user",
        actor_id=principal.user_id,
    )

def _knowledge_source_response(
    session: Session,
    source: KnowledgeSource,
) -> KnowledgeSourceResponse:
    latest_documents = _knowledge_document_responses(session, source, limit=5)
    validation_status, validation_messages = connector_validation_status(source)
    settings_json = source.settings_json if isinstance(source.settings_json, dict) else {}
    response_settings_json = _safe_connector_settings_for_response(settings_json)
    secret_ref = str(settings_json.get("secret_ref") or settings_json.get("auth_secret_ref") or "")
    return KnowledgeSourceResponse(
        id=source.id,
        organization_id=source.organization_id,
        agent_id=source.agent_id,
        name=source.name,
        description=source.description,
        source_type=source.source_type,
        status=source.status,
        version=source.version,
        scope="org" if source.agent_id is None else "agent",
        expires_at=source.expires_at,
        disabled_at=source.disabled_at,
        archived_at=source.archived_at,
        last_indexed_at=source.last_indexed_at,
        last_ingestion_error=source.last_ingestion_error,
        health_status=source.health_status,
        connector_provider=connector_provider_key(
            settings_json,
            source_type=source.source_type,
        ),
        connector_release_state=connector_release_state(
            settings_json,
            source_type=source.source_type,
        ),
        connector_counts_toward_complete_usable=connector_counts_toward_complete_usable(
            settings_json,
            source_type=source.source_type,
        ),
        connector_validation_status=validation_status,
        connector_validation_messages=validation_messages,
        connector_secret_configured=bool(
            read_connector_secret_ref(
                session,
                organization_id=source.organization_id,
                secret_ref=secret_ref,
            )
        ),
        settings_json=response_settings_json,
        metadata_json=source.metadata_json if isinstance(source.metadata_json, dict) else {},
        idempotency_key=source.idempotency_key,
        created_by=source.created_by,
        created_at=source.created_at,
        updated_at=source.updated_at,
        latest_documents=latest_documents,
    )


def _safe_connector_settings_for_response(settings: dict) -> dict:
    safe_settings = dict(settings)
    secret_ref = str(safe_settings.get("secret_ref") or "").strip()
    if secret_ref_looks_like_raw_secret(secret_ref):
        safe_settings["secret_ref"] = "[REDACTED_RAW_SECRET_REF]"
        safe_settings["secret_ref_invalid"] = True
    return safe_settings


def _knowledge_document_responses(
    session: Session,
    source: KnowledgeSource,
    *,
    limit: int | None = None,
) -> list[KnowledgeDocumentResponse]:
    statement = (
        select(KnowledgeDocument)
        .where(KnowledgeDocument.source_id == source.id)
        .order_by(KnowledgeDocument.version.desc(), KnowledgeDocument.created_at.desc())
    )
    if limit is not None:
        statement = statement.limit(limit)
    documents = list(session.execute(statement).scalars())
    document_ids = [document.id for document in documents]
    chunk_counts = (
        dict(
            session.execute(
                select(KnowledgeChunk.document_id, func.count(KnowledgeChunk.id))
                .where(
                    KnowledgeChunk.document_id.in_(document_ids),
                    KnowledgeChunk.status == "ACTIVE",
                )
                .group_by(KnowledgeChunk.document_id)
            ).all()
        )
        if document_ids
        else {}
    )
    return [
        KnowledgeDocumentResponse.model_validate(document).model_copy(
            update={"chunk_count": int(chunk_counts.get(document.id, 0))}
        )
        for document in documents
    ]

__all__ = [name for name in globals() if not name.startswith("__") and name != "annotations"]
