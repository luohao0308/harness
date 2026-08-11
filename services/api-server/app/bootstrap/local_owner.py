from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Organization, OrganizationMember, SystemSetting, User, utc_now

logger = logging.getLogger(__name__)

LOCAL_USER_ID = "00000000-0000-4000-8000-000000000001"
LOCAL_ORGANIZATION_ID = "00000000-0000-4000-8000-000000000002"
LOCAL_MEMBERSHIP_ID = "00000000-0000-4000-8000-000000000003"
LOCAL_USER_EMAIL = "local-owner@harness.invalid"
LOCAL_PRINCIPAL_SETTING_KEY = "local_runtime.principal"


def bootstrap_local_owner(session: Session) -> User:
    """Create the one deterministic local principal without login credentials."""
    imported = resolve_local_principal(session, required=False)
    if imported is not None:
        return imported[0]
    existing = session.get(User, LOCAL_USER_ID)
    if existing is not None:
        _validate_local_principal(session, existing)
        return existing

    any_user_id = session.execute(select(User.id).limit(1)).scalar_one_or_none()
    if any_user_id is not None:
        raise RuntimeError("local runtime database contains users but no selected local owner")

    now = utc_now()
    user = User(
        id=LOCAL_USER_ID,
        email=LOCAL_USER_EMAIL,
        name="Local Owner",
        password_hash="!local-runtime-password-login-disabled",
        email_verified=True,
        status="active",
        created_at=now,
        updated_at=now,
    )
    organization = Organization(
        id=LOCAL_ORGANIZATION_ID,
        name="Harness",
        slug="local-harness",
        owner_user_id=LOCAL_USER_ID,
        plan="local",
        created_at=now,
    )
    membership = OrganizationMember(
        id=LOCAL_MEMBERSHIP_ID,
        organization_id=LOCAL_ORGANIZATION_ID,
        user_id=LOCAL_USER_ID,
        role="owner",
        invited_at=now,
        accepted_at=now,
    )
    session.add_all([user, organization, membership])
    session.commit()
    _validate_local_principal(session, user)
    logger.info("Bootstrapped local runtime owner")
    return user


def resolve_local_principal(
    session: Session,
    *,
    required: bool = True,
) -> tuple[User, Organization, OrganizationMember] | None:
    """Resolve an imported principal, falling back to the clean-install identity."""
    settings = session.execute(
        select(SystemSetting).where(SystemSetting.key == LOCAL_PRINCIPAL_SETTING_KEY)
    ).scalars().all()
    if len(settings) > 1:
        raise RuntimeError("local runtime contains multiple selected principals")
    if settings:
        value = settings[0].value_json
        user_id = value.get("user_id") if isinstance(value, dict) else None
        organization_id = value.get("organization_id") if isinstance(value, dict) else None
        membership_id = value.get("membership_id") if isinstance(value, dict) else None
        identifiers = (user_id, organization_id, membership_id)
        if not all(isinstance(item, str) and item for item in identifiers):
            raise RuntimeError("local runtime principal metadata is invalid")
        principal = (
            session.get(User, user_id),
            session.get(Organization, organization_id),
            session.get(OrganizationMember, membership_id),
        )
        _validate_principal(*principal)
        return principal  # type: ignore[return-value]

    user = session.get(User, LOCAL_USER_ID)
    organization = session.get(Organization, LOCAL_ORGANIZATION_ID)
    membership = session.get(OrganizationMember, LOCAL_MEMBERSHIP_ID)
    if user is None and not required:
        return None
    _validate_principal(user, organization, membership)
    return user, organization, membership  # type: ignore[return-value]


def _validate_local_principal(session: Session, user: User) -> None:
    organization = session.get(Organization, LOCAL_ORGANIZATION_ID)
    membership = session.get(OrganizationMember, LOCAL_MEMBERSHIP_ID)
    _validate_principal(user, organization, membership)


def _validate_principal(
    user: User | None,
    organization: Organization | None,
    membership: OrganizationMember | None,
) -> None:
    if (
        user is None
        or organization is None
        or membership is None
        or user.status != "active"
        or organization.owner_user_id != user.id
        or membership.organization_id != organization.id
        or membership.user_id != user.id
        or membership.role != "owner"
        or membership.accepted_at is None
    ):
        raise RuntimeError("local runtime principal is incomplete or inactive")
