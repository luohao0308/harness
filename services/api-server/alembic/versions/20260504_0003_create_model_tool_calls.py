"""create_model_tool_calls

Revision ID: 20260504_0003
Revises: 20260504_0002
Create Date: 2026-05-04 19:40:00
"""

from alembic import op
import sqlalchemy as sa

revision = "20260504_0003"
down_revision = "20260504_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "model_calls",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("task_id", sa.String(length=36), sa.ForeignKey("tasks.id"), nullable=False),
        sa.Column(
            "agent_run_id",
            sa.String(length=36),
            sa.ForeignKey("agent_runs.id"),
            nullable=True,
        ),
        sa.Column("model_provider", sa.Text(), nullable=False),
        sa.Column("model_name", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=64), nullable=False),
        sa.Column("prompt_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("completion_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("duration_ms", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("request_json", sa.JSON(), nullable=False),
        sa.Column("response_json", sa.JSON(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("model_calls_task_id_idx", "model_calls", ["task_id"])

    op.create_table(
        "tool_calls",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("task_id", sa.String(length=36), sa.ForeignKey("tasks.id"), nullable=False),
        sa.Column(
            "agent_run_id",
            sa.String(length=36),
            sa.ForeignKey("agent_runs.id"),
            nullable=True,
        ),
        sa.Column("tool_name", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=64), nullable=False),
        sa.Column("risk_level", sa.String(length=64), nullable=False),
        sa.Column("requires_sandbox", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "sandbox_id",
            sa.String(length=36),
            sa.ForeignKey("sandbox_instances.id"),
            nullable=True,
        ),
        sa.Column("duration_ms", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("input_json", sa.JSON(), nullable=False),
        sa.Column("output_json", sa.JSON(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("tool_calls_task_id_idx", "tool_calls", ["task_id"])

    op.create_table(
        "admin_audit_events",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("organization_id", sa.String(length=36), nullable=True),
        sa.Column("actor_id", sa.Text(), nullable=True),
        sa.Column("event_type", sa.String(length=128), nullable=False),
        sa.Column("resource_type", sa.String(length=128), nullable=False),
        sa.Column("resource_id", sa.Text(), nullable=False),
        sa.Column("action", sa.String(length=128), nullable=False),
        sa.Column("payload_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("admin_audit_events_org_idx", "admin_audit_events", ["organization_id"])
    op.create_index("admin_audit_events_event_type_idx", "admin_audit_events", ["event_type"])


def downgrade() -> None:
    op.drop_index("admin_audit_events_event_type_idx", table_name="admin_audit_events")
    op.drop_index("admin_audit_events_org_idx", table_name="admin_audit_events")
    op.drop_table("admin_audit_events")
    op.drop_index("tool_calls_task_id_idx", table_name="tool_calls")
    op.drop_table("tool_calls")
    op.drop_index("model_calls_task_id_idx", table_name="model_calls")
    op.drop_table("model_calls")
