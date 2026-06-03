"""create team mode tables

Revision ID: 20260523_0020
Revises: 20260518_0019
Create Date: 2026-05-23 00:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "20260523_0020"
down_revision = "20260518_0019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "teams",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("workspace", sa.Text(), nullable=False),
        sa.Column("workspace_mode", sa.String(length=32), nullable=False),
        sa.Column("leader_slot_id", sa.String(length=64), nullable=False),
        sa.Column("created_by", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "name", name="teams_org_name_uidx"),
    )
    op.create_index("ix_teams_organization_id", "teams", ["organization_id"])
    op.create_index("ix_teams_status", "teams", ["status"])
    op.create_index("ix_teams_org_updated", "teams", ["organization_id", "updated_at"])

    op.create_table(
        "team_agents",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("team_id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=True),
        sa.Column("slot_id", sa.String(length=64), nullable=False),
        sa.Column("agent_id", sa.String(length=64), nullable=False),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.Column("agent_name", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("model_provider", sa.Text(), nullable=False),
        sa.Column("model_name", sa.Text(), nullable=False),
        sa.Column("conversation_id", sa.String(length=36), nullable=True),
        sa.Column("session_id", sa.String(length=36), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["agent_id"], ["agents.id"]),
        sa.ForeignKeyConstraint(["session_id"], ["agent_sessions.id"]),
        sa.ForeignKeyConstraint(["team_id"], ["teams.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("team_id", "slot_id", name="team_agents_team_slot_uidx"),
    )
    op.create_index("ix_team_agents_agent_id", "team_agents", ["agent_id"])
    op.create_index("ix_team_agents_conversation_id", "team_agents", ["conversation_id"])
    op.create_index("ix_team_agents_organization_id", "team_agents", ["organization_id"])
    op.create_index("ix_team_agents_role", "team_agents", ["role"])
    op.create_index("ix_team_agents_session_id", "team_agents", ["session_id"])
    op.create_index("ix_team_agents_status", "team_agents", ["status"])
    op.create_index("ix_team_agents_team_id", "team_agents", ["team_id"])
    op.create_index("ix_team_agents_org_team", "team_agents", ["organization_id", "team_id"])

    op.create_table(
        "team_mailbox_messages",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("team_id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=True),
        sa.Column("to_agent_slot_id", sa.String(length=64), nullable=False),
        sa.Column("from_agent_slot_id", sa.String(length=64), nullable=False),
        sa.Column("type", sa.String(length=32), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("read", sa.Boolean(), nullable=False),
        sa.Column("files_json", sa.JSON(), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["team_id"], ["teams.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_team_mailbox_messages_from_agent_slot_id", "team_mailbox_messages", ["from_agent_slot_id"])
    op.create_index("ix_team_mailbox_messages_organization_id", "team_mailbox_messages", ["organization_id"])
    op.create_index("ix_team_mailbox_messages_read", "team_mailbox_messages", ["read"])
    op.create_index("ix_team_mailbox_messages_team_id", "team_mailbox_messages", ["team_id"])
    op.create_index("ix_team_mailbox_messages_to_agent_slot_id", "team_mailbox_messages", ["to_agent_slot_id"])
    op.create_index(
        "ix_team_mailbox_team_to_read",
        "team_mailbox_messages",
        ["team_id", "to_agent_slot_id", "read"],
    )
    op.create_index("ix_team_mailbox_team_created", "team_mailbox_messages", ["team_id", "created_at"])

    op.create_table(
        "team_tasks",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("team_id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=True),
        sa.Column("subject", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("owner_slot_id", sa.String(length=64), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("blocked_by_json", sa.JSON(), nullable=False),
        sa.Column("blocks_json", sa.JSON(), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["team_id"], ["teams.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_team_tasks_organization_id", "team_tasks", ["organization_id"])
    op.create_index("ix_team_tasks_owner_slot_id", "team_tasks", ["owner_slot_id"])
    op.create_index("ix_team_tasks_status", "team_tasks", ["status"])
    op.create_index("ix_team_tasks_team_id", "team_tasks", ["team_id"])
    op.create_index("ix_team_tasks_team_owner", "team_tasks", ["team_id", "owner_slot_id"])
    op.create_index("ix_team_tasks_team_status", "team_tasks", ["team_id", "status"])

    op.create_table(
        "team_events",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("team_id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=True),
        sa.Column("sequence", sa.BigInteger(), nullable=False),
        sa.Column("event_type", sa.String(length=128), nullable=False),
        sa.Column("payload_json", sa.JSON(), nullable=False),
        sa.Column("actor_type", sa.String(length=64), nullable=False),
        sa.Column("actor_id", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["team_id"], ["teams.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("team_id", "sequence", name="team_events_team_sequence_uidx"),
    )
    op.create_index("ix_team_events_event_type", "team_events", ["event_type"])
    op.create_index("ix_team_events_organization_id", "team_events", ["organization_id"])
    op.create_index("ix_team_events_team_id", "team_events", ["team_id"])
    op.create_index("ix_team_events_team_created", "team_events", ["team_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_team_events_team_created", table_name="team_events")
    op.drop_index("ix_team_events_team_id", table_name="team_events")
    op.drop_index("ix_team_events_organization_id", table_name="team_events")
    op.drop_index("ix_team_events_event_type", table_name="team_events")
    op.drop_table("team_events")

    op.drop_index("ix_team_tasks_team_status", table_name="team_tasks")
    op.drop_index("ix_team_tasks_team_owner", table_name="team_tasks")
    op.drop_index("ix_team_tasks_team_id", table_name="team_tasks")
    op.drop_index("ix_team_tasks_status", table_name="team_tasks")
    op.drop_index("ix_team_tasks_owner_slot_id", table_name="team_tasks")
    op.drop_index("ix_team_tasks_organization_id", table_name="team_tasks")
    op.drop_table("team_tasks")

    op.drop_index("ix_team_mailbox_team_created", table_name="team_mailbox_messages")
    op.drop_index("ix_team_mailbox_team_to_read", table_name="team_mailbox_messages")
    op.drop_index("ix_team_mailbox_messages_to_agent_slot_id", table_name="team_mailbox_messages")
    op.drop_index("ix_team_mailbox_messages_team_id", table_name="team_mailbox_messages")
    op.drop_index("ix_team_mailbox_messages_read", table_name="team_mailbox_messages")
    op.drop_index("ix_team_mailbox_messages_organization_id", table_name="team_mailbox_messages")
    op.drop_index("ix_team_mailbox_messages_from_agent_slot_id", table_name="team_mailbox_messages")
    op.drop_table("team_mailbox_messages")

    op.drop_index("ix_team_agents_org_team", table_name="team_agents")
    op.drop_index("ix_team_agents_team_id", table_name="team_agents")
    op.drop_index("ix_team_agents_status", table_name="team_agents")
    op.drop_index("ix_team_agents_session_id", table_name="team_agents")
    op.drop_index("ix_team_agents_role", table_name="team_agents")
    op.drop_index("ix_team_agents_organization_id", table_name="team_agents")
    op.drop_index("ix_team_agents_conversation_id", table_name="team_agents")
    op.drop_index("ix_team_agents_agent_id", table_name="team_agents")
    op.drop_table("team_agents")

    op.drop_index("ix_teams_org_updated", table_name="teams")
    op.drop_index("ix_teams_status", table_name="teams")
    op.drop_index("ix_teams_organization_id", table_name="teams")
    op.drop_table("teams")
