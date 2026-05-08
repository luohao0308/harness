"""create agents registry

Revision ID: 20260508_0007
Revises: 20260507_0006
Create Date: 2026-05-08 10:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260508_0007"
down_revision: str | None = "20260507_0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "agents",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("role", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=64), nullable=False),
        sa.Column("model_provider", sa.Text(), nullable=False),
        sa.Column("model_name", sa.Text(), nullable=False),
        sa.Column("system_prompt", sa.Text(), nullable=False),
        sa.Column("tools_json", sa.JSON(), nullable=False),
        sa.Column("routing_tags", sa.JSON(), nullable=False),
        sa.Column("max_parallel_assignments", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "id", name="agents_org_id_uidx"),
    )
    op.create_index(op.f("ix_agents_organization_id"), "agents", ["organization_id"])
    op.create_index(op.f("ix_agents_status"), "agents", ["status"])
    op.create_table(
        "agent_sessions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=True),
        sa.Column("agent_id", sa.String(length=64), nullable=False),
        sa.Column("created_by", sa.String(length=36), nullable=True),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["agent_id"], ["agents.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_agent_sessions_agent_id"), "agent_sessions", ["agent_id"])
    op.create_index(
        op.f("ix_agent_sessions_organization_id"),
        "agent_sessions",
        ["organization_id"],
    )
    op.create_index(op.f("ix_agent_sessions_status"), "agent_sessions", ["status"])
    op.create_table(
        "agent_messages",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("session_id", sa.String(length=36), nullable=False),
        sa.Column("agent_id", sa.String(length=64), nullable=False),
        sa.Column("role", sa.String(length=64), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["agent_id"], ["agents.id"]),
        sa.ForeignKeyConstraint(["session_id"], ["agent_sessions.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_agent_messages_agent_id"), "agent_messages", ["agent_id"])
    op.create_index(op.f("ix_agent_messages_session_id"), "agent_messages", ["session_id"])
    op.create_table(
        "agent_assignments",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("run_id", sa.String(length=36), nullable=False),
        sa.Column("agent_id", sa.String(length=64), nullable=False),
        sa.Column("parent_assignment_id", sa.String(length=36), nullable=True),
        sa.Column("step_key", sa.Text(), nullable=True),
        sa.Column("role", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=64), nullable=False),
        sa.Column("input_json", sa.JSON(), nullable=False),
        sa.Column("output_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["agent_id"], ["agents.id"]),
        sa.ForeignKeyConstraint(["parent_assignment_id"], ["agent_assignments.id"]),
        sa.ForeignKeyConstraint(["run_id"], ["tasks.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_agent_assignments_agent_id"), "agent_assignments", ["agent_id"])
    op.create_index(op.f("ix_agent_assignments_run_id"), "agent_assignments", ["run_id"])
    op.create_index(op.f("ix_agent_assignments_status"), "agent_assignments", ["status"])
    op.create_table(
        "agent_handoffs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("run_id", sa.String(length=36), nullable=False),
        sa.Column("from_assignment_id", sa.String(length=36), nullable=True),
        sa.Column("to_assignment_id", sa.String(length=36), nullable=False),
        sa.Column("handoff_type", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=64), nullable=False),
        sa.Column("payload_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["from_assignment_id"], ["agent_assignments.id"]),
        sa.ForeignKeyConstraint(["run_id"], ["tasks.id"]),
        sa.ForeignKeyConstraint(["to_assignment_id"], ["agent_assignments.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_agent_handoffs_run_id"), "agent_handoffs", ["run_id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_agent_handoffs_run_id"), table_name="agent_handoffs")
    op.drop_table("agent_handoffs")
    op.drop_index(op.f("ix_agent_assignments_status"), table_name="agent_assignments")
    op.drop_index(op.f("ix_agent_assignments_run_id"), table_name="agent_assignments")
    op.drop_index(op.f("ix_agent_assignments_agent_id"), table_name="agent_assignments")
    op.drop_table("agent_assignments")
    op.drop_index(op.f("ix_agent_messages_session_id"), table_name="agent_messages")
    op.drop_index(op.f("ix_agent_messages_agent_id"), table_name="agent_messages")
    op.drop_table("agent_messages")
    op.drop_index(op.f("ix_agent_sessions_status"), table_name="agent_sessions")
    op.drop_index(op.f("ix_agent_sessions_organization_id"), table_name="agent_sessions")
    op.drop_index(op.f("ix_agent_sessions_agent_id"), table_name="agent_sessions")
    op.drop_table("agent_sessions")
    op.drop_index(op.f("ix_agents_status"), table_name="agents")
    op.drop_index(op.f("ix_agents_organization_id"), table_name="agents")
    op.drop_table("agents")
