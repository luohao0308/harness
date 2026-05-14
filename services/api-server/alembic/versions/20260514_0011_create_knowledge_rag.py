"""create knowledge rag records

Revision ID: 20260514_0011
Revises: 20260514_0010
Create Date: 2026-05-14 12:58:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260514_0011"
down_revision: str | None = "20260514_0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        # The v1 schema stores vectors as JSON/Text so private deployments do
        # not fail when pgvector is absent. Operators can enable the extension
        # before switching the app's vector capability to "available".
        try:
            with op.get_context().autocommit_block():
                op.execute("CREATE EXTENSION IF NOT EXISTS vector")
        except Exception:
            pass

    op.create_table(
        "knowledge_sources",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("organization_id", sa.String(length=36), nullable=True),
        sa.Column("agent_id", sa.String(length=64), sa.ForeignKey("agents.id"), nullable=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("source_type", sa.String(length=64), nullable=False, server_default="text"),
        sa.Column("status", sa.String(length=64), nullable=False, server_default="ACTIVE"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("settings_json", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("metadata_json", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("idempotency_key", sa.Text(), nullable=True),
        sa.Column("created_by", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint(
            "organization_id",
            "agent_id",
            "idempotency_key",
            name="knowledge_sources_scope_idempotency_uidx",
        ),
    )
    op.create_index("ix_knowledge_sources_org", "knowledge_sources", ["organization_id"])
    op.create_index("ix_knowledge_sources_agent", "knowledge_sources", ["agent_id"])
    op.create_index("ix_knowledge_sources_status", "knowledge_sources", ["status"])

    op.create_table(
        "knowledge_documents",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("source_id", sa.String(length=36), sa.ForeignKey("knowledge_sources.id"), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=True),
        sa.Column("agent_id", sa.String(length=64), sa.ForeignKey("agents.id"), nullable=True),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("uri", sa.Text(), nullable=True),
        sa.Column("content_sha256", sa.String(length=64), nullable=False),
        sa.Column("mime_type", sa.Text(), nullable=False, server_default="text/markdown"),
        sa.Column("status", sa.String(length=64), nullable=False, server_default="INDEXED"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("supersedes_document_id", sa.String(length=36), sa.ForeignKey("knowledge_documents.id"), nullable=True),
        sa.Column("ingestion_error", sa.Text(), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("idempotency_key", sa.Text(), nullable=True),
        sa.Column("created_by", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("indexed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_knowledge_documents_source", "knowledge_documents", ["source_id"])
    op.create_index("ix_knowledge_documents_org", "knowledge_documents", ["organization_id"])
    op.create_index("ix_knowledge_documents_agent", "knowledge_documents", ["agent_id"])
    op.create_index("ix_knowledge_documents_status", "knowledge_documents", ["status"])

    op.create_table(
        "knowledge_chunks",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("document_id", sa.String(length=36), sa.ForeignKey("knowledge_documents.id"), nullable=False),
        sa.Column("source_id", sa.String(length=36), sa.ForeignKey("knowledge_sources.id"), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=True),
        sa.Column("agent_id", sa.String(length=64), sa.ForeignKey("agents.id"), nullable=True),
        sa.Column("source_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("document_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("chunk_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("text_sha256", sa.String(length=64), nullable=False),
        sa.Column("start_offset", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("end_offset", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(length=64), nullable=False, server_default="ACTIVE"),
        sa.Column("metadata_json", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("document_id", "chunk_index", "chunk_version", name="knowledge_chunks_document_chunk_version_uidx"),
    )
    op.create_index("ix_knowledge_chunks_document", "knowledge_chunks", ["document_id"])
    op.create_index("ix_knowledge_chunks_source", "knowledge_chunks", ["source_id"])
    op.create_index("ix_knowledge_chunks_org", "knowledge_chunks", ["organization_id"])
    op.create_index("ix_knowledge_chunks_agent", "knowledge_chunks", ["agent_id"])
    op.create_index("ix_knowledge_chunks_status", "knowledge_chunks", ["status"])

    op.create_table(
        "knowledge_embeddings",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("chunk_id", sa.String(length=36), sa.ForeignKey("knowledge_chunks.id"), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=True),
        sa.Column("agent_id", sa.String(length=64), sa.ForeignKey("agents.id"), nullable=True),
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("model", sa.Text(), nullable=False),
        sa.Column("model_version", sa.Text(), nullable=False),
        sa.Column("dimensions", sa.Integer(), nullable=False),
        sa.Column("embedding_vector", sa.Text(), nullable=True),
        sa.Column("embedding_json", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("status", sa.String(length=64), nullable=False, server_default="READY"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_knowledge_embeddings_chunk", "knowledge_embeddings", ["chunk_id"])
    op.create_index("ix_knowledge_embeddings_org", "knowledge_embeddings", ["organization_id"])
    op.create_index("ix_knowledge_embeddings_agent", "knowledge_embeddings", ["agent_id"])

    op.create_table(
        "retrieval_sessions",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("organization_id", sa.String(length=36), nullable=True),
        sa.Column("agent_id", sa.String(length=64), sa.ForeignKey("agents.id"), nullable=False),
        sa.Column("run_id", sa.String(length=36), sa.ForeignKey("tasks.id"), nullable=True),
        sa.Column("query", sa.Text(), nullable=False),
        sa.Column("mode", sa.String(length=64), nullable=False, server_default="local"),
        sa.Column("local_status", sa.String(length=64), nullable=False, server_default="insufficient"),
        sa.Column("vector_capability", sa.String(length=64), nullable=False, server_default="unavailable"),
        sa.Column("strategy", sa.String(length=64), nullable=False, server_default="lexical"),
        sa.Column("min_hits", sa.Integer(), nullable=False, server_default="2"),
        sa.Column("min_score", sa.Float(), nullable=False, server_default="0.62"),
        sa.Column("max_local_chunks", sa.Integer(), nullable=False, server_default="6"),
        sa.Column("max_web_results", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("metadata_json", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_retrieval_sessions_org", "retrieval_sessions", ["organization_id"])
    op.create_index("ix_retrieval_sessions_agent", "retrieval_sessions", ["agent_id"])
    op.create_index("ix_retrieval_sessions_run", "retrieval_sessions", ["run_id"])

    op.create_table(
        "web_research_sources",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("retrieval_session_id", sa.String(length=36), sa.ForeignKey("retrieval_sessions.id"), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=True),
        sa.Column("agent_id", sa.String(length=64), sa.ForeignKey("agents.id"), nullable=False),
        sa.Column("run_id", sa.String(length=36), sa.ForeignKey("tasks.id"), nullable=True),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("content_sha256", sa.String(length=64), nullable=False),
        sa.Column("snippet", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=64), nullable=False, server_default="READY"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_web_research_sources_retrieval", "web_research_sources", ["retrieval_session_id"])
    op.create_index("ix_web_research_sources_org", "web_research_sources", ["organization_id"])
    op.create_index("ix_web_research_sources_agent", "web_research_sources", ["agent_id"])
    op.create_index("ix_web_research_sources_run", "web_research_sources", ["run_id"])

    op.create_table(
        "retrieval_hits",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("retrieval_session_id", sa.String(length=36), sa.ForeignKey("retrieval_sessions.id"), nullable=False),
        sa.Column("chunk_id", sa.String(length=36), sa.ForeignKey("knowledge_chunks.id"), nullable=True),
        sa.Column("web_source_id", sa.String(length=36), sa.ForeignKey("web_research_sources.id"), nullable=True),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("score", sa.Float(), nullable=False, server_default="0"),
        sa.Column("source_kind", sa.String(length=64), nullable=False),
        sa.Column("document_id", sa.String(length=36), sa.ForeignKey("knowledge_documents.id"), nullable=True),
        sa.Column("document_version", sa.Integer(), nullable=True),
        sa.Column("snippet", sa.Text(), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_retrieval_hits_session", "retrieval_hits", ["retrieval_session_id"])
    op.create_index("ix_retrieval_hits_chunk", "retrieval_hits", ["chunk_id"])
    op.create_index("ix_retrieval_hits_web_source", "retrieval_hits", ["web_source_id"])

    op.create_table(
        "citation_records",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("retrieval_session_id", sa.String(length=36), sa.ForeignKey("retrieval_sessions.id"), nullable=False),
        sa.Column("retrieval_hit_id", sa.String(length=36), sa.ForeignKey("retrieval_hits.id"), nullable=False),
        sa.Column("run_id", sa.String(length=36), sa.ForeignKey("tasks.id"), nullable=True),
        sa.Column("message_id", sa.Text(), nullable=True),
        sa.Column("citation_key", sa.Text(), nullable=False),
        sa.Column("source_kind", sa.String(length=64), nullable=False),
        sa.Column("chunk_id", sa.String(length=36), sa.ForeignKey("knowledge_chunks.id"), nullable=True),
        sa.Column("web_source_id", sa.String(length=36), sa.ForeignKey("web_research_sources.id"), nullable=True),
        sa.Column("claim_text", sa.Text(), nullable=True),
        sa.Column("quoted_text", sa.Text(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="0"),
        sa.Column("metadata_json", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_citation_records_session", "citation_records", ["retrieval_session_id"])
    op.create_index("ix_citation_records_hit", "citation_records", ["retrieval_hit_id"])
    op.create_index("ix_citation_records_run", "citation_records", ["run_id"])


def downgrade() -> None:
    op.drop_index("ix_citation_records_run", table_name="citation_records")
    op.drop_index("ix_citation_records_hit", table_name="citation_records")
    op.drop_index("ix_citation_records_session", table_name="citation_records")
    op.drop_table("citation_records")
    op.drop_index("ix_retrieval_hits_web_source", table_name="retrieval_hits")
    op.drop_index("ix_retrieval_hits_chunk", table_name="retrieval_hits")
    op.drop_index("ix_retrieval_hits_session", table_name="retrieval_hits")
    op.drop_table("retrieval_hits")
    op.drop_index("ix_web_research_sources_run", table_name="web_research_sources")
    op.drop_index("ix_web_research_sources_agent", table_name="web_research_sources")
    op.drop_index("ix_web_research_sources_org", table_name="web_research_sources")
    op.drop_index("ix_web_research_sources_retrieval", table_name="web_research_sources")
    op.drop_table("web_research_sources")
    op.drop_index("ix_retrieval_sessions_run", table_name="retrieval_sessions")
    op.drop_index("ix_retrieval_sessions_agent", table_name="retrieval_sessions")
    op.drop_index("ix_retrieval_sessions_org", table_name="retrieval_sessions")
    op.drop_table("retrieval_sessions")
    op.drop_index("ix_knowledge_embeddings_agent", table_name="knowledge_embeddings")
    op.drop_index("ix_knowledge_embeddings_org", table_name="knowledge_embeddings")
    op.drop_index("ix_knowledge_embeddings_chunk", table_name="knowledge_embeddings")
    op.drop_table("knowledge_embeddings")
    op.drop_index("ix_knowledge_chunks_status", table_name="knowledge_chunks")
    op.drop_index("ix_knowledge_chunks_agent", table_name="knowledge_chunks")
    op.drop_index("ix_knowledge_chunks_org", table_name="knowledge_chunks")
    op.drop_index("ix_knowledge_chunks_source", table_name="knowledge_chunks")
    op.drop_index("ix_knowledge_chunks_document", table_name="knowledge_chunks")
    op.drop_table("knowledge_chunks")
    op.drop_index("ix_knowledge_documents_status", table_name="knowledge_documents")
    op.drop_index("ix_knowledge_documents_agent", table_name="knowledge_documents")
    op.drop_index("ix_knowledge_documents_org", table_name="knowledge_documents")
    op.drop_index("ix_knowledge_documents_source", table_name="knowledge_documents")
    op.drop_table("knowledge_documents")
    op.drop_index("ix_knowledge_sources_status", table_name="knowledge_sources")
    op.drop_index("ix_knowledge_sources_agent", table_name="knowledge_sources")
    op.drop_index("ix_knowledge_sources_org", table_name="knowledge_sources")
    op.drop_table("knowledge_sources")
