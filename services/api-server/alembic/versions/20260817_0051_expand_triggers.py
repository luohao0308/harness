"""expand triggers with automation configuration and invocation receipts

Revision ID: 20260817_0051
Revises: 20260807_0050
Create Date: 2026-08-17 00:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "20260817_0051"
down_revision = "20260807_0050"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("triggers") as batch_op:
        batch_op.add_column(
            sa.Column("name", sa.String(length=128), nullable=False, server_default="")
        )
        batch_op.add_column(
            sa.Column("config_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'"))
        )
        batch_op.add_column(
            sa.Column(
                "runtime_state_json",
                sa.JSON(),
                nullable=False,
                server_default=sa.text("'{}'"),
            )
        )
        batch_op.add_column(sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.alter_column(
            "endpoint_path",
            existing_type=sa.String(length=128),
            nullable=True,
        )
        batch_op.alter_column(
            "secret_hash",
            existing_type=sa.String(length=64),
            nullable=True,
        )
    op.execute(sa.text("UPDATE triggers SET name = endpoint_path WHERE name = ''"))
    op.create_index("ix_triggers_deleted_at", "triggers", ["deleted_at"])

    op.create_table(
        "trigger_invocations",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("trigger_id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("idempotency_key", sa.String(length=255), nullable=True),
        sa.Column("config_summary_json", sa.JSON(), nullable=False),
        sa.Column("payload_summary_json", sa.JSON(), nullable=False),
        sa.Column("workspace_root", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("run_id", sa.String(length=36), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("lease_owner", sa.String(length=128), nullable=True),
        sa.Column("lease_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("lease_generation", sa.Integer(), nullable=False, server_default="0"),
        sa.CheckConstraint(
            "lease_generation >= 0",
            name="trigger_invocations_lease_generation_chk",
        ),
        sa.CheckConstraint(
            "status IN ('RECEIVED', 'PLANNED', 'RETRYING', 'RUNNING', 'WAITING_APPROVAL', "
            "'SUCCEEDED', 'FAILED', 'DISABLED')",
            name="trigger_invocations_status_chk",
        ),
        sa.ForeignKeyConstraint(["run_id"], ["tasks.id"]),
        sa.ForeignKeyConstraint(["trigger_id"], ["triggers.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "trigger_id",
            "idempotency_key",
            name="trigger_invocations_trigger_key_uidx",
        ),
    )
    op.create_index(
        "ix_trigger_invocations_trigger_created",
        "trigger_invocations",
        ["trigger_id", "created_at"],
    )
    op.create_index(
        "ix_trigger_invocations_org_created",
        "trigger_invocations",
        ["organization_id", "created_at"],
    )
    op.create_index("ix_trigger_invocations_trigger_id", "trigger_invocations", ["trigger_id"])
    op.create_index(
        "ix_trigger_invocations_organization_id",
        "trigger_invocations",
        ["organization_id"],
    )
    op.create_index("ix_trigger_invocations_status", "trigger_invocations", ["status"])
    op.create_index("ix_trigger_invocations_run_id", "trigger_invocations", ["run_id"])


def downgrade() -> None:
    bind = op.get_bind()
    _ensure_downgrade_safe(bind)
    op.drop_index("ix_trigger_invocations_run_id", table_name="trigger_invocations")
    op.drop_index("ix_trigger_invocations_status", table_name="trigger_invocations")
    op.drop_index("ix_trigger_invocations_organization_id", table_name="trigger_invocations")
    op.drop_index("ix_trigger_invocations_trigger_id", table_name="trigger_invocations")
    op.drop_index("ix_trigger_invocations_org_created", table_name="trigger_invocations")
    op.drop_index("ix_trigger_invocations_trigger_created", table_name="trigger_invocations")
    op.drop_table("trigger_invocations")
    op.drop_index("ix_triggers_deleted_at", table_name="triggers")
    with op.batch_alter_table("triggers") as batch_op:
        batch_op.alter_column(
            "secret_hash",
            existing_type=sa.String(length=64),
            nullable=False,
        )
        batch_op.alter_column(
            "endpoint_path",
            existing_type=sa.String(length=128),
            nullable=False,
        )
        batch_op.drop_column("deleted_at")
        batch_op.drop_column("runtime_state_json")
        batch_op.drop_column("config_json")
        batch_op.drop_column("name")


def _ensure_downgrade_safe(bind: sa.Connection) -> None:
    invocation_count = bind.execute(
        sa.text("SELECT COUNT(*) FROM trigger_invocations")
    ).scalar_one()
    incompatible_trigger_count = bind.execute(
        sa.text(
            "SELECT COUNT(*) FROM triggers "
            "WHERE type <> 'webhook' OR endpoint_path IS NULL OR secret_hash IS NULL "
            "OR deleted_at IS NOT NULL OR name <> endpoint_path "
            "OR (config_json IS NOT NULL AND CAST(config_json AS TEXT) NOT IN ('{}', 'null')) "
            "OR (runtime_state_json IS NOT NULL "
            "AND CAST(runtime_state_json AS TEXT) NOT IN ('{}', 'null'))"
        )
    ).scalar_one()
    if invocation_count or incompatible_trigger_count:
        raise RuntimeError(
            "Cannot downgrade trigger automation while invocation history or "
            "incompatible trigger data exists"
        )
