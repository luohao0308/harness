"""create capability package lifecycle table

Revision ID: 20260518_0019
Revises: 20260517_0018
Create Date: 2026-05-18 15:42:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "20260518_0019"
down_revision = "20260517_0018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "capability_packages",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=True),
        sa.Column("package_key", sa.String(length=128), nullable=False),
        sa.Column("package_type", sa.String(length=64), nullable=False),
        sa.Column("source_kind", sa.String(length=32), nullable=False),
        sa.Column("source_uri", sa.Text(), nullable=True),
        sa.Column("source_sha256", sa.String(length=64), nullable=False),
        sa.Column("pinned_ref", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("risk_level", sa.String(length=32), nullable=False),
        sa.Column("manifest_json", sa.JSON(), nullable=False),
        sa.Column("validation_json", sa.JSON(), nullable=False),
        sa.Column("provenance_json", sa.JSON(), nullable=False),
        sa.Column("audit_json", sa.JSON(), nullable=False),
        sa.Column("capability_id", sa.String(length=36), nullable=True),
        sa.Column("capability_version_id", sa.String(length=64), nullable=True),
        sa.Column("created_by", sa.String(length=36), nullable=True),
        sa.Column("approved_by", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["capability_id"], ["capabilities.id"]),
        sa.ForeignKeyConstraint(["capability_version_id"], ["capability_versions.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organization_id",
            "package_key",
            "source_sha256",
            name="capability_packages_org_key_source_uidx",
        ),
    )
    op.create_index("ix_capability_packages_capability_id", "capability_packages", ["capability_id"])
    op.create_index(
        "ix_capability_packages_capability_version_id",
        "capability_packages",
        ["capability_version_id"],
    )
    op.create_index("ix_capability_packages_organization_id", "capability_packages", ["organization_id"])
    op.create_index("ix_capability_packages_package_key", "capability_packages", ["package_key"])
    op.create_index("ix_capability_packages_package_type", "capability_packages", ["package_type"])
    op.create_index("ix_capability_packages_source_kind", "capability_packages", ["source_kind"])
    op.create_index("ix_capability_packages_source_sha256", "capability_packages", ["source_sha256"])
    op.create_index("ix_capability_packages_status", "capability_packages", ["status"])


def downgrade() -> None:
    op.drop_index("ix_capability_packages_status", table_name="capability_packages")
    op.drop_index("ix_capability_packages_source_sha256", table_name="capability_packages")
    op.drop_index("ix_capability_packages_source_kind", table_name="capability_packages")
    op.drop_index("ix_capability_packages_package_type", table_name="capability_packages")
    op.drop_index("ix_capability_packages_package_key", table_name="capability_packages")
    op.drop_index("ix_capability_packages_organization_id", table_name="capability_packages")
    op.drop_index("ix_capability_packages_capability_version_id", table_name="capability_packages")
    op.drop_index("ix_capability_packages_capability_id", table_name="capability_packages")
    op.drop_table("capability_packages")
