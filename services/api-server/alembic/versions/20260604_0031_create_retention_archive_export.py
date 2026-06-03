"""create retention archive export

Revision ID: 20260604_0031
Revises: 20260604_0030
Create Date: 2026-06-04 00:10:00.000000
"""

from __future__ import annotations

from datetime import datetime, timezone

import sqlalchemy as sa

from alembic import op

revision = "20260604_0031"
down_revision = "20260604_0030"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "retention_policies",
        sa.Column("id", sa.String(length=128), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=True),
        sa.Column("entity_type", sa.String(length=128), nullable=False),
        sa.Column("action", sa.String(length=32), nullable=False, server_default="delete"),
        sa.Column("retention_days", sa.Integer(), nullable=True),
        sa.Column("delete_after_days", sa.Integer(), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organization_id",
            "entity_type",
            "action",
            name="retention_policies_scope_action_uidx",
        ),
    )
    op.create_index("ix_retention_policies_action", "retention_policies", ["action"])
    op.create_index("ix_retention_policies_enabled", "retention_policies", ["enabled"])
    op.create_index("ix_retention_policies_entity_type", "retention_policies", ["entity_type"])
    op.create_index("ix_retention_policies_organization_id", "retention_policies", ["organization_id"])
    op.create_index(
        "ix_retention_policies_org_enabled",
        "retention_policies",
        ["organization_id", "enabled"],
    )

    op.create_table(
        "retention_runs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("policy_id", sa.String(length=128), nullable=True),
        sa.Column("organization_id", sa.String(length=36), nullable=True),
        sa.Column("entity_type", sa.String(length=128), nullable=False),
        sa.Column("action", sa.String(length=32), nullable=False),
        sa.Column("deleted_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("archived_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_retention_runs_action", "retention_runs", ["action"])
    op.create_index("ix_retention_runs_entity_type", "retention_runs", ["entity_type"])
    op.create_index("ix_retention_runs_org_started", "retention_runs", ["organization_id", "started_at"])
    op.create_index("ix_retention_runs_organization_id", "retention_runs", ["organization_id"])
    op.create_index("ix_retention_runs_policy_id", "retention_runs", ["policy_id"])
    op.create_index("ix_retention_runs_policy_started", "retention_runs", ["policy_id", "started_at"])

    op.create_table(
        "archived_records",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=True),
        sa.Column("entity_type", sa.String(length=128), nullable=False),
        sa.Column("original_id", sa.String(length=128), nullable=False),
        sa.Column("payload_json", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organization_id",
            "entity_type",
            "original_id",
            name="archived_records_org_entity_original_uidx",
        ),
    )
    op.create_index("ix_archived_records_entity_type", "archived_records", ["entity_type"])
    op.create_index("ix_archived_records_org_entity_archived", "archived_records", ["organization_id", "entity_type", "archived_at"])
    op.create_index("ix_archived_records_organization_id", "archived_records", ["organization_id"])
    op.create_index("ix_archived_records_original_id", "archived_records", ["original_id"])

    op.create_table(
        "data_exports",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("requested_by", sa.String(length=36), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("file_path", sa.Text(), nullable=True),
        sa.Column("file_sha256", sa.String(length=64), nullable=True),
        sa.Column("size_bytes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_data_exports_org_requested", "data_exports", ["organization_id", "requested_at"])
    op.create_index("ix_data_exports_organization_id", "data_exports", ["organization_id"])
    op.create_index("ix_data_exports_requested_by", "data_exports", ["requested_by"])
    op.create_index("ix_data_exports_status", "data_exports", ["status"])

    op.create_table(
        "organization_deletion_logs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("deleted_by", sa.String(length=36), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_counts_json", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="completed"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_org_deletion_logs_org_deleted", "organization_deletion_logs", ["organization_id", "deleted_at"])
    op.create_index("ix_organization_deletion_logs_organization_id", "organization_deletion_logs", ["organization_id"])

    _seed_retention_defaults()


def downgrade() -> None:
    op.drop_index("ix_organization_deletion_logs_organization_id", table_name="organization_deletion_logs")
    op.drop_index("ix_org_deletion_logs_org_deleted", table_name="organization_deletion_logs")
    op.drop_table("organization_deletion_logs")
    op.drop_index("ix_data_exports_status", table_name="data_exports")
    op.drop_index("ix_data_exports_requested_by", table_name="data_exports")
    op.drop_index("ix_data_exports_organization_id", table_name="data_exports")
    op.drop_index("ix_data_exports_org_requested", table_name="data_exports")
    op.drop_table("data_exports")
    op.drop_index("ix_archived_records_original_id", table_name="archived_records")
    op.drop_index("ix_archived_records_organization_id", table_name="archived_records")
    op.drop_index("ix_archived_records_org_entity_archived", table_name="archived_records")
    op.drop_index("ix_archived_records_entity_type", table_name="archived_records")
    op.drop_table("archived_records")
    op.drop_index("ix_retention_runs_policy_started", table_name="retention_runs")
    op.drop_index("ix_retention_runs_policy_id", table_name="retention_runs")
    op.drop_index("ix_retention_runs_organization_id", table_name="retention_runs")
    op.drop_index("ix_retention_runs_org_started", table_name="retention_runs")
    op.drop_index("ix_retention_runs_entity_type", table_name="retention_runs")
    op.drop_index("ix_retention_runs_action", table_name="retention_runs")
    op.drop_table("retention_runs")
    op.drop_index("ix_retention_policies_org_enabled", table_name="retention_policies")
    op.drop_index("ix_retention_policies_organization_id", table_name="retention_policies")
    op.drop_index("ix_retention_policies_entity_type", table_name="retention_policies")
    op.drop_index("ix_retention_policies_enabled", table_name="retention_policies")
    op.drop_index("ix_retention_policies_action", table_name="retention_policies")
    op.drop_table("retention_policies")


def _seed_retention_defaults() -> None:
    now = datetime.now(timezone.utc)
    policies = sa.table(
        "retention_policies",
        sa.column("id", sa.String),
        sa.column("organization_id", sa.String),
        sa.column("entity_type", sa.String),
        sa.column("action", sa.String),
        sa.column("retention_days", sa.Integer),
        sa.column("delete_after_days", sa.Integer),
        sa.column("enabled", sa.Boolean),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("updated_at", sa.DateTime(timezone=True)),
    )
    op.bulk_insert(
        policies,
        [
            _policy("sys-retention-otel-spans", "otel_spans", "delete", 90, None, now),
            _policy("sys-retention-agent-events", "agent_events", "archive", 180, 365, now),
            _policy("sys-retention-frontend-errors", "frontend_errors", "delete", 60, None, now),
            _policy("sys-retention-model-calls", "model_calls", "archive", 90, 365, now),
            _policy("sys-retention-tool-calls", "tool_calls", "archive", 90, 365, now),
            _policy("sys-retention-eval-results", "eval_results", "keep", None, None, now),
            _policy("sys-retention-subagent-outputs", "subagent_outputs", "keep", None, None, now),
            _policy("sys-retention-admin-audit-events", "admin_audit_events", "keep", None, None, now),
            _policy("sys-retention-workspace-context-caches", "workspace_context_caches", "delete", 30, None, now),
        ],
    )


def _policy(
    policy_id: str,
    entity_type: str,
    action: str,
    retention_days: int | None,
    delete_after_days: int | None,
    now: datetime,
) -> dict:
    return {
        "id": policy_id,
        "organization_id": None,
        "entity_type": entity_type,
        "action": action,
        "retention_days": retention_days,
        "delete_after_days": delete_after_days,
        "enabled": True,
        "created_at": now,
        "updated_at": now,
    }
