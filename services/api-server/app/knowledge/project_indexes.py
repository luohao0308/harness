"""Durable project Knowledge binding lifecycle shared by API and sync workers."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from pathlib import PurePosixPath

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.db.models import (
    AdminAuditEvent,
    KnowledgeChunk,
    KnowledgeDocument,
    KnowledgeSource,
    ProjectKnowledgeFile,
    ProjectKnowledgeIndex,
    WorkspaceContextCache,
    new_uuid,
    utc_now,
)

from .common import (
    CHUNK_STATUS_STALE,
    DOCUMENT_STATUS_INDEXED,
    DOCUMENT_STATUS_SUPERSEDED,
    KnowledgeIngestionError,
)
from .lifecycle import ingest_knowledge_source

PROJECT_INDEX_ACTIVE = "ACTIVE"
PROJECT_INDEX_PAUSED = "PAUSED"
PROJECT_INDEX_ERROR = "ERROR"
PROJECT_INDEX_UNBOUND = "UNBOUND"

PROJECT_FILE_INDEXED = "INDEXED"
PROJECT_FILE_ERROR = "ERROR"
PROJECT_FILE_IGNORED = "IGNORED"
PROJECT_FILE_TOMBSTONED = "TOMBSTONED"

PROJECT_INDEX_SOURCE_TYPE = "project"
PROJECT_INDEX_SCHEMA_VERSION = "project-knowledge-index-v1"
PROJECT_INDEX_DEFAULT_IGNORE_VERSION = "v1"


class ProjectKnowledgeIndexConflict(ValueError):
    pass


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def list_project_knowledge_indexes(
    session: Session,
    *,
    organization_id: str,
    agent_id: str,
) -> list[ProjectKnowledgeIndex]:
    return list(
        session.execute(
            select(ProjectKnowledgeIndex)
            .where(
                ProjectKnowledgeIndex.organization_id == organization_id,
                ProjectKnowledgeIndex.agent_id == agent_id,
            )
            .order_by(
                ProjectKnowledgeIndex.created_at.desc(),
                ProjectKnowledgeIndex.id.asc(),
            )
        ).scalars()
    )


def get_project_knowledge_index(
    session: Session,
    *,
    organization_id: str,
    agent_id: str,
    index_id: str,
) -> ProjectKnowledgeIndex | None:
    return session.execute(
        select(ProjectKnowledgeIndex).where(
            ProjectKnowledgeIndex.id == index_id,
            ProjectKnowledgeIndex.organization_id == organization_id,
            ProjectKnowledgeIndex.agent_id == agent_id,
        )
    ).scalar_one_or_none()


def create_project_knowledge_index(
    session: Session,
    *,
    organization_id: str,
    agent_id: str,
    desktop_profile_id: str,
    root_identity: str,
    name: str,
    description: str,
    ignore_patterns: list[str],
    created_by: str | None,
    idempotency_key: str | None,
) -> tuple[ProjectKnowledgeIndex, bool]:
    if idempotency_key:
        receipt = session.execute(
            select(ProjectKnowledgeIndex).where(
                ProjectKnowledgeIndex.organization_id == organization_id,
                ProjectKnowledgeIndex.agent_id == agent_id,
                ProjectKnowledgeIndex.idempotency_key == idempotency_key,
            )
        ).scalar_one_or_none()
        if receipt is not None:
            if (
                receipt.desktop_profile_id != desktop_profile_id
                or receipt.root_identity != root_identity
            ):
                raise ProjectKnowledgeIndexConflict(
                    "Idempotency key is already bound to another project root"
                )
            return receipt, False

    existing = session.execute(
        select(ProjectKnowledgeIndex).where(
            ProjectKnowledgeIndex.organization_id == organization_id,
            ProjectKnowledgeIndex.agent_id == agent_id,
            ProjectKnowledgeIndex.desktop_profile_id == desktop_profile_id,
            ProjectKnowledgeIndex.root_identity == root_identity,
        )
    ).scalar_one_or_none()
    if existing is not None:
        if existing.status == PROJECT_INDEX_UNBOUND:
            _set_project_index_state(
                session,
                index=existing,
                status=PROJECT_INDEX_ACTIVE,
                actor_id=created_by,
                action="rebound",
                reason="same_root_rebound",
            )
            existing.name = name
            existing.description = description
            existing.ignore_patterns_json = list(ignore_patterns)
            existing.idempotency_key = idempotency_key
            existing.updated_at = utc_now()
            return existing, False
        raise ProjectKnowledgeIndexConflict("Project root is already bound")

    now = utc_now()
    index_id = new_uuid()
    source = KnowledgeSource(
        organization_id=organization_id,
        agent_id=agent_id,
        name=name,
        description=description,
        source_type=PROJECT_INDEX_SOURCE_TYPE,
        status="ACTIVE",
        version=1,
        last_indexed_at=None,
        last_ingestion_error=None,
        health_status="HEALTHY",
        settings_json={
            "schema_version": PROJECT_INDEX_SCHEMA_VERSION,
            "default_ignore_version": PROJECT_INDEX_DEFAULT_IGNORE_VERSION,
            "ignore_patterns": list(ignore_patterns),
        },
        metadata_json={
            "schema_version": "project-knowledge-source-v1",
            "project_index": {
                "index_id": index_id,
                "desktop_profile_id": desktop_profile_id,
                "root_identity": root_identity,
            },
        },
        idempotency_key=f"project-index:{index_id}",
        created_by=created_by,
        created_at=now,
        updated_at=now,
    )
    session.add(source)
    session.flush()
    index = ProjectKnowledgeIndex(
        id=index_id,
        organization_id=organization_id,
        agent_id=agent_id,
        knowledge_source_id=source.id,
        desktop_profile_id=desktop_profile_id,
        root_identity=root_identity,
        name=name,
        description=description,
        status=PROJECT_INDEX_ACTIVE,
        ignore_patterns_json=list(ignore_patterns),
        snapshot_generation=0,
        snapshot_cursor=None,
        last_snapshot_at=None,
        last_sync_at=None,
        last_error=None,
        idempotency_key=idempotency_key,
        unbound_at=None,
        created_by=created_by,
        created_at=now,
        updated_at=now,
    )
    session.add(index)
    session.flush()
    _record_project_index_audit(
        session,
        index=index,
        actor_id=created_by,
        action="created",
        reason=None,
    )
    return index, True


def pause_project_knowledge_index(
    session: Session,
    *,
    index: ProjectKnowledgeIndex,
    actor_id: str | None,
    reason: str | None,
) -> bool:
    if index.status == PROJECT_INDEX_UNBOUND:
        raise ProjectKnowledgeIndexConflict("Unbound project index cannot be paused")
    if index.status == PROJECT_INDEX_PAUSED:
        return False
    _set_project_index_state(
        session,
        index=index,
        status=PROJECT_INDEX_PAUSED,
        actor_id=actor_id,
        action="paused",
        reason=reason,
    )
    return True


def resume_project_knowledge_index(
    session: Session,
    *,
    index: ProjectKnowledgeIndex,
    actor_id: str | None,
    reason: str | None,
) -> bool:
    if index.status == PROJECT_INDEX_UNBOUND:
        raise ProjectKnowledgeIndexConflict("Unbound project index must be bound again")
    if index.status == PROJECT_INDEX_ACTIVE:
        return False
    _set_project_index_state(
        session,
        index=index,
        status=PROJECT_INDEX_ACTIVE,
        actor_id=actor_id,
        action="resumed",
        reason=reason,
    )
    return True


def unbind_project_knowledge_index(
    session: Session,
    *,
    index: ProjectKnowledgeIndex,
    actor_id: str | None,
    reason: str | None,
) -> bool:
    if index.status == PROJECT_INDEX_UNBOUND:
        return False
    _set_project_index_state(
        session,
        index=index,
        status=PROJECT_INDEX_UNBOUND,
        actor_id=actor_id,
        action="unbound",
        reason=reason,
    )
    return True


def sync_project_knowledge_snapshot(
    session: Session,
    *,
    index: ProjectKnowledgeIndex,
    snapshot_cursor: str,
    snapshot_generation: int | None,
    complete: bool,
    files: list[dict],
    snapshot_started_at,
    snapshot_completed_at,
    scan_errors: list[dict],
    actor_id: str | None,
) -> dict[str, int | bool]:
    # Serialize snapshot decisions for concurrent Desktop sync requests.
    index = session.execute(
        select(ProjectKnowledgeIndex)
        .where(ProjectKnowledgeIndex.id == index.id)
        .with_for_update()
    ).scalar_one()
    if index.status in {PROJECT_INDEX_PAUSED, PROJECT_INDEX_UNBOUND}:
        raise ProjectKnowledgeIndexConflict("Project knowledge index is not active")
    source = session.get(KnowledgeSource, index.knowledge_source_id)
    if source is None:
        raise ProjectKnowledgeIndexConflict("Project knowledge source is missing")
    snapshot_started_at = _as_utc(snapshot_started_at)
    current_started_at = _as_utc(index.last_snapshot_at) if index.last_snapshot_at else None
    if snapshot_generation is not None:
        if snapshot_generation < index.snapshot_generation:
            return {
                "idempotent": index.snapshot_cursor == snapshot_cursor,
                "stale": True,
                "created": 0,
                "updated": 0,
                "tombstoned": 0,
                "skipped": 0,
            }
        if (
            snapshot_generation == index.snapshot_generation
            and index.snapshot_cursor != snapshot_cursor
        ):
            raise ProjectKnowledgeIndexConflict(
                "A different project snapshot already exists for this generation"
            )
    if current_started_at is not None and snapshot_started_at < current_started_at:
        return {
            "idempotent": index.snapshot_cursor == snapshot_cursor,
            "stale": True,
            "created": 0,
            "updated": 0,
            "tombstoned": 0,
            "skipped": 0,
        }
    if current_started_at == snapshot_started_at and index.snapshot_cursor != snapshot_cursor:
        raise ProjectKnowledgeIndexConflict(
            "A different project snapshot already exists for this scan start time"
        )
    if index.snapshot_cursor == snapshot_cursor:
        if current_started_at is None or snapshot_started_at > current_started_at:
            index.last_snapshot_at = snapshot_started_at
            index.last_sync_at = utc_now()
            index.updated_at = index.last_sync_at
        return {
            "idempotent": True,
            "created": 0,
            "updated": 0,
            "tombstoned": 0,
            "skipped": 0,
        }

    if not complete:
        generation = index.snapshot_generation
    else:
        generation = index.snapshot_generation + 1

    now = utc_now()
    seen_paths: set[str] = set()
    created = 0
    updated = 0
    tombstoned = 0
    skipped = 0
    file_errors: list[str] = []

    for item in files:
        relative_path = str(item["relative_path"])
        seen_paths.add(relative_path)
        path_sha256 = hashlib.sha256(relative_path.encode("utf-8")).hexdigest()
        receipt = session.execute(
            select(ProjectKnowledgeFile).where(
                ProjectKnowledgeFile.index_id == index.id,
                ProjectKnowledgeFile.relative_path == relative_path,
            )
        ).scalar_one_or_none()
        if receipt is None:
            receipt = ProjectKnowledgeFile(
                index_id=index.id,
                relative_path=relative_path,
                path_sha256=path_sha256,
                content_sha256=None,
                size_bytes=item["size_bytes"],
                mime_type=item.get("mime_type"),
                knowledge_document_id=None,
                document_version=None,
                status="PENDING",
                last_seen_generation=generation,
                last_scanned_at=snapshot_completed_at,
                tombstoned_at=None,
                last_error=None,
                metadata_json={},
                created_at=now,
                updated_at=now,
            )
            session.add(receipt)
            session.flush()
            created += 1
        receipt.path_sha256 = path_sha256
        receipt.size_bytes = item["size_bytes"]
        receipt.mime_type = item.get("mime_type")
        receipt.last_seen_generation = generation
        receipt.last_scanned_at = snapshot_completed_at
        receipt.updated_at = now
        receipt.tombstoned_at = None
        receipt.metadata_json = {
            "schema_version": "project-knowledge-file-receipt-v1",
            "modified_at": item["modified_at"].isoformat(),
            "skip_reason": item.get("skip_reason"),
        }

        if item["status"] == "ready":
            if _sync_ready_project_file(
                session,
                index=index,
                source=source,
                receipt=receipt,
                item=item,
                snapshot_cursor=snapshot_cursor,
                actor_id=actor_id,
            ):
                updated += 1
            if receipt.status == PROJECT_FILE_ERROR:
                file_errors.append(f"{relative_path}:{receipt.last_error or 'ingestion_failed'}")
            continue

        skipped += 1
        reason = str(item.get("skip_reason") or "scan_skipped")
        _stale_project_file_document(session, receipt=receipt, now=now)
        receipt.content_sha256 = None
        receipt.status = PROJECT_FILE_IGNORED if reason == "symlink" else PROJECT_FILE_ERROR
        receipt.last_error = None if receipt.status == PROJECT_FILE_IGNORED else reason
        if receipt.status == PROJECT_FILE_ERROR:
            file_errors.append(f"{relative_path}:{reason}")

    if complete:
        missing_receipts = list(
            session.execute(
                select(ProjectKnowledgeFile).where(
                    ProjectKnowledgeFile.index_id == index.id,
                    ProjectKnowledgeFile.status != PROJECT_FILE_TOMBSTONED,
                )
            ).scalars()
        )
        for receipt in missing_receipts:
            if receipt.relative_path in seen_paths:
                continue
            _stale_project_file_document(session, receipt=receipt, now=now)
            receipt.status = PROJECT_FILE_TOMBSTONED
            receipt.tombstoned_at = now
            receipt.last_error = None
            receipt.updated_at = now
            tombstoned += 1

    scan_error_codes = [str(item.get("reason") or "scan_error") for item in scan_errors]
    issues = [*scan_error_codes, *file_errors]
    if not complete:
        issues.insert(0, "snapshot_incomplete")
    index.last_snapshot_at = snapshot_started_at
    if complete:
        index.snapshot_generation = (
            snapshot_generation if snapshot_generation is not None else generation
        )
        index.snapshot_cursor = snapshot_cursor
    index.last_sync_at = now
    index.updated_at = now
    index.status = PROJECT_INDEX_ERROR if issues else PROJECT_INDEX_ACTIVE
    index.last_error = "; ".join(issues[:10])[:2_000] if issues else None

    source.status = "ACTIVE"
    source.disabled_at = None
    source.archived_at = None
    source.updated_at = now
    source.health_status = "ERROR" if issues else "HEALTHY"
    source.last_ingestion_error = index.last_error
    source.metadata_json = {
        **(source.metadata_json if isinstance(source.metadata_json, dict) else {}),
        "project_index": {
            "index_id": index.id,
            "desktop_profile_id": index.desktop_profile_id,
            "root_identity": index.root_identity,
            "snapshot_cursor": index.snapshot_cursor,
            "snapshot_generation": index.snapshot_generation,
            "snapshot_complete": complete,
            "attempted_snapshot_cursor": snapshot_cursor,
        },
    }
    if created or updated or tombstoned or skipped:
        session.execute(
            update(WorkspaceContextCache)
            .where(
                WorkspaceContextCache.organization_id == index.organization_id,
                WorkspaceContextCache.cache_source == "rag_retrieval",
                WorkspaceContextCache.status == "active",
            )
            .values(
                status="stale",
                metadata_json={
                    "reason": "project_knowledge_index_synced",
                    "project_index_id": index.id,
                    "snapshot_cursor": snapshot_cursor,
                },
                updated_at=now,
            )
        )
    _record_project_index_audit(
        session,
        index=index,
        actor_id=actor_id,
        action="synced",
        reason=index.last_error,
        details={
            "snapshot_cursor": snapshot_cursor,
            "snapshot_generation": generation,
            "snapshot_complete": complete,
            "created": created,
            "updated": updated,
            "tombstoned": tombstoned,
            "skipped": skipped,
        },
    )
    return {
        "idempotent": False,
        "created": created,
        "updated": updated,
        "tombstoned": tombstoned,
        "skipped": skipped,
    }


def _sync_ready_project_file(
    session: Session,
    *,
    index: ProjectKnowledgeIndex,
    source: KnowledgeSource,
    receipt: ProjectKnowledgeFile,
    item: dict,
    snapshot_cursor: str,
    actor_id: str | None,
) -> bool:
    current_document = (
        session.get(KnowledgeDocument, receipt.knowledge_document_id)
        if receipt.knowledge_document_id
        else None
    )
    if (
        receipt.content_sha256 == item["content_sha256"]
        and current_document is not None
        and current_document.status == DOCUMENT_STATUS_INDEXED
    ):
        receipt.status = PROJECT_FILE_INDEXED
        receipt.last_error = None
        return False

    relative_path = str(item["relative_path"])
    project_uri = f"project://{relative_path}"
    try:
        _source, document, chunks, _embeddings = ingest_knowledge_source(
            session,
            organization_id=index.organization_id,
            agent_id=index.agent_id,
            source_id=source.id,
            name=source.name,
            description=source.description,
            source_type=PROJECT_INDEX_SOURCE_TYPE,
            title=PurePosixPath(relative_path).name,
            content=str(item["content"]),
            uri=project_uri,
            mime_type=str(item.get("mime_type") or "text/plain"),
            created_by=actor_id,
            idempotency_key=f"project-file:{receipt.path_sha256}",
            create_new_logical_document=receipt.knowledge_document_id is None,
            reingest_document_id=receipt.knowledge_document_id,
        )
    except KnowledgeIngestionError as error:
        _stale_project_file_document(session, receipt=receipt, now=utc_now())
        receipt.knowledge_document_id = error.document.id
        receipt.document_version = error.document.version
        receipt.status = PROJECT_FILE_ERROR
        receipt.last_error = str(error)[:2_000]
        return True

    document_metadata = {
        "schema_version": "project-knowledge-document-v1",
        "project_index_id": index.id,
        "project_uri": project_uri,
        "relative_path": relative_path,
        "file_content_sha256": item["content_sha256"],
        "desktop_profile_id": index.desktop_profile_id,
        "root_identity": index.root_identity,
        "snapshot_cursor": snapshot_cursor,
        "observed_modified_at": item["modified_at"].isoformat(),
    }
    document.uri = project_uri
    document.metadata_json = document_metadata
    for chunk in chunks:
        chunk.metadata_json = document_metadata
    receipt.content_sha256 = item["content_sha256"]
    receipt.knowledge_document_id = document.id
    receipt.document_version = document.version
    receipt.status = PROJECT_FILE_INDEXED
    receipt.last_error = None
    return True


def _stale_project_file_document(
    session: Session,
    *,
    receipt: ProjectKnowledgeFile,
    now,
) -> None:
    if not receipt.knowledge_document_id:
        return
    document = session.get(KnowledgeDocument, receipt.knowledge_document_id)
    if document is None or document.status != DOCUMENT_STATUS_INDEXED:
        return
    document.status = DOCUMENT_STATUS_SUPERSEDED
    document.superseded_at = now
    document.updated_at = now
    session.execute(
        update(KnowledgeChunk)
        .where(KnowledgeChunk.document_id == document.id)
        .values(status=CHUNK_STATUS_STALE)
    )


def project_knowledge_file_counts(
    session: Session,
    *,
    index_id: str,
) -> dict[str, int]:
    rows = session.execute(
        select(ProjectKnowledgeFile.status, func.count(ProjectKnowledgeFile.id))
        .where(ProjectKnowledgeFile.index_id == index_id)
        .group_by(ProjectKnowledgeFile.status)
    ).all()
    counts = {str(status): int(count) for status, count in rows}
    return {
        "file_count": sum(counts.values()),
        "indexed_file_count": counts.get(PROJECT_FILE_INDEXED, 0),
        "error_file_count": counts.get(PROJECT_FILE_ERROR, 0),
    }


def _set_project_index_state(
    session: Session,
    *,
    index: ProjectKnowledgeIndex,
    status: str,
    actor_id: str | None,
    action: str,
    reason: str | None,
) -> None:
    now = utc_now()
    index.status = status
    index.updated_at = now
    index.unbound_at = now if status == PROJECT_INDEX_UNBOUND else None
    if status == PROJECT_INDEX_ACTIVE:
        index.last_error = None

    source = session.get(KnowledgeSource, index.knowledge_source_id)
    if source is None:
        raise ProjectKnowledgeIndexConflict("Project knowledge source is missing")
    source.updated_at = now
    if status == PROJECT_INDEX_ACTIVE:
        source.status = "ACTIVE"
        source.disabled_at = None
        source.archived_at = None
        source.health_status = "HEALTHY"
    elif status == PROJECT_INDEX_UNBOUND:
        source.status = "ARCHIVED"
        source.disabled_at = None
        source.archived_at = now
    else:
        source.status = "DISABLED"
        source.disabled_at = now
    _record_project_index_audit(
        session,
        index=index,
        actor_id=actor_id,
        action=action,
        reason=reason,
    )


def _record_project_index_audit(
    session: Session,
    *,
    index: ProjectKnowledgeIndex,
    actor_id: str | None,
    action: str,
    reason: str | None,
    details: dict | None = None,
) -> None:
    session.add(
        AdminAuditEvent(
            organization_id=index.organization_id,
            actor_id=actor_id,
            event_type=f"project_knowledge_index.{action}",
            resource_type="project_knowledge_index",
            resource_id=index.id,
            action=action,
            payload_json={
                "schema_version": PROJECT_INDEX_SCHEMA_VERSION,
                "agent_id": index.agent_id,
                "knowledge_source_id": index.knowledge_source_id,
                "desktop_profile_id": index.desktop_profile_id,
                "root_identity": index.root_identity,
                "status": index.status,
                "reason": reason,
                **(details or {}),
            },
            created_at=utc_now(),
        )
    )


__all__ = [name for name in globals() if not name.startswith("_")]
