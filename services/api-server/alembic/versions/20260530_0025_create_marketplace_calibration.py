"""create specialist marketplace and calibration tables

Revision ID: 20260530_0025
Revises: 20260529_0024
Create Date: 2026-05-30 00:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "20260530_0025"
down_revision = "20260529_0024"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "specialist_selection_decisions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=True),
        sa.Column("task_id", sa.String(length=36), nullable=False),
        sa.Column("plan_step_key", sa.Text(), nullable=False),
        sa.Column("selected_slug", sa.String(length=64), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="0"),
        sa.Column("reasoning", sa.Text(), nullable=False, server_default=""),
        sa.Column("selector", sa.String(length=32), nullable=False),
        sa.Column("alternative_slugs_json", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("candidate_slugs_json", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("trace_json", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_specialist_selection_decisions_org_created",
        "specialist_selection_decisions",
        ["organization_id", "created_at"],
    )
    op.create_index(
        "ix_specialist_selection_decisions_task_step",
        "specialist_selection_decisions",
        ["task_id", "plan_step_key"],
    )
    op.create_index(
        "ix_specialist_selection_decisions_selector",
        "specialist_selection_decisions",
        ["selector"],
    )

    op.create_table(
        "specialist_marketplace_listings",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("slug", sa.String(length=96), nullable=False),
        sa.Column("display_name", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("author_org_id", sa.String(length=36), nullable=True),
        sa.Column("author_name", sa.Text(), nullable=False),
        sa.Column("version", sa.String(length=32), nullable=False),
        sa.Column("manifest_json", sa.JSON(), nullable=False),
        sa.Column("signature", sa.String(length=128), nullable=False),
        sa.Column("verified", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("download_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug", name="specialist_marketplace_listings_slug_uidx"),
    )
    op.create_index(
        "ix_specialist_marketplace_listings_author_org",
        "specialist_marketplace_listings",
        ["author_org_id"],
    )
    op.create_index(
        "ix_specialist_marketplace_listings_verified",
        "specialist_marketplace_listings",
        ["verified"],
    )

    op.create_table(
        "specialist_installations",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("listing_id", sa.String(length=36), nullable=False),
        sa.Column("installed_org_id", sa.String(length=36), nullable=False),
        sa.Column("installed_specialist_id", sa.String(length=36), nullable=False),
        sa.Column("installed_version", sa.String(length=32), nullable=False),
        sa.Column("auto_update_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("installed_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["installed_specialist_id"], ["subagent_specialists.id"]),
        sa.ForeignKeyConstraint(["listing_id"], ["specialist_marketplace_listings.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "listing_id",
            "installed_org_id",
            name="specialist_installations_listing_org_uidx",
        ),
    )
    op.create_index(
        "ix_specialist_installations_installed_org",
        "specialist_installations",
        ["installed_org_id"],
    )
    op.create_index(
        "ix_specialist_installations_listing",
        "specialist_installations",
        ["listing_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_specialist_installations_listing", table_name="specialist_installations")
    op.drop_index(
        "ix_specialist_installations_installed_org",
        table_name="specialist_installations",
    )
    op.drop_table("specialist_installations")

    op.drop_index(
        "ix_specialist_marketplace_listings_verified",
        table_name="specialist_marketplace_listings",
    )
    op.drop_index(
        "ix_specialist_marketplace_listings_author_org",
        table_name="specialist_marketplace_listings",
    )
    op.drop_table("specialist_marketplace_listings")

    op.drop_index(
        "ix_specialist_selection_decisions_selector",
        table_name="specialist_selection_decisions",
    )
    op.drop_index(
        "ix_specialist_selection_decisions_task_step",
        table_name="specialist_selection_decisions",
    )
    op.drop_index(
        "ix_specialist_selection_decisions_org_created",
        table_name="specialist_selection_decisions",
    )
    op.drop_table("specialist_selection_decisions")
