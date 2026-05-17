"""add knowledge lifecycle contract

Revision ID: 20260517_0015
Revises: 20260517_0014
Create Date: 2026-05-17 21:30:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260517_0015"
down_revision: str | None = "20260517_0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "knowledge_sources",
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "knowledge_sources",
        sa.Column("disabled_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "knowledge_sources",
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "knowledge_sources",
        sa.Column("last_indexed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "knowledge_sources",
        sa.Column("last_ingestion_error", sa.Text(), nullable=True),
    )
    op.add_column(
        "knowledge_sources",
        sa.Column(
            "health_status",
            sa.String(length=64),
            nullable=False,
            server_default="HEALTHY",
        ),
    )
    op.create_index(
        "ix_knowledge_sources_health_status",
        "knowledge_sources",
        ["health_status"],
    )

    op.add_column(
        "knowledge_documents",
        sa.Column("logical_document_id", sa.String(length=36), nullable=True),
    )
    op.add_column(
        "knowledge_documents",
        sa.Column("superseded_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_knowledge_documents_logical_document_id",
        "knowledge_documents",
        ["logical_document_id"],
    )
    op.execute(
        """
        UPDATE knowledge_documents
        SET logical_document_id = id
        WHERE logical_document_id IS NULL
        """
    )


def downgrade() -> None:
    op.drop_index("ix_knowledge_documents_logical_document_id", table_name="knowledge_documents")
    op.drop_column("knowledge_documents", "superseded_at")
    op.drop_column("knowledge_documents", "logical_document_id")
    op.drop_index("ix_knowledge_sources_health_status", table_name="knowledge_sources")
    op.drop_column("knowledge_sources", "health_status")
    op.drop_column("knowledge_sources", "last_ingestion_error")
    op.drop_column("knowledge_sources", "last_indexed_at")
    op.drop_column("knowledge_sources", "archived_at")
    op.drop_column("knowledge_sources", "disabled_at")
    op.drop_column("knowledge_sources", "expires_at")
