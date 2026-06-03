from __future__ import annotations

import hashlib
import json
from datetime import timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import SystemSetting, utc_now

IDEMPOTENCY_SETTING_KEY = "tools.write_idempotency.v1"
IDEMPOTENCY_TTL_SECONDS = 24 * 60 * 60


def idempotency_cache_key(
    *,
    organization_id: str | None,
    tool_name: str,
    idempotency_key: str,
) -> str:
    normalized = {
        "organization_id": organization_id or "global",
        "tool_name": tool_name.strip(),
        "idempotency_key": idempotency_key.strip(),
    }
    raw = json.dumps(normalized, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def get_idempotent_result(
    session: Session,
    *,
    organization_id: str | None,
    tool_name: str,
    idempotency_key: str | None,
) -> dict[str, Any] | None:
    normalized_key = str(idempotency_key or "").strip()
    if not normalized_key:
        return None
    setting = _setting(session=session, organization_id=organization_id)
    if setting is None:
        return None
    records = _active_records(setting.value_json)
    key = idempotency_cache_key(
        organization_id=organization_id,
        tool_name=tool_name,
        idempotency_key=normalized_key,
    )
    record = records.get(key)
    if not isinstance(record, dict):
        return None
    output = record.get("output_json")
    if not isinstance(output, dict):
        return None
    return {
        **output,
        "idempotent_replay": True,
        "idempotency_key": normalized_key,
        "original_tool_call_id": record.get("tool_call_id"),
    }


def remember_idempotent_result(
    session: Session,
    *,
    organization_id: str | None,
    tool_name: str,
    idempotency_key: str | None,
    tool_call_id: str,
    output_json: dict[str, Any],
) -> None:
    normalized_key = str(idempotency_key or "").strip()
    if not normalized_key:
        return
    setting = _setting(session=session, organization_id=organization_id)
    if setting is None:
        setting = SystemSetting(
            organization_id=organization_id,
            key=IDEMPOTENCY_SETTING_KEY,
            value_json={"records": {}},
            updated_by="tool-runner",
            updated_at=utc_now(),
        )
        session.add(setting)
        session.flush()
    records = _active_records(setting.value_json)
    key = idempotency_cache_key(
        organization_id=organization_id,
        tool_name=tool_name,
        idempotency_key=normalized_key,
    )
    records[key] = {
        "tool_name": tool_name,
        "idempotency_key_sha256": hashlib.sha256(
            normalized_key.encode("utf-8")
        ).hexdigest(),
        "tool_call_id": tool_call_id,
        "output_json": output_json,
        "created_at": utc_now().isoformat(),
        "expires_at": (utc_now() + timedelta(seconds=IDEMPOTENCY_TTL_SECONDS)).isoformat(),
    }
    setting.value_json = {"records": records, "ttl_seconds": IDEMPOTENCY_TTL_SECONDS}
    setting.updated_by = "tool-runner"
    setting.updated_at = utc_now()
    session.flush()


def _setting(*, session: Session, organization_id: str | None) -> SystemSetting | None:
    return session.execute(
        select(SystemSetting).where(
            SystemSetting.organization_id == organization_id,
            SystemSetting.key == IDEMPOTENCY_SETTING_KEY,
        )
    ).scalar_one_or_none()


def _active_records(value: Any) -> dict[str, dict[str, Any]]:
    if not isinstance(value, dict):
        return {}
    records = value.get("records")
    if not isinstance(records, dict):
        return {}
    now = utc_now()
    active: dict[str, dict[str, Any]] = {}
    for key, record in records.items():
        if not isinstance(key, str) or not isinstance(record, dict):
            continue
        expires_at_raw = record.get("expires_at")
        if isinstance(expires_at_raw, str):
            try:
                expires_at = utc_now().fromisoformat(expires_at_raw)
            except ValueError:
                expires_at = now - timedelta(seconds=1)
            if expires_at <= now:
                continue
        active[key] = record
    return active
