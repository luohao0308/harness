"""create local otel span storage and alert rules

Revision ID: 20260529_0024
Revises: 20260528_0023
Create Date: 2026-05-29 00:00:00.000000
"""

from __future__ import annotations

from datetime import UTC, datetime

import sqlalchemy as sa

from alembic import op

revision = "20260529_0024"
down_revision = "20260528_0023"
branch_labels = None
depends_on = None


_SEED_NOW = datetime(2026, 5, 29, tzinfo=UTC)

_DEFAULT_ALERT_RULES: list[dict[str, object]] = [
    {
        "id": "system-alert-eval-regression-triggered",
        "organization_id": None,
        "name": "eval_regression_triggered",
        "metric": "eval_regression_triggered",
        "comparator": ">",
        "threshold": 0.0,
        "window_seconds": 86_400,
        "enabled": True,
        "severity": "warning",
        "notification_channels_json": ["in_app"],
        "created_at": _SEED_NOW,
        "updated_at": _SEED_NOW,
    },
    {
        "id": "system-alert-subagent-budget-exceeded-high",
        "organization_id": None,
        "name": "subagent_budget_exceeded_high",
        "metric": "subagent_budget_exceeded_count",
        "comparator": ">",
        "threshold": 3.0,
        "window_seconds": 300,
        "enabled": True,
        "severity": "warning",
        "notification_channels_json": ["in_app"],
        "created_at": _SEED_NOW,
        "updated_at": _SEED_NOW,
    },
    {
        "id": "system-alert-tool-adapter-health-failing",
        "organization_id": None,
        "name": "tool_adapter_health_failing",
        "metric": "tool_adapter_failure_rate",
        "comparator": ">",
        "threshold": 0.3,
        "window_seconds": 300,
        "enabled": True,
        "severity": "warning",
        "notification_channels_json": ["in_app"],
        "created_at": _SEED_NOW,
        "updated_at": _SEED_NOW,
    },
    {
        "id": "system-alert-total-cost-spike",
        "organization_id": None,
        "name": "total_cost_spike",
        "metric": "total_cost_spike_ratio",
        "comparator": ">",
        "threshold": 3.0,
        "window_seconds": 3_600,
        "enabled": True,
        "severity": "critical",
        "notification_channels_json": ["in_app"],
        "created_at": _SEED_NOW,
        "updated_at": _SEED_NOW,
    },
]


