from __future__ import annotations

from collections.abc import Iterable
from enum import StrEnum
from typing import Annotated

from fastapi import Depends, HTTPException, status


class Role(StrEnum):
    OWNER = "owner"
    ADMIN = "admin"
    MEMBER = "member"
    VIEWER = "viewer"


class Permission(StrEnum):
    ORG_MANAGE = "org:manage"
    USER_INVITE = "user:invite"
    USER_ROLE_UPDATE = "user:role_update"
    USER_REMOVE = "user:remove"
    API_KEY_MANAGE = "api_key:manage"
    AUDIT_READ = "audit:read"
    DATA_EXPORT = "data:export"
    DATA_DELETE = "data:delete"
    DATA_RETENTION_MANAGE = "data_retention:manage"
    AGENT_READ = "agent:read"
    AGENT_CREATE = "agent:create"
    AGENT_DELETE = "agent:delete"
    RUN_READ = "run:read"
    RUN_CREATE = "run:create"
    RUN_CANCEL = "run:cancel"
    EVAL_RUN = "eval:run"
    TOOL_CONFIGURE = "tool:configure"
    MARKETPLACE_PUBLISH = "marketplace:publish"
    SETTINGS_READ = "settings:read"
    SETTINGS_WRITE = "settings:write"


ROLE_PERMISSIONS: dict[Role, set[Permission]] = {
    Role.OWNER: set(Permission),
    Role.ADMIN: {
        Permission.ORG_MANAGE,
        Permission.USER_INVITE,
        Permission.USER_ROLE_UPDATE,
        Permission.USER_REMOVE,
        Permission.API_KEY_MANAGE,
        Permission.AUDIT_READ,
        Permission.DATA_EXPORT,
        Permission.DATA_DELETE,
        Permission.DATA_RETENTION_MANAGE,
        Permission.AGENT_READ,
        Permission.AGENT_CREATE,
        Permission.AGENT_DELETE,
        Permission.RUN_READ,
        Permission.RUN_CREATE,
        Permission.RUN_CANCEL,
        Permission.EVAL_RUN,
        Permission.TOOL_CONFIGURE,
        Permission.MARKETPLACE_PUBLISH,
        Permission.SETTINGS_READ,
        Permission.SETTINGS_WRITE,
    },
    Role.MEMBER: {
        Permission.AGENT_READ,
        Permission.AGENT_CREATE,
        Permission.RUN_READ,
        Permission.RUN_CREATE,
        Permission.RUN_CANCEL,
        Permission.EVAL_RUN,
        Permission.SETTINGS_READ,
    },
    Role.VIEWER: {
        Permission.AGENT_READ,
        Permission.RUN_READ,
        Permission.AUDIT_READ,
        Permission.SETTINGS_READ,
    },
}

ROLE_LEGACY_ROLES: dict[Role, list[str]] = {
    Role.OWNER: ["owner", "admin", "engineer", "operator"],
    Role.ADMIN: ["admin", "engineer", "operator"],
    Role.MEMBER: ["member", "engineer", "operator"],
    Role.VIEWER: ["viewer", "operator"],
}


def normalize_role(value: str | None) -> Role:
    try:
        return Role((value or Role.MEMBER.value).lower())
    except ValueError:
        if value == "admin":
            return Role.ADMIN
        if value in {"engineer", "operator"}:
            return Role.MEMBER if value == "engineer" else Role.VIEWER
        return Role.MEMBER


def legacy_roles_for(role: str | Role) -> list[str]:
    normalized = role if isinstance(role, Role) else normalize_role(role)
    return ROLE_LEGACY_ROLES[normalized]


def permissions_for_role(role: str | Role) -> set[Permission]:
    normalized = role if isinstance(role, Role) else normalize_role(role)
    return ROLE_PERMISSIONS[normalized]


def permissions_as_strings(role: str | Role) -> list[str]:
    return sorted(permission.value for permission in permissions_for_role(role))


def has_permission(
    role: str | Role,
    permission: Permission,
    *,
    api_key_permissions: Iterable[str] | None = None,
) -> bool:
    if permission not in permissions_for_role(role):
        return False
    if api_key_permissions is None:
        return True
    return permission.value in set(api_key_permissions)


def require_permission(permission: Permission):
    from app.security.auth import get_current_principal

    def _require_permission(
        principal: Annotated[object, Depends(get_current_principal)],
    ) -> None:
        if not has_permission(
            getattr(principal, "role", Role.MEMBER.value),
            permission,
            api_key_permissions=getattr(principal, "permissions", None),
        ):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="权限不足",
            )

    return _require_permission
