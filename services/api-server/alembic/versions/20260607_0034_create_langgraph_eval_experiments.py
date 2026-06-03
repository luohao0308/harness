"""create langgraph eval experiments

Revision ID: 20260607_0034
Revises: 20260606_0033
Create Date: 2026-06-07 00:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "20260607_0034"
down_revision = "20260606_0033"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "capability_packages",
        sa.Column("content_json", sa.JSON(), nullable=False, server_default="{}"),
    )
    if op.get_bind().dialect.name != "sqlite":
        op.alter_column("capability_packages", "content_json", server_default=None)

    op.create_table(
        "eval_experiments",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("dataset_id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=64), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("created_by", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["dataset_id"], ["eval_datasets.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_eval_experiments_dataset_id",
        "eval_experiments",
        ["dataset_id"],
        unique=False,
    )
    op.create_index(
        "ix_eval_experiments_organization_id",
        "eval_experiments",
        ["organization_id"],
        unique=False,
    )
    op.create_index(
        "ix_eval_experiments_org_created",
        "eval_experiments",
        ["organization_id", "created_at"],
        unique=False,
    )
    op.create_index("ix_eval_experiments_status", "eval_experiments", ["status"], unique=False)

    op.create_table(
        "eval_experiment_arms",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("experiment_id", sa.String(length=36), nullable=False),
        sa.Column("dataset_id", sa.String(length=36), nullable=False),
        sa.Column("eval_run_id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("arm_type", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=64), nullable=False),
        sa.Column("capability_hashes_json", sa.JSON(), nullable=False),
        sa.Column("metrics_json", sa.JSON(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["dataset_id"], ["eval_datasets.id"]),
        sa.ForeignKeyConstraint(["eval_run_id"], ["eval_runs.id"]),
        sa.ForeignKeyConstraint(["experiment_id"], ["eval_experiments.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "experiment_id",
            "name",
            name="eval_experiment_arms_experiment_name_uidx",
        ),
    )
    op.create_index(
        "ix_eval_experiment_arms_dataset_id",
        "eval_experiment_arms",
        ["dataset_id"],
        unique=False,
    )
    op.create_index(
        "ix_eval_experiment_arms_eval_run_id",
        "eval_experiment_arms",
        ["eval_run_id"],
        unique=False,
    )
    op.create_index(
        "ix_eval_experiment_arms_experiment_created",
        "eval_experiment_arms",
        ["experiment_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_eval_experiment_arms_experiment_id",
        "eval_experiment_arms",
        ["experiment_id"],
        unique=False,
    )
    op.create_index(
        "ix_eval_experiment_arms_organization_id",
        "eval_experiment_arms",
        ["organization_id"],
        unique=False,
    )
    op.create_index("ix_eval_experiment_arms_status", "eval_experiment_arms", ["status"])


def downgrade() -> None:
    op.drop_index("ix_eval_experiment_arms_status", table_name="eval_experiment_arms")
    op.drop_index("ix_eval_experiment_arms_organization_id", table_name="eval_experiment_arms")
    op.drop_index("ix_eval_experiment_arms_experiment_id", table_name="eval_experiment_arms")
    op.drop_index("ix_eval_experiment_arms_experiment_created", table_name="eval_experiment_arms")
    op.drop_index("ix_eval_experiment_arms_eval_run_id", table_name="eval_experiment_arms")
    op.drop_index("ix_eval_experiment_arms_dataset_id", table_name="eval_experiment_arms")
    op.drop_table("eval_experiment_arms")
    op.drop_index("ix_eval_experiments_status", table_name="eval_experiments")
    op.drop_index("ix_eval_experiments_org_created", table_name="eval_experiments")
    op.drop_index("ix_eval_experiments_organization_id", table_name="eval_experiments")
    op.drop_index("ix_eval_experiments_dataset_id", table_name="eval_experiments")
    op.drop_table("eval_experiments")
    op.drop_column("capability_packages", "content_json")
