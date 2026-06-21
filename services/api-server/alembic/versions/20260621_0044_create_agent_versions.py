"""create agent versions

Revision ID: 20260621_0044
Revises: 9e0680b286a1
Create Date: 2026-06-21 00:44:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "20260621_0044"
down_revision = "9e0680b286a1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "agent_versions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("agent_id", sa.String(length=64), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("config_snapshot", sa.JSON(), nullable=False),
        sa.Column("created_by", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(["agent_id"], ["agents.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organization_id",
            "agent_id",
            "version_number",
            name="agent_versions_org_agent_number_uidx",
        ),
    )
    op.create_index("ix_agent_versions_agent_id", "agent_versions", ["agent_id"])
    op.create_index(
        "ix_agent_versions_org_agent_active",
        "agent_versions",
        ["organization_id", "agent_id", "is_active"],
    )
    op.create_index(
        "ix_agent_versions_org_agent_created",
        "agent_versions",
        ["organization_id", "agent_id", "created_at"],
    )
    op.create_index(
        "ix_agent_versions_organization_id",
        "agent_versions",
        ["organization_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_agent_versions_organization_id", table_name="agent_versions")
    op.drop_index("ix_agent_versions_org_agent_created", table_name="agent_versions")
    op.drop_index("ix_agent_versions_org_agent_active", table_name="agent_versions")
    op.drop_index("ix_agent_versions_agent_id", table_name="agent_versions")
    op.drop_table("agent_versions")
