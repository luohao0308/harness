"""Knowledge source visibility, lifecycle, and ingestion helpers."""

# ruff: noqa: F401,F403,F405,I001,UP037
from .common import *
from .chunking import *
from .connectors import *
from .settings import *


def list_knowledge_sources(
    session: Session,
    *,
    organization_id: str | None,
    agent_id: str,
) -> list[KnowledgeSource]:
    sources = list(
        session.execute(
            select(KnowledgeSource)
            .where(
                KnowledgeSource.organization_id == organization_id,
                or_(KnowledgeSource.agent_id == None, KnowledgeSource.agent_id == agent_id),  # noqa: E711
            )
            .order_by(KnowledgeSource.created_at.desc(), KnowledgeSource.id.asc())
        ).scalars()
    )
    return sources


def get_visible_knowledge_source(
    session: Session,
    *,
    organization_id: str | None,
    agent_id: str,
    source_id: str,
) -> KnowledgeSource | None:
    return session.execute(
        select(KnowledgeSource).where(
            KnowledgeSource.id == source_id,
            KnowledgeSource.organization_id == organization_id,
            or_(KnowledgeSource.agent_id == None, KnowledgeSource.agent_id == agent_id),  # noqa: E711
        )
    ).scalar_one_or_none()


def provider_release_state_matrix() -> dict[str, dict[str, str]]:
    return {
        provider: {
            "provider": provider,
            "label": str(details["label"]),
            "release_state": str(details["release_state"]),
        }
        for provider, details in connector_provider_release_matrix().items()
    }


def normalize_connector_contract(
    *,
    source_type: str,
    uri: str | None,
    connector_provider: str | None = None,
    release_state: str | None = None,
    endpoint: str | None = None,
    auth_secret_ref: str | None = None,
    sync_mode: str = "manual",
    connector_metadata: dict | None = None,
) -> tuple[dict, dict]:
    provider = (
        (connector_provider or (source_type if source_type in CONNECTOR_SOURCE_TYPES else ""))
        .strip()
        .lower()
    )
    if source_type in {"text", "markdown", "document", "project"} and not provider:
        return {}, {}
    if source_type == "connector" and not provider:
        raise KnowledgeConnectorValidationError(
            "connector_provider is required for connector sources"
        )
    if provider not in CONNECTOR_PROVIDER_RELEASE_MATRIX:
        raise KnowledgeConnectorValidationError(f"unsupported connector provider: {provider}")
    normalized_release = (
        (release_state or str(CONNECTOR_PROVIDER_RELEASE_MATRIX[provider]["release_state"]))
        .strip()
        .lower()
    )
    if normalized_release not in CONNECTOR_RELEASE_STATES:
        raise KnowledgeConnectorValidationError("invalid connector release_state")
    normalized_sync = (sync_mode or "manual").strip().lower()
    if normalized_sync not in CONNECTOR_ALLOWED_SYNC_MODES:
        raise KnowledgeConnectorValidationError(
            "connector sync_mode must be manual, scheduled, or reindex"
        )
    metadata = connector_metadata or {}
    if _contains_raw_secret(metadata):
        raise KnowledgeConnectorValidationError(
            "connector metadata must use secret refs, not raw secrets"
        )
    if _endpoint_has_userinfo(endpoint or uri):
        raise KnowledgeConnectorValidationError("connector endpoint must not include credentials")
    crawler_flags = {"crawl", "crawler", "recursive", "follow_links"}
    if any(flag in metadata for flag in crawler_flags):
        raise KnowledgeConnectorValidationError("crawler-style connector behavior is out of scope")
    if "max_depth" in metadata:
        raise KnowledgeConnectorValidationError("recursive connector depth is out of scope")
    if connector_requires_secret_ref(provider) and not auth_secret_ref:
        raise KnowledgeConnectorValidationError(f"{provider} connector requires auth_secret_ref")
    if connector_requires_endpoint(provider) and not (endpoint or uri):
        raise KnowledgeConnectorValidationError(f"{provider} connector requires endpoint or uri")
    if provider == "postgres" and not (metadata.get("read_only") or metadata.get("policy_bound")):
        raise KnowledgeConnectorValidationError(
            "postgres connector must be read_only or policy_bound"
        )
    settings = {
        "schema_version": "knowledge-connector-v1",
        "provider": provider,
        "provider_label": connector_provider_label(provider),
        "release_state": normalized_release,
        "endpoint": endpoint or uri,
        "auth_secret_ref": auth_secret_ref,
        "sync_mode": normalized_sync,
        "secret_storage": "secret_ref_only" if auth_secret_ref else "not_required",
        "no_crawler_path": True,
        "metadata": metadata,
    }
    manifest = {
        "connector": {
            "provider": provider,
            "provider_label": connector_provider_label(provider),
            "release_state": normalized_release,
            "usable_for_release": normalized_release == CONNECTOR_RELEASE_USABLE,
            "sync_mode": normalized_sync,
            "health": (
                SOURCE_HEALTH_HEALTHY
                if normalized_release == CONNECTOR_RELEASE_USABLE
                else SOURCE_HEALTH_ERROR
            ),
            "evidence_contract": {
                "source_id": True,
                "document_id": True,
                "retrieval_hit_id": True,
                "citation_id": True,
                "policy_decision": True,
            },
            "provider_release_state_matrix": provider_release_state_matrix(),
        }
    }
    return settings, manifest


