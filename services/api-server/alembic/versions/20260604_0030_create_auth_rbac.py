"""create auth rbac

Revision ID: 20260604_0030
Revises: 20260603_0029
Create Date: 2026-06-04 00:00:00.000000
"""

from __future__ import annotations

from datetime import datetime, timezone

import sqlalchemy as sa

from alembic import op

revision = "20260604_0030"
down_revision = "20260603_0029"
branch_labels = None
depends_on = None

DEV_PASSWORD_HASH = (
    "pbkdf2_sha256$260000$dev-seed-salt$"
    "09b9f7c7137bdbfdf08c43ff1e58f4f4cf147352b2c88c53b8e5cd8523545525"
)


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("email_verified", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email", name="users_email_uidx"),
    )
    op.create_index("ix_users_email", "users", ["email"])
    op.create_index("ix_users_status", "users", ["status"])

    op.create_table(
        "organizations",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("slug", sa.String(length=128), nullable=False),
        sa.Column("owner_user_id", sa.String(length=36), nullable=True),
        sa.Column("plan", sa.String(length=32), nullable=False, server_default="free"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug", name="organizations_slug_uidx"),
    )
    op.create_index("ix_organizations_owner_user_id", "organizations", ["owner_user_id"])
    op.create_index("ix_organizations_slug", "organizations", ["slug"])

    op.create_table(
        "organization_members",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("role", sa.String(length=32), nullable=False, server_default="member"),
        sa.Column("invited_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organization_id",
            "user_id",
            name="organization_members_org_user_uidx",
        ),
    )
    op.create_index(
        "ix_organization_members_organization_id",
        "organization_members",
        ["organization_id"],
    )
    op.create_index(
        "ix_organization_members_role",
        "organization_members",
        ["role"],
    )
    op.create_index("ix_organization_members_user_id", "organization_members", ["user_id"])
    op.create_index(
        "ix_organization_members_user_org",
        "organization_members",
        ["user_id", "organization_id"],
    )

    op.create_table(
        "oauth_accounts",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("provider_user_id", sa.Text(), nullable=False),
        sa.Column("email", sa.Text(), nullable=False, server_default=""),
        sa.Column("raw_profile_json", sa.JSON(), nullable=False, server_default="{}"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "provider",
            "provider_user_id",
            name="oauth_accounts_provider_user_uidx",
        ),
    )
    op.create_index("ix_oauth_accounts_provider", "oauth_accounts", ["provider"])
    op.create_index("ix_oauth_accounts_user_id", "oauth_accounts", ["user_id"])
    op.create_index("ix_oauth_accounts_user_provider", "oauth_accounts", ["user_id", "provider"])

    op.create_table(
        "api_keys",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("key_hash", sa.String(length=64), nullable=False),
        sa.Column("key_prefix", sa.String(length=16), nullable=False),
        sa.Column("scope_json", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_api_keys_key_hash", "api_keys", ["key_hash"])
    op.create_index("ix_api_keys_key_prefix", "api_keys", ["key_prefix"])
    op.create_index("ix_api_keys_organization_id", "api_keys", ["organization_id"])
    op.create_index("ix_api_keys_org_prefix", "api_keys", ["organization_id", "key_prefix"])
    op.create_index("ix_api_keys_user_created", "api_keys", ["user_id", "created_at"])
    op.create_index("ix_api_keys_user_id", "api_keys", ["user_id"])

    now = datetime.now(timezone.utc)
    users = sa.table(
        "users",
        sa.column("id", sa.String),
        sa.column("email", sa.String),
        sa.column("name", sa.Text),
        sa.column("password_hash", sa.Text),
        sa.column("email_verified", sa.Boolean),
        sa.column("status", sa.String),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("updated_at", sa.DateTime(timezone=True)),
    )
    organizations = sa.table(
        "organizations",
        sa.column("id", sa.String),
        sa.column("name", sa.Text),
        sa.column("slug", sa.String),
        sa.column("owner_user_id", sa.String),
        sa.column("plan", sa.String),
        sa.column("created_at", sa.DateTime(timezone=True)),
    )
    members = sa.table(
        "organization_members",
        sa.column("id", sa.String),
        sa.column("organization_id", sa.String),
        sa.column("user_id", sa.String),
        sa.column("role", sa.String),
        sa.column("accepted_at", sa.DateTime(timezone=True)),
    )
    op.bulk_insert(
        users,
        [
            {
                "id": "dev-admin",
                "email": "admin@dev.local",
                "name": "Dev Admin",
                "password_hash": DEV_PASSWORD_HASH,
                "email_verified": True,
                "status": "active",
                "created_at": now,
                "updated_at": now,
            },
            {
                "id": "dev-engineer",
                "email": "engineer@dev.local",
                "name": "Dev Engineer",
                "password_hash": DEV_PASSWORD_HASH,
                "email_verified": True,
                "status": "active",
                "created_at": now,
                "updated_at": now,
            },
        ],
    )
    op.bulk_insert(
        organizations,
        [
            {
                "id": "dev-org",
                "name": "Dev Workspace",
                "slug": "dev-org",
                "owner_user_id": "dev-admin",
                "plan": "pro",
                "created_at": now,
            }
        ],
    )
    op.bulk_insert(
        members,
        [
            {
                "id": "dev-admin-membership",
                "organization_id": "dev-org",
                "user_id": "dev-admin",
                "role": "owner",
                "accepted_at": now,
            },
            {
                "id": "dev-engineer-membership",
                "organization_id": "dev-org",
                "user_id": "dev-engineer",
                "role": "member",
                "accepted_at": now,
            },
        ],
    )


def downgrade() -> None:
    op.drop_index("ix_api_keys_user_id", table_name="api_keys")
    op.drop_index("ix_api_keys_user_created", table_name="api_keys")
    op.drop_index("ix_api_keys_org_prefix", table_name="api_keys")
    op.drop_index("ix_api_keys_organization_id", table_name="api_keys")
    op.drop_index("ix_api_keys_key_prefix", table_name="api_keys")
    op.drop_index("ix_api_keys_key_hash", table_name="api_keys")
    op.drop_table("api_keys")
    op.drop_index("ix_oauth_accounts_user_provider", table_name="oauth_accounts")
    op.drop_index("ix_oauth_accounts_user_id", table_name="oauth_accounts")
    op.drop_index("ix_oauth_accounts_provider", table_name="oauth_accounts")
    op.drop_table("oauth_accounts")
    op.drop_index("ix_organization_members_user_org", table_name="organization_members")
    op.drop_index("ix_organization_members_user_id", table_name="organization_members")
    op.drop_index("ix_organization_members_role", table_name="organization_members")
    op.drop_index(
        "ix_organization_members_organization_id",
        table_name="organization_members",
    )
    op.drop_table("organization_members")
    op.drop_index("ix_organizations_slug", table_name="organizations")
    op.drop_index("ix_organizations_owner_user_id", table_name="organizations")
    op.drop_table("organizations")
    op.drop_index("ix_users_status", table_name="users")
    op.drop_index("ix_users_email", table_name="users")
    op.drop_table("users")
