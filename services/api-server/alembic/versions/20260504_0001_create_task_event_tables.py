"""create_task_event_tables

Revision ID: 20260504_0001
Revises:
Create Date: 2026-05-04 12:30:00
"""

from alembic import op
import sqlalchemy as sa

revision = "20260504_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tasks",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("organization_id", sa.String(length=36), nullable=True),
        sa.Column("created_by", sa.String(length=36), nullable=True),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("goal", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=64), nullable=False),
        sa.Column("model_provider", sa.Text(), nullable=False),
        sa.Column("model_name", sa.Text(), nullable=False),
        sa.Column("max_runtime_seconds", sa.Integer(), nullable=False),
        sa.Column("max_subagents", sa.Integer(), nullable=False),
        sa.Column("enable_sandbox", sa.Boolean(), nullable=False),
        sa.Column("enable_network", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("tasks_status_created_at_idx", "tasks", ["status", "created_at"])
    op.create_index("tasks_created_by_created_at_idx", "tasks", ["created_by", "created_at"])

    op.create_table(
        "execution_plans",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("task_id", sa.String(length=36), sa.ForeignKey("tasks.id"), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=64), nullable=False),
        sa.Column("plan_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "task_steps",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("task_id", sa.String(length=36), sa.ForeignKey("tasks.id"), nullable=False),
        sa.Column(
            "plan_id",
            sa.String(length=36),
            sa.ForeignKey("execution_plans.id"),
            nullable=False,
        ),
        sa.Column("step_key", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=64), nullable=False),
        sa.Column("execution_mode", sa.String(length=64), nullable=False),
        sa.Column("assigned_agent_id", sa.String(length=36), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
    )

    op.create_table(
        "agent_runs",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("task_id", sa.String(length=36), sa.ForeignKey("tasks.id"), nullable=False),
        sa.Column("parent_agent_id", sa.String(length=36), sa.ForeignKey("agent_runs.id")),
        sa.Column("agent_type", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=64), nullable=False),
        sa.Column("context_json", sa.JSON(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("timeout_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        "agent_events",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("task_id", sa.String(length=36), sa.ForeignKey("tasks.id"), nullable=False),
        sa.Column("agent_run_id", sa.String(length=36), sa.ForeignKey("agent_runs.id")),
        sa.Column("sequence", sa.BigInteger(), nullable=False),
        sa.Column("event_type", sa.String(length=128), nullable=False),
        sa.Column("payload_json", sa.JSON(), nullable=False),
        sa.Column("actor_type", sa.String(length=64), nullable=False),
        sa.Column("actor_id", sa.Text(), nullable=True),
        sa.Column("trace_id", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("task_id", "sequence", name="agent_events_task_sequence_uidx"),
    )
    op.create_index("agent_events_task_created_at_idx", "agent_events", ["task_id", "created_at"])
    op.create_index(
        "agent_events_event_type_created_at_idx",
        "agent_events",
        ["event_type", "created_at"],
    )
    op.create_index(
        "agent_events_agent_run_sequence_idx",
        "agent_events",
        ["agent_run_id", "sequence"],
    )

    op.create_table(
        "sandbox_instances",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("task_id", sa.String(length=36), sa.ForeignKey("tasks.id"), nullable=False),
        sa.Column("agent_run_id", sa.String(length=36), sa.ForeignKey("agent_runs.id")),
        sa.Column("container_id", sa.Text(), nullable=False),
        sa.Column("image", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=64), nullable=False),
        sa.Column("cpu_limit", sa.Text(), nullable=False),
        sa.Column("memory_limit_mb", sa.Integer(), nullable=False),
        sa.Column("network_enabled", sa.Boolean(), nullable=False),
        sa.Column("warm_pool_reused", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("destroyed_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        "task_snapshots",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("task_id", sa.String(length=36), sa.ForeignKey("tasks.id"), nullable=False),
        sa.Column("sequence", sa.BigInteger(), nullable=False),
        sa.Column("state_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("task_snapshots")
    op.drop_table("sandbox_instances")
    op.drop_index("agent_events_agent_run_sequence_idx", table_name="agent_events")
    op.drop_index("agent_events_event_type_created_at_idx", table_name="agent_events")
    op.drop_index("agent_events_task_created_at_idx", table_name="agent_events")
    op.drop_table("agent_events")
    op.drop_table("agent_runs")
    op.drop_table("task_steps")
    op.drop_table("execution_plans")
    op.drop_index("tasks_created_by_created_at_idx", table_name="tasks")
    op.drop_index("tasks_status_created_at_idx", table_name="tasks")
    op.drop_table("tasks")
