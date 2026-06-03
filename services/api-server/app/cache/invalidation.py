from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import SystemSetting, utc_now


def entity_version(
    session: Session,
    *,
    organization_id: str | None,
    entity: str,
) -> int:
    record = _get_record(session, organization_id=organization_id, entity=entity)
    if record is None:
        return 1
    version = record.value_json.get("version") if isinstance(record.value_json, dict) else None
    try:
        return max(1, int(version))
    except (TypeError, ValueError):
        return 1


def bump_entity_version(
    session: Session,
    *,
    organization_id: str | None,
    entity: str,
    updated_by: str | None = None,
) -> int:
    record = _get_record(session, organization_id=organization_id, entity=entity)
    current = 1
    if record is None:
        record = SystemSetting(
            organization_id=organization_id,
            key=_key(entity),
            value_json={"version": current},
            updated_by=updated_by,
            updated_at=utc_now(),
        )
        session.add(record)
    else:
        try:
            current = max(1, int(record.value_json.get("version", 1)))
        except (AttributeError, TypeError, ValueError):
            current = 1
    next_version = current + 1
    record.value_json = {"version": next_version}
    record.updated_by = updated_by
    record.updated_at = utc_now()
    session.flush()
    return next_version


def _get_record(
    session: Session,
    *,
    organization_id: str | None,
    entity: str,
) -> SystemSetting | None:
    return session.execute(
        select(SystemSetting).where(
            SystemSetting.organization_id == organization_id,
            SystemSetting.key == _key(entity),
        )
    ).scalar_one_or_none()


def _key(entity: str) -> str:
    return f"entity_version:{entity}"
