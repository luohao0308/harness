"""create web research attempts

Revision ID: 20260517_0016
Revises: 20260517_0015
Create Date: 2026-05-17 22:05:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260517_0016"
down_revision: str | None = "20260517_0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "web_research_attempts",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("run_id", sa.String(length=36), nullable=False),
        sa.Column("retrieval_session_id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=True),
        sa.Column("agent_id", sa.String(length=64), nullable=False),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("call_slot", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=64), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["agent_id"], ["agents.id"]),
        sa.ForeignKeyConstraint(["retrieval_session_id"], ["retrieval_sessions.id"]),
        sa.ForeignKeyConstraint(["run_id"], ["tasks.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "run_id",
            "call_slot",
            name="web_research_attempts_run_slot_uidx",
        ),
    )
    op.create_index(
        "ix_web_research_attempts_run_id",
        "web_research_attempts",
        ["run_id"],
    )
    op.create_index(
        "ix_web_research_attempts_retrieval_session_id",
        "web_research_attempts",
        ["retrieval_session_id"],
    )
    op.create_index(
        "ix_web_research_attempts_organization_id",
        "web_research_attempts",
        ["organization_id"],
    )
    op.create_index(
        "ix_web_research_attempts_agent_id",
        "web_research_attempts",
        ["agent_id"],
    )
    op.create_index(
        "ix_web_research_attempts_provider",
        "web_research_attempts",
        ["provider"],
    )
    op.create_index(
        "ix_web_research_attempts_status",
        "web_research_attempts",
        ["status"],
    )


def downgrade() -> None:
    op.drop_index("ix_web_research_attempts_status", table_name="web_research_attempts")
    op.drop_index("ix_web_research_attempts_provider", table_name="web_research_attempts")
    op.drop_index("ix_web_research_attempts_agent_id", table_name="web_research_attempts")
    op.drop_index(
        "ix_web_research_attempts_organization_id",
        table_name="web_research_attempts",
    )
    op.drop_index(
        "ix_web_research_attempts_retrieval_session_id",
        table_name="web_research_attempts",
    )
    op.drop_index("ix_web_research_attempts_run_id", table_name="web_research_attempts")
    op.drop_table("web_research_attempts")
