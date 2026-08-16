"""create mobile devices

Revision ID: 20260627_0048
Revises: 20260626_0047
Create Date: 2026-06-27 00:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "20260627_0048"
down_revision = "20260626_0047"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "mobile_devices",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=True),
        sa.Column("platform", sa.String(length=16), nullable=False),
        sa.Column("push_token", sa.Text(), nullable=False),
        sa.Column("device_name", sa.Text(), nullable=True),
        sa.Column("app_version", sa.String(length=64), nullable=True),
        sa.Column("notifications_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("preferences_json", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("push_token", name="mobile_devices_push_token_uidx"),
    )
    op.create_index("ix_mobile_devices_user_id", "mobile_devices", ["user_id"])
    op.create_index("ix_mobile_devices_organization_id", "mobile_devices", ["organization_id"])
    op.create_index(
        "ix_mobile_devices_user_platform",
        "mobile_devices",
        ["user_id", "platform"],
    )
    op.create_index(
        "ix_mobile_devices_org_enabled",
        "mobile_devices",
        ["organization_id", "notifications_enabled"],
    )


def downgrade() -> None:
    op.drop_index("ix_mobile_devices_org_enabled", table_name="mobile_devices")
    op.drop_index("ix_mobile_devices_user_platform", table_name="mobile_devices")
    op.drop_index("ix_mobile_devices_organization_id", table_name="mobile_devices")
    op.drop_index("ix_mobile_devices_user_id", table_name="mobile_devices")
    op.drop_table("mobile_devices")
