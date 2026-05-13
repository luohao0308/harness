"""add eval_dataset baseline_run_id

Revision ID: 20260514_0010
Revises: 20260508_0009
Create Date: 2026-05-14 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260514_0010"
down_revision: str | None = "20260508_0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "eval_datasets",
        sa.Column("baseline_run_id", sa.String(length=36), nullable=True),
    )
    op.create_foreign_key(
        "fk_eval_datasets_baseline_run_id",
        "eval_datasets",
        "eval_runs",
        ["baseline_run_id"],
        ["id"],
    )


def downgrade() -> None:
    op.drop_constraint("fk_eval_datasets_baseline_run_id", "eval_datasets", type_="foreignkey")
    op.drop_column("eval_datasets", "baseline_run_id")
