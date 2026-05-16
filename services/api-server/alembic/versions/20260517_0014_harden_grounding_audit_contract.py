"""harden grounding audit contract

Revision ID: 20260517_0014
Revises: 20260516_0013
Create Date: 2026-05-17 00:45:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260517_0014"
down_revision: str | None = "20260516_0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "model_calls",
        sa.Column("legacy_prompt_manifest_id", sa.String(length=36), nullable=True),
    )
    op.add_column(
        "model_calls",
        sa.Column(
            "model_request_hash_schema_version",
            sa.Integer(),
            nullable=False,
            server_default="1",
        ),
    )
    op.add_column(
        "model_calls",
        sa.Column(
            "request_message_hashes_json",
            sa.JSON(),
            nullable=False,
            server_default="[]",
        ),
    )
    op.add_column(
        "model_calls",
        sa.Column("request_message_hashes_sha256", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "model_calls",
        sa.Column(
            "hash_recomputability_status",
            sa.String(length=64),
            nullable=False,
            server_default="legacy_not_recomputable",
        ),
    )

    op.execute(
        """
        UPDATE model_calls
        SET legacy_prompt_manifest_id = prompt_manifest_id,
            prompt_manifest_id = NULL
        WHERE prompt_manifest_id IS NOT NULL
          AND NOT EXISTS (
            SELECT 1
            FROM prompt_assembly_manifests
            WHERE prompt_assembly_manifests.id = model_calls.prompt_manifest_id
              AND prompt_assembly_manifests.run_id = model_calls.task_id
              AND prompt_assembly_manifests.grounding_correlation_id =
                  model_calls.grounding_correlation_id
          )
        """
    )

    if op.get_bind().dialect.name == "sqlite":
        with op.batch_alter_table("prompt_assembly_manifests") as batch:
            batch.create_unique_constraint(
                "prompt_assembly_manifests_binding_uidx",
                ["id", "run_id", "grounding_correlation_id"],
            )
        with op.batch_alter_table("model_calls") as batch:
            batch.create_foreign_key(
                "model_calls_prompt_manifest_id_fkey",
                "prompt_assembly_manifests",
                ["prompt_manifest_id"],
                ["id"],
            )
            batch.create_foreign_key(
                "model_calls_prompt_manifest_binding_fkey",
                "prompt_assembly_manifests",
                ["prompt_manifest_id", "task_id", "grounding_correlation_id"],
                ["id", "run_id", "grounding_correlation_id"],
            )
        return

    op.create_unique_constraint(
        "prompt_assembly_manifests_binding_uidx",
        "prompt_assembly_manifests",
        ["id", "run_id", "grounding_correlation_id"],
    )
    op.create_foreign_key(
        "model_calls_prompt_manifest_id_fkey",
        "model_calls",
        "prompt_assembly_manifests",
        ["prompt_manifest_id"],
        ["id"],
    )
    op.create_foreign_key(
        "model_calls_prompt_manifest_binding_fkey",
        "model_calls",
        "prompt_assembly_manifests",
        ["prompt_manifest_id", "task_id", "grounding_correlation_id"],
        ["id", "run_id", "grounding_correlation_id"],
    )


def downgrade() -> None:
    if op.get_bind().dialect.name == "sqlite":
        with op.batch_alter_table("model_calls") as batch:
            batch.drop_constraint(
                "model_calls_prompt_manifest_binding_fkey",
                type_="foreignkey",
            )
            batch.drop_constraint(
                "model_calls_prompt_manifest_id_fkey",
                type_="foreignkey",
            )
        with op.batch_alter_table("prompt_assembly_manifests") as batch:
            batch.drop_constraint(
                "prompt_assembly_manifests_binding_uidx",
                type_="unique",
            )
        op.drop_column("model_calls", "hash_recomputability_status")
        op.drop_column("model_calls", "request_message_hashes_sha256")
        op.drop_column("model_calls", "request_message_hashes_json")
        op.drop_column("model_calls", "model_request_hash_schema_version")
        op.drop_column("model_calls", "legacy_prompt_manifest_id")
        return

    op.drop_constraint(
        "model_calls_prompt_manifest_binding_fkey",
        "model_calls",
        type_="foreignkey",
    )
    op.drop_constraint(
        "model_calls_prompt_manifest_id_fkey",
        "model_calls",
        type_="foreignkey",
    )
    op.drop_constraint(
        "prompt_assembly_manifests_binding_uidx",
        "prompt_assembly_manifests",
        type_="unique",
    )
    op.drop_column("model_calls", "hash_recomputability_status")
    op.drop_column("model_calls", "request_message_hashes_sha256")
    op.drop_column("model_calls", "request_message_hashes_json")
    op.drop_column("model_calls", "model_request_hash_schema_version")
    op.drop_column("model_calls", "legacy_prompt_manifest_id")
