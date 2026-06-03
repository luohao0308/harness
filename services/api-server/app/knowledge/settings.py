"""Knowledge capability and provider settings helpers."""

# ruff: noqa: F401,F403,F405,I001,UP037
from .common import *

def _system_setting(session: Session, key: str, organization_id: str | None) -> dict | None:
    row = session.execute(
        select(SystemSetting)
        .where(
            SystemSetting.key == key,
            SystemSetting.organization_id == organization_id,
        )
        .order_by(SystemSetting.updated_at.desc())
        .limit(1)
    ).scalar_one_or_none()
    if row is None:
        return None
    return row.value_json if isinstance(row.value_json, dict) else None


def _upsert_system_setting(
    session: Session,
    *,
    key: str,
    organization_id: str | None,
    value: dict,
    updated_by: str | None = None,
) -> None:
    row = session.execute(
        select(SystemSetting).where(
            SystemSetting.key == key,
            SystemSetting.organization_id == organization_id,
        )
    ).scalar_one_or_none()
    now = utc_now()
    if row is None:
        row = SystemSetting(
            organization_id=organization_id,
            key=key,
            value_json=value,
            updated_by=updated_by,
            updated_at=now,
        )
        session.add(row)
    else:
        row.value_json = value
        row.updated_by = updated_by
        row.updated_at = now
    session.flush()


def vector_capability(session: Session, organization_id: str | None) -> str:
    value = _system_setting(session, VECTOR_CAPABILITY_KEY, organization_id)
    if not value:
        return VECTOR_CAPABILITY_UNAVAILABLE
    status = str(value.get("status") or VECTOR_CAPABILITY_UNAVAILABLE).strip().lower()
    if status not in {
        VECTOR_CAPABILITY_AVAILABLE,
        VECTOR_CAPABILITY_UNAVAILABLE,
        VECTOR_CAPABILITY_DISABLED,
    }:
        return VECTOR_CAPABILITY_UNAVAILABLE
    return status


def set_vector_capability(
    session: Session,
    *,
    organization_id: str | None,
    status: str,
    reason: str | None = None,
) -> None:
    value = {"status": status, "reason": reason, "updated_at": utc_now().isoformat()}
    _upsert_system_setting(
        session,
        key=VECTOR_CAPABILITY_KEY,
        organization_id=organization_id,
        value=value,
    )


def web_research_provider(session: Session, organization_id: str | None) -> str:
    value = _system_setting(session, WEB_RESEARCH_PROVIDER_KEY, organization_id)
    provider = str((value or {}).get("provider") or WEB_RESEARCH_PROVIDER_DISABLED).strip().lower()
    if provider in {WEB_RESEARCH_PROVIDER_FAKE, WEB_RESEARCH_PROVIDER_TAVILY}:
        return provider
    return WEB_RESEARCH_PROVIDER_DISABLED


def set_web_research_provider(
    session: Session,
    *,
    organization_id: str | None,
    provider: str,
    updated_by: str = "system",
) -> None:
    normalized = provider.strip().lower()
    if normalized not in {
        WEB_RESEARCH_PROVIDER_DISABLED,
        WEB_RESEARCH_PROVIDER_FAKE,
        WEB_RESEARCH_PROVIDER_TAVILY,
    }:
        normalized = WEB_RESEARCH_PROVIDER_DISABLED
    _upsert_system_setting(
        session,
        key=WEB_RESEARCH_PROVIDER_KEY,
        organization_id=organization_id,
        value={"provider": normalized},
        updated_by=updated_by,
    )

__all__ = [name for name in globals() if not name.startswith("__") and name != "annotations"]
