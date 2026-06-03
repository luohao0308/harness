from __future__ import annotations

import base64
import hashlib
import re
import secrets
from email.parser import BytesParser
from email.policy import default as email_default_policy
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.schemas import (
    AuthConfigResponse,
    AuthLoginRequest,
    AuthMeResponse,
    AuthRefreshRequest,
    AuthRegisterRequest,
    AuthTokenResponse,
    OAuthStartResponse,
    OrganizationSummary,
)
from app.core.config import get_settings, public_registration_enabled
from app.db.models import Organization, OrganizationMember, User, new_uuid, utc_now
from app.db.session import get_db_session
from app.security.auth import Principal
from app.security.jwt_utils import (
    InvalidTokenError,
    decode_jwt,
    hash_password,
    issue_access_token,
    issue_refresh_token,
    verify_password,
)
from app.security.rbac import normalize_role, permissions_as_strings

router = APIRouter(prefix="/auth", tags=["auth"])
DbSession = Annotated[Session, Depends(get_db_session)]
AVATAR_MAX_BYTES = 2 * 1024 * 1024
AVATAR_MAX_MULTIPART_BYTES = AVATAR_MAX_BYTES + 128 * 1024
AVATAR_ALLOWED_TYPES = {
    "image/gif",
    "image/jpeg",
    "image/png",
    "image/webp",
}


@router.get("/config", response_model=AuthConfigResponse)
def auth_config() -> AuthConfigResponse:
    return AuthConfigResponse(
        public_registration_enabled=public_registration_enabled(),
        oauth_providers=[],
    )


@router.post("/register", response_model=AuthTokenResponse, status_code=status.HTTP_201_CREATED)
def register(payload: AuthRegisterRequest, session: DbSession) -> AuthTokenResponse:
    if not public_registration_enabled():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Public registration is disabled",
        )
    email = _normalize_email(payload.email)
    existing = session.execute(select(User).where(User.email == email)).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")
    user = User(
        id=new_uuid(),
        email=email,
        name=payload.name.strip(),
        password_hash=hash_password(payload.password),
        email_verified=False,
        status="active",
        created_at=utc_now(),
        updated_at=utc_now(),
    )
    org_name = (payload.organization_name or f"{payload.name.strip()} Workspace").strip()
    org = Organization(
        id=new_uuid(),
        name=org_name,
        slug=_unique_slug(session, org_name),
        owner_user_id=user.id,
        plan="free",
        created_at=utc_now(),
    )
    membership = OrganizationMember(
        organization_id=org.id,
        user_id=user.id,
        role="owner",
        invited_at=utc_now(),
        accepted_at=utc_now(),
    )
    session.add_all([user, org, membership])
    session.commit()
    return _tokens_for(user_id=user.id, organization_id=org.id, role="owner")


@router.post("/login", response_model=AuthTokenResponse)
def login(payload: AuthLoginRequest, session: DbSession) -> AuthTokenResponse:
    email = _normalize_email(payload.email)
    user = session.execute(select(User).where(User.email == email)).scalar_one_or_none()
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    if user.status != "active":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User disabled")
    memberships = _accepted_memberships(session, user.id)
    membership = _select_membership(memberships, payload.organization_id)
    user.last_login_at = utc_now()
    user.updated_at = utc_now()
    session.commit()
    return _tokens_for(
        user_id=user.id,
        organization_id=membership.organization_id,
        role=membership.role,
    )


