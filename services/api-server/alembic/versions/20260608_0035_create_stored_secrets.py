"""create stored secrets

Revision ID: 20260608_0035
Revises: 20260607_0034
Create Date: 2026-06-08 00:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "20260608_0035"
down_revision = "20260607_0034"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "stored_secrets",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("owner_user_id", sa.String(length=36), nullable=True),
        sa.Column("scope", sa.String(length=16), nullable=False),
        sa.Column("provider", sa.String(length=128), nullable=False),
        sa.Column("purpose", sa.String(length=64), nullable=False),
        sa.Column("secret_ref", sa.Text(), nullable=True),
        sa.Column("encrypted_value", sa.Text(), nullable=False),
        sa.Column("encryption_key_id", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("created_by", sa.String(length=36), nullable=True),
        sa.Column("updated_by", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("scope IN ('user', 'org')", name="stored_secrets_scope_chk"),
        sa.CheckConstraint(
            "status IN ('active', 'disabled')",
            name="stored_secrets_status_chk",
        ),
        sa.CheckConstraint(
            "scope != 'user' OR owner_user_id IS NOT NULL",
            name="stored_secrets_user_owner_chk",
        ),
        sa.CheckConstraint(
            "scope != 'org' OR owner_user_id IS NULL",
            name="stored_secrets_org_owner_chk",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_stored_secrets_organization_id", "stored_secrets", ["organization_id"])
    op.create_index("ix_stored_secrets_owner_user_id", "stored_secrets", ["owner_user_id"])
    op.create_index("ix_stored_secrets_provider", "stored_secrets", ["provider"])
    op.create_index("ix_stored_secrets_purpose", "stored_secrets", ["purpose"])
    op.create_index("ix_stored_secrets_scope", "stored_secrets", ["scope"])
    op.create_index("ix_stored_secrets_status", "stored_secrets", ["status"])
    op.create_index(
        "ix_stored_secrets_lookup",
        "stored_secrets",
        ["organization_id", "owner_user_id", "provider", "purpose", "status"],
    )
    dialect = op.get_bind().dialect.name
    user_where = sa.text("scope = 'user' AND status = 'active'")
    org_where = sa.text("scope = 'org' AND status = 'active'")
    if dialect == "postgresql":
        op.create_index(
            "ix_stored_secrets_user_active_uidx",
            "stored_secrets",
            ["organization_id", "owner_user_id", "provider", "purpose"],
            unique=True,
            postgresql_where=user_where,
        )
        op.create_index(
            "ix_stored_secrets_org_active_uidx",
            "stored_secrets",
            ["organization_id", "provider", "purpose"],
            unique=True,
            postgresql_where=org_where,
        )
    elif dialect == "sqlite":
        op.create_index(
            "ix_stored_secrets_user_active_uidx",
            "stored_secrets",
            ["organization_id", "owner_user_id", "provider", "purpose"],
            unique=True,
            sqlite_where=user_where,
        )
        op.create_index(
            "ix_stored_secrets_org_active_uidx",
            "stored_secrets",
            ["organization_id", "provider", "purpose"],
            unique=True,
            sqlite_where=org_where,
        )
    else:
        op.create_index(
            "ix_stored_secrets_user_active_uidx",
            "stored_secrets",
            ["organization_id", "scope", "owner_user_id", "provider", "purpose", "status"],
            unique=True,
        )
        op.create_index(
            "ix_stored_secrets_org_active_uidx",
            "stored_secrets",
            ["organization_id", "scope", "provider", "purpose", "status"],
            unique=True,
        )


def downgrade() -> None:
    op.drop_index("ix_stored_secrets_org_active_uidx", table_name="stored_secrets")
    op.drop_index("ix_stored_secrets_user_active_uidx", table_name="stored_secrets")
    op.drop_index("ix_stored_secrets_lookup", table_name="stored_secrets")
    op.drop_index("ix_stored_secrets_status", table_name="stored_secrets")
    op.drop_index("ix_stored_secrets_scope", table_name="stored_secrets")
    op.drop_index("ix_stored_secrets_purpose", table_name="stored_secrets")
    op.drop_index("ix_stored_secrets_provider", table_name="stored_secrets")
    op.drop_index("ix_stored_secrets_owner_user_id", table_name="stored_secrets")
    op.drop_index("ix_stored_secrets_organization_id", table_name="stored_secrets")
    op.drop_table("stored_secrets")
