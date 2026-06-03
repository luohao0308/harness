"""create model pricing table

Revision ID: 20260527_0022
Revises: 20260525_0021
Create Date: 2026-05-27 00:00:00.000000
"""

from __future__ import annotations

from datetime import datetime, timezone

import sqlalchemy as sa

from alembic import op

revision = "20260527_0022"
down_revision = "20260525_0021"
branch_labels = None
depends_on = None


_SEED_NOW = datetime(2026, 5, 27, tzinfo=timezone.utc)


_DEFAULT_PRICING_ROWS: list[dict[str, object]] = [
    {
        "id": "pricing-default-deepseek-chat",
        "organization_id": None,
        "provider": "deepseek",
        "model": "deepseek-chat",
        "prompt_per_1k_usd": "0.00027",
        "completion_per_1k_usd": "0.00110",
        "cache_prompt_per_1k_usd": "0.00007",
        "currency": "USD",
        "active": True,
        "source": "default_seed",
        "created_at": _SEED_NOW,
        "updated_at": _SEED_NOW,
    },
    {
        "id": "pricing-default-deepseek-reasoner",
        "organization_id": None,
        "provider": "deepseek",
        "model": "deepseek-reasoner",
        "prompt_per_1k_usd": "0.00055",
        "completion_per_1k_usd": "0.00219",
        "cache_prompt_per_1k_usd": "0.00014",
        "currency": "USD",
        "active": True,
        "source": "default_seed",
        "created_at": _SEED_NOW,
        "updated_at": _SEED_NOW,
    },
    {
        "id": "pricing-default-openai-compatible",
        "organization_id": None,
        "provider": "openai-compatible",
        "model": "default",
        "prompt_per_1k_usd": "0.00015",
        "completion_per_1k_usd": "0.00060",
        "cache_prompt_per_1k_usd": "0.00000",
        "currency": "USD",
        "active": True,
        "source": "default_seed",
        "created_at": _SEED_NOW,
        "updated_at": _SEED_NOW,
    },
    {
        "id": "pricing-default-default",
        "organization_id": None,
        "provider": "default",
        "model": "default",
        "prompt_per_1k_usd": "0.00000",
        "completion_per_1k_usd": "0.00000",
        "cache_prompt_per_1k_usd": "0.00000",
        "currency": "USD",
        "active": True,
        "source": "default_seed",
        "created_at": _SEED_NOW,
        "updated_at": _SEED_NOW,
    },
]


def upgrade() -> None:
    table = op.create_table(
        "model_pricing",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=True),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("model", sa.String(length=128), nullable=False),
        sa.Column("prompt_per_1k_usd", sa.String(length=32), nullable=False),
        sa.Column("completion_per_1k_usd", sa.String(length=32), nullable=False),
        sa.Column("cache_prompt_per_1k_usd", sa.String(length=32), nullable=False, server_default="0"),
        sa.Column("currency", sa.String(length=8), nullable=False, server_default="USD"),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("source", sa.String(length=32), nullable=False, server_default="manual"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organization_id",
            "provider",
            "model",
            name="model_pricing_org_provider_model_uidx",
        ),
    )
    op.create_index(
        "ix_model_pricing_organization_id",
        "model_pricing",
        ["organization_id"],
    )
    op.create_index(
        "ix_model_pricing_provider_model",
        "model_pricing",
        ["provider", "model"],
    )
    op.create_index(
        "ix_model_pricing_active",
        "model_pricing",
        ["active"],
    )
    op.bulk_insert(table, _DEFAULT_PRICING_ROWS)


def downgrade() -> None:
    op.drop_index("ix_model_pricing_active", table_name="model_pricing")
    op.drop_index("ix_model_pricing_provider_model", table_name="model_pricing")
    op.drop_index("ix_model_pricing_organization_id", table_name="model_pricing")
    op.drop_table("model_pricing")
