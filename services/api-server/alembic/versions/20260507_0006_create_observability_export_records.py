"""create observability export records

Revision ID: 20260507_0006
Revises: 20260506_0005
Create Date: 2026-05-07 10:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260507_0006"
down_revision: str | None = "20260506_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "observability_export_records",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=True),
        sa.Column("actor_id", sa.Text(), nullable=True),
        sa.Column("export_type", sa.String(length=64), nullable=False),
        sa.Column("filename", sa.Text(), nullable=False),
        sa.Column("content_type", sa.Text(), nullable=False),
        sa.Column("format", sa.String(length=32), nullable=False),
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.Column("row_count", sa.Integer(), nullable=False),
        sa.Column("filter_json", sa.JSON(), nullable=False),
        sa.Column("storage_driver", sa.String(length=64), nullable=False),
        sa.Column("storage_uri", sa.Text(), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_observability_export_records_export_type"),
        "observability_export_records",
        ["export_type"],
        unique=False,
    )
    op.create_index(
        op.f("ix_observability_export_records_organization_id"),
        "observability_export_records",
        ["organization_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_observability_export_records_organization_id"),
        table_name="observability_export_records",
    )
    op.drop_index(
        op.f("ix_observability_export_records_export_type"),
        table_name="observability_export_records",
    )
    op.drop_table("observability_export_records")
