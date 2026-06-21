"""add eval human review fields

Revision ID: 20260621_0045
Revises: 9e0680b286a1
Create Date: 2026-06-21 00:42:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "20260621_0045"
down_revision = "9e0680b286a1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("eval_results", sa.Column("human_verdict", sa.String(length=32), nullable=True))
    op.add_column("eval_results", sa.Column("reviewer_id", sa.String(length=36), nullable=True))
    op.add_column(
        "eval_results",
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
    )
    with op.batch_alter_table("eval_results") as batch_op:
        batch_op.create_index("ix_eval_results_human_verdict", ["human_verdict"])
        batch_op.create_index("ix_eval_results_reviewer_id", ["reviewer_id"])
        batch_op.create_foreign_key(
            "fk_eval_results_reviewer_id_users",
            "users",
            ["reviewer_id"],
            ["id"],
        )


def downgrade() -> None:
    with op.batch_alter_table("eval_results") as batch_op:
        batch_op.drop_constraint("fk_eval_results_reviewer_id_users", type_="foreignkey")
        batch_op.drop_index("ix_eval_results_reviewer_id")
        batch_op.drop_index("ix_eval_results_human_verdict")
    op.drop_column("eval_results", "reviewed_at")
    op.drop_column("eval_results", "reviewer_id")
    op.drop_column("eval_results", "human_verdict")
