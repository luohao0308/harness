"""create eval harness

Revision ID: 20260508_0008
Revises: 20260508_0007
Create Date: 2026-05-08 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260508_0008"
down_revision: str | None = "20260508_0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "tool_approvals",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("task_id", sa.String(length=36), nullable=False),
        sa.Column("tool_call_id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=True),
        sa.Column("requested_by", sa.Text(), nullable=True),
        sa.Column("decided_by", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=64), nullable=False),
        sa.Column("risk_level", sa.String(length=64), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("request_json", sa.JSON(), nullable=False),
        sa.Column("decision_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"]),
        sa.ForeignKeyConstraint(["tool_call_id"], ["tool_calls.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_tool_approvals_organization_id"), "tool_approvals", ["organization_id"])
    op.create_index(op.f("ix_tool_approvals_status"), "tool_approvals", ["status"])
    op.create_index(op.f("ix_tool_approvals_task_id"), "tool_approvals", ["task_id"])
    op.create_index(op.f("ix_tool_approvals_tool_call_id"), "tool_approvals", ["tool_call_id"])
    op.create_table(
        "eval_datasets",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=64), nullable=False),
        sa.Column("created_by", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_eval_datasets_organization_id"), "eval_datasets", ["organization_id"])
    op.create_index(op.f("ix_eval_datasets_status"), "eval_datasets", ["status"])
    op.create_table(
        "eval_cases",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("dataset_id", sa.String(length=36), nullable=False),
        sa.Column("source_task_id", sa.String(length=36), nullable=True),
        sa.Column("input_json", sa.JSON(), nullable=False),
        sa.Column("expected_json", sa.JSON(), nullable=False),
        sa.Column("tags_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["dataset_id"], ["eval_datasets.id"]),
        sa.ForeignKeyConstraint(["source_task_id"], ["tasks.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_eval_cases_dataset_id"), "eval_cases", ["dataset_id"])
    op.create_index(op.f("ix_eval_cases_source_task_id"), "eval_cases", ["source_task_id"])
    op.create_table(
        "eval_runs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("dataset_id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=True),
        sa.Column("agent_id", sa.String(length=64), nullable=True),
        sa.Column("status", sa.String(length=64), nullable=False),
        sa.Column("metrics_json", sa.JSON(), nullable=False),
        sa.Column("created_by", sa.String(length=36), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["agent_id"], ["agents.id"]),
        sa.ForeignKeyConstraint(["dataset_id"], ["eval_datasets.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_eval_runs_agent_id"), "eval_runs", ["agent_id"])
    op.create_index(op.f("ix_eval_runs_dataset_id"), "eval_runs", ["dataset_id"])
    op.create_index(op.f("ix_eval_runs_organization_id"), "eval_runs", ["organization_id"])
    op.create_index(op.f("ix_eval_runs_status"), "eval_runs", ["status"])
    op.create_table(
        "eval_results",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("eval_run_id", sa.String(length=36), nullable=False),
        sa.Column("eval_case_id", sa.String(length=36), nullable=False),
        sa.Column("task_id", sa.String(length=36), nullable=True),
        sa.Column("status", sa.String(length=64), nullable=False),
        sa.Column("scores_json", sa.JSON(), nullable=False),
        sa.Column("grader_trace_json", sa.JSON(), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=False),
        sa.Column("cost_usd", sa.String(length=32), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["eval_case_id"], ["eval_cases.id"]),
        sa.ForeignKeyConstraint(["eval_run_id"], ["eval_runs.id"]),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_eval_results_eval_case_id"), "eval_results", ["eval_case_id"])
    op.create_index(op.f("ix_eval_results_eval_run_id"), "eval_results", ["eval_run_id"])
    op.create_index(op.f("ix_eval_results_task_id"), "eval_results", ["task_id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_eval_results_task_id"), table_name="eval_results")
    op.drop_index(op.f("ix_eval_results_eval_run_id"), table_name="eval_results")
    op.drop_index(op.f("ix_eval_results_eval_case_id"), table_name="eval_results")
    op.drop_table("eval_results")
    op.drop_index(op.f("ix_eval_runs_status"), table_name="eval_runs")
    op.drop_index(op.f("ix_eval_runs_organization_id"), table_name="eval_runs")
    op.drop_index(op.f("ix_eval_runs_dataset_id"), table_name="eval_runs")
    op.drop_index(op.f("ix_eval_runs_agent_id"), table_name="eval_runs")
    op.drop_table("eval_runs")
    op.drop_index(op.f("ix_eval_cases_source_task_id"), table_name="eval_cases")
    op.drop_index(op.f("ix_eval_cases_dataset_id"), table_name="eval_cases")
    op.drop_table("eval_cases")
    op.drop_index(op.f("ix_eval_datasets_status"), table_name="eval_datasets")
    op.drop_index(op.f("ix_eval_datasets_organization_id"), table_name="eval_datasets")
    op.drop_table("eval_datasets")
    op.drop_index(op.f("ix_tool_approvals_tool_call_id"), table_name="tool_approvals")
    op.drop_index(op.f("ix_tool_approvals_task_id"), table_name="tool_approvals")
    op.drop_index(op.f("ix_tool_approvals_status"), table_name="tool_approvals")
    op.drop_index(op.f("ix_tool_approvals_organization_id"), table_name="tool_approvals")
    op.drop_table("tool_approvals")
