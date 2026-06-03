from __future__ import annotations

import logging
import re

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.db.models import Organization, OrganizationMember, User, new_uuid, utc_now
from app.security.jwt_utils import hash_password

logger = logging.getLogger(__name__)


def bootstrap_first_admin(
    session: Session,
    *,
    settings: Settings | None = None,
) -> User | None:
    settings = settings or get_settings()
    existing_user_id = session.execute(select(User.id).limit(1)).scalar_one_or_none()
    if existing_user_id is not None:
        logger.info("users exist, skipping bootstrap")
        return None

    email = settings.harness_initial_admin_email.strip().lower()
    password = settings.harness_initial_admin_password
    if not email or not password:
        logger.warning(
            "No users exist. Set HARNESS_INITIAL_ADMIN_EMAIL/PASSWORD env to bootstrap."
        )
        return None
    try:
        return create_admin_user(
            session,
            email=email,
            password=password,
            name=_admin_name(email),
            organization_name="Default Workspace",
        )
    except IntegrityError:
        session.rollback()
        existing_user_id = session.execute(select(User.id).limit(1)).scalar_one_or_none()
        if existing_user_id is not None:
            logger.info("users exist after bootstrap race, skipping bootstrap")
            return None
        raise


def create_admin_user(
    session: Session,
    *,
    email: str,
    password: str,
    name: str | None = None,
    organization_name: str = "Default Workspace",
) -> User:
    normalized_email = email.strip().lower()
    if not normalized_email:
        raise ValueError("email is required")
    if len(password) < 8:
        raise ValueError("password must be at least 8 characters")
    existing = session.execute(
        select(User).where(User.email == normalized_email)
    ).scalar_one_or_none()
    if existing is not None:
        raise ValueError(f"user already exists: {normalized_email}")

    now = utc_now()
    user = User(
        id=new_uuid(),
        email=normalized_email,
        name=(name or _admin_name(normalized_email)).strip(),
        password_hash=hash_password(password),
        email_verified=True,
        status="active",
        created_at=now,
        updated_at=now,
    )
    org = Organization(
        id=new_uuid(),
        name=organization_name.strip() or "Default Workspace",
        slug=_unique_slug(session, organization_name),
        owner_user_id=user.id,
        plan="pro",
        created_at=now,
    )
    membership = OrganizationMember(
        id=new_uuid(),
        organization_id=org.id,
        user_id=user.id,
        role="owner",
        invited_at=now,
        accepted_at=now,
    )
    session.add_all([user, org, membership])
    session.commit()
    session.refresh(user)
    logger.info("Bootstrapped initial admin user %s", normalized_email)
    return user


def _admin_name(email: str) -> str:
    local_part = email.split("@", 1)[0].strip()
    return local_part or "Admin"


def _unique_slug(session: Session, name: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "default-workspace"
    candidate = base[:96]
    index = 2
    while session.execute(
        select(Organization.id).where(Organization.slug == candidate)
    ).scalar_one_or_none():
        candidate = f"{base[:88]}-{index}"
        index += 1
    return candidate
