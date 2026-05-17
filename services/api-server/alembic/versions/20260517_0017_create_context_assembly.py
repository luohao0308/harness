"""create context assembly manifests and memory records

Revision ID: 20260517_0017
Revises: 20260517_0016
Create Date: 2026-05-17 09:22:38.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260517_0017"
down_revision = "20260517_0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "agent_memory_records",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=True),
        sa.Column("agent_id", sa.String(length=64), nullable=True),
        sa.Column("owner_user_id", sa.String(length=36), nullable=True),
        sa.Column("run_id", sa.String(length=36), nullable=True),
        sa.Column("message_id", sa.Text(), nullable=True),
        sa.Column("scope", sa.String(length=16), nullable=False),
        sa.Column("source_type", sa.String(length=64), nullable=False),
        sa.Column("canonical_text", sa.Text(), nullable=False),
        sa.Column("content_sha256", sa.String(length=64), nullable=False),
        sa.Column("content_length", sa.Integer(), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("policy_flags_json", sa.JSON(), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("lifecycle_status", sa.String(length=32), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.String(length=36), nullable=True),
        sa.Column("updated_by", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "scope IN ('org', 'agent', 'user', 'run')",
            name="agent_memory_records_scope_check",
        ),
        sa.CheckConstraint(
            "lifecycle_status IN ('active', 'disabled', 'archived', 'deleted', 'expired')",
            name="agent_memory_records_lifecycle_check",
        ),
        sa.CheckConstraint(
            "scope != 'user' OR owner_user_id IS NOT NULL",
            name="agent_memory_records_user_owner_check",
        ),
        sa.CheckConstraint(
            "scope != 'run' OR run_id IS NOT NULL",
            name="agent_memory_records_run_id_check",
        ),
        sa.ForeignKeyConstraint(["agent_id"], ["agents.id"]),
        sa.ForeignKeyConstraint(["run_id"], ["tasks.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_agent_memory_records_agent_id", "agent_memory_records", ["agent_id"])
    op.create_index(
        "ix_agent_memory_records_content_sha256",
        "agent_memory_records",
        ["content_sha256"],
    )
    op.create_index(
        "ix_agent_memory_records_lifecycle_status",
        "agent_memory_records",
        ["lifecycle_status"],
    )
    op.create_index("ix_agent_memory_records_organization_id", "agent_memory_records", ["organization_id"])
    op.create_index("ix_agent_memory_records_owner_user_id", "agent_memory_records", ["owner_user_id"])
    op.create_index("ix_agent_memory_records_run_id", "agent_memory_records", ["run_id"])
    op.create_index("ix_agent_memory_records_scope", "agent_memory_records", ["scope"])
    op.create_index(
        "ix_agent_memory_records_scope_lookup",
        "agent_memory_records",
        ["organization_id", "agent_id", "owner_user_id", "scope", "lifecycle_status"],
    )

    op.create_table(
        "context_assembly_manifests",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=True),
        sa.Column("agent_id", sa.String(length=64), nullable=False),
        sa.Column("run_id", sa.String(length=36), nullable=True),
        sa.Column("retrieval_session_id", sa.String(length=36), nullable=True),
        sa.Column("prompt_manifest_id", sa.String(length=36), nullable=True),
        sa.Column("active_branch_id", sa.Text(), nullable=True),
        sa.Column("active_leaf_id", sa.Text(), nullable=True),
        sa.Column("mode", sa.String(length=32), nullable=False),
        sa.Column("token_budget_json", sa.JSON(), nullable=False),
        sa.Column("sections_json", sa.JSON(), nullable=False),
        sa.Column("included_refs_json", sa.JSON(), nullable=False),
        sa.Column("omitted_refs_json", sa.JSON(), nullable=False),
        sa.Column("policy_decisions_json", sa.JSON(), nullable=False),
        sa.Column("tombstoned_refs_json", sa.JSON(), nullable=False),
        sa.Column("context_text_sha256", sa.String(length=64), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["agent_id"], ["agents.id"]),
        sa.ForeignKeyConstraint(["prompt_manifest_id"], ["prompt_assembly_manifests.id"]),
        sa.ForeignKeyConstraint(["retrieval_session_id"], ["retrieval_sessions.id"]),
        sa.ForeignKeyConstraint(["run_id"], ["tasks.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_context_assembly_manifests_agent_id",
        "context_assembly_manifests",
        ["agent_id"],
    )
    op.create_index(
        "ix_context_assembly_manifests_mode",
        "context_assembly_manifests",
        ["mode"],
    )
    op.create_index(
        "ix_context_assembly_manifests_org_created",
        "context_assembly_manifests",
        ["organization_id", "created_at"],
    )
    op.create_index(
        "ix_context_assembly_manifests_organization_id",
        "context_assembly_manifests",
        ["organization_id"],
    )
    op.create_index(
        "ix_context_assembly_manifests_prompt_manifest_id",
        "context_assembly_manifests",
        ["prompt_manifest_id"],
    )
    op.create_index(
        "ix_context_assembly_manifests_retrieval_session_id",
        "context_assembly_manifests",
        ["retrieval_session_id"],
    )
    op.create_index(
        "ix_context_assembly_manifests_run_id",
        "context_assembly_manifests",
        ["run_id"],
    )

    op.create_table(
        "context_assembly_manifest_lifecycle",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("context_manifest_id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=True),
        sa.Column("lifecycle_status", sa.String(length=32), nullable=False),
        sa.Column("tombstoned_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "lifecycle_status IN ('active', 'tombstoned', 'expired')",
            name="context_assembly_manifest_lifecycle_status_check",
        ),
        sa.ForeignKeyConstraint(["context_manifest_id"], ["context_assembly_manifests.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_context_assembly_manifest_lifecycle_context_manifest_id",
        "context_assembly_manifest_lifecycle",
        ["context_manifest_id"],
    )
    op.create_index(
        "ix_context_assembly_manifest_lifecycle_org_expires",
        "context_assembly_manifest_lifecycle",
        ["organization_id", "expires_at"],
    )
    op.create_index(
        "ix_context_assembly_manifest_lifecycle_organization_id",
        "context_assembly_manifest_lifecycle",
        ["organization_id"],
    )

    bind = op.get_bind()
    op.add_column("model_calls", sa.Column("context_manifest_id", sa.String(length=36), nullable=True))
    if bind.dialect.name != "sqlite":
        op.create_foreign_key(
            "model_calls_context_manifest_id_fkey",
            "model_calls",
            "context_assembly_manifests",
            ["context_manifest_id"],
            ["id"],
        )
    op.create_index("ix_model_calls_context_manifest_id", "model_calls", ["context_manifest_id"])

    if bind.dialect.name == "postgresql":
        op.execute(
            """
            CREATE OR REPLACE FUNCTION reject_context_assembly_manifest_mutation()
            RETURNS trigger AS $$
            BEGIN
              RAISE EXCEPTION 'context_assembly_manifests is append-only';
            END;
            $$ LANGUAGE plpgsql;
            """
        )
        op.execute(
            """
            CREATE TRIGGER context_assembly_manifests_no_update
            BEFORE UPDATE ON context_assembly_manifests
            FOR EACH ROW EXECUTE FUNCTION reject_context_assembly_manifest_mutation();
            """
        )
        op.execute(
            """
            CREATE TRIGGER context_assembly_manifests_no_delete
            BEFORE DELETE ON context_assembly_manifests
            FOR EACH ROW EXECUTE FUNCTION reject_context_assembly_manifest_mutation();
            """
        )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("DROP TRIGGER IF EXISTS context_assembly_manifests_no_delete ON context_assembly_manifests")
        op.execute("DROP TRIGGER IF EXISTS context_assembly_manifests_no_update ON context_assembly_manifests")
        op.execute("DROP FUNCTION IF EXISTS reject_context_assembly_manifest_mutation")

    op.drop_index("ix_model_calls_context_manifest_id", table_name="model_calls")
    if bind.dialect.name != "sqlite":
        op.drop_constraint("model_calls_context_manifest_id_fkey", "model_calls", type_="foreignkey")
    op.drop_column("model_calls", "context_manifest_id")

    op.drop_index(
        "ix_context_assembly_manifest_lifecycle_organization_id",
        table_name="context_assembly_manifest_lifecycle",
    )
    op.drop_index(
        "ix_context_assembly_manifest_lifecycle_org_expires",
        table_name="context_assembly_manifest_lifecycle",
    )
    op.drop_index(
        "ix_context_assembly_manifest_lifecycle_context_manifest_id",
        table_name="context_assembly_manifest_lifecycle",
    )
    op.drop_table("context_assembly_manifest_lifecycle")

    op.drop_index("ix_context_assembly_manifests_run_id", table_name="context_assembly_manifests")
    op.drop_index("ix_context_assembly_manifests_retrieval_session_id", table_name="context_assembly_manifests")
    op.drop_index("ix_context_assembly_manifests_prompt_manifest_id", table_name="context_assembly_manifests")
    op.drop_index("ix_context_assembly_manifests_organization_id", table_name="context_assembly_manifests")
    op.drop_index("ix_context_assembly_manifests_org_created", table_name="context_assembly_manifests")
    op.drop_index("ix_context_assembly_manifests_mode", table_name="context_assembly_manifests")
    op.drop_index("ix_context_assembly_manifests_agent_id", table_name="context_assembly_manifests")
    op.drop_table("context_assembly_manifests")

    op.drop_index("ix_agent_memory_records_scope_lookup", table_name="agent_memory_records")
    op.drop_index("ix_agent_memory_records_scope", table_name="agent_memory_records")
    op.drop_index("ix_agent_memory_records_run_id", table_name="agent_memory_records")
    op.drop_index("ix_agent_memory_records_owner_user_id", table_name="agent_memory_records")
    op.drop_index("ix_agent_memory_records_organization_id", table_name="agent_memory_records")
    op.drop_index("ix_agent_memory_records_lifecycle_status", table_name="agent_memory_records")
    op.drop_index("ix_agent_memory_records_content_sha256", table_name="agent_memory_records")
    op.drop_index("ix_agent_memory_records_agent_id", table_name="agent_memory_records")
    op.drop_table("agent_memory_records")
