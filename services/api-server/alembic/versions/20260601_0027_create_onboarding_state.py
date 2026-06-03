"""create onboarding state

Revision ID: 20260601_0027
Revises: 20260531_0026
Create Date: 2026-06-01 00:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "20260601_0027"
down_revision = "20260531_0026"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user_onboarding_state",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("current_step", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("completed", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("skipped", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("demo_loaded", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("provider_json", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("agent_id", sa.String(length=64), nullable=True),
        sa.Column("demo_task_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["agent_id"], ["agents.id"]),
        sa.ForeignKeyConstraint(["demo_task_id"], ["tasks.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organization_id",
            "user_id",
            name="user_onboarding_state_org_user_uidx",
        ),
    )
    op.create_index(
        "ix_user_onboarding_state_agent_id",
        "user_onboarding_state",
        ["agent_id"],
    )
    op.create_index(
        "ix_user_onboarding_state_demo_task_id",
        "user_onboarding_state",
        ["demo_task_id"],
    )
    op.create_index(
        "ix_user_onboarding_state_org_completed",
        "user_onboarding_state",
        ["organization_id", "completed"],
    )
    op.create_index(
        "ix_user_onboarding_state_organization_id",
        "user_onboarding_state",
        ["organization_id"],
    )
    op.create_index("ix_user_onboarding_state_user_id", "user_onboarding_state", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_user_onboarding_state_user_id", table_name="user_onboarding_state")
    op.drop_index(
        "ix_user_onboarding_state_organization_id",
        table_name="user_onboarding_state",
    )
    op.drop_index(
        "ix_user_onboarding_state_org_completed",
        table_name="user_onboarding_state",
    )
    op.drop_index("ix_user_onboarding_state_demo_task_id", table_name="user_onboarding_state")
    op.drop_index("ix_user_onboarding_state_agent_id", table_name="user_onboarding_state")
    op.drop_table("user_onboarding_state")