@router.post("/refresh", response_model=AuthTokenResponse)
def refresh(payload: AuthRefreshRequest, session: DbSession) -> AuthTokenResponse:
    try:
        claims = decode_jwt(payload.refresh_token, expected_type="refresh")
    except InvalidTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token",
        ) from exc
    user = session.get(User, claims["sub"])
    if user is None or user.status != "active":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token",
        )
    target_org_id = payload.organization_id or claims["org"]
    membership = session.execute(
        select(OrganizationMember).where(
            OrganizationMember.organization_id == target_org_id,
            OrganizationMember.user_id == user.id,
            OrganizationMember.accepted_at.is_not(None),
        )
    ).scalar_one_or_none()
    if membership is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token",
        )
    return _tokens_for(
        user_id=user.id,
        organization_id=membership.organization_id,
        role=membership.role,
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout() -> None:
    return None


@router.get("/me", response_model=AuthMeResponse)
def me(session: DbSession, principal: Principal) -> AuthMeResponse:
    return _auth_me_response(session, principal)


@router.post("/me/avatar", response_model=AuthMeResponse)
async def upload_my_avatar(
    request: Request,
    session: DbSession,
    principal: Principal,
) -> AuthMeResponse:
    if principal.auth_type != "jwt":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Avatar upload requires a JWT user session",
        )
    user = session.get(User, principal.user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Avatar upload requires a database-backed user",
        )
    content, content_type = await _parse_avatar_multipart_upload(request)
    if content_type not in AVATAR_ALLOWED_TYPES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Avatar must be PNG, JPEG, WEBP, or GIF",
        )
    if not content:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Avatar file is empty")
    if len(content) > AVATAR_MAX_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail="Avatar file is too large; limit is 2 MiB",
        )
    if not _avatar_magic_matches(content, content_type):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Avatar content does not match the declared image type",
        )
    user.avatar_mime_type = content_type
    user.avatar_content = content
    user.avatar_sha256 = hashlib.sha256(content).hexdigest()
    user.avatar_updated_at = utc_now()
    user.updated_at = utc_now()
    session.commit()
    return _auth_me_response(session, principal)


def _auth_me_response(session: Session, principal: Principal) -> AuthMeResponse:
    user = session.get(User, principal.user_id)
    memberships = _accepted_memberships(session, principal.user_id)
    org_ids = [membership.organization_id for membership in memberships]
    orgs = {
        org.id: org
        for org in session.execute(
            select(Organization).where(Organization.id.in_(org_ids))
        ).scalars()
    }
    if user is None:
        return AuthMeResponse(
            user_id=principal.user_id,
            email=f"{principal.user_id}@dev.local",
            name=principal.user_id,
            avatar_data_url=None,
            organization_id=principal.organization_id,
            role=principal.role,
            permissions=principal.permissions or permissions_as_strings(principal.role),
            organizations=[
                OrganizationSummary(
                    id=principal.organization_id,
                    name=principal.organization_id,
                    slug=principal.organization_id,
                    role=principal.role,
                )
            ],
        )
    organizations = [
        OrganizationSummary(
            id=membership.organization_id,
            name=_org_name(orgs, membership.organization_id),
            slug=_org_slug(orgs, membership.organization_id),
            role=membership.role,
        )
        for membership in memberships
    ]
    return AuthMeResponse(
        user_id=user.id,
        email=user.email,
        name=user.name,
        avatar_data_url=_avatar_data_url(user),
        organization_id=principal.organization_id,
        role=principal.role,
        permissions=principal.permissions or permissions_as_strings(principal.role),
        organizations=organizations,
    )


def _avatar_data_url(user: User) -> str | None:
    if not user.avatar_content or not user.avatar_mime_type:
        return None
    encoded = base64.b64encode(user.avatar_content).decode("ascii")
    return f"data:{user.avatar_mime_type};base64,{encoded}"


