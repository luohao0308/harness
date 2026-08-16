"""create triggers

Revision ID: 20260621_0042
Revises: 9e0680b286a1
Create Date: 2026-06-21 00:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "20260621_0042"
down_revision = "9e0680b286a1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "triggers",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("agent_id", sa.String(length=64), nullable=False),
        sa.Column("type", sa.String(length=32), nullable=False),
        sa.Column("endpoint_path", sa.String(length=128), nullable=False),
        sa.Column("secret_hash", sa.String(length=64), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("created_by", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_triggered_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["agent_id"], ["agents.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("endpoint_path", name="triggers_endpoint_path_uidx"),
    )
    op.create_index("ix_triggers_agent_id", "triggers", ["agent_id"])
    op.create_index("ix_triggers_enabled", "triggers", ["enabled"])
    op.create_index(
        "ix_triggers_org_agent_enabled",
        "triggers",
        ["organization_id", "agent_id", "enabled"],
    )
    op.create_index("ix_triggers_org_created", "triggers", ["organization_id", "created_at"])
    op.create_index("ix_triggers_organization_id", "triggers", ["organization_id"])


def downgrade() -> None:
    op.drop_index("ix_triggers_organization_id", table_name="triggers")
    op.drop_index("ix_triggers_org_created", table_name="triggers")
    op.drop_index("ix_triggers_org_agent_enabled", table_name="triggers")
    op.drop_index("ix_triggers_enabled", table_name="triggers")
    op.drop_index("ix_triggers_agent_id", table_name="triggers")
    op.drop_table("triggers")
