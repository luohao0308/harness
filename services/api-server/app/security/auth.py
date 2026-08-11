import logging
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.db.models import ApiKey, LocalAgentBridgeTask, OrganizationMember, User, utc_now
from app.db.session import get_db_session
from app.local_runtime.api import LOCAL_SESSION_COOKIE
from app.security.jwt_utils import InvalidTokenError, decode_jwt, hash_api_key, token_error
from app.security.rbac import (
    Permission,
    has_permission,
    legacy_roles_for,
    normalize_role,
    permissions_as_strings,
)

bearer_scheme = HTTPBearer(auto_error=False)
DbSession = Annotated[Session, Depends(get_db_session)]
logger = logging.getLogger(__name__)
LOCAL_AGENT_BRIDGE_STREAM_SCOPE = "local_agent_bridge_stream"


@dataclass(frozen=True)
class AuthenticatedPrincipal:
    user_id: str
    organization_id: str
    roles: list[str]
    role: str = "member"
    permissions: list[str] | None = None
    auth_type: str = "dev-token"
    api_key_id: str | None = None


@dataclass(frozen=True)
class LocalAgentBridgeStreamPrincipal:
    principal: AuthenticatedPrincipal
    token_jti: str
    bridge_task_id: str


_DEV_TOKEN_ENVIRONMENTS = {"development", "test"}
_dev_token_warning_logged_for: set[str] = set()

_DEV_TOKEN_PRINCIPAL_VALUES = {
    "dev-admin-token": AuthenticatedPrincipal(
        user_id="dev-admin",
        organization_id="dev-org",
        roles=["admin", "engineer"],
        role="owner",
        permissions=permissions_as_strings("owner"),
    ),
    "dev-engineer-token": AuthenticatedPrincipal(
        user_id="dev-engineer",
        organization_id="dev-org",
        roles=["engineer"],
        role="member",
        permissions=permissions_as_strings("member"),
    ),
    "dev-operator-token": AuthenticatedPrincipal(
        user_id="dev-operator",
        organization_id="dev-org",
        roles=["operator"],
        role="viewer",
        permissions=permissions_as_strings("viewer"),
    ),
    "dev-other-org-token": AuthenticatedPrincipal(
        user_id="dev-other-engineer",
        organization_id="other-org",
        roles=["engineer"],
        role="member",
        permissions=permissions_as_strings("member"),
    ),
}


def _dev_tokens_enabled() -> bool:
    env = get_settings().app_env.strip().lower()
    log_dev_token_status(env=env)
    return env in _DEV_TOKEN_ENVIRONMENTS


def log_dev_token_status(
    settings: Settings | None = None,
    *,
    env: str | None = None,
) -> None:
    env = (env or (settings or get_settings()).app_env).strip().lower()
    if env not in _DEV_TOKEN_ENVIRONMENTS:
        return
    if env not in _dev_token_warning_logged_for:
        logger.warning("Dev tokens enabled because APP_ENV=%s; do not use in production", env)
        _dev_token_warning_logged_for.add(env)


class _DevTokenPrincipals:
    def get(
        self,
        token: str,
        default: AuthenticatedPrincipal | None = None,
    ) -> AuthenticatedPrincipal | None:
        if not _dev_tokens_enabled():
            return default
        return _DEV_TOKEN_PRINCIPAL_VALUES.get(token, default)

    def __len__(self) -> int:
        return len(_DEV_TOKEN_PRINCIPAL_VALUES) if _dev_tokens_enabled() else 0

    def __contains__(self, token: object) -> bool:
        return isinstance(token, str) and self.get(token) is not None


DEV_TOKEN_PRINCIPALS = _DevTokenPrincipals()


def get_current_principal(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    session: DbSession,
) -> AuthenticatedPrincipal:
    token = (
        credentials.credentials
        if credentials is not None
        else request.query_params.get("access_token")
    )
    if token is None and get_settings().runtime_profile == "local":
        token = request.cookies.get(LOCAL_SESSION_COOKIE)
    if token is None:
        raise token_error("缺少 Bearer token")
    principal = DEV_TOKEN_PRINCIPALS.get(token)
    if principal is not None:
        return principal
    if token.startswith("hk_"):
        return _principal_from_api_key(token, session)
    return _principal_from_jwt(token, session)


Principal = Annotated[AuthenticatedPrincipal, Depends(get_current_principal)]


def require_role(principal: AuthenticatedPrincipal, allowed_roles: set[str]) -> None:
    if not allowed_roles.intersection(principal.roles):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="权限不足",
        )


def require_permission_value(principal: AuthenticatedPrincipal, permission: Permission) -> None:
    if not has_permission(principal.role, permission, api_key_permissions=principal.permissions):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="权限不足",
        )


def _principal_from_jwt(token: str, session: Session) -> AuthenticatedPrincipal:
    try:
        payload = decode_jwt(token, expected_type="access")
    except InvalidTokenError as exc:
        raise token_error("Bearer token 无效") from exc
    if payload.get("scope") is not None:
        raise token_error("Bearer token scope is not valid for this endpoint")
    user_id = payload["sub"]
    organization_id = payload["org"]
    user = session.get(User, user_id)
    if user is None:
        raise token_error("用户不存在")
    if user.status != "active":
        raise token_error("用户已停用")
    membership = session.execute(
        select(OrganizationMember).where(
            OrganizationMember.organization_id == organization_id,
            OrganizationMember.user_id == user_id,
            OrganizationMember.accepted_at.is_not(None),
        )
    ).scalar_one_or_none()
    if membership is None:
        raise token_error("用户不在组织中")
    role = normalize_role(membership.role)
    return AuthenticatedPrincipal(
        user_id=user_id,
        organization_id=organization_id,
        role=role.value,
        roles=legacy_roles_for(role),
        permissions=permissions_as_strings(role),
        auth_type="jwt",
    )