async def _parse_avatar_multipart_upload(request: Request) -> tuple[bytes, str]:
    content_type = request.headers.get("content-type", "")
    if "multipart/form-data" not in content_type.lower():
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Expected multipart/form-data",
        )
    content_length = request.headers.get("content-length")
    if content_length is not None:
        try:
            declared_length = int(content_length)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid Content-Length",
            ) from exc
        if declared_length > AVATAR_MAX_MULTIPART_BYTES:
            raise HTTPException(
                status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                detail="Avatar upload is too large; limit is 2 MiB",
            )

    body_parts: list[bytes] = []
    body_size = 0
    async for chunk in request.stream():
        body_size += len(chunk)
        if body_size > AVATAR_MAX_MULTIPART_BYTES:
            raise HTTPException(
                status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                detail="Avatar upload is too large; limit is 2 MiB",
            )
        body_parts.append(chunk)
    body = b"".join(body_parts)
    message = BytesParser(policy=email_default_policy).parsebytes(
        b"Content-Type: " + content_type.encode("utf-8") + b"\r\nMIME-Version: 1.0\r\n\r\n" + body
    )
    for part in message.iter_parts():
        name = part.get_param("name", header="content-disposition")
        if name != "file" or not part.get_filename():
            continue
        payload = part.get_payload(decode=True) or b""
        file_content_type = part.get_content_type().split(";", 1)[0].strip().lower()
        return payload, file_content_type
    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Avatar file is required")


def _avatar_magic_matches(content: bytes, content_type: str) -> bool:
    if content_type == "image/png":
        return content.startswith(b"\x89PNG\r\n\x1a\n")
    if content_type == "image/jpeg":
        return content.startswith(b"\xff\xd8\xff")
    if content_type == "image/gif":
        return content.startswith((b"GIF87a", b"GIF89a"))
    if content_type == "image/webp":
        return len(content) >= 12 and content[:4] == b"RIFF" and content[8:12] == b"WEBP"
    return False


@router.get("/oauth/{provider}/start", response_model=OAuthStartResponse)
def oauth_start(provider: str) -> OAuthStartResponse:
    if provider not in {"github", "google"}:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unsupported provider")
    state = secrets.token_urlsafe(16)
    return OAuthStartResponse(
        provider=provider,
        authorization_url=f"https://oauth.local/{provider}/authorize?state={state}",
        state=state,
    )


@router.get("/oauth/{provider}/callback", response_model=OAuthStartResponse)
def oauth_callback(provider: str, code: str, state: str) -> OAuthStartResponse:
    if provider not in {"github", "google"}:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unsupported provider")
    return OAuthStartResponse(
        provider=provider,
        authorization_url=f"oauth://callback/{provider}?code={code}&state={state}",
        state=state,
    )


def _tokens_for(*, user_id: str, organization_id: str, role: str) -> AuthTokenResponse:
    normalized = normalize_role(role)
    settings = get_settings()
    return AuthTokenResponse(
        access_token=issue_access_token(
            user_id=user_id,
            organization_id=organization_id,
            role=normalized.value,
        ),
        refresh_token=issue_refresh_token(
            user_id=user_id,
            organization_id=organization_id,
            role=normalized.value,
        ),
        expires_in=settings.auth_access_token_minutes * 60,
    )


def _accepted_memberships(session: Session, user_id: str) -> list[OrganizationMember]:
    return list(
        session.execute(
            select(OrganizationMember).where(
                OrganizationMember.user_id == user_id,
                OrganizationMember.accepted_at.is_not(None),
            )
        ).scalars()
    )


def _select_membership(
    memberships: list[OrganizationMember],
    organization_id: str | None,
) -> OrganizationMember:
    if not memberships:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No accepted organization",
        )
    if organization_id is None:
        return memberships[0]
    for membership in memberships:
        if membership.organization_id == organization_id:
            return membership
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Organization not available")


def _normalize_email(value: str) -> str:
    return value.strip().lower()


def _unique_slug(session: Session, name: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "workspace"
    candidate = base[:96]
    index = 2
    while session.execute(
        select(Organization.id).where(Organization.slug == candidate)
    ).scalar_one_or_none():
        candidate = f"{base[:88]}-{index}"
        index += 1
    return candidate


def _org_name(orgs: dict[str, Organization], organization_id: str) -> str:
    org = orgs.get(organization_id)
    return org.name if org is not None else organization_id


def _org_slug(orgs: dict[str, Organization], organization_id: str) -> str:
    org = orgs.get(organization_id)
    return org.slug if org is not None else organization_id
