"""create workspace context caches

Revision ID: 20260525_0021
Revises: 20260523_0020
Create Date: 2026-05-25 00:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "20260525_0021"
down_revision = "20260523_0020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "workspace_context_caches",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=True),
        sa.Column("agent_id", sa.String(length=64), nullable=True),
        sa.Column("owner_user_id", sa.String(length=36), nullable=True),
        sa.Column("cache_source", sa.String(length=64), nullable=False),
        sa.Column("cache_key_hash", sa.String(length=64), nullable=False),
        sa.Column("schema_version", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("payload_json", sa.JSON(), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("hit_count", sa.Integer(), nullable=False),
        sa.Column("miss_count", sa.Integer(), nullable=False),
        sa.Column("stale_count", sa.Integer(), nullable=False),
        sa.Column("estimated_saved_tokens", sa.Integer(), nullable=False),
        sa.Column("last_hit_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["agent_id"], ["agents.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organization_id",
            "cache_source",
            "cache_key_hash",
            name="workspace_context_caches_org_source_key_uidx",
        ),
    )
    op.create_index(
        "ix_workspace_context_caches_agent_id",
        "workspace_context_caches",
        ["agent_id"],
    )
    op.create_index(
        "ix_workspace_context_caches_cache_key_hash",
        "workspace_context_caches",
        ["cache_key_hash"],
    )
    op.create_index(
        "ix_workspace_context_caches_cache_source",
        "workspace_context_caches",
        ["cache_source"],
    )
    op.create_index(
        "ix_workspace_context_caches_organization_id",
        "workspace_context_caches",
        ["organization_id"],
    )
    op.create_index(
        "ix_workspace_context_caches_owner_user_id",
        "workspace_context_caches",
        ["owner_user_id"],
    )
    op.create_index("ix_workspace_context_caches_status", "workspace_context_caches", ["status"])
    op.create_index(
        "ix_workspace_context_caches_org_source_agent",
        "workspace_context_caches",
        ["organization_id", "cache_source", "agent_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_workspace_context_caches_org_source_agent",
        table_name="workspace_context_caches",
    )
    op.drop_index("ix_workspace_context_caches_status", table_name="workspace_context_caches")
    op.drop_index(
        "ix_workspace_context_caches_owner_user_id",
        table_name="workspace_context_caches",
    )
    op.drop_index(
        "ix_workspace_context_caches_organization_id",
        table_name="workspace_context_caches",
    )
    op.drop_index("ix_workspace_context_caches_cache_source", table_name="workspace_context_caches")
    op.drop_index(
        "ix_workspace_context_caches_cache_key_hash",
        table_name="workspace_context_caches",
    )
    op.drop_index("ix_workspace_context_caches_agent_id", table_name="workspace_context_caches")
    op.drop_table("workspace_context_caches")
