"""add user avatar storage

Revision ID: 20260609_0036
Revises: 20260608_0035
Create Date: 2026-06-09 00:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "20260609_0036"
down_revision = "20260608_0035"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("avatar_mime_type", sa.String(length=128), nullable=True))
    op.add_column("users", sa.Column("avatar_content", sa.LargeBinary(), nullable=True))
    op.add_column("users", sa.Column("avatar_sha256", sa.String(length=64), nullable=True))
    op.add_column(
        "users",
        sa.Column("avatar_updated_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("users", "avatar_updated_at")
    op.drop_column("users", "avatar_sha256")
    op.drop_column("users", "avatar_content")
    op.drop_column("users", "avatar_mime_type")
