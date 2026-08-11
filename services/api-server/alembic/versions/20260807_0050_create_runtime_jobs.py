"""create persistent local runtime jobs

Revision ID: 20260807_0050
Revises: 20260628_0049
Create Date: 2026-08-07 00:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "20260807_0050"
down_revision = "20260628_0049"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "runtime_jobs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("kind", sa.String(length=128), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("lease_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("lease_owner", sa.String(length=128), nullable=True),
        sa.Column("lease_generation", sa.Integer(), nullable=False),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("dedupe_key", sa.String(length=255), nullable=True),
        sa.Column("cancel_requested_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("result_json", sa.JSON(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("attempt >= 0", name="runtime_jobs_attempt_chk"),
        sa.CheckConstraint("lease_generation >= 0", name="runtime_jobs_lease_generation_chk"),
        sa.CheckConstraint("max_attempts >= 1", name="runtime_jobs_max_attempts_chk"),
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'succeeded', 'failed', 'cancelled')",
            name="runtime_jobs_status_chk",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_runtime_jobs_kind", "runtime_jobs", ["kind"])
    op.create_index("ix_runtime_jobs_status", "runtime_jobs", ["status"])
    op.create_index(
        "ix_runtime_jobs_claim",
        "runtime_jobs",
        ["status", "available_at", "created_at"],
    )
    op.create_index(
        "ix_runtime_jobs_lease",
        "runtime_jobs",
        ["status", "lease_until"],
    )
    active_where = sa.text("dedupe_key IS NOT NULL AND status IN ('queued', 'running')")
    dialect = op.get_bind().dialect.name
    kwargs = {}
    if dialect == "sqlite":
        kwargs["sqlite_where"] = active_where
    elif dialect == "postgresql":
        kwargs["postgresql_where"] = active_where
    op.create_index(
        "ix_runtime_jobs_active_dedupe_uidx",
        "runtime_jobs",
        ["dedupe_key"],
        unique=True,
        **kwargs,
    )


def downgrade() -> None:
    op.drop_index("ix_runtime_jobs_active_dedupe_uidx", table_name="runtime_jobs")
    op.drop_index("ix_runtime_jobs_lease", table_name="runtime_jobs")
    op.drop_index("ix_runtime_jobs_claim", table_name="runtime_jobs")
    op.drop_index("ix_runtime_jobs_status", table_name="runtime_jobs")
    op.drop_index("ix_runtime_jobs_kind", table_name="runtime_jobs")
    op.drop_table("runtime_jobs")
