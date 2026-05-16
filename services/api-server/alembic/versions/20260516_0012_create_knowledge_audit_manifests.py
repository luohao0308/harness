"""create knowledge audit manifests

Revision ID: 20260516_0012
Revises: 20260514_0011
Create Date: 2026-05-16 07:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260516_0012"
down_revision: str | None = "20260514_0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "prompt_assembly_manifests",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "retrieval_session_id",
            sa.String(length=36),
            sa.ForeignKey("retrieval_sessions.id"),
            nullable=False,
        ),
        sa.Column("run_id", sa.String(length=36), sa.ForeignKey("tasks.id"), nullable=True),
        sa.Column("organization_id", sa.String(length=36), nullable=True),
        sa.Column("agent_id", sa.String(length=64), sa.ForeignKey("agents.id"), nullable=False),
        sa.Column("query", sa.Text(), nullable=False),
        sa.Column("included_retrieval_hit_ids_json", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("omitted_candidates_json", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("source_snapshots_json", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("token_budget_json", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("prompt_sections_json", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("evidence_text_sha256", sa.String(length=64), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_prompt_assembly_manifests_session", "prompt_assembly_manifests", ["retrieval_session_id"])
    op.create_index("ix_prompt_assembly_manifests_run", "prompt_assembly_manifests", ["run_id"])
    op.create_index("ix_prompt_assembly_manifests_org", "prompt_assembly_manifests", ["organization_id"])
    op.create_index("ix_prompt_assembly_manifests_agent", "prompt_assembly_manifests", ["agent_id"])

    op.create_table(
        "knowledge_policy_audits",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "retrieval_session_id",
            sa.String(length=36),
            sa.ForeignKey("retrieval_sessions.id"),
            nullable=False,
        ),
        sa.Column("run_id", sa.String(length=36), sa.ForeignKey("tasks.id"), nullable=True),
        sa.Column("organization_id", sa.String(length=36), nullable=True),
        sa.Column("agent_id", sa.String(length=64), sa.ForeignKey("agents.id"), nullable=False),
        sa.Column("decision", sa.String(length=64), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("source_kind", sa.String(length=64), nullable=True),
        sa.Column("source_ref_id", sa.Text(), nullable=True),
        sa.Column("safe_metadata_json", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_knowledge_policy_audits_session", "knowledge_policy_audits", ["retrieval_session_id"])
    op.create_index("ix_knowledge_policy_audits_run", "knowledge_policy_audits", ["run_id"])
    op.create_index("ix_knowledge_policy_audits_org", "knowledge_policy_audits", ["organization_id"])
    op.create_index("ix_knowledge_policy_audits_agent", "knowledge_policy_audits", ["agent_id"])
    op.create_index("ix_knowledge_policy_audits_decision", "knowledge_policy_audits", ["decision"])


def downgrade() -> None:
    op.drop_index("ix_knowledge_policy_audits_decision", table_name="knowledge_policy_audits")
    op.drop_index("ix_knowledge_policy_audits_agent", table_name="knowledge_policy_audits")
    op.drop_index("ix_knowledge_policy_audits_org", table_name="knowledge_policy_audits")
    op.drop_index("ix_knowledge_policy_audits_run", table_name="knowledge_policy_audits")
    op.drop_index("ix_knowledge_policy_audits_session", table_name="knowledge_policy_audits")
    op.drop_table("knowledge_policy_audits")
    op.drop_index("ix_prompt_assembly_manifests_agent", table_name="prompt_assembly_manifests")
    op.drop_index("ix_prompt_assembly_manifests_org", table_name="prompt_assembly_manifests")
    op.drop_index("ix_prompt_assembly_manifests_run", table_name="prompt_assembly_manifests")
    op.drop_index("ix_prompt_assembly_manifests_session", table_name="prompt_assembly_manifests")
    op.drop_table("prompt_assembly_manifests")
