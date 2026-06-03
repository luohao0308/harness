"""create notification channels

Revision ID: 20260602_0028
Revises: 20260601_0027
Create Date: 2026-06-02 00:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "20260602_0028"
down_revision = "20260601_0027"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "notification_channels",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("config_json", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("verified", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_by", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "kind IN ('slack', 'email', 'webhook')",
            name="notification_channels_kind_chk",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_notification_channels_kind", "notification_channels", ["kind"])
    op.create_index(
        "ix_notification_channels_org_kind",
        "notification_channels",
        ["organization_id", "kind"],
    )
    op.create_index(
        "ix_notification_channels_organization_id",
        "notification_channels",
        ["organization_id"],
    )
    op.create_index("ix_notification_channels_verified", "notification_channels", ["verified"])


def downgrade() -> None:
    op.drop_index("ix_notification_channels_verified", table_name="notification_channels")
    op.drop_index("ix_notification_channels_organization_id", table_name="notification_channels")
    op.drop_index("ix_notification_channels_org_kind", table_name="notification_channels")
    op.drop_index("ix_notification_channels_kind", table_name="notification_channels")
    op.drop_table("notification_channels")