def knowledge_source_lifecycle_snapshot(source: KnowledgeSource) -> dict:
    settings_json = source.settings_json if isinstance(source.settings_json, dict) else {}
    return {
        "name": source.name,
        "description": source.description,
        "status": source.status,
        "agent_id": source.agent_id,
        "expires_at": source.expires_at.isoformat() if source.expires_at else None,
        "disabled_at": source.disabled_at.isoformat() if source.disabled_at else None,
        "archived_at": source.archived_at.isoformat() if source.archived_at else None,
        "health_status": source.health_status,
        "connector_provider": connector_provider_key(settings_json, source_type=source.source_type),
        "connector_release_state": connector_release_state(
            settings_json,
            source_type=source.source_type,
        ),
        "connector_counts_toward_complete_usable": connector_counts_toward_complete_usable(
            settings_json,
            source_type=source.source_type,
        ),
        "connector_settings_json": settings_json,
    }


def create_knowledge_lifecycle_audit(
    session: Session,
    *,
    organization_id: str | None,
    actor_id: str | None,
    action: str,
    source: KnowledgeSource,
    before: dict | None,
    after: dict | None,
    document_id: str | None = None,
    idempotency_key: str | None = None,
    request_id: str | None = None,
) -> AdminAuditEvent:
    event = AdminAuditEvent(
        organization_id=organization_id,
        actor_id=actor_id,
        event_type=f"knowledge_source.{action}",
        resource_type="knowledge_source",
        resource_id=source.id,
        action=action,
        payload_json={
            "schema_version": "knowledge-lifecycle-v1",
            "org_id": organization_id,
            "agent_id": source.agent_id,
            "actor_user_id": actor_id,
            "source_id": source.id,
            "document_id": document_id,
            "before": before,
            "after": after,
            "request_id": request_id,
            "idempotency_key": idempotency_key,
            "timestamp": utc_now().isoformat(),
        },
        created_at=utc_now(),
    )
    session.add(event)
    session.flush()
    return event


