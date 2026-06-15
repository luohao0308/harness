"""create local agent connection tables

Revision ID: 20260611_0038
Revises: 20260610_0037
Create Date: 2026-06-11 00:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "20260611_0038"
down_revision = "20260610_0037"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "local_agent_pairing_tokens",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=True),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("agent_id", sa.String(length=64), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("pair_code", sa.String(length=16), nullable=False),
        sa.Column("scope_json", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["agent_id"], ["agents.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash", name="local_agent_pairing_tokens_hash_uidx"),
    )
    op.create_index(
        "ix_local_agent_pairing_expires",
        "local_agent_pairing_tokens",
        ["expires_at"],
    )
    op.create_index(
        "ix_local_agent_pairing_org_user",
        "local_agent_pairing_tokens",
        ["organization_id", "user_id"],
    )
    op.create_index(
        op.f("ix_local_agent_pairing_tokens_agent_id"),
        "local_agent_pairing_tokens",
        ["agent_id"],
    )
    op.create_index(
        op.f("ix_local_agent_pairing_tokens_organization_id"),
        "local_agent_pairing_tokens",
        ["organization_id"],
    )
    op.create_index(
        op.f("ix_local_agent_pairing_tokens_pair_code"),
        "local_agent_pairing_tokens",
        ["pair_code"],
    )
    op.create_index(
        op.f("ix_local_agent_pairing_tokens_status"),
        "local_agent_pairing_tokens",
        ["status"],
    )
    op.create_index(
        op.f("ix_local_agent_pairing_tokens_user_id"),
        "local_agent_pairing_tokens",
        ["user_id"],
    )

    op.create_table(
        "local_agent_connections",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=True),
        sa.Column("owner_user_id", sa.String(length=36), nullable=False),
        sa.Column("agent_id", sa.String(length=64), nullable=False),
        sa.Column("pairing_token_id", sa.String(length=36), nullable=True),
        sa.Column("device_token_hash", sa.String(length=64), nullable=False),
        sa.Column("display_name", sa.Text(), nullable=False),
        sa.Column("adapter_kind", sa.String(length=64), nullable=False),
        sa.Column("protocol_version", sa.String(length=32), nullable=False),
        sa.Column("bridge_version", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("workspace_root", sa.Text(), nullable=True),
        sa.Column("capabilities_json", sa.JSON(), nullable=False),
        sa.Column("risk_capabilities_json", sa.JSON(), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["agent_id"], ["agents.id"]),
        sa.ForeignKeyConstraint(["pairing_token_id"], ["local_agent_pairing_tokens.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "device_token_hash",
            name="local_agent_connections_device_token_hash_uidx",
        ),
        sa.UniqueConstraint(
            "pairing_token_id",
            name="local_agent_connections_pairing_token_uidx",
        ),
    )
    op.create_index(
        "ix_local_agent_connections_org_user",
        "local_agent_connections",
        ["organization_id", "owner_user_id"],
    )
    op.create_index(
        "ix_local_agent_connections_status",
        "local_agent_connections",
        ["status"],
    )
    op.create_index(
        op.f("ix_local_agent_connections_adapter_kind"),
        "local_agent_connections",
        ["adapter_kind"],
    )
    op.create_index(
        op.f("ix_local_agent_connections_agent_id"),
        "local_agent_connections",
        ["agent_id"],
    )
    op.create_index(
        op.f("ix_local_agent_connections_organization_id"),
        "local_agent_connections",
        ["organization_id"],
    )
    op.create_index(
        op.f("ix_local_agent_connections_owner_user_id"),
        "local_agent_connections",
        ["owner_user_id"],
    )
    op.create_index(
        op.f("ix_local_agent_connections_pairing_token_id"),
        "local_agent_connections",
        ["pairing_token_id"],
    )

    op.create_table(
        "local_agent_conversation_bindings",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=True),
        sa.Column("owner_user_id", sa.String(length=36), nullable=False),
        sa.Column("connection_id", sa.String(length=36), nullable=False),
        sa.Column("agent_id", sa.String(length=64), nullable=False),
        sa.Column("agent_session_id", sa.String(length=36), nullable=False),
        sa.Column("adapter_session_id", sa.Text(), nullable=True),
        sa.Column("resume_mode", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["agent_id"], ["agents.id"]),
        sa.ForeignKeyConstraint(["agent_session_id"], ["agent_sessions.id"]),
        sa.ForeignKeyConstraint(["connection_id"], ["local_agent_connections.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "connection_id",
            "agent_session_id",
            name="local_agent_bindings_connection_session_uidx",
        ),
    )
    op.create_index(
        "ix_local_agent_bindings_org_user",
        "local_agent_conversation_bindings",
        ["organization_id", "owner_user_id"],
    )
    op.create_index(
        op.f("ix_local_agent_conversation_bindings_agent_id"),
        "local_agent_conversation_bindings",
        ["agent_id"],
    )
    op.create_index(
        op.f("ix_local_agent_conversation_bindings_agent_session_id"),
        "local_agent_conversation_bindings",
        ["agent_session_id"],
    )
    op.create_index(
        op.f("ix_local_agent_conversation_bindings_connection_id"),
        "local_agent_conversation_bindings",
        ["connection_id"],
    )
    op.create_index(
        op.f("ix_local_agent_conversation_bindings_organization_id"),
        "local_agent_conversation_bindings",
        ["organization_id"],
    )
    op.create_index(
        op.f("ix_local_agent_conversation_bindings_owner_user_id"),
        "local_agent_conversation_bindings",
        ["owner_user_id"],
    )
    op.create_index(
        op.f("ix_local_agent_conversation_bindings_status"),
        "local_agent_conversation_bindings",
        ["status"],
    )

    op.create_table(
        "local_agent_bridge_tasks",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=True),
        sa.Column("owner_user_id", sa.String(length=36), nullable=False),
        sa.Column("connection_id", sa.String(length=36), nullable=False),
        sa.Column("binding_id", sa.String(length=36), nullable=False),
        sa.Column("agent_session_id", sa.String(length=36), nullable=False),
        sa.Column("task_id", sa.String(length=36), nullable=False),
        sa.Column("user_message_id", sa.String(length=36), nullable=False),
        sa.Column("client_message_id", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("payload_json", sa.JSON(), nullable=False),
        sa.Column("leased_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("acked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["agent_session_id"], ["agent_sessions.id"]),
        sa.ForeignKeyConstraint(["binding_id"], ["local_agent_conversation_bindings.id"]),
        sa.ForeignKeyConstraint(["connection_id"], ["local_agent_connections.id"]),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"]),
        sa.ForeignKeyConstraint(["user_message_id"], ["agent_messages.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "binding_id",
            "client_message_id",
            name="local_agent_bridge_tasks_binding_message_uidx",
        ),
    )
    op.create_index(
        "ix_local_agent_bridge_tasks_connection_status",
        "local_agent_bridge_tasks",
        ["connection_id", "status"],
    )
    op.create_index("ix_local_agent_bridge_tasks_task", "local_agent_bridge_tasks", ["task_id"])
    op.create_index(
        op.f("ix_local_agent_bridge_tasks_agent_session_id"),
        "local_agent_bridge_tasks",
        ["agent_session_id"],
    )
    op.create_index(
        op.f("ix_local_agent_bridge_tasks_binding_id"),
        "local_agent_bridge_tasks",
        ["binding_id"],
    )
    op.create_index(
        op.f("ix_local_agent_bridge_tasks_connection_id"),
        "local_agent_bridge_tasks",
        ["connection_id"],
    )
    op.create_index(
        op.f("ix_local_agent_bridge_tasks_organization_id"),
        "local_agent_bridge_tasks",
        ["organization_id"],
    )
    op.create_index(
        op.f("ix_local_agent_bridge_tasks_owner_user_id"),
        "local_agent_bridge_tasks",
        ["owner_user_id"],
    )
    op.create_index(
        op.f("ix_local_agent_bridge_tasks_status"),
        "local_agent_bridge_tasks",
        ["status"],
    )
    op.create_index(
        op.f("ix_local_agent_bridge_tasks_user_message_id"),
        "local_agent_bridge_tasks",
        ["user_message_id"],
    )

    op.create_table(
        "local_agent_bridge_event_receipts",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=True),
        sa.Column("connection_id", sa.String(length=36), nullable=False),
        sa.Column("bridge_task_id", sa.String(length=36), nullable=True),
        sa.Column("task_id", sa.String(length=36), nullable=True),
        sa.Column("event_id", sa.Text(), nullable=False),
        sa.Column("sequence", sa.BigInteger(), nullable=True),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("payload_json", sa.JSON(), nullable=False),
        sa.Column("agent_event_id", sa.String(length=36), nullable=True),
        sa.Column("tool_call_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["agent_event_id"], ["agent_events.id"]),
        sa.ForeignKeyConstraint(["bridge_task_id"], ["local_agent_bridge_tasks.id"]),
        sa.ForeignKeyConstraint(["connection_id"], ["local_agent_connections.id"]),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"]),
        sa.ForeignKeyConstraint(["tool_call_id"], ["tool_calls.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "connection_id",
            "event_id",
            name="local_agent_bridge_receipts_connection_event_uidx",
        ),
    )
    op.create_index(
        "ix_local_agent_bridge_receipts_task",
        "local_agent_bridge_event_receipts",
        ["task_id"],
    )
    op.create_index(
        op.f("ix_local_agent_bridge_event_receipts_bridge_task_id"),
        "local_agent_bridge_event_receipts",
        ["bridge_task_id"],
    )
    op.create_index(
        op.f("ix_local_agent_bridge_event_receipts_connection_id"),
        "local_agent_bridge_event_receipts",
        ["connection_id"],
    )
    op.create_index(
        op.f("ix_local_agent_bridge_event_receipts_organization_id"),
        "local_agent_bridge_event_receipts",
        ["organization_id"],
    )
    op.create_index(
        op.f("ix_local_agent_bridge_event_receipts_task_id"),
        "local_agent_bridge_event_receipts",
        ["task_id"],
    )


def downgrade() -> None:
    op.drop_table("local_agent_bridge_event_receipts")
    op.drop_table("local_agent_bridge_tasks")
    op.drop_table("local_agent_conversation_bindings")
    op.drop_table("local_agent_connections")
    op.drop_table("local_agent_pairing_tokens")
