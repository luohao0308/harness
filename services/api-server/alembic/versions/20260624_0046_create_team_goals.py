"""create team goals

Revision ID: 20260624_0046
Revises: 20260621_0045
Create Date: 2026-06-24 10:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "20260624_0046"
down_revision = "20260621_0045"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "team_goals",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("team_id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("objective", sa.Text(), nullable=False),
        sa.Column("non_goals_json", sa.JSON(), nullable=False),
        sa.Column("acceptance_criteria_json", sa.JSON(), nullable=False),
        sa.Column("supervision_policy_json", sa.JSON(), nullable=False),
        sa.Column("correction_budget_json", sa.JSON(), nullable=False),
        sa.Column("progress_json", sa.JSON(), nullable=False),
        sa.Column("supervisor_state_json", sa.JSON(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["team_id"], ["teams.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("team_goals") as batch_op:
        batch_op.create_index("ix_team_goals_team_status", ["team_id", "status"])
        batch_op.create_index(
            "ix_team_goals_org_team_created",
            ["organization_id", "team_id", "created_at"],
        )
    current_goal_where = sa.text("status IN ('active', 'paused')")
    dialect = op.get_bind().dialect.name
    if dialect == "postgresql":
        op.create_index(
            "ix_team_goals_one_current_per_team_uidx",
            "team_goals",
            ["team_id"],
            unique=True,
            postgresql_where=current_goal_where,
        )
    elif dialect == "sqlite":
        op.create_index(
            "ix_team_goals_one_current_per_team_uidx",
            "team_goals",
            ["team_id"],
            unique=True,
            sqlite_where=current_goal_where,
        )
    else:
        op.create_index(
            "ix_team_goals_one_current_per_team_uidx",
            "team_goals",
            ["team_id", "status"],
            unique=True,
        )


def downgrade() -> None:
    op.drop_index("ix_team_goals_one_current_per_team_uidx", table_name="team_goals")
    with op.batch_alter_table("team_goals") as batch_op:
        batch_op.drop_index("ix_team_goals_org_team_created")
        batch_op.drop_index("ix_team_goals_team_status")
    op.drop_table("team_goals")
