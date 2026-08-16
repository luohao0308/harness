"""create saml providers

Revision ID: 20260614_0038
Revises: 20260610_0037
Create Date: 2026-06-14 00:00:00.000000

Story 1.2 - IdP Configuration Management
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "20260614_0038"
down_revision = "20260610_0037"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "saml_providers",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("entity_id", sa.Text(), nullable=False),
        sa.Column("sso_url", sa.Text(), nullable=False),
        sa.Column("slo_url", sa.Text(), nullable=True),
        sa.Column("x509_cert", sa.Text(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_saml_providers_organization_id",
        "saml_providers",
        ["organization_id"],
    )
    op.create_index(
        "ix_saml_providers_org_active",
        "saml_providers",
        ["organization_id", "is_active"],
    )
    op.create_index(
        "ix_saml_providers_entity_id",
        "saml_providers",
        ["entity_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_saml_providers_entity_id", table_name="saml_providers")
    op.drop_index("ix_saml_providers_org_active", table_name="saml_providers")
    op.drop_index("ix_saml_providers_organization_id", table_name="saml_providers")
    op.drop_table("saml_providers")
