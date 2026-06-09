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
        now = datetime.now(UTC)
        conflict_reason = "Local Agent binding was marked conflict"
        local_terminal_decision = {
            "terminal_status": "cancelled",
            "terminal_reason": conflict_reason,
            "terminalized_at": now.isoformat(),
            "server_execution": False,
        }
        local_terminal_result = {
            "status": "CANCELLED",
            "reason": conflict_reason,
            "server_execution": False,
        }
        approval_decision = {
            "decision": "DENIED",
            "reason": conflict_reason,
            "server_execution": False,
        }
        tool_output = {
            "status": "CANCELLED",
            "reason": conflict_reason,
            "server_execution": False,
        }
        bind.execute(
            sa.text(
                """
                UPDATE tasks
                SET status = 'CANCELLED', completed_at = COALESCE(completed_at, :updated_at), updated_at = :updated_at
                WHERE id IN (
                    SELECT task_id
                    FROM local_agent_bridge_tasks
                    WHERE binding_id IN :binding_ids
                      AND status IN ('pending', 'leased', 'running')
                )
                """
            ).bindparams(sa.bindparam("binding_ids", expanding=True)),
            {"binding_ids": conflict_ids, "updated_at": now},
        )
        bind.execute(
            sa.text(
                """
                UPDATE local_agent_bridge_tasks
                SET status = 'cancelled', completed_at = COALESCE(completed_at, :updated_at), updated_at = :updated_at
                WHERE binding_id IN :binding_ids
                  AND status IN ('pending', 'leased', 'running')
                """
            ).bindparams(sa.bindparam("binding_ids", expanding=True)),
            {"binding_ids": conflict_ids, "updated_at": now},
        )
        bind.execute(
            sa.text(
                """
                UPDATE tool_approvals
                SET status = 'DENIED',
                    decided_by = 'system:migration',
                    decided_at = COALESCE(decided_at, :updated_at),
                    decision_json = :decision_json
                WHERE status = 'PENDING'
                  AND id IN (
                    SELECT approval_id
                    FROM local_agent_tool_requests
                    WHERE binding_id IN :binding_ids
                      AND approval_id IS NOT NULL
                      AND status NOT IN ('succeeded', 'failed', 'cancelled', 'denied', 'expired')
                  )
                """
            )
            .bindparams(sa.bindparam("binding_ids", expanding=True))
            .bindparams(sa.bindparam("decision_json", type_=sa.JSON())),
            {
                "binding_ids": conflict_ids,
                "updated_at": now,
                "decision_json": approval_decision,
            },
        )
        bind.execute(
            sa.text(
                """
                UPDATE tool_calls
                SET status = 'CANCELLED',
                    error_message = COALESCE(error_message, :reason),
                    output_json = :output_json
                WHERE status NOT IN ('SUCCESS', 'FAILED', 'TIMEOUT', 'DENIED', 'CANCELLED')
                  AND id IN (
                    SELECT tool_call_id
                    FROM local_agent_tool_requests
                    WHERE binding_id IN :binding_ids
                      AND tool_call_id IS NOT NULL
                      AND status NOT IN ('succeeded', 'failed', 'cancelled', 'denied', 'expired')
                  )
                """
            )
            .bindparams(sa.bindparam("binding_ids", expanding=True))
            .bindparams(sa.bindparam("output_json", type_=sa.JSON())),
            {
                "binding_ids": conflict_ids,
                "reason": conflict_reason,
                "output_json": tool_output,
            },
        )
        bind.execute(
            sa.text(
                """
                UPDATE local_agent_tool_requests
                SET status = 'cancelled',
                    completed_at = COALESCE(completed_at, :updated_at),
                    updated_at = :updated_at,
                    decision_json = :decision_json,
                    result_json = :result_json
                WHERE binding_id IN :binding_ids
                  AND status NOT IN ('succeeded', 'failed', 'cancelled', 'denied', 'expired')
                """
            )
            .bindparams(sa.bindparam("binding_ids", expanding=True))
            .bindparams(sa.bindparam("decision_json", type_=sa.JSON()))
            .bindparams(sa.bindparam("result_json", type_=sa.JSON())),
            {
                "binding_ids": conflict_ids,
                "updated_at": now,
                "decision_json": local_terminal_decision,
                "result_json": local_terminal_result,
            },
        )
        bind.execute(
            sa.text(
                """
                UPDATE local_agent_commands
                SET status = 'cancelled', finished_at = COALESCE(finished_at, :updated_at), updated_at = :updated_at
                WHERE binding_id IN :binding_ids
                  AND status NOT IN ('success', 'failed', 'timeout', 'cancelled')
                """
            ).bindparams(sa.bindparam("binding_ids", expanding=True)),
            {"binding_ids": conflict_ids, "updated_at": now},
        )
        bind.execute(
            sa.text(
                """
                UPDATE local_agent_pending_changes
                SET status = 'denied',
                    denied_at = COALESCE(denied_at, :updated_at),
                    error_message = COALESCE(error_message, 'Local Agent binding was marked conflict'),
                    updated_at = :updated_at
                WHERE binding_id IN :binding_ids
                  AND status NOT IN ('committed', 'denied', 'failed')
                """
            ).bindparams(sa.bindparam("binding_ids", expanding=True)),
            {"binding_ids": conflict_ids, "updated_at": now},
        )
        bind.execute(
            sa.text(
                """
                UPDATE local_agent_conversation_bindings
                SET status = 'conflict', updated_at = :updated_at
                WHERE id IN :binding_ids
                """
            ).bindparams(sa.bindparam("binding_ids", expanding=True)),
            {"binding_ids": conflict_ids, "updated_at": now},
        )

    dialect = bind.dialect.name
    active_where = sa.text("status = 'active'")
    active_global_where = sa.text("status = 'active' AND organization_id IS NULL")
    if dialect == "postgresql":
        op.create_index(
            "ix_local_agent_bindings_active_session_uidx",
            "local_agent_conversation_bindings",
            ["organization_id", "agent_session_id"],
            unique=True,
            postgresql_where=active_where,
        )
        op.create_index(
            "ix_local_agent_bindings_active_global_session_uidx",
            "local_agent_conversation_bindings",
            ["agent_session_id"],
            unique=True,
            postgresql_where=active_global_where,
        )
    elif dialect == "sqlite":
        op.create_index(
            "ix_local_agent_bindings_active_session_uidx",
            "local_agent_conversation_bindings",
            ["organization_id", "agent_session_id"],
            unique=True,
            sqlite_where=active_where,
        )
        op.create_index(
            "ix_local_agent_bindings_active_global_session_uidx",
            "local_agent_conversation_bindings",
            ["agent_session_id"],
            unique=True,
            sqlite_where=active_global_where,
        )
    else:
        op.create_index(
            "ix_local_agent_bindings_active_session_uidx",
            "local_agent_conversation_bindings",
            ["organization_id", "agent_session_id"],
            unique=True,
        )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name in {"postgresql", "sqlite"}:
        op.drop_index(
            "ix_local_agent_bindings_active_global_session_uidx",
            table_name="local_agent_conversation_bindings",
        )
    op.drop_index(
        "ix_local_agent_bindings_active_session_uidx",
        table_name="local_agent_conversation_bindings",
    )