def upgrade() -> None:
    op.create_table(
        "otel_spans",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=True),
        sa.Column("trace_id", sa.String(length=128), nullable=False),
        sa.Column("span_id", sa.String(length=32), nullable=False),
        sa.Column("parent_span_id", sa.String(length=32), nullable=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False, server_default="internal"),
        sa.Column("start_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("attributes_json", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="OK"),
        sa.Column("task_id", sa.String(length=36), nullable=True),
        sa.Column("agent_run_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["agent_run_id"], ["agent_runs.id"]),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("trace_id", "span_id", name="otel_spans_trace_span_uidx"),
    )
    op.create_index("ix_otel_spans_agent_run_id", "otel_spans", ["agent_run_id"])
    op.create_index("ix_otel_spans_org_start", "otel_spans", ["organization_id", "start_time"])
    op.create_index("ix_otel_spans_organization_id", "otel_spans", ["organization_id"])
    op.create_index("ix_otel_spans_parent_span_id", "otel_spans", ["parent_span_id"])
    op.create_index("ix_otel_spans_span_id", "otel_spans", ["span_id"])
    op.create_index("ix_otel_spans_status", "otel_spans", ["status"])
    op.create_index("ix_otel_spans_task_id", "otel_spans", ["task_id"])
    op.create_index("ix_otel_spans_task_start", "otel_spans", ["task_id", "start_time"])
    op.create_index("ix_otel_spans_trace_id", "otel_spans", ["trace_id"])
    op.create_index("ix_otel_spans_trace_start", "otel_spans", ["trace_id", "start_time"])

    op.create_table(
        "alert_rules",
        sa.Column("id", sa.String(length=128), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=True),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("metric", sa.String(length=128), nullable=False),
        sa.Column("comparator", sa.String(length=2), nullable=False),
        sa.Column("threshold", sa.Float(), nullable=False),
        sa.Column("window_seconds", sa.Integer(), nullable=False, server_default="300"),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("severity", sa.String(length=16), nullable=False, server_default="warning"),
        sa.Column("notification_channels_json", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "comparator IN ('>', '<', '>=', '<=', '==')",
            name="alert_rules_comparator_chk",
        ),
        sa.CheckConstraint(
            "severity IN ('info', 'warning', 'critical')",
            name="alert_rules_severity_chk",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "name", name="alert_rules_org_name_uidx"),
    )
    op.create_index("ix_alert_rules_enabled", "alert_rules", ["enabled"])
    op.create_index("ix_alert_rules_metric", "alert_rules", ["metric"])
    op.create_index("ix_alert_rules_org_enabled", "alert_rules", ["organization_id", "enabled"])
    op.create_index("ix_alert_rules_organization_id", "alert_rules", ["organization_id"])

    op.create_table(
        "alert_events",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=True),
        sa.Column("rule_id", sa.String(length=128), nullable=False),
        sa.Column("rule_name", sa.String(length=128), nullable=False),
        sa.Column("metric", sa.String(length=128), nullable=False),
        sa.Column("comparator", sa.String(length=2), nullable=False),
        sa.Column("threshold", sa.Float(), nullable=False),
        sa.Column("observed_value", sa.Float(), nullable=False),
        sa.Column("severity", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="active"),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("context_json", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("triggered_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["rule_id"], ["alert_rules.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_alert_events_metric", "alert_events", ["metric"])
    op.create_index(
        "ix_alert_events_org_triggered",
        "alert_events",
        ["organization_id", "triggered_at"],
    )
    op.create_index("ix_alert_events_organization_id", "alert_events", ["organization_id"])
    op.create_index("ix_alert_events_rule_id", "alert_events", ["rule_id"])
    op.create_index("ix_alert_events_rule_triggered", "alert_events", ["rule_id", "triggered_at"])
    op.create_index("ix_alert_events_severity", "alert_events", ["severity"])
    op.create_index("ix_alert_events_status", "alert_events", ["status"])

    op.bulk_insert(
        sa.table(
            "alert_rules",
            sa.column("id", sa.String(length=36)),
            sa.column("organization_id", sa.String(length=36)),
            sa.column("name", sa.String(length=128)),
            sa.column("metric", sa.String(length=128)),
            sa.column("comparator", sa.String(length=2)),
            sa.column("threshold", sa.Float()),
            sa.column("window_seconds", sa.Integer()),
            sa.column("enabled", sa.Boolean()),
            sa.column("severity", sa.String(length=16)),
            sa.column("notification_channels_json", sa.JSON()),
            sa.column("created_at", sa.DateTime(timezone=True)),
            sa.column("updated_at", sa.DateTime(timezone=True)),
        ),
        _DEFAULT_ALERT_RULES,
    )


def downgrade() -> None:
    op.drop_index("ix_alert_events_status", table_name="alert_events")
    op.drop_index("ix_alert_events_severity", table_name="alert_events")
    op.drop_index("ix_alert_events_rule_triggered", table_name="alert_events")
    op.drop_index("ix_alert_events_rule_id", table_name="alert_events")
    op.drop_index("ix_alert_events_organization_id", table_name="alert_events")
    op.drop_index("ix_alert_events_org_triggered", table_name="alert_events")
    op.drop_index("ix_alert_events_metric", table_name="alert_events")
    op.drop_table("alert_events")

    op.drop_index("ix_alert_rules_organization_id", table_name="alert_rules")
    op.drop_index("ix_alert_rules_org_enabled", table_name="alert_rules")
    op.drop_index("ix_alert_rules_metric", table_name="alert_rules")
    op.drop_index("ix_alert_rules_enabled", table_name="alert_rules")
    op.drop_table("alert_rules")

    op.drop_index("ix_otel_spans_trace_start", table_name="otel_spans")
    op.drop_index("ix_otel_spans_trace_id", table_name="otel_spans")
    op.drop_index("ix_otel_spans_task_start", table_name="otel_spans")
    op.drop_index("ix_otel_spans_task_id", table_name="otel_spans")
    op.drop_index("ix_otel_spans_status", table_name="otel_spans")
    op.drop_index("ix_otel_spans_span_id", table_name="otel_spans")
    op.drop_index("ix_otel_spans_parent_span_id", table_name="otel_spans")
    op.drop_index("ix_otel_spans_organization_id", table_name="otel_spans")
    op.drop_index("ix_otel_spans_org_start", table_name="otel_spans")
    op.drop_index("ix_otel_spans_agent_run_id", table_name="otel_spans")
    op.drop_table("otel_spans")
