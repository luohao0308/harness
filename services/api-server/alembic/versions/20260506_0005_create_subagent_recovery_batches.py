"""create subagent recovery batches

Revision ID: 20260506_0005
Revises: 20260505_0004
Create Date: 2026-05-06 00:05:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260506_0005"
down_revision: str | None = "20260505_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "subagent_recovery_batches",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("batch_id", sa.Text(), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=True),
        sa.Column("task_id", sa.String(length=36), nullable=True),
        sa.Column("trigger", sa.String(length=64), nullable=False),
        sa.Column("lock_acquired", sa.Boolean(), nullable=False),
        sa.Column("replay_sequence", sa.Integer(), nullable=False),
        sa.Column("stale_after_seconds", sa.Integer(), nullable=False),
        sa.Column("enqueue", sa.Boolean(), nullable=False),
        sa.Column("task_count", sa.Integer(), nullable=False),
        sa.Column("scanned_count", sa.Integer(), nullable=False),
        sa.Column("recovered_count", sa.Integer(), nullable=False),
        sa.Column("action_counts", sa.JSON(), nullable=False),
        sa.Column("recovered", sa.JSON(), nullable=False),
        sa.Column("recovered_by_task", sa.JSON(), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_subagent_recovery_batches_batch_id"),
        "subagent_recovery_batches",
        ["batch_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_subagent_recovery_batches_organization_id"),
        "subagent_recovery_batches",
        ["organization_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_subagent_recovery_batches_task_id"),
        "subagent_recovery_batches",
        ["task_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_subagent_recovery_batches_batch_id"),
        table_name="subagent_recovery_batches",
    )
    op.drop_index(
        op.f("ix_subagent_recovery_batches_task_id"),
        table_name="subagent_recovery_batches",
    )
    op.drop_index(
        op.f("ix_subagent_recovery_batches_organization_id"),
        table_name="subagent_recovery_batches",
    )
    op.drop_table("subagent_recovery_batches")
