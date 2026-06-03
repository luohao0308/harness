from __future__ import annotations

import secrets
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.schemas import ApiKeyCreateRequest, ApiKeyCreateResponse, ApiKeyResponse
from app.db.models import AdminAuditEvent, ApiKey, utc_now
from app.db.session import get_db_session
from app.events.event_types import EventType
from app.security.auth import Principal
from app.security.jwt_utils import hash_api_key
from app.security.rbac import Permission

router = APIRouter(prefix="/api-keys", tags=["api-keys"])
DbSession = Annotated[Session, Depends(get_db_session)]


@router.get("", response_model=list[ApiKeyResponse])
def list_api_keys(session: DbSession, principal: Principal) -> list[ApiKey]:
    _require(principal, Permission.API_KEY_MANAGE)
    return list(
        session.execute(
            select(ApiKey)
            .where(ApiKey.organization_id == principal.organization_id)
            .order_by(ApiKey.created_at.desc())
        ).scalars()
    )


@router.post("", response_model=ApiKeyCreateResponse, status_code=status.HTTP_201_CREATED)
def create_api_key(
    payload: ApiKeyCreateRequest,
    session: DbSession,
    principal: Principal,
) -> ApiKeyCreateResponse:
    _require(principal, Permission.API_KEY_MANAGE)
    prefix = secrets.token_urlsafe(6).replace("-", "").replace("_", "")[:8]
    token = f"hk_{prefix}_{secrets.token_urlsafe(32)}"
    scopes = payload.scopes or (principal.permissions or [])
    api_key = ApiKey(
        organization_id=principal.organization_id,
        user_id=principal.user_id,
        name=payload.name,
        key_hash=hash_api_key(token),
        key_prefix=prefix,
        scope_json=scopes,
        expires_at=payload.expires_at,
        created_at=utc_now(),
    )
    session.add(api_key)
    session.flush()
    _audit(
        session,
        principal,
        resource_type="api_key",
        resource_id=api_key.id,
        action="api_key.create",
        payload={"name": payload.name, "scopes": scopes},
    )
    session.commit()
    session.refresh(api_key)
    return ApiKeyCreateResponse(**ApiKeyResponse.model_validate(api_key).model_dump(), key=token)


@router.delete("/{key_id}", status_code=status.HTTP_204_NO_CONTENT)
def revoke_api_key(key_id: str, session: DbSession, principal: Principal) -> None:
    _require(principal, Permission.API_KEY_MANAGE)
    api_key = session.get(ApiKey, key_id)
    if api_key is None or api_key.organization_id != principal.organization_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="API key not found")
    api_key.revoked_at = utc_now()
    _audit(
        session,
        principal,
        resource_type="api_key",
        resource_id=api_key.id,
        action="api_key.revoke",
        payload={"name": api_key.name},
    )
    session.commit()
    return None


def _require(principal: Principal, permission: Permission) -> None:
    from app.security.auth import require_permission_value

    require_permission_value(principal, permission)


def _audit(
    session: Session,
    principal: Principal,
    *,
    resource_type: str,
    resource_id: str,
    action: str,
    payload: dict,
) -> None:
    session.add(
        AdminAuditEvent(
            organization_id=principal.organization_id,
            actor_id=principal.user_id,
            event_type=EventType.ADMIN_ACTION,
            resource_type=resource_type,
            resource_id=resource_id,
            action=action,
            payload_json=payload,
            created_at=utc_now(),
        )
    )
