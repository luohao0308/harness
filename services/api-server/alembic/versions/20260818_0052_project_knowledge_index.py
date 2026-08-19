"""add durable Desktop project Knowledge index receipts

Revision ID: 20260818_0052
Revises: 20260817_0051
Create Date: 2026-08-18 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260818_0052"
down_revision: str | None = "20260817_0051"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "project_knowledge_indexes",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("agent_id", sa.String(length=64), nullable=False),
        sa.Column("knowledge_source_id", sa.String(length=36), nullable=False),
        sa.Column("desktop_profile_id", sa.String(length=128), nullable=False),
        sa.Column("root_identity", sa.String(length=64), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="ACTIVE"),
        sa.Column("ignore_patterns_json", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("snapshot_generation", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("snapshot_cursor", sa.String(length=128), nullable=True),
        sa.Column("last_snapshot_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_sync_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("idempotency_key", sa.String(length=200), nullable=True),
        sa.Column("unbound_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('ACTIVE', 'PAUSED', 'ERROR', 'UNBOUND')",
            name="project_knowledge_indexes_status_chk",
        ),
        sa.ForeignKeyConstraint(["agent_id"], ["agents.id"]),
        sa.ForeignKeyConstraint(["knowledge_source_id"], ["knowledge_sources.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organization_id",
            "agent_id",
            "desktop_profile_id",
            "root_identity",
            name="project_knowledge_indexes_binding_uidx",
        ),
        sa.UniqueConstraint(
            "organization_id",
            "agent_id",
            "idempotency_key",
            name="project_knowledge_indexes_scope_idempotency_uidx",
        ),
        sa.UniqueConstraint(
            "knowledge_source_id",
            name="project_knowledge_indexes_source_uidx",
        ),
    )
    op.create_index(
        "ix_project_knowledge_indexes_organization_id",
        "project_knowledge_indexes",
        ["organization_id"],
    )
    op.create_index(
        "ix_project_knowledge_indexes_agent_id",
        "project_knowledge_indexes",
        ["agent_id"],
    )
    op.create_index(
        "ix_project_knowledge_indexes_knowledge_source_id",
        "project_knowledge_indexes",
        ["knowledge_source_id"],
    )
    op.create_index(
        "ix_project_knowledge_indexes_desktop_profile_id",
        "project_knowledge_indexes",
        ["desktop_profile_id"],
    )
    op.create_index(
        "ix_project_knowledge_indexes_root_identity",
        "project_knowledge_indexes",
        ["root_identity"],
    )
    op.create_index(
        "ix_project_knowledge_indexes_status",
        "project_knowledge_indexes",
        ["status"],
    )
    op.create_index(
        "ix_project_knowledge_indexes_idempotency_key",
        "project_knowledge_indexes",
        ["idempotency_key"],
    )

    op.create_table(
        "project_knowledge_files",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("index_id", sa.String(length=36), nullable=False),
        sa.Column("relative_path", sa.Text(), nullable=False),
        sa.Column("path_sha256", sa.String(length=64), nullable=False),
        sa.Column("content_sha256", sa.String(length=64), nullable=True),
        sa.Column("size_bytes", sa.BigInteger(), nullable=True),
        sa.Column("mime_type", sa.String(length=120), nullable=True),
        sa.Column("knowledge_document_id", sa.String(length=36), nullable=True),
        sa.Column("document_version", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="PENDING"),
        sa.Column("last_seen_generation", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_scanned_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("tombstoned_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('PENDING', 'INDEXED', 'STALE', 'TOMBSTONED', 'IGNORED', 'ERROR')",
            name="project_knowledge_files_status_chk",
        ),
        sa.ForeignKeyConstraint(["index_id"], ["project_knowledge_indexes.id"]),
        sa.ForeignKeyConstraint(["knowledge_document_id"], ["knowledge_documents.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "index_id",
            "relative_path",
            name="project_knowledge_files_index_path_uidx",
        ),
    )
    op.create_index("ix_project_knowledge_files_index_id", "project_knowledge_files", ["index_id"])
    op.create_index(
        "ix_project_knowledge_files_path_sha256",
        "project_knowledge_files",
        ["path_sha256"],
    )
    op.create_index(
        "ix_project_knowledge_files_content_sha256",
        "project_knowledge_files",
        ["content_sha256"],
    )
    op.create_index(
        "ix_project_knowledge_files_knowledge_document_id",
        "project_knowledge_files",
        ["knowledge_document_id"],
    )
    op.create_index("ix_project_knowledge_files_status", "project_knowledge_files", ["status"])


def downgrade() -> None:
    bind = op.get_bind()
    _ensure_downgrade_safe(bind)
    op.drop_index("ix_project_knowledge_files_status", table_name="project_knowledge_files")
    op.drop_index(
        "ix_project_knowledge_files_knowledge_document_id",
        table_name="project_knowledge_files",
    )
    op.drop_index("ix_project_knowledge_files_content_sha256", table_name="project_knowledge_files")
    op.drop_index("ix_project_knowledge_files_path_sha256", table_name="project_knowledge_files")
    op.drop_index("ix_project_knowledge_files_index_id", table_name="project_knowledge_files")
    op.drop_table("project_knowledge_files")
    op.drop_index(
        "ix_project_knowledge_indexes_idempotency_key",
        table_name="project_knowledge_indexes",
    )
    op.drop_index("ix_project_knowledge_indexes_status", table_name="project_knowledge_indexes")
    op.drop_index(
        "ix_project_knowledge_indexes_root_identity",
        table_name="project_knowledge_indexes",
    )
    op.drop_index(
        "ix_project_knowledge_indexes_desktop_profile_id",
        table_name="project_knowledge_indexes",
    )
    op.drop_index(
        "ix_project_knowledge_indexes_knowledge_source_id",
        table_name="project_knowledge_indexes",
    )
    op.drop_index("ix_project_knowledge_indexes_agent_id", table_name="project_knowledge_indexes")
    op.drop_index(
        "ix_project_knowledge_indexes_organization_id",
        table_name="project_knowledge_indexes",
    )
    op.drop_table("project_knowledge_indexes")


def _ensure_downgrade_safe(bind: sa.Connection) -> None:
    remaining = bind.execute(
        sa.text("SELECT COUNT(*) FROM project_knowledge_indexes WHERE status <> 'UNBOUND'")
    ).scalar_one()
    if remaining:
        raise RuntimeError("Cannot downgrade project Knowledge index while active bindings exist")
