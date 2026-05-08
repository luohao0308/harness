"""create_system_settings

Revision ID: 20260505_0004
Revises: 20260504_0003
Create Date: 2026-05-05 15:30:00
"""

from alembic import op
import sqlalchemy as sa

revision = "20260505_0004"
down_revision = "20260504_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "system_settings",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("organization_id", sa.String(length=36), nullable=True),
        sa.Column("key", sa.String(length=128), nullable=False),
        sa.Column("value_json", sa.JSON(), nullable=False),
        sa.Column("updated_by", sa.Text(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("organization_id", "key", name="system_settings_org_key_uidx"),
    )
    op.create_index("system_settings_organization_id_idx", "system_settings", ["organization_id"])
    op.create_index("system_settings_key_idx", "system_settings", ["key"])


def downgrade() -> None:
    op.drop_index("system_settings_key_idx", table_name="system_settings")
    op.drop_index("system_settings_organization_id_idx", table_name="system_settings")
    op.drop_table("system_settings")