def ingest_knowledge_source(
    session: Session,
    *,
    organization_id: str | None,
    agent_id: str | None,
    name: str,
    description: str,
    source_type: str,
    title: str,
    content: str,
    uri: str | None,
    mime_type: str,
    created_by: str | None,
    idempotency_key: str | None = None,
    connector_settings_json: dict | None = None,
    source_id: str | None = None,
    create_new_logical_document: bool = False,
    reingest_document_id: str | None = None,
) -> tuple[KnowledgeSource, KnowledgeDocument, list[KnowledgeChunk], list[KnowledgeEmbedding]]:
    normalized_content = _normalize_text(content)
    content_sha256 = _sha256(normalized_content)
    now = utc_now()
    source = None
    if source_id:
        source = session.execute(
            select(KnowledgeSource).where(
                KnowledgeSource.id == source_id,
                KnowledgeSource.organization_id == organization_id,
            )
        ).scalar_one_or_none()
        if source is None:
            raise ValueError("knowledge source not found")
    if source is None and idempotency_key:
        source = session.execute(
            select(KnowledgeSource).where(
                KnowledgeSource.organization_id == organization_id,
                KnowledgeSource.agent_id == agent_id,
                KnowledgeSource.idempotency_key == idempotency_key,
            )
        ).scalar_one_or_none()
    if source is None:
        source = session.execute(
            select(KnowledgeSource)
            .where(
                KnowledgeSource.organization_id == organization_id,
                KnowledgeSource.agent_id == agent_id,
                KnowledgeSource.name == name,
            )
            .order_by(KnowledgeSource.version.desc(), KnowledgeSource.created_at.desc())
        ).scalar_one_or_none()
    if source is None:
        normalized_connector_settings = normalize_connector_settings(
            connector_settings_json,
            source_type=source_type,
        )
        source = KnowledgeSource(
            organization_id=organization_id,
            agent_id=agent_id,
            name=name,
            description=description,
            source_type=source_type,
            status=SOURCE_STATUS_ACTIVE,
            version=1,
            expires_at=None,
            disabled_at=None,
            archived_at=None,
            last_indexed_at=now,
            last_ingestion_error=None,
            health_status=SOURCE_HEALTH_HEALTHY,
            settings_json=normalized_connector_settings,
            metadata_json={},
            idempotency_key=idempotency_key,
            created_by=created_by,
            created_at=now,
            updated_at=now,
        )
        session.add(source)
        session.flush()
    elif source.status != SOURCE_STATUS_ARCHIVED:
        if connector_settings_json is not None:
            source.settings_json = normalize_connector_settings(
                connector_settings_json,
                source_type=source_type,
            )
        source.description = description
        source.source_type = source_type
        source.updated_at = now
    if source_type.startswith("connector:"):
        provider = source_type.split(":", 1)[1]
        source.settings_json = {
            **(source.settings_json if isinstance(source.settings_json, dict) else {}),
            "provider": provider,
        }
        source.metadata_json = {
            **(source.metadata_json if isinstance(source.metadata_json, dict) else {}),
            "connector_provider": provider,
        }
        apply_connector_contract(source)

    previous_document = session.execute(
        select(KnowledgeDocument)
        .where(
            KnowledgeDocument.source_id == source.id,
            KnowledgeDocument.idempotency_key == idempotency_key,
            KnowledgeDocument.content_sha256 == content_sha256,
            KnowledgeDocument.status == DOCUMENT_STATUS_INDEXED,
        )
        .order_by(KnowledgeDocument.version.desc(), KnowledgeDocument.created_at.desc())
        .limit(1)
    ).scalar_one_or_none()
    if previous_document is not None:
        chunks = list(
            session.execute(
                select(KnowledgeChunk)
                .where(KnowledgeChunk.document_id == previous_document.id)
                .order_by(KnowledgeChunk.chunk_index.asc())
            ).scalars()
        )
        embeddings = list(
            session.execute(
                select(KnowledgeEmbedding)
                .join(KnowledgeChunk, KnowledgeEmbedding.chunk_id == KnowledgeChunk.id)
                .where(KnowledgeChunk.document_id == previous_document.id)
                .order_by(KnowledgeChunk.chunk_index.asc())
            ).scalars()
        )
        return source, previous_document, chunks, embeddings

    previous_version = None
    if reingest_document_id is not None:
        previous_version = session.get(KnowledgeDocument, reingest_document_id)
        if previous_version is None or previous_version.source_id != source.id:
            raise ValueError("knowledge document not found")
    elif not create_new_logical_document:
        previous_version = session.execute(
            select(KnowledgeDocument)
            .where(KnowledgeDocument.source_id == source.id)
            .order_by(KnowledgeDocument.version.desc(), KnowledgeDocument.created_at.desc())
            .limit(1)
        ).scalar_one_or_none()
    logical_document_id = (
        (previous_version.logical_document_id or previous_version.id)
        if previous_version is not None
        else None
    )
    next_version = 1
    if logical_document_id is not None:
        latest_logical_version = session.execute(
            select(KnowledgeDocument)
            .where(
                KnowledgeDocument.source_id == source.id,
                KnowledgeDocument.logical_document_id == logical_document_id,
            )
            .order_by(KnowledgeDocument.version.desc(), KnowledgeDocument.created_at.desc())
            .limit(1)
        ).scalar_one_or_none()
        if latest_logical_version is not None:
            next_version = latest_logical_version.version + 1
            if latest_logical_version.status == DOCUMENT_STATUS_INDEXED:
                previous_version = latest_logical_version
            else:
                latest_indexed_version = session.execute(
                    select(KnowledgeDocument)
                    .where(
                        KnowledgeDocument.source_id == source.id,
                        KnowledgeDocument.logical_document_id == logical_document_id,
                        KnowledgeDocument.status == DOCUMENT_STATUS_INDEXED,
                    )
                    .order_by(
                        KnowledgeDocument.version.desc(),
                        KnowledgeDocument.created_at.desc(),
                    )
                    .limit(1)
                ).scalar_one_or_none()
                if latest_indexed_version is not None:
                    previous_version = latest_indexed_version
    chunk_specs = _chunk_text(normalized_content)
    import app.knowledge as knowledge_api

    if len(chunk_specs) > knowledge_api.MAX_INGESTION_CHUNKS:
        failed_document = KnowledgeDocument(
            source_id=source.id,
            organization_id=organization_id,
            agent_id=source.agent_id,
            title=title,
            uri=uri,
            content_sha256=content_sha256,
            mime_type=mime_type,
            status=DOCUMENT_STATUS_FAILED,
            version=next_version,
            logical_document_id=logical_document_id,
            supersedes_document_id=previous_version.id if previous_version is not None else None,
            ingestion_error=(
                f"knowledge source produced {len(chunk_specs)} chunks; "
                f"maximum is {knowledge_api.MAX_INGESTION_CHUNKS}"
            ),
            metadata_json={},
            idempotency_key=idempotency_key,
            created_by=created_by,
            created_at=now,
            updated_at=now,
            indexed_at=None,
        )
        session.add(failed_document)
        session.flush()
        if failed_document.logical_document_id is None:
            failed_document.logical_document_id = (
                previous_version.logical_document_id
                if previous_version is not None
                else failed_document.id
            )
        source.health_status = SOURCE_HEALTH_ERROR
        source.last_ingestion_error = failed_document.ingestion_error
        source.updated_at = now
        session.flush()
        raise KnowledgeIngestionError(
            source.last_ingestion_error,
            source=source,
            document=failed_document,
        )
    document = KnowledgeDocument(
        source_id=source.id,
        organization_id=organization_id,
        agent_id=source.agent_id,
        title=title,
        uri=uri,
        content_sha256=content_sha256,
        mime_type=mime_type,
        status=DOCUMENT_STATUS_INDEXED,
        version=next_version,
        logical_document_id=logical_document_id,
        supersedes_document_id=previous_version.id if previous_version is not None else None,
        metadata_json=(
            {
                "connector_config_only": True,
                "retrieval_eligible": False,
            }
            if source.source_type == "connector"
            else {}
        ),
        idempotency_key=idempotency_key,
        created_by=created_by,
        created_at=now,
        updated_at=now,
        indexed_at=now,
    )
    session.add(document)
    session.flush()
    if document.logical_document_id is None:
        document.logical_document_id = document.id

    if previous_version is not None:
        previous_version.status = DOCUMENT_STATUS_SUPERSEDED
        previous_version.superseded_at = now
        previous_version.updated_at = now
        for chunk in session.execute(
            select(KnowledgeChunk).where(KnowledgeChunk.document_id == previous_version.id)
        ).scalars():
            chunk.status = CHUNK_STATUS_STALE

    chunks: list[KnowledgeChunk] = []
    embeddings: list[KnowledgeEmbedding] = []
    capability = vector_capability(session, organization_id)
    for index, (start_offset, end_offset, chunk_text) in enumerate(chunk_specs, start=1):
        chunk = KnowledgeChunk(
            document_id=document.id,
            source_id=source.id,
            organization_id=organization_id,
            agent_id=source.agent_id,
            source_version=source.version,
            document_version=document.version,
            chunk_version=1,
            chunk_index=index,
            text=chunk_text,
            text_sha256=_sha256(chunk_text),
            start_offset=start_offset,
            end_offset=end_offset,
            status=CHUNK_STATUS_ACTIVE,
            metadata_json={},
            created_at=now,
        )
        session.add(chunk)
        session.flush()
        chunks.append(chunk)
        embedding = KnowledgeEmbedding(
            chunk_id=chunk.id,
            organization_id=organization_id,
            agent_id=source.agent_id,
            provider="deterministic",
            model="hash-embedding",
            model_version="v1",
            dimensions=24,
            embedding_vector=json.dumps(_fake_embedding(chunk_text, dimensions=24)),
            embedding_json=_fake_embedding(chunk_text, dimensions=24),
            status="READY" if capability != VECTOR_CAPABILITY_DISABLED else "UNAVAILABLE",
            created_at=now,
            updated_at=now,
        )
        session.add(embedding)
        session.flush()
        embeddings.append(embedding)

    source.updated_at = now
    source.last_indexed_at = now
    source.last_ingestion_error = None
    source.health_status = SOURCE_HEALTH_HEALTHY
    session.flush()
    return source, document, chunks, embeddings


__all__ = [name for name in globals() if not name.startswith("__") and name != "annotations"]