def principal_from_local_agent_bridge_stream_token(
    token: str,
    session: Session,
    *,
    agent_id: str,
    run_id: str,
    bridge_task_id: str,
) -> LocalAgentBridgeStreamPrincipal:
    try:
        payload = decode_jwt(token, expected_type="access")
    except InvalidTokenError as exc:
        raise token_error("Bearer token 无效") from exc
    if payload.get("scope") != LOCAL_AGENT_BRIDGE_STREAM_SCOPE:
        raise token_error("Bearer token scope is not valid for local Agent stream")
    user_id = payload["sub"]
    organization_id = payload["org"]
    if (
        payload.get("agent_id") != agent_id
        or payload.get("run_id") != run_id
        or payload.get("bridge_task_id") != bridge_task_id
    ):
        raise token_error("Bearer token scope does not match local Agent stream")
    bridge_task = session.get(LocalAgentBridgeTask, bridge_task_id)
    if (
        bridge_task is None
        or bridge_task.organization_id != organization_id
        or bridge_task.owner_user_id != user_id
        or bridge_task.task_id != run_id
        or bridge_task.status not in {"pending", "leased", "running"}
    ):
        raise token_error("Local Agent stream target is not valid")
    bridge_payload = (
        bridge_task.payload_json if isinstance(bridge_task.payload_json, dict) else {}
    )
    if bridge_payload.get("agent_id") != agent_id or bridge_payload.get("run_id") != run_id:
        raise token_error("Local Agent stream target is not valid")
    user = session.get(User, user_id)
    if user is None:
        dev_principal = _dev_principal_for_subject(user_id, organization_id)
        if dev_principal is None:
            raise token_error("用户不存在")
        if not set(dev_principal.roles).intersection({"admin", "engineer"}):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="权限不足")
        return LocalAgentBridgeStreamPrincipal(
            principal=AuthenticatedPrincipal(
                user_id=dev_principal.user_id,
                organization_id=dev_principal.organization_id,
                role=dev_principal.role,
                roles=dev_principal.roles,
                permissions=[LOCAL_AGENT_BRIDGE_STREAM_SCOPE],
                auth_type="local-agent-bridge-stream",
            ),
            token_jti=str(payload.get("jti") or ""),
            bridge_task_id=bridge_task_id,
        )
    if user.status != "active":
        raise token_error("用户不存在")
    membership = session.execute(
        select(OrganizationMember).where(
            OrganizationMember.organization_id == organization_id,
            OrganizationMember.user_id == user_id,
            OrganizationMember.accepted_at.is_not(None),
        )
    ).scalar_one_or_none()
    if membership is None:
        raise token_error("用户不在组织中")
    role = normalize_role(membership.role)
    roles = legacy_roles_for(role)
    if not set(roles).intersection({"admin", "engineer"}):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="权限不足")
    return LocalAgentBridgeStreamPrincipal(
        principal=AuthenticatedPrincipal(
            user_id=user_id,
            organization_id=organization_id,
            role=role.value,
            roles=roles,
            permissions=[LOCAL_AGENT_BRIDGE_STREAM_SCOPE],
            auth_type="local-agent-bridge-stream",
        ),
        token_jti=str(payload.get("jti") or ""),
        bridge_task_id=bridge_task_id,
    )


def _dev_principal_for_subject(
    user_id: str,
    organization_id: str | None,
) -> AuthenticatedPrincipal | None:
    if not _dev_tokens_enabled():
        return None
    for principal in _DEV_TOKEN_PRINCIPAL_VALUES.values():
        if principal.user_id == user_id and principal.organization_id == organization_id:
            return principal
    return None


def _principal_from_api_key(token: str, session: Session) -> AuthenticatedPrincipal:
    digest = hash_api_key(token)
    key_prefix = _api_key_prefix(token)
    statement = select(ApiKey).where(
        ApiKey.key_hash == digest,
        ApiKey.key_prefix == key_prefix,
        ApiKey.revoked_at.is_(None),
    )
    api_key = session.execute(statement).scalar_one_or_none()
    if api_key is None:
        raise token_error("API key 无效")
    now = utc_now()
    if api_key.expires_at is not None and api_key.expires_at < now:
        raise token_error("API key 已过期")
    user = session.get(User, api_key.user_id)
    if user is None:
        raise token_error("API key 所属用户不存在")
    if user.status != "active":
        raise token_error("API key 所属用户已停用")
    membership = session.execute(
        select(OrganizationMember).where(
            OrganizationMember.organization_id == api_key.organization_id,
            OrganizationMember.user_id == api_key.user_id,
            OrganizationMember.accepted_at.is_not(None),
        )
    ).scalar_one_or_none()
    if membership is None:
        raise token_error("API key 所属用户不在组织中")
    api_key.last_used_at = now
    session.commit()
    role = normalize_role(membership.role)
    scopes = [str(item) for item in (api_key.scope_json or [])]
    return AuthenticatedPrincipal(
        user_id=api_key.user_id,
        organization_id=api_key.organization_id,
        role=role.value,
        roles=legacy_roles_for(role),
        permissions=scopes,
        auth_type="api-key",
        api_key_id=api_key.id,
    )


def _api_key_prefix(token: str) -> str:
    parts = token.split("_", 2)
    if len(parts) >= 2 and parts[1]:
        return parts[1][:8]
    return token[:8]
