"""create deleted entities

Revision ID: 20260626_0047
Revises: 20260624_0046
Create Date: 2026-06-26 00:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "20260626_0047"
down_revision = "20260624_0046"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "deleted_entities",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("entity_type", sa.String(length=64), nullable=False),
        sa.Column("entity_id", sa.String(length=36), nullable=False),
        sa.Column("deleted_by", sa.String(length=36), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("data_snapshot", sa.JSON(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("deleted_entities") as batch_op:
        batch_op.create_index("ix_deleted_entities_entity_type", ["entity_type"])
        batch_op.create_index("ix_deleted_entities_entity_id", ["entity_id"])
        batch_op.create_index("ix_deleted_entities_deleted_at", ["deleted_at"])


def downgrade() -> None:
    with op.batch_alter_table("deleted_entities") as batch_op:
        batch_op.drop_index("ix_deleted_entities_deleted_at")
        batch_op.drop_index("ix_deleted_entities_entity_id")
        batch_op.drop_index("ix_deleted_entities_entity_type")
    op.drop_table("deleted_entities")
