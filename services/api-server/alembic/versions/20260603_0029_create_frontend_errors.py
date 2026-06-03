"""create frontend errors

Revision ID: 20260603_0029
Revises: 20260602_0028
Create Date: 2026-06-03 00:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "20260603_0029"
down_revision = "20260602_0028"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "frontend_errors",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=False),
        sa.Column("stack", sa.Text(), nullable=True),
        sa.Column("browser", sa.Text(), nullable=False, server_default=""),
        sa.Column("metadata_json", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_frontend_errors_org_created",
        "frontend_errors",
        ["organization_id", "created_at"],
    )
    op.create_index("ix_frontend_errors_organization_id", "frontend_errors", ["organization_id"])
    op.create_index("ix_frontend_errors_user_created", "frontend_errors", ["user_id", "created_at"])
    op.create_index("ix_frontend_errors_user_id", "frontend_errors", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_frontend_errors_user_id", table_name="frontend_errors")
    op.drop_index("ix_frontend_errors_user_created", table_name="frontend_errors")
    op.drop_index("ix_frontend_errors_organization_id", table_name="frontend_errors")
    op.drop_index("ix_frontend_errors_org_created", table_name="frontend_errors")
    op.drop_table("frontend_errors")
