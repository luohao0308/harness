"""guard active local agent sessions

Revision ID: 20260614_0041
Revises: 20260613_0040
Create Date: 2026-06-14 00:00:00.000000
"""

from __future__ import annotations

from datetime import UTC, datetime

import sqlalchemy as sa

from alembic import op

revision = "20260614_0041"
down_revision = "20260613_0040"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    rows = list(
        bind.execute(
            sa.text(
                """
                SELECT id, organization_id, agent_session_id
                FROM local_agent_conversation_bindings
                WHERE status = 'active'
                ORDER BY
                    organization_id,
                    agent_session_id,
                    updated_at DESC,
                    created_at DESC,
                    id DESC
                """
            )
        ).mappings()
    )
    seen: set[tuple[str | None, str]] = set()
    conflict_ids: list[str] = []
    for row in rows:
        key = (row["organization_id"], row["agent_session_id"])
        if key in seen:
            conflict_ids.append(row["id"])
            continue
        seen.add(key)
    if conflict_ids:
        bind.execute(
            sa.text(
                """
                UPDATE local_agent_conversation_bindings
                SET status = 'conflict', updated_at = :updated_at
                WHERE id IN :binding_ids
                """
            ).bindparams(sa.bindparam("binding_ids", expanding=True)),
            {"binding_ids": conflict_ids, "updated_at": datetime.now(UTC)},
        )

    dialect = bind.dialect.name
    active_where = sa.text("status = 'active'")
    if dialect == "postgresql":
        op.create_index(
            "ix_local_agent_bindings_active_session_uidx",
            "local_agent_conversation_bindings",
            ["organization_id", "agent_session_id"],
            unique=True,
            postgresql_where=active_where,
        )
    elif dialect == "sqlite":
        op.create_index(
            "ix_local_agent_bindings_active_session_uidx",
            "local_agent_conversation_bindings",
            ["organization_id", "agent_session_id"],
            unique=True,
            sqlite_where=active_where,
        )
    else:
        op.create_index(
            "ix_local_agent_bindings_active_session_uidx",
            "local_agent_conversation_bindings",
            ["organization_id", "agent_session_id"],
            unique=True,
        )


def downgrade() -> None:
    op.drop_index(
        "ix_local_agent_bindings_active_session_uidx",
        table_name="local_agent_conversation_bindings",
    )
