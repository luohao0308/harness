from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

bearer_scheme = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class AuthenticatedPrincipal:
    user_id: str
    organization_id: str
    roles: list[str]


DEV_TOKEN_PRINCIPALS = {
    "dev-admin-token": AuthenticatedPrincipal(
        user_id="dev-admin",
        organization_id="dev-org",
        roles=["admin", "engineer"],
    ),
    "dev-engineer-token": AuthenticatedPrincipal(
        user_id="dev-engineer",
        organization_id="dev-org",
        roles=["engineer"],
    ),
    "dev-operator-token": AuthenticatedPrincipal(
        user_id="dev-operator",
        organization_id="dev-org",
        roles=["operator"],
    ),
    "dev-other-org-token": AuthenticatedPrincipal(
        user_id="dev-other-engineer",
        organization_id="other-org",
        roles=["engineer"],
    ),
}


def get_current_principal(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
) -> AuthenticatedPrincipal:
    token = (
        credentials.credentials
        if credentials is not None
        else request.query_params.get("access_token")
    )
    if token is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="缺少 Bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    principal = DEV_TOKEN_PRINCIPALS.get(token)
    if principal is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Bearer token 无效",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return principal


Principal = Annotated[AuthenticatedPrincipal, Depends(get_current_principal)]


def require_role(principal: AuthenticatedPrincipal, allowed_roles: set[str]) -> None:
    if not allowed_roles.intersection(principal.roles):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="权限不足",
        )
