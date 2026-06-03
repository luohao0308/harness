from __future__ import annotations

import os
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.schemas import (
    StoredSecretImportResponse,
    StoredSecretPage,
    StoredSecretResponse,
    StoredSecretUpsertRequest,
)
from app.db.models import AdminAuditEvent, StoredSecret, utc_now
from app.db.session import get_db_session
from app.events.event_types import EventType
from app.security.auth import Principal, require_role
from app.security.secrets import (
    SECRET_PURPOSE_KNOWLEDGE_CONNECTOR,
    SECRET_PURPOSE_MODEL_PROVIDER,
    SECRET_PURPOSE_WEB_RESEARCH,
    SECRET_SCOPE_ORG,
    SECRET_SOURCE_ORG,
    SECRET_SOURCE_USER,
    SecretEncryptionError,
    list_secrets,
    upsert_secret,
)

router = APIRouter(prefix="/secrets", tags=["secrets"])
DbSession = Annotated[Session, Depends(get_db_session)]

ENV_IMPORT_SPECS = [
    ("DEEPSEEK_API_KEY", "deepseek-flash", SECRET_PURPOSE_MODEL_PROVIDER),
    ("DEEPSEEK_API_KEY", "deepseek-pro", SECRET_PURPOSE_MODEL_PROVIDER),
    ("OPENAI_API_KEY", "openai-compatible", SECRET_PURPOSE_MODEL_PROVIDER),
    ("MOONSHOT_API_KEY", "kimi", SECRET_PURPOSE_MODEL_PROVIDER),
    ("ZAI_API_KEY", "z-ai", SECRET_PURPOSE_MODEL_PROVIDER),
    ("TAVILY_API_KEY", "tavily", SECRET_PURPOSE_WEB_RESEARCH),
    ("DIFY_API_KEY", "dify", SECRET_PURPOSE_KNOWLEDGE_CONNECTOR),
    ("DIFY_CLOUD_API_KEY", "dify", SECRET_PURPOSE_KNOWLEDGE_CONNECTOR),
    ("DIFY_KNOWLEDGE_API_KEY", "dify", SECRET_PURPOSE_KNOWLEDGE_CONNECTOR),
    ("COZE_API_KEY", "coze", SECRET_PURPOSE_KNOWLEDGE_CONNECTOR),
    ("COZE_PAT", "coze", SECRET_PURPOSE_KNOWLEDGE_CONNECTOR),
]


@router.get("", response_model=StoredSecretPage, summary="查询密钥库")
def list_stored_secrets(session: DbSession, principal: Principal) -> StoredSecretPage:
    require_role(principal, {"admin", "engineer", "operator"})
    rows = list_secrets(
        session,
        organization_id=principal.organization_id,
        user_id=principal.user_id,
        include_org=True,
    )
    return StoredSecretPage(items=[_response(row) for row in rows], next_cursor=None)


@router.put("", response_model=StoredSecretResponse, summary="保存密钥")
def save_stored_secret(
    payload: StoredSecretUpsertRequest,
    session: DbSession,
    principal: Principal,
) -> StoredSecretResponse:
    require_role(principal, {"admin", "engineer"})
    if payload.scope == SECRET_SCOPE_ORG:
        require_role(principal, {"admin"})
    try:
        row = upsert_secret(
            session,
            organization_id=principal.organization_id,
            actor_id=principal.user_id,
            scope=payload.scope,
            owner_user_id=principal.user_id if payload.scope == "user" else None,
            provider=payload.provider,
            purpose=payload.purpose,
            secret_ref=payload.secret_ref,
            secret_value=payload.secret_value,
        )
    except (SecretEncryptionError, ValueError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    _audit(
        session,
        principal,
        resource_id=row.id,
        action="secret.upsert",
        payload={
            "scope": row.scope,
            "provider": row.provider,
            "purpose": row.purpose,
            "secret_ref": row.secret_ref,
            "secret_value_present": True,
        },
    )
    session.commit()
    session.refresh(row)
    return _response(row)


@router.delete("/{secret_id}", status_code=status.HTTP_204_NO_CONTENT, summary="停用密钥")
def delete_stored_secret(secret_id: str, session: DbSession, principal: Principal) -> None:
    require_role(principal, {"admin", "engineer"})
    row = session.get(StoredSecret, secret_id)
    if row is None or row.organization_id != principal.organization_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Secret not found")
    if row.scope == "org" and "admin" not in principal.roles:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Secret not found")
    if row.scope == "user" and row.owner_user_id != principal.user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Secret not found")
    row.status = "disabled"
    row.updated_by = principal.user_id
    row.updated_at = utc_now()
    _audit(
        session,
        principal,
        resource_id=row.id,
        action="secret.disable",
        payload={"scope": row.scope, "provider": row.provider, "purpose": row.purpose},
    )
    session.commit()
    return None


@router.post(
    "/import-env",
    response_model=StoredSecretImportResponse,
    summary="导入环境变量业务密钥",
)
def import_env_secrets(session: DbSession, principal: Principal) -> StoredSecretImportResponse:
    require_role(principal, {"admin"})
    imported: list[StoredSecretResponse] = []
    skipped: list[dict] = []
    seen: set[tuple[str, str, str]] = set()
    for env_name, provider, purpose in ENV_IMPORT_SPECS:
        key = (env_name, provider, purpose)
        if key in seen:
            continue
        seen.add(key)
        value = os.environ.get(env_name, "").strip()
        if not value:
            skipped.append({"env": env_name, "provider": provider, "reason": "unset"})
            continue
        try:
            row = upsert_secret(
                session,
                organization_id=principal.organization_id,
                actor_id=principal.user_id,
                scope=SECRET_SCOPE_ORG,
                owner_user_id=None,
                provider=provider,
                purpose=purpose,
                secret_ref=f"env://{env_name}",
                secret_value=value,
            )
        except (SecretEncryptionError, ValueError) as exc:
            skipped.append({"env": env_name, "provider": provider, "reason": str(exc)})
            continue
        imported.append(_response(row))
    _audit(
        session,
        principal,
        resource_id="env",
        action="secret.import_env",
        payload={"imported_count": len(imported), "skipped_count": len(skipped)},
    )
    session.commit()
    return StoredSecretImportResponse(imported=imported, skipped=skipped)


def _response(row: StoredSecret) -> StoredSecretResponse:
    return StoredSecretResponse(
        id=row.id,
        organization_id=row.organization_id,
        owner_user_id=row.owner_user_id,
        scope=row.scope,
        provider=row.provider,
        purpose=row.purpose,
        secret_ref=row.secret_ref,
        status=row.status,
        configured=row.status == "active",
        source=SECRET_SOURCE_ORG if row.scope == SECRET_SCOPE_ORG else SECRET_SOURCE_USER,
        created_at=row.created_at,
        updated_at=row.updated_at,
        last_used_at=row.last_used_at,
    )


def _audit(
    session: Session,
    principal: Principal,
    *,
    resource_id: str,
    action: str,
    payload: dict,
) -> None:
    session.add(
        AdminAuditEvent(
            organization_id=principal.organization_id,
            actor_id=principal.user_id,
            event_type=EventType.ADMIN_ACTION,
            resource_type="secret",
            resource_id=resource_id,
            action=action,
            payload_json=payload,
            created_at=utc_now(),
        )
    )
