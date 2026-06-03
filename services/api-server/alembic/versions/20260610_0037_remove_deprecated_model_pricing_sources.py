"""remove deprecated builtin model pricing sources

Revision ID: 20260610_0037
Revises: 20260609_0036
Create Date: 2026-06-10 00:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "20260610_0037"
down_revision = "20260609_0036"
branch_labels = None
depends_on = None

_DEPRECATED_PRICING_SOURCE_IDS = [
    "price-official-moonshot-v1-8k",
    "price-official-zai-glm5-turbo",
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
        {"ids": _DEPRECATED_PRICING_SOURCE_IDS},
    )


def downgrade() -> None:
    # Deprecated source rows are intentionally not restored. Current source
    # authority is services/api-server/app/settings/model_pricing_sources.json.
    return None
