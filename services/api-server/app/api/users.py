from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.schemas import UserInviteRequest, UserMemberResponse, UserRoleUpdateRequest
from app.db.models import AdminAuditEvent, Organization, OrganizationMember, User, utc_now
from app.db.session import get_db_session
from app.events.event_types import EventType
from app.security.auth import Principal, require_permission_value
from app.security.jwt_utils import hash_password
from app.security.rbac import Permission

router = APIRouter(prefix="/users", tags=["users"])
DbSession = Annotated[Session, Depends(get_db_session)]


@router.get("", response_model=list[UserMemberResponse])
def list_users(session: DbSession, principal: Principal) -> list[UserMemberResponse]:
    require_permission_value(principal, Permission.USER_INVITE)
    rows = session.execute(
        select(OrganizationMember, User)
        .join(User, User.id == OrganizationMember.user_id)
        .where(OrganizationMember.organization_id == principal.organization_id)
        .order_by(User.email)
    ).all()
    return [_member_response(member, user) for member, user in rows]


@router.post("", response_model=UserMemberResponse, status_code=status.HTTP_201_CREATED)
def invite_user(
    payload: UserInviteRequest,
    session: DbSession,
    principal: Principal,
) -> UserMemberResponse:
    require_permission_value(principal, Permission.USER_INVITE)
    email = payload.email.strip().lower()
    user = session.execute(select(User).where(User.email == email)).scalar_one_or_none()
    if user is None:
        user = User(
            email=email,
            name=(payload.name or email.split("@", 1)[0]).strip(),
            password_hash=hash_password("temporary-password"),
            email_verified=False,
            status="active",
            created_at=utc_now(),
            updated_at=utc_now(),
        )
        session.add(user)
        session.flush()
    existing = session.execute(
        select(OrganizationMember).where(
            OrganizationMember.organization_id == principal.organization_id,
            OrganizationMember.user_id == user.id,
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="User already in org")
    membership = OrganizationMember(
        organization_id=principal.organization_id,
        user_id=user.id,
        role=payload.role,
        invited_at=utc_now(),
        accepted_at=utc_now(),
    )
    session.add(membership)
    _audit(session, principal, "user.invite", user.id, {"email": email, "role": payload.role})
    session.commit()
    session.refresh(membership)
    return _member_response(membership, user)


@router.patch("/{user_id}/role", response_model=UserMemberResponse)
def update_user_role(
    user_id: str,
    payload: UserRoleUpdateRequest,
    session: DbSession,
    principal: Principal,
) -> UserMemberResponse:
    require_permission_value(principal, Permission.USER_ROLE_UPDATE)
    org = session.get(Organization, principal.organization_id)
    if org is not None and org.owner_user_id == user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Owner role is immutable",
        )
    membership = _membership(session, principal.organization_id, user_id)
    user = session.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    membership.role = payload.role
    _audit(session, principal, "user.role_update", user_id, {"role": payload.role})
    session.commit()
    session.refresh(membership)
    return _member_response(membership, user)


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_user(user_id: str, session: DbSession, principal: Principal) -> None:
    require_permission_value(principal, Permission.USER_REMOVE)
    org = session.get(Organization, principal.organization_id)
    if org is not None and org.owner_user_id == user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Owner cannot be removed",
        )
    membership = _membership(session, principal.organization_id, user_id)
    session.delete(membership)
    _audit(session, principal, "user.remove", user_id, {})
    session.commit()
    return None


def _membership(session: Session, organization_id: str, user_id: str) -> OrganizationMember:
    membership = session.execute(
        select(OrganizationMember).where(
            OrganizationMember.organization_id == organization_id,
            OrganizationMember.user_id == user_id,
        )
    ).scalar_one_or_none()
    if membership is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Membership not found")
    return membership


def _member_response(member: OrganizationMember, user: User) -> UserMemberResponse:
    return UserMemberResponse(
        membership_id=member.id,
        user_id=user.id,
        email=user.email,
        name=user.name,
        role=member.role,
        invited_at=member.invited_at,
        accepted_at=member.accepted_at,
        status=user.status,
    )


def _audit(
    session: Session,
    principal: Principal,
    action: str,
    resource_id: str,
    payload: dict,
) -> None:
    session.add(
        AdminAuditEvent(
            organization_id=principal.organization_id,
            actor_id=principal.user_id,
            event_type=EventType.ADMIN_ACTION,
            resource_type="user",
            resource_id=resource_id,
            action=action,
            payload_json=payload,
            created_at=utc_now(),
        )
    )
