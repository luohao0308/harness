"""local agent tool safety v3

Revision ID: 20260612_0039
Revises: 20260611_0038
Create Date: 2026-06-12 00:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "20260612_0039"
down_revision = "20260611_0038"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "local_agent_tool_requests",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=True),
        sa.Column("connection_id", sa.String(length=36), nullable=False),
        sa.Column("binding_id", sa.String(length=36), nullable=False),
        sa.Column("bridge_task_id", sa.String(length=36), nullable=False),
        sa.Column("task_id", sa.String(length=36), nullable=False),
        sa.Column("tool_request_id", sa.Text(), nullable=False),
        sa.Column("tool_call_id", sa.String(length=36), nullable=False),
        sa.Column("approval_id", sa.String(length=36), nullable=True),
        sa.Column("tool_name", sa.String(length=160), nullable=False),
        sa.Column("execution_target", sa.String(length=32), nullable=False),
        sa.Column("risk_level", sa.String(length=64), nullable=False),
        sa.Column("permission_mode", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=64), nullable=False),
        sa.Column("input_json", sa.JSON(), nullable=False),
        sa.Column("policy_decision_json", sa.JSON(), nullable=False),
        sa.Column("decision_json", sa.JSON(), nullable=False),
        sa.Column("result_json", sa.JSON(), nullable=False),
        sa.Column("decision_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["approval_id"], ["tool_approvals.id"]),
        sa.ForeignKeyConstraint(["binding_id"], ["local_agent_conversation_bindings.id"]),
        sa.ForeignKeyConstraint(["bridge_task_id"], ["local_agent_bridge_tasks.id"]),
        sa.ForeignKeyConstraint(["connection_id"], ["local_agent_connections.id"]),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"]),
        sa.ForeignKeyConstraint(["tool_call_id"], ["tool_calls.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "connection_id",
            "tool_request_id",
            name="local_agent_tool_requests_connection_request_uidx",
        ),
        sa.UniqueConstraint("tool_call_id", name="local_agent_tool_requests_tool_call_uidx"),
    )
    op.create_index(
        "ix_local_agent_tool_requests_task",
        "local_agent_tool_requests",
        ["task_id"],
    )
    for column in (
        "approval_id",
        "binding_id",
        "bridge_task_id",
        "connection_id",
        "organization_id",
        "status",
        "tool_call_id",
        "tool_name",
    ):
        op.create_index(
            op.f(f"ix_local_agent_tool_requests_{column}"),
            "local_agent_tool_requests",
            [column],
        )

    op.create_table(
        "local_agent_commands",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=True),
        sa.Column("connection_id", sa.String(length=36), nullable=False),
        sa.Column("binding_id", sa.String(length=36), nullable=False),
        sa.Column("bridge_task_id", sa.String(length=36), nullable=False),
        sa.Column("task_id", sa.String(length=36), nullable=False),
        sa.Column("local_agent_tool_request_id", sa.String(length=36), nullable=False),
        sa.Column("tool_request_id", sa.Text(), nullable=False),
        sa.Column("command_id", sa.Text(), nullable=False),
        sa.Column("tool_name", sa.String(length=160), nullable=False),
        sa.Column("command", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=64), nullable=False),
        sa.Column("retry_of_command_id", sa.Text(), nullable=True),
        sa.Column("cancel_requested_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("exit_code", sa.Integer(), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=False),
        sa.Column("output_summary_json", sa.JSON(), nullable=False),
        sa.Column("event_receipts_json", sa.JSON(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["binding_id"], ["local_agent_conversation_bindings.id"]),
        sa.ForeignKeyConstraint(["bridge_task_id"], ["local_agent_bridge_tasks.id"]),
        sa.ForeignKeyConstraint(["connection_id"], ["local_agent_connections.id"]),
        sa.ForeignKeyConstraint(
            ["local_agent_tool_request_id"],
            ["local_agent_tool_requests.id"],
        ),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "connection_id",
            "command_id",
            name="local_agent_commands_connection_command_uidx",
        ),
    )
    op.create_index("ix_local_agent_commands_task", "local_agent_commands", ["task_id"])
    for column in (
        "binding_id",
        "bridge_task_id",
        "connection_id",
        "local_agent_tool_request_id",
        "organization_id",
        "status",
        "task_id",
        "tool_request_id",
    ):
        op.create_index(
            op.f(f"ix_local_agent_commands_{column}"),
            "local_agent_commands",
            [column],
        )

    op.create_table(
        "local_agent_pending_changes",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=True),
        sa.Column("connection_id", sa.String(length=36), nullable=False),
        sa.Column("binding_id", sa.String(length=36), nullable=False),
        sa.Column("bridge_task_id", sa.String(length=36), nullable=False),
        sa.Column("task_id", sa.String(length=36), nullable=False),
        sa.Column("local_agent_tool_request_id", sa.String(length=36), nullable=False),
        sa.Column("tool_request_id", sa.Text(), nullable=False),
        sa.Column("command_id", sa.Text(), nullable=True),
        sa.Column("approval_id", sa.String(length=36), nullable=True),
        sa.Column("change_id", sa.Text(), nullable=False),
        sa.Column("target_paths_json", sa.JSON(), nullable=False),
        sa.Column("diff_sha256", sa.String(length=64), nullable=False),
        sa.Column("preview_json", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=64), nullable=False),
        sa.Column("committed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("denied_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["approval_id"], ["tool_approvals.id"]),
        sa.ForeignKeyConstraint(["binding_id"], ["local_agent_conversation_bindings.id"]),
        sa.ForeignKeyConstraint(["bridge_task_id"], ["local_agent_bridge_tasks.id"]),
        sa.ForeignKeyConstraint(["connection_id"], ["local_agent_connections.id"]),
        sa.ForeignKeyConstraint(
            ["local_agent_tool_request_id"],
            ["local_agent_tool_requests.id"],
        ),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "connection_id",
            "change_id",
            name="local_agent_pending_changes_connection_change_uidx",
        ),
    )
    op.create_index(
        "ix_local_agent_pending_changes_task",
        "local_agent_pending_changes",
        ["task_id"],
    )
    for column in (
        "approval_id",
        "binding_id",
        "bridge_task_id",
        "connection_id",
        "local_agent_tool_request_id",
        "organization_id",
        "status",
        "task_id",
        "tool_request_id",
    ):
        op.create_index(
            op.f(f"ix_local_agent_pending_changes_{column}"),
            "local_agent_pending_changes",
            [column],
        )


def downgrade() -> None:
    op.drop_table("local_agent_pending_changes")
    op.drop_table("local_agent_commands")
    op.drop_table("local_agent_tool_requests")
