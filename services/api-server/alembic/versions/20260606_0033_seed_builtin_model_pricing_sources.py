"""seed builtin model pricing sources

Revision ID: 20260606_0033
Revises: 20260605_0032
Create Date: 2026-06-06 00:00:00.000000
"""

from __future__ import annotations

from datetime import UTC, datetime

import sqlalchemy as sa

from alembic import op

revision = "20260606_0033"
down_revision = "20260605_0032"
branch_labels = None
depends_on = None

_SEED_NOW = datetime(2026, 5, 30, tzinfo=UTC)

_BUILTIN_PRICING_ROWS: list[dict[str, object]] = [
    {
        "id": "price-official-deepseek-flash-v4",
        "organization_id": None,
        "provider": "deepseek-flash",
        "model": "deepseek-v4-flash",
        "prompt_per_1k_usd": "0.00014",
        "completion_per_1k_usd": "0.00028",
        "cache_prompt_per_1k_usd": "0.0000028",
        "currency": "USD",
        "active": True,
        "source": "official_source",
        "created_at": _SEED_NOW,
        "updated_at": _SEED_NOW,
    },
    {
        "id": "price-official-deepseek-pro-v4",
        "organization_id": None,
        "provider": "deepseek-pro",
        "model": "deepseek-v4-pro",
        "prompt_per_1k_usd": "0.000435",
        "completion_per_1k_usd": "0.00087",
        "cache_prompt_per_1k_usd": "0.000003625",
        "currency": "USD",
        "active": True,
        "source": "official_source",
        "created_at": _SEED_NOW,
        "updated_at": _SEED_NOW,
    },
    {
        "id": "price-official-openai-gpt55",
        "organization_id": None,
        "provider": "openai-compatible",
        "model": "gpt-5.5",
        "prompt_per_1k_usd": "0.005",
        "completion_per_1k_usd": "0.030",
        "cache_prompt_per_1k_usd": "0.0005",
        "currency": "USD",
        "active": True,
        "source": "official_source",
        "created_at": _SEED_NOW,
        "updated_at": _SEED_NOW,
    },
    {
        "id": "price-official-kimi-k26",
        "organization_id": None,
        "provider": "kimi",
        "model": "kimi-k2.6",
        "prompt_per_1k_usd": "0.00095",
        "completion_per_1k_usd": "0.00400",
        "cache_prompt_per_1k_usd": "0.00016",
        "currency": "USD",
        "active": True,
        "source": "official_source",
        "created_at": _SEED_NOW,
        "updated_at": _SEED_NOW,
    },
    {
        "id": "price-official-zai-glm51",
        "organization_id": None,
        "provider": "z-ai",
        "model": "glm-5.1",
        "prompt_per_1k_usd": "0.0014",
        "completion_per_1k_usd": "0.0044",
        "cache_prompt_per_1k_usd": "0.00026",
        "currency": "USD",
        "active": True,
        "source": "official_source",
        "created_at": _SEED_NOW,
        "updated_at": _SEED_NOW,
    },
]


def upgrade() -> None:
    connection = op.get_bind()
    connection.execute(
        sa.text(
            """
            DELETE FROM model_pricing
            WHERE organization_id IS NULL
              AND id IN :ids
              AND source = 'official_source'
            """
        ).bindparams(sa.bindparam("ids", expanding=True)),
        {
            "ids": [
                "price-official-openai-gpt41-mini",
                "price-official-openai-gpt55-pro",
                "price-official-openai-gpt54",
                "price-official-openai-gpt54-mini",
                "price-official-openai-gpt54-nano",
                "price-official-openai-gpt54-pro",
                "price-official-moonshot-v1-8k",
                "price-official-zai-glm5-turbo",
            ]
        },
    )
    table = sa.table(
        "model_pricing",
        sa.column("id", sa.String),
        sa.column("organization_id", sa.String),
        sa.column("provider", sa.String),
        sa.column("model", sa.String),
        sa.column("prompt_per_1k_usd", sa.String),
        sa.column("completion_per_1k_usd", sa.String),
        sa.column("cache_prompt_per_1k_usd", sa.String),
        sa.column("currency", sa.String),
        sa.column("active", sa.Boolean),
        sa.column("source", sa.String),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("updated_at", sa.DateTime(timezone=True)),
    )
    for row in _BUILTIN_PRICING_ROWS:
        exists = connection.execute(
            sa.text(
                """
                SELECT 1 FROM model_pricing
                WHERE organization_id IS NULL
                  AND provider = :provider
                  AND model = :model
                """
            ),
            {"provider": row["provider"], "model": row["model"]},
        ).scalar_one_or_none()
        if exists is None:
            op.bulk_insert(table, [row])
            continue
        connection.execute(
            sa.text(
                """
                UPDATE model_pricing
                SET prompt_per_1k_usd = :prompt_per_1k_usd,
                    completion_per_1k_usd = :completion_per_1k_usd,
                    cache_prompt_per_1k_usd = :cache_prompt_per_1k_usd,
                    currency = :currency,
                    active = true,
                    source = :source,
                    updated_at = :updated_at
                WHERE organization_id IS NULL
                  AND provider = :provider
                  AND model = :model
                """
            ),
            row,
        )


def downgrade() -> None:
    connection = op.get_bind()
    connection.execute(
        sa.text(
            """
            DELETE FROM model_pricing
            WHERE organization_id IS NULL
              AND id IN :ids
              AND source = 'official_source'
            """
        ).bindparams(sa.bindparam("ids", expanding=True)),
        {"ids": [row["id"] for row in _BUILTIN_PRICING_ROWS]},
    )
