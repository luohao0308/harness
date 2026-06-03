"""remove legacy admin seed

Revision ID: 20260605_0032
Revises: 20260604_0031
Create Date: 2026-06-05 00:00:00.000000
"""

from __future__ import annotations

from datetime import datetime, timezone

import sqlalchemy as sa

from alembic import op

revision = "20260605_0032"
down_revision = "20260604_0031"
branch_labels = None
depends_on = None

DEV_PASSWORD_HASH = (
    "pbkdf2_sha256$260000$dev-seed-salt$"
    "09b9f7c7137bdbfdf08c43ff1e58f4f4cf147352b2c88c53b8e5cd8523545525"
)


def upgrade() -> None:
    connection = op.get_bind()
    connection.execute(
        sa.text(
            """
            DELETE FROM organization_members
            WHERE organization_id = 'dev-org'
              AND user_id IN ('dev-admin', 'dev-engineer')
            """
        )
    )
    connection.execute(
        sa.text(
            """
            DELETE FROM organizations
            WHERE id = 'dev-org'
              AND slug = 'dev-org'
              AND owner_user_id = 'dev-admin'
            """
        )
    )
    connection.execute(
        sa.text(
            """
            DELETE FROM users
            WHERE id IN ('dev-admin', 'dev-engineer')
              AND email IN ('admin@dev.local', 'engineer@dev.local')
              AND password_hash = :password_hash
            """
        ),
        {"password_hash": DEV_PASSWORD_HASH},
    )


def downgrade() -> None:
    connection = op.get_bind()
    now = datetime.now(timezone.utc)
    _insert_user_if_missing(
        connection,
        user_id="dev-admin",
        email="admin@dev.local",
        name="Dev Admin",
        now=now,
    )
    _insert_user_if_missing(
        connection,
        user_id="dev-engineer",
        email="engineer@dev.local",
        name="Dev Engineer",
        now=now,
    )
    connection.execute(
        sa.text(
            """
            INSERT INTO organizations (id, name, slug, owner_user_id, plan, created_at)
            SELECT 'dev-org', 'Dev Workspace', 'dev-org', 'dev-admin', 'pro', :now
            WHERE NOT EXISTS (SELECT 1 FROM organizations WHERE id = 'dev-org')
            """
        ),
        {"now": now},
    )
    _insert_member_if_missing(
        connection,
        member_id="dev-admin-membership",
        user_id="dev-admin",
        role="owner",
        now=now,
    )
    _insert_member_if_missing(
        connection,
        member_id="dev-engineer-membership",
        user_id="dev-engineer",
        role="member",
        now=now,
    )


def _insert_user_if_missing(
    connection,
    *,
    user_id: str,
    email: str,
    name: str,
    now: datetime,
) -> None:
    connection.execute(
        sa.text(
            """
            INSERT INTO users (
              id, email, name, password_hash, email_verified, status, created_at, updated_at
            )
            SELECT :user_id, :email, :name, :password_hash, true, 'active', :now, :now
            WHERE NOT EXISTS (SELECT 1 FROM users WHERE id = :user_id)
            """
        ),
        {
            "user_id": user_id,
            "email": email,
            "name": name,
            "password_hash": DEV_PASSWORD_HASH,
            "now": now,
        },
    )


def _insert_member_if_missing(
    connection,
    *,
    member_id: str,
    user_id: str,
    role: str,
    now: datetime,
) -> None:
    connection.execute(
        sa.text(
            """
            INSERT INTO organization_members (
              id, organization_id, user_id, role, accepted_at
            )
            SELECT :member_id, 'dev-org', :user_id, :role, :now
            WHERE NOT EXISTS (
              SELECT 1 FROM organization_members WHERE id = :member_id
            )
              AND EXISTS (SELECT 1 FROM organizations WHERE id = 'dev-org')
              AND EXISTS (SELECT 1 FROM users WHERE id = :user_id)
            """
        ),
        {
            "member_id": member_id,
            "user_id": user_id,
            "role": role,
            "now": now,
        },
    )
