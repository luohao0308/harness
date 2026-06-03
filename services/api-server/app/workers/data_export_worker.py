from __future__ import annotations

import hashlib
import json
import zipfile
from datetime import timedelta
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import (
    AdminAuditEvent,
    Agent,
    ApiKey,
    ArchivedRecord,
    DataExport,
    Organization,
    OrganizationMember,
    Task,
    User,
    utc_now,
)

EXPORT_MODELS: list[tuple[str, type[Any]]] = [
    ("organizations", Organization),
    ("organization_members", OrganizationMember),
    ("users", User),
    ("tasks", Task),
    ("agents", Agent),
    ("api_keys", ApiKey),
    ("archived_records", ArchivedRecord),
    ("admin_audit_events", AdminAuditEvent),
]

REDACTED_EXPORT_COLUMNS = {"key_hash", "password_hash"}


def create_org_export(
    session: Session,
    *,
    organization_id: str,
    requested_by: str,
) -> DataExport:
    export = DataExport(
        organization_id=organization_id,
        requested_by=requested_by,
        status="running",
        requested_at=utc_now(),
    )
    session.add(export)
    session.flush()
    try:
        file_path = _write_export_file(session, export)
        digest = hashlib.sha256(file_path.read_bytes()).hexdigest()
        export.status = "completed"
        export.file_path = str(file_path)
        export.file_sha256 = digest
        export.size_bytes = file_path.stat().st_size
        export.completed_at = utc_now()
        export.expires_at = utc_now() + timedelta(hours=24)
    except Exception as exc:
        export.status = "failed"
        export.error_message = str(exc)
        export.completed_at = utc_now()
    session.commit()
    session.refresh(export)
    return export


def _write_export_file(session: Session, export: DataExport) -> Path:
    base_dir = Path(get_settings().observability_export_dir).expanduser().resolve()
    org_dir = base_dir / "org-exports" / export.organization_id
    org_dir.mkdir(parents=True, exist_ok=True)
    file_path = org_dir / f"{export.id}.zip"
    with zipfile.ZipFile(file_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            "README.md",
            (
                "# Harness organization export\n\n"
                f"organization_id: {export.organization_id}\n"
                f"export_id: {export.id}\n"
            ),
        )
        for name, model in EXPORT_MODELS:
            records = _records_for_org(session, model=model, organization_id=export.organization_id)
            archive.writestr(f"{name}.json", json.dumps(records, ensure_ascii=False, indent=2))
    return file_path


def _records_for_org(session: Session, *, model: type[Any], organization_id: str) -> list[dict]:
    if model is User:
        member_user_ids = select(OrganizationMember.user_id).where(
            OrganizationMember.organization_id == organization_id
        )
        rows = session.execute(select(User).where(User.id.in_(member_user_ids))).scalars()
    elif model is Organization:
        rows = session.execute(
            select(Organization).where(Organization.id == organization_id)
        ).scalars()
    elif hasattr(model, "organization_id"):
        rows = session.execute(
            select(model).where(model.organization_id == organization_id)
        ).scalars()
    else:
        rows = []
    return [_row_payload(row) for row in rows]


def _row_payload(row: Any) -> dict:
    result = {}
    for column in row.__table__.columns:
        if column.name in REDACTED_EXPORT_COLUMNS:
            result[column.name] = "[redacted]"
            continue
        value = getattr(row, column.name)
        if hasattr(value, "isoformat"):
            result[column.name] = value.isoformat()
        else:
            result[column.name] = value
    return result
