"""create_warm_pool_containers

Revision ID: 20260504_0002
Revises: 20260504_0001
Create Date: 2026-05-04 15:50:00
"""

from alembic import op
import sqlalchemy as sa

revision = "20260504_0002"
down_revision = "20260504_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "warm_pool_containers",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("container_id", sa.Text(), nullable=False),
        sa.Column("image", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=64), nullable=False),
        sa.Column("locked_by", sa.Text(), nullable=True),
        sa.Column("task_id", sa.String(length=36), sa.ForeignKey("tasks.id"), nullable=True),
        sa.Column(
            "sandbox_id",
            sa.String(length=36),
            sa.ForeignKey("sandbox_instances.id"),
            nullable=True,
        ),
        sa.Column("idle_since", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "container_id",
            name="warm_pool_containers_container_id_uidx",
        ),
    )
    op.create_index("warm_pool_containers_status_idx", "warm_pool_containers", ["status"])
    op.create_index("warm_pool_containers_task_id_idx", "warm_pool_containers", ["task_id"])
    op.create_index(
        "warm_pool_containers_sandbox_id_idx",
        "warm_pool_containers",
        ["sandbox_id"],
    )


def downgrade() -> None:
    op.drop_index("warm_pool_containers_sandbox_id_idx", table_name="warm_pool_containers")
    op.drop_index("warm_pool_containers_task_id_idx", table_name="warm_pool_containers")
    op.drop_index("warm_pool_containers_status_idx", table_name="warm_pool_containers")
    op.drop_table("warm_pool_containers")
