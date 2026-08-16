"""create api gateway routes

Revision ID: 20260621_0043
Revises: 9e0680b286a1
Create Date: 2026-06-21 00:43:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "20260621_0043"
down_revision = "9e0680b286a1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "api_gateway_routes",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("agent_id", sa.String(length=64), nullable=False),
        sa.Column("slug", sa.String(length=128), nullable=False),
        sa.Column("api_key_hash", sa.String(length=64), nullable=False),
        sa.Column("rate_limit", sa.Integer(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("created_by", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_invoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["agent_id"], ["agents.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug", name="api_gateway_routes_slug_uidx"),
    )
    op.create_index("ix_api_gateway_routes_agent_id", "api_gateway_routes", ["agent_id"])
    op.create_index(
        "ix_api_gateway_routes_org_agent_enabled",
        "api_gateway_routes",
        ["organization_id", "agent_id", "enabled"],
    )
    op.create_index(
        "ix_api_gateway_routes_org_created",
        "api_gateway_routes",
        ["organization_id", "created_at"],
    )
    op.create_index(
        "ix_api_gateway_routes_organization_id",
        "api_gateway_routes",
        ["organization_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_api_gateway_routes_organization_id", table_name="api_gateway_routes")
    op.drop_index("ix_api_gateway_routes_org_created", table_name="api_gateway_routes")
    op.drop_index("ix_api_gateway_routes_org_agent_enabled", table_name="api_gateway_routes")
    op.drop_index("ix_api_gateway_routes_agent_id", table_name="api_gateway_routes")
    op.drop_table("api_gateway_routes")
