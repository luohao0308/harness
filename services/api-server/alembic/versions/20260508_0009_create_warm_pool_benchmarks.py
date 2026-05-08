"""create warm pool benchmarks

Revision ID: 20260508_0009
Revises: 20260508_0008
Create Date: 2026-05-08 04:58:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260508_0009"
down_revision: str | None = "20260508_0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "warm_pool_benchmark_runs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=True),
        sa.Column("mode", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=64), nullable=False),
        sa.Column("target_startup_ms", sa.Integer(), nullable=False),
        sa.Column("iteration_count", sa.Integer(), nullable=False),
        sa.Column("warm_avg_ms", sa.Integer(), nullable=False),
        sa.Column("warm_p95_ms", sa.Integer(), nullable=False),
        sa.Column("cold_avg_ms", sa.Integer(), nullable=False),
        sa.Column("hit_rate", sa.Integer(), nullable=False),
        sa.Column("report_json", sa.JSON(), nullable=False),
        sa.Column("created_by", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_warm_pool_benchmark_runs_organization_id"),
        "warm_pool_benchmark_runs",
        ["organization_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_warm_pool_benchmark_runs_status"),
        "warm_pool_benchmark_runs",
        ["status"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_warm_pool_benchmark_runs_status"), table_name="warm_pool_benchmark_runs")
    op.drop_index(
        op.f("ix_warm_pool_benchmark_runs_organization_id"),
        table_name="warm_pool_benchmark_runs",
    )
    op.drop_table("warm_pool_benchmark_runs")
