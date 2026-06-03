from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.db.models import ArchivedRecord, new_uuid, utc_now


def archive_and_delete(
    session: Session,
    *,
    model: type,
    entity_type: str,
    cutoff: datetime,
    organization_id: str | None,
    batch_size: int = 10_000,
) -> tuple[int, int]:
    rows = _select_expired(
        session,
        model=model,
        cutoff=cutoff,
        organization_id=organization_id,
        batch_size=batch_size,
    )
    archived_count = 0
    for row in rows:
        original_id = str(row.id)
        existing = session.execute(
            select(ArchivedRecord.id).where(
                ArchivedRecord.organization_id == organization_id,
                ArchivedRecord.entity_type == entity_type,
                ArchivedRecord.original_id == original_id,
            )
        ).scalar_one_or_none()
        if existing is None:
            session.add(
                ArchivedRecord(
                    id=new_uuid(),
                    organization_id=organization_id,
                    entity_type=entity_type,
                    original_id=original_id,
                    payload_json=_row_payload(row),
                    archived_at=utc_now(),
                )
            )
            archived_count += 1
    deleted_count = _delete_by_ids(session, model=model, ids=[row.id for row in rows])
    return archived_count, deleted_count


def delete_expired(
    session: Session,
    *,
    model: type,
    cutoff: datetime,
    organization_id: str | None,
    batch_size: int = 10_000,
) -> int:
    rows = _select_expired(
        session,
        model=model,
        cutoff=cutoff,
        organization_id=organization_id,
        batch_size=batch_size,
    )
    return _delete_by_ids(session, model=model, ids=[row.id for row in rows])


def _select_expired(
    session: Session,
    *,
    model: type,
    cutoff: datetime,
    organization_id: str | None,
    batch_size: int,
) -> list[Any]:
    created = model.created_at
    statement = select(model).where(created < cutoff).limit(batch_size)
    org_column = getattr(model, "organization_id", None)
    if org_column is not None:
        statement = statement.where(org_column == organization_id)
    return list(session.execute(statement).scalars())


def _delete_by_ids(session: Session, *, model: type, ids: list[Any]) -> int:
    if not ids:
        return 0
    result = session.execute(delete(model).where(model.id.in_(ids)))
    return int(result.rowcount or 0)


def _row_payload(row: Any) -> dict:
    payload = {}
    for column in row.__table__.columns:
        value = getattr(row, column.name)
        if isinstance(value, datetime):
            payload[column.name] = value.isoformat()
        else:
            payload[column.name] = value
    return payload
