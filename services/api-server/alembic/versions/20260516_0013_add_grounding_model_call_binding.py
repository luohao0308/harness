"""add grounding model call binding fields

Revision ID: 20260516_0013
Revises: 20260516_0012
Create Date: 2026-05-16 11:15:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260516_0013"
down_revision: str | None = "20260516_0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "model_calls",
        sa.Column("grounding_correlation_id", sa.String(length=36), nullable=True),
    )
    op.add_column(
        "model_calls",
        sa.Column("prompt_manifest_id", sa.String(length=36), nullable=True),
    )
    op.add_column(
        "model_calls",
        sa.Column("model_request_sha256", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "model_calls",
        sa.Column("attempt_index", sa.Integer(), nullable=False, server_default="1"),
    )
    op.add_column(
        "model_calls",
        sa.Column("terminal_status", sa.String(length=64), nullable=True),
    )
    op.create_index(
        "ix_model_calls_grounding_correlation",
        "model_calls",
        ["grounding_correlation_id"],
    )
    op.create_index("ix_model_calls_prompt_manifest", "model_calls", ["prompt_manifest_id"])

    op.add_column(
        "prompt_assembly_manifests",
        sa.Column("grounding_correlation_id", sa.String(length=36), nullable=True),
    )
    op.execute(
        "UPDATE prompt_assembly_manifests "
        "SET grounding_correlation_id = retrieval_session_id "
        "WHERE grounding_correlation_id IS NULL"
    )
    with op.batch_alter_table("prompt_assembly_manifests") as batch_op:
        batch_op.alter_column("grounding_correlation_id", nullable=False)
    op.create_index(
        "ix_prompt_assembly_manifests_grounding_correlation",
        "prompt_assembly_manifests",
        ["grounding_correlation_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_prompt_assembly_manifests_grounding_correlation",
        table_name="prompt_assembly_manifests",
    )
    op.drop_column("prompt_assembly_manifests", "grounding_correlation_id")
    op.drop_index("ix_model_calls_prompt_manifest", table_name="model_calls")
    op.drop_index("ix_model_calls_grounding_correlation", table_name="model_calls")
    op.drop_column("model_calls", "terminal_status")
    op.drop_column("model_calls", "attempt_index")
    op.drop_column("model_calls", "model_request_sha256")
    op.drop_column("model_calls", "prompt_manifest_id")
    op.drop_column("model_calls", "grounding_correlation_id")
