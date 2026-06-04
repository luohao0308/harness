from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
    event,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def new_uuid() -> str:
    return str(uuid4())


def utc_now() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint("email", name="users_email_uidx"),
        Index("ix_users_status", "status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    email: Mapped[str] = mapped_column(String(320), nullable=False, index=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    email_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    avatar_mime_type: Mapped[str | None] = mapped_column(String(128), nullable=True)
    avatar_content: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    avatar_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    avatar_updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class Organization(Base):
    __tablename__ = "organizations"
    __table_args__ = (
        UniqueConstraint("slug", name="organizations_slug_uidx"),
        Index("ix_organizations_owner_user_id", "owner_user_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    slug: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    owner_user_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    plan: Mapped[str] = mapped_column(String(32), nullable=False, default="free")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class OrganizationMember(Base):
    __tablename__ = "organization_members"
    __table_args__ = (
        UniqueConstraint("organization_id", "user_id", name="organization_members_org_user_uidx"),
        Index("ix_organization_members_user_org", "user_id", "organization_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    organization_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(32), nullable=False, default="member", index=True)
    invited_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class OAuthAccount(Base):
    __tablename__ = "oauth_accounts"
    __table_args__ = (
        UniqueConstraint(
            "provider",
            "provider_user_id",
            name="oauth_accounts_provider_user_uidx",
        ),
        Index("ix_oauth_accounts_user_provider", "user_id", "provider"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    user_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    provider: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    provider_user_id: Mapped[str] = mapped_column(Text, nullable=False)
    email: Mapped[str] = mapped_column(Text, nullable=False, default="")
    raw_profile_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)


class ApiKey(Base):
    __tablename__ = "api_keys"
    __table_args__ = (
        Index("ix_api_keys_org_prefix", "organization_id", "key_prefix"),
        Index("ix_api_keys_user_created", "user_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    organization_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    key_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    key_prefix: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    scope_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class RetentionPolicy(Base):
    __tablename__ = "retention_policies"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "entity_type",
            "action",
            name="retention_policies_scope_action_uidx",
        ),
        Index("ix_retention_policies_org_enabled", "organization_id", "enabled"),
    )

    id: Mapped[str] = mapped_column(String(128), primary_key=True, default=new_uuid)
    organization_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    entity_type: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    action: Mapped[str] = mapped_column(String(32), nullable=False, default="delete", index=True)
    retention_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    delete_after_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class RetentionRun(Base):
    __tablename__ = "retention_runs"
    __table_args__ = (
        Index("ix_retention_runs_policy_started", "policy_id", "started_at"),
        Index("ix_retention_runs_org_started", "organization_id", "started_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    policy_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    organization_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    entity_type: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    action: Mapped[str] = mapped_column(String(32), nullable=False)
    deleted_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    archived_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)


class ArchivedRecord(Base):
    __tablename__ = "archived_records"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "entity_type",
            "original_id",
            name="archived_records_org_entity_original_uidx",
        ),
        Index(
            "ix_archived_records_org_entity_archived",
            "organization_id",
            "entity_type",
            "archived_at",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    organization_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    entity_type: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    original_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    payload_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    archived_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class DataExport(Base):
    __tablename__ = "data_exports"
    __table_args__ = (Index("ix_data_exports_org_requested", "organization_id", "requested_at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    organization_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    requested_by: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending", index=True)
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    file_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    file_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)


class OrganizationDeletionLog(Base):
    __tablename__ = "organization_deletion_logs"
    __table_args__ = (Index("ix_org_deletion_logs_org_deleted", "organization_id", "deleted_at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    organization_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    deleted_by: Mapped[str] = mapped_column(String(36), nullable=False)
    deleted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    deleted_counts_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="completed")


class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    organization_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    agent_id: Mapped[str | None] = mapped_column(ForeignKey("agents.id"), nullable=True, index=True)
    created_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    goal: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(64), nullable=False, default="CREATED", index=True)
    model_provider: Mapped[str] = mapped_column(Text, nullable=False)
    model_name: Mapped[str] = mapped_column(Text, nullable=False)
    max_runtime_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=1800)
    max_subagents: Mapped[int] = mapped_column(Integer, nullable=False, default=5)
    enable_sandbox: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    enable_network: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    capability_snapshot_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    events: Mapped[list[AgentEvent]] = relationship(back_populates="task")


class Agent(Base):
    __tablename__ = "agents"
    __table_args__ = (UniqueConstraint("organization_id", "id", name="agents_org_id_uidx"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    organization_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    role: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(64), nullable=False, default="ACTIVE", index=True)
    model_provider: Mapped[str] = mapped_column(Text, nullable=False, default="default")
    model_name: Mapped[str] = mapped_column(Text, nullable=False, default="default")
    system_prompt: Mapped[str] = mapped_column(Text, nullable=False)
    tools_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    routing_tags: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    max_parallel_assignments: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class Team(Base):
    __tablename__ = "teams"
    __table_args__ = (
        UniqueConstraint("organization_id", "name", name="teams_org_name_uidx"),
        Index("ix_teams_org_updated", "organization_id", "updated_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    organization_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="ACTIVE", index=True)
    workspace: Mapped[str] = mapped_column(Text, nullable=False, default="")
    workspace_mode: Mapped[str] = mapped_column(String(32), nullable=False, default="shared")
    leader_slot_id: Mapped[str] = mapped_column(String(64), nullable=False, default="leader")
    created_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    agents: Mapped[list[TeamAgent]] = relationship(
        back_populates="team",
        cascade="all, delete-orphan",
    )
    messages: Mapped[list[TeamMailboxMessage]] = relationship(
        back_populates="team",
        cascade="all, delete-orphan",
    )
    tasks: Mapped[list[TeamTask]] = relationship(
        back_populates="team",
        cascade="all, delete-orphan",
    )
    events: Mapped[list[TeamEvent]] = relationship(
        back_populates="team",
        cascade="all, delete-orphan",
    )


class TeamAgent(Base):
    __tablename__ = "team_agents"
    __table_args__ = (
        UniqueConstraint("team_id", "slot_id", name="team_agents_team_slot_uidx"),
        Index("ix_team_agents_org_team", "organization_id", "team_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    team_id: Mapped[str] = mapped_column(ForeignKey("teams.id"), nullable=False, index=True)
    organization_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    slot_id: Mapped[str] = mapped_column(String(64), nullable=False)
    agent_id: Mapped[str] = mapped_column(ForeignKey("agents.id"), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(32), nullable=False, default="teammate", index=True)
    agent_name: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="idle", index=True)
    model_provider: Mapped[str] = mapped_column(Text, nullable=False, default="default")
    model_name: Mapped[str] = mapped_column(Text, nullable=False, default="default")
    conversation_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    session_id: Mapped[str | None] = mapped_column(
        ForeignKey("agent_sessions.id"),
        nullable=True,
        index=True,
    )
    metadata_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    team: Mapped[Team] = relationship(back_populates="agents")


class TeamMailboxMessage(Base):
    __tablename__ = "team_mailbox_messages"
    __table_args__ = (
        Index("ix_team_mailbox_team_to_read", "team_id", "to_agent_slot_id", "read"),
        Index("ix_team_mailbox_team_created", "team_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    team_id: Mapped[str] = mapped_column(ForeignKey("teams.id"), nullable=False, index=True)
    organization_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    to_agent_slot_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    from_agent_slot_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    type: Mapped[str] = mapped_column(String(32), nullable=False, default="message", index=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    read: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    files_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    metadata_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    team: Mapped[Team] = relationship(back_populates="messages")


class TeamTask(Base):
    __tablename__ = "team_tasks"
    __table_args__ = (
        Index("ix_team_tasks_team_status", "team_id", "status"),
        Index("ix_team_tasks_team_owner", "team_id", "owner_slot_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    team_id: Mapped[str] = mapped_column(ForeignKey("teams.id"), nullable=False, index=True)
    organization_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    subject: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    owner_slot_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending", index=True)
    blocked_by_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    blocks_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    metadata_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    team: Mapped[Team] = relationship(back_populates="tasks")


class TeamEvent(Base):
    __tablename__ = "team_events"
    __table_args__ = (
        UniqueConstraint("team_id", "sequence", name="team_events_team_sequence_uidx"),
        Index("ix_team_events_team_created", "team_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    team_id: Mapped[str] = mapped_column(ForeignKey("teams.id"), nullable=False, index=True)
    organization_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    sequence: Mapped[int] = mapped_column(BigInteger, nullable=False)
    event_type: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    payload_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    actor_type: Mapped[str] = mapped_column(String(64), nullable=False, default="system")
    actor_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    team: Mapped[Team] = relationship(back_populates="events")


class Capability(Base):
    __tablename__ = "capabilities"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "capability_key",
            name="capabilities_org_key_uidx",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    organization_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    capability_key: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active", index=True)
    current_version_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    schema_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class CapabilityVersion(Base):
    __tablename__ = "capability_versions"
    __table_args__ = (
        UniqueConstraint("capability_id", "version", name="capability_versions_version_uidx"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    capability_id: Mapped[str] = mapped_column(
        ForeignKey("capabilities.id"), nullable=False, index=True
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active", index=True)
    content_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    config_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    content_sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    config_sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    schema_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class AgentCapabilityAttachment(Base):
    __tablename__ = "agent_capability_attachments"
    __table_args__ = (
        UniqueConstraint(
            "agent_id",
            "capability_version_id",
            name="agent_capability_attachments_agent_version_uidx",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    organization_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    agent_id: Mapped[str] = mapped_column(ForeignKey("agents.id"), nullable=False, index=True)
    capability_id: Mapped[str] = mapped_column(
        ForeignKey("capabilities.id"), nullable=False, index=True
    )
    capability_version_id: Mapped[str] = mapped_column(
        ForeignKey("capability_versions.id"),
        nullable=False,
        index=True,
    )
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    attached_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    attached_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class CapabilitySnapshot(Base):
    __tablename__ = "capability_snapshots"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    organization_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    agent_id: Mapped[str | None] = mapped_column(ForeignKey("agents.id"), nullable=True, index=True)
    task_id: Mapped[str | None] = mapped_column(ForeignKey("tasks.id"), nullable=True, index=True)
    source: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    schema_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    snapshot_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    snapshot_sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class CapabilityPackage(Base):
    __tablename__ = "capability_packages"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "package_key",
            "source_sha256",
            name="capability_packages_org_key_source_uidx",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    organization_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    package_key: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    package_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    source_kind: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    source_uri: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    pinned_ref: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="staged", index=True)
    risk_level: Mapped[str] = mapped_column(String(32), nullable=False, default="medium")
    manifest_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    content_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    validation_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    provenance_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    audit_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    capability_id: Mapped[str | None] = mapped_column(
        ForeignKey("capabilities.id"),
        nullable=True,
        index=True,
    )
    capability_version_id: Mapped[str | None] = mapped_column(
        ForeignKey("capability_versions.id"),
        nullable=True,
        index=True,
    )
    created_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    approved_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AgentSession(Base):
    __tablename__ = "agent_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    organization_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    agent_id: Mapped[str] = mapped_column(ForeignKey("agents.id"), nullable=False, index=True)
    created_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(64), nullable=False, default="ACTIVE", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class AgentMessage(Base):
    __tablename__ = "agent_messages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    session_id: Mapped[str] = mapped_column(
        ForeignKey("agent_sessions.id"),
        nullable=False,
        index=True,
    )
    agent_id: Mapped[str] = mapped_column(ForeignKey("agents.id"), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(64), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    metadata_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class LocalAgentPairingToken(Base):
    __tablename__ = "local_agent_pairing_tokens"
    __table_args__ = (
        UniqueConstraint("token_hash", name="local_agent_pairing_tokens_hash_uidx"),
        Index("ix_local_agent_pairing_org_user", "organization_id", "user_id"),
        Index("ix_local_agent_pairing_expires", "expires_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    organization_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    user_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    agent_id: Mapped[str] = mapped_column(ForeignKey("agents.id"), nullable=False, index=True)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    pair_code: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    scope_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active", index=True)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class LocalAgentConnection(Base):
    __tablename__ = "local_agent_connections"
    __table_args__ = (
        UniqueConstraint(
            "device_token_hash",
            name="local_agent_connections_device_token_hash_uidx",
        ),
        UniqueConstraint(
            "pairing_token_id",
            name="local_agent_connections_pairing_token_uidx",
        ),
        Index("ix_local_agent_connections_org_user", "organization_id", "owner_user_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    organization_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    owner_user_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    agent_id: Mapped[str] = mapped_column(ForeignKey("agents.id"), nullable=False, index=True)
    pairing_token_id: Mapped[str | None] = mapped_column(
        ForeignKey("local_agent_pairing_tokens.id"),
        nullable=True,
        index=True,
    )
    device_token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    display_name: Mapped[str] = mapped_column(Text, nullable=False)
    adapter_kind: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    protocol_version: Mapped[str] = mapped_column(String(32), nullable=False)
    bridge_version: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="online", index=True)
    workspace_root: Mapped[str | None] = mapped_column(Text, nullable=True)
    capabilities_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    risk_capabilities_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    metadata_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class LocalAgentConversationBinding(Base):
    __tablename__ = "local_agent_conversation_bindings"
    __table_args__ = (
        UniqueConstraint(
            "connection_id",
            "agent_session_id",
            name="local_agent_bindings_connection_session_uidx",
        ),
        Index("ix_local_agent_bindings_org_user", "organization_id", "owner_user_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    organization_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    owner_user_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    connection_id: Mapped[str] = mapped_column(
        ForeignKey("local_agent_connections.id"),
        nullable=False,
        index=True,
    )
    agent_id: Mapped[str] = mapped_column(ForeignKey("agents.id"), nullable=False, index=True)
    agent_session_id: Mapped[str] = mapped_column(
        ForeignKey("agent_sessions.id"),
        nullable=False,
        index=True,
    )
    adapter_session_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    resume_mode: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        default="native_resume",
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active", index=True)
    metadata_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class LocalAgentBridgeTask(Base):
    __tablename__ = "local_agent_bridge_tasks"
    __table_args__ = (
        UniqueConstraint(
            "binding_id",
            "client_message_id",
            name="local_agent_bridge_tasks_binding_message_uidx",
        ),
        Index("ix_local_agent_bridge_tasks_connection_status", "connection_id", "status"),
        Index("ix_local_agent_bridge_tasks_task", "task_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    organization_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    owner_user_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    connection_id: Mapped[str] = mapped_column(
        ForeignKey("local_agent_connections.id"),
        nullable=False,
        index=True,
    )
    binding_id: Mapped[str] = mapped_column(
        ForeignKey("local_agent_conversation_bindings.id"),
        nullable=False,
        index=True,
    )
    agent_session_id: Mapped[str] = mapped_column(
        ForeignKey("agent_sessions.id"),
        nullable=False,
        index=True,
    )
    task_id: Mapped[str] = mapped_column(ForeignKey("tasks.id"), nullable=False, index=True)
    user_message_id: Mapped[str] = mapped_column(
        ForeignKey("agent_messages.id"),
        nullable=False,
        index=True,
    )
    client_message_id: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending", index=True)
    payload_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    leased_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    acked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class LocalAgentBridgeEventReceipt(Base):
    __tablename__ = "local_agent_bridge_event_receipts"
    __table_args__ = (
        UniqueConstraint(
            "connection_id",
            "event_id",
            name="local_agent_bridge_receipts_connection_event_uidx",
        ),
        Index("ix_local_agent_bridge_receipts_task", "task_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    organization_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    connection_id: Mapped[str] = mapped_column(
        ForeignKey("local_agent_connections.id"),
        nullable=False,
        index=True,
    )
    bridge_task_id: Mapped[str | None] = mapped_column(
        ForeignKey("local_agent_bridge_tasks.id"),
        nullable=True,
        index=True,
    )
    task_id: Mapped[str | None] = mapped_column(ForeignKey("tasks.id"), nullable=True, index=True)
    event_id: Mapped[str] = mapped_column(Text, nullable=False)
    sequence: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    payload_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    agent_event_id: Mapped[str | None] = mapped_column(ForeignKey("agent_events.id"), nullable=True)
    tool_call_id: Mapped[str | None] = mapped_column(ForeignKey("tool_calls.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class ExecutionPlan(Base):
    __tablename__ = "execution_plans"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    task_id: Mapped[str] = mapped_column(ForeignKey("tasks.id"), nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(64), nullable=False)
    plan_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class TaskStep(Base):
    __tablename__ = "task_steps"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    task_id: Mapped[str] = mapped_column(ForeignKey("tasks.id"), nullable=False, index=True)
    plan_id: Mapped[str] = mapped_column(
        ForeignKey("execution_plans.id"),
        nullable=False,
        index=True,
    )
    step_key: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(64), nullable=False)
    execution_mode: Mapped[str] = mapped_column(String(64), nullable=False)
    assigned_agent_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)


class AgentRun(Base):
    __tablename__ = "agent_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    task_id: Mapped[str] = mapped_column(ForeignKey("tasks.id"), nullable=False, index=True)
    parent_agent_id: Mapped[str | None] = mapped_column(ForeignKey("agent_runs.id"), nullable=True)
    agent_type: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(64), nullable=False)
    specialist_id: Mapped[str | None] = mapped_column(
        ForeignKey("subagent_specialists.id"),
        nullable=True,
        index=True,
    )
    context_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    capability_snapshot_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    timeout_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    specialist: Mapped[SubagentSpecialist | None] = relationship()
    subagent_output: Mapped[SubagentOutput | None] = relationship(
        back_populates="agent_run",
        uselist=False,
    )


class SubagentSpecialist(Base):
    __tablename__ = "subagent_specialists"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "slug",
            name="subagent_specialists_org_slug_uidx",
        ),
        Index("ix_subagent_specialists_visibility_status", "visibility", "status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    organization_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    slug: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    display_name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    system_prompt: Mapped[str] = mapped_column(Text, nullable=False)
    capability_slugs_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    output_schema_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    budget_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    trigger_keywords_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    visibility: Mapped[str] = mapped_column(String(16), nullable=False, default="org", index=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="ACTIVE", index=True)
    created_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class SubagentOutput(Base):
    __tablename__ = "subagent_outputs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    agent_run_id: Mapped[str] = mapped_column(
        ForeignKey("agent_runs.id"),
        nullable=False,
        unique=True,
        index=True,
    )
    task_id: Mapped[str] = mapped_column(ForeignKey("tasks.id"), nullable=False, index=True)
    specialist_id: Mapped[str | None] = mapped_column(
        ForeignKey("subagent_specialists.id"),
        nullable=True,
        index=True,
    )
    output_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    output_schema_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    budget_consumed_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    budget_exceeded_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    written_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    agent_run: Mapped[AgentRun] = relationship(back_populates="subagent_output")
    specialist: Mapped[SubagentSpecialist | None] = relationship()


class SpecialistSelectionDecision(Base):
    __tablename__ = "specialist_selection_decisions"
    __table_args__ = (
        Index(
            "ix_specialist_selection_decisions_org_created",
            "organization_id",
            "created_at",
        ),
        Index("ix_specialist_selection_decisions_task_step", "task_id", "plan_step_key"),
    )

    id: Mapped[str] = mapped_column(String(128), primary_key=True, default=new_uuid)
    organization_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    task_id: Mapped[str] = mapped_column(ForeignKey("tasks.id"), nullable=False, index=True)
    plan_step_key: Mapped[str] = mapped_column(Text, nullable=False)
    selected_slug: Mapped[str | None] = mapped_column(String(64), nullable=True)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    reasoning: Mapped[str] = mapped_column(Text, nullable=False, default="")
    selector: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    alternative_slugs_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    candidate_slugs_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    trace_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class SpecialistMarketplaceListing(Base):
    __tablename__ = "specialist_marketplace_listings"
    __table_args__ = (UniqueConstraint("slug", name="specialist_marketplace_listings_slug_uidx"),)

    id: Mapped[str] = mapped_column(String(128), primary_key=True, default=new_uuid)
    slug: Mapped[str] = mapped_column(String(96), nullable=False, index=True)
    display_name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    author_org_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    author_name: Mapped[str] = mapped_column(Text, nullable=False)
    version: Mapped[str] = mapped_column(String(32), nullable=False)
    manifest_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    signature: Mapped[str] = mapped_column(String(128), nullable=False)
    verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    download_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class SpecialistInstallation(Base):
    __tablename__ = "specialist_installations"
    __table_args__ = (
        UniqueConstraint(
            "listing_id",
            "installed_org_id",
            name="specialist_installations_listing_org_uidx",
        ),
    )

    id: Mapped[str] = mapped_column(String(128), primary_key=True, default=new_uuid)
    listing_id: Mapped[str] = mapped_column(
        String(128), ForeignKey("specialist_marketplace_listings.id"), nullable=False, index=True
    )
    installed_org_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    installed_specialist_id: Mapped[str] = mapped_column(
        ForeignKey("subagent_specialists.id"), nullable=False
    )
    installed_version: Mapped[str] = mapped_column(String(32), nullable=False)
    auto_update_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    installed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    listing: Mapped[SpecialistMarketplaceListing] = relationship()
    installed_specialist: Mapped[SubagentSpecialist] = relationship()


class AgentAssignment(Base):
    __tablename__ = "agent_assignments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    run_id: Mapped[str] = mapped_column(ForeignKey("tasks.id"), nullable=False, index=True)
    agent_id: Mapped[str] = mapped_column(ForeignKey("agents.id"), nullable=False, index=True)
    parent_assignment_id: Mapped[str | None] = mapped_column(
        ForeignKey("agent_assignments.id"),
        nullable=True,
    )
    step_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    role: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(64), nullable=False, default="PENDING", index=True)
    input_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    output_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AgentHandoff(Base):
    __tablename__ = "agent_handoffs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    run_id: Mapped[str] = mapped_column(ForeignKey("tasks.id"), nullable=False, index=True)
    from_assignment_id: Mapped[str | None] = mapped_column(
        ForeignKey("agent_assignments.id"),
        nullable=True,
    )
    to_assignment_id: Mapped[str] = mapped_column(
        ForeignKey("agent_assignments.id"),
        nullable=False,
    )
    handoff_type: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(64), nullable=False, default="COMPLETED")
    payload_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class SubagentRecoveryBatch(Base):
    __tablename__ = "subagent_recovery_batches"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    batch_id: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    organization_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    task_id: Mapped[str | None] = mapped_column(ForeignKey("tasks.id"), nullable=True, index=True)
    trigger: Mapped[str] = mapped_column(String(64), nullable=False)
    lock_acquired: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    replay_sequence: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    stale_after_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    enqueue: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    task_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    scanned_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    recovered_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    action_counts: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    recovered: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    recovered_by_task: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    completed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class AgentEvent(Base):
    __tablename__ = "agent_events"
    __table_args__ = (
        UniqueConstraint("task_id", "sequence", name="agent_events_task_sequence_uidx"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    task_id: Mapped[str] = mapped_column(ForeignKey("tasks.id"), nullable=False, index=True)
    agent_run_id: Mapped[str | None] = mapped_column(ForeignKey("agent_runs.id"), nullable=True)
    sequence: Mapped[int] = mapped_column(BigInteger, nullable=False)
    event_type: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    payload_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    actor_type: Mapped[str] = mapped_column(String(64), nullable=False, default="system")
    actor_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    trace_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    task: Mapped[Task] = relationship(back_populates="events")


class SandboxInstance(Base):
    __tablename__ = "sandbox_instances"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    task_id: Mapped[str] = mapped_column(ForeignKey("tasks.id"), nullable=False, index=True)
    agent_run_id: Mapped[str | None] = mapped_column(ForeignKey("agent_runs.id"), nullable=True)
    container_id: Mapped[str] = mapped_column(Text, nullable=False)
    image: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(64), nullable=False)
    cpu_limit: Mapped[str] = mapped_column(Text, nullable=False)
    memory_limit_mb: Mapped[int] = mapped_column(Integer, nullable=False)
    network_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    warm_pool_reused: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    destroyed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class WarmPoolContainer(Base):
    __tablename__ = "warm_pool_containers"
    __table_args__ = (
        UniqueConstraint("container_id", name="warm_pool_containers_container_id_uidx"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    container_id: Mapped[str] = mapped_column(Text, nullable=False)
    image: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    locked_by: Mapped[str | None] = mapped_column(Text, nullable=True)
    task_id: Mapped[str | None] = mapped_column(ForeignKey("tasks.id"), nullable=True, index=True)
    sandbox_id: Mapped[str | None] = mapped_column(
        ForeignKey("sandbox_instances.id"),
        nullable=True,
        index=True,
    )
    idle_since: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class TaskSnapshot(Base):
    __tablename__ = "task_snapshots"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    task_id: Mapped[str] = mapped_column(ForeignKey("tasks.id"), nullable=False, index=True)
    sequence: Mapped[int] = mapped_column(BigInteger, nullable=False)
    state_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class ModelCall(Base):
    __tablename__ = "model_calls"
    __table_args__ = (
        ForeignKeyConstraint(
            ["context_manifest_id"],
            ["context_assembly_manifests.id"],
            name="model_calls_context_manifest_id_fkey",
        ),
        ForeignKeyConstraint(
            ["prompt_manifest_id"],
            ["prompt_assembly_manifests.id"],
            name="model_calls_prompt_manifest_id_fkey",
        ),
        ForeignKeyConstraint(
            ["prompt_manifest_id", "task_id", "grounding_correlation_id"],
            [
                "prompt_assembly_manifests.id",
                "prompt_assembly_manifests.run_id",
                "prompt_assembly_manifests.grounding_correlation_id",
            ],
            name="model_calls_prompt_manifest_binding_fkey",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    task_id: Mapped[str] = mapped_column(ForeignKey("tasks.id"), nullable=False, index=True)
    agent_run_id: Mapped[str | None] = mapped_column(ForeignKey("agent_runs.id"), nullable=True)
    model_provider: Mapped[str] = mapped_column(Text, nullable=False)
    model_name: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(64), nullable=False)
    prompt_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    completion_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    grounding_correlation_id: Mapped[str | None] = mapped_column(
        String(36),
        nullable=True,
        index=True,
    )
    prompt_manifest_id: Mapped[str | None] = mapped_column(
        String(36),
        nullable=True,
        index=True,
    )
    context_manifest_id: Mapped[str | None] = mapped_column(
        String(36),
        nullable=True,
        index=True,
    )
    capability_snapshot_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    legacy_prompt_manifest_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    model_request_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    model_request_hash_schema_version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=2,
    )
    request_message_hashes_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    request_message_hashes_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    hash_recomputability_status: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        default="recomputable_v2",
    )
    attempt_index: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    terminal_status: Mapped[str | None] = mapped_column(String(64), nullable=True)
    request_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    response_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class ToolCall(Base):
    __tablename__ = "tool_calls"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    task_id: Mapped[str] = mapped_column(ForeignKey("tasks.id"), nullable=False, index=True)
    agent_run_id: Mapped[str | None] = mapped_column(ForeignKey("agent_runs.id"), nullable=True)
    tool_name: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(64), nullable=False)
    risk_level: Mapped[str] = mapped_column(String(64), nullable=False)
    capability_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    capability_version_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    capability_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    capability_content_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    capability_config_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    capability_schema_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    capability_snapshot_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    requires_sandbox: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    sandbox_id: Mapped[str | None] = mapped_column(
        ForeignKey("sandbox_instances.id"),
        nullable=True,
    )
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    input_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    output_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class ToolApproval(Base):
    __tablename__ = "tool_approvals"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    task_id: Mapped[str] = mapped_column(ForeignKey("tasks.id"), nullable=False, index=True)
    tool_call_id: Mapped[str] = mapped_column(
        ForeignKey("tool_calls.id"),
        nullable=False,
        index=True,
    )
    organization_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    requested_by: Mapped[str | None] = mapped_column(Text, nullable=True)
    decided_by: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(64), nullable=False, default="PENDING", index=True)
    risk_level: Mapped[str] = mapped_column(String(64), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    request_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    decision_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class KnowledgeSource(Base):
    __tablename__ = "knowledge_sources"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "agent_id",
            "idempotency_key",
            name="knowledge_sources_scope_idempotency_uidx",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    organization_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    agent_id: Mapped[str | None] = mapped_column(ForeignKey("agents.id"), nullable=True, index=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    source_type: Mapped[str] = mapped_column(String(64), nullable=False, default="text")
    status: Mapped[str] = mapped_column(String(64), nullable=False, default="ACTIVE", index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    disabled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_indexed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_ingestion_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    health_status: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        default="HEALTHY",
        index=True,
    )
    settings_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    metadata_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    idempotency_key: Mapped[str | None] = mapped_column(Text, nullable=True, index=True)
    created_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class KnowledgeDocument(Base):
    __tablename__ = "knowledge_documents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    source_id: Mapped[str] = mapped_column(
        ForeignKey("knowledge_sources.id"),
        nullable=False,
        index=True,
    )
    organization_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    agent_id: Mapped[str | None] = mapped_column(ForeignKey("agents.id"), nullable=True, index=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    uri: Mapped[str | None] = mapped_column(Text, nullable=True)
    content_sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    mime_type: Mapped[str] = mapped_column(Text, nullable=False, default="text/markdown")
    status: Mapped[str] = mapped_column(String(64), nullable=False, default="INDEXED", index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    logical_document_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    supersedes_document_id: Mapped[str | None] = mapped_column(
        ForeignKey("knowledge_documents.id"),
        nullable=True,
    )
    superseded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ingestion_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    idempotency_key: Mapped[str | None] = mapped_column(Text, nullable=True, index=True)
    created_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    indexed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class KnowledgeChunk(Base):
    __tablename__ = "knowledge_chunks"
    __table_args__ = (
        UniqueConstraint(
            "document_id",
            "chunk_index",
            "chunk_version",
            name="knowledge_chunks_document_chunk_version_uidx",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    document_id: Mapped[str] = mapped_column(
        ForeignKey("knowledge_documents.id"),
        nullable=False,
        index=True,
    )
    source_id: Mapped[str] = mapped_column(
        ForeignKey("knowledge_sources.id"),
        nullable=False,
        index=True,
    )
    organization_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    agent_id: Mapped[str | None] = mapped_column(ForeignKey("agents.id"), nullable=True, index=True)
    source_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    document_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    chunk_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    text_sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    start_offset: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    end_offset: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(64), nullable=False, default="ACTIVE", index=True)
    metadata_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class KnowledgeEmbedding(Base):
    __tablename__ = "knowledge_embeddings"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    chunk_id: Mapped[str] = mapped_column(
        ForeignKey("knowledge_chunks.id"),
        nullable=False,
        index=True,
    )
    organization_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    agent_id: Mapped[str | None] = mapped_column(ForeignKey("agents.id"), nullable=True, index=True)
    provider: Mapped[str] = mapped_column(Text, nullable=False)
    model: Mapped[str] = mapped_column(Text, nullable=False)
    model_version: Mapped[str] = mapped_column(Text, nullable=False)
    dimensions: Mapped[int] = mapped_column(Integer, nullable=False)
    embedding_vector: Mapped[str | None] = mapped_column(Text, nullable=True)
    embedding_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    status: Mapped[str] = mapped_column(String(64), nullable=False, default="READY", index=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class RetrievalSession(Base):
    __tablename__ = "retrieval_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    organization_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    agent_id: Mapped[str] = mapped_column(ForeignKey("agents.id"), nullable=False, index=True)
    run_id: Mapped[str | None] = mapped_column(ForeignKey("tasks.id"), nullable=True, index=True)
    query: Mapped[str] = mapped_column(Text, nullable=False)
    mode: Mapped[str] = mapped_column(String(64), nullable=False, default="local")
    local_status: Mapped[str] = mapped_column(String(64), nullable=False, default="insufficient")
    vector_capability: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        default="unavailable",
    )
    strategy: Mapped[str] = mapped_column(String(64), nullable=False, default="lexical")
    min_hits: Mapped[int] = mapped_column(Integer, nullable=False, default=2)
    min_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.62)
    max_local_chunks: Mapped[int] = mapped_column(Integer, nullable=False, default=6)
    max_web_results: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    metadata_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class WebResearchSource(Base):
    __tablename__ = "web_research_sources"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    retrieval_session_id: Mapped[str] = mapped_column(
        ForeignKey("retrieval_sessions.id"),
        nullable=False,
        index=True,
    )
    organization_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    agent_id: Mapped[str] = mapped_column(ForeignKey("agents.id"), nullable=False, index=True)
    run_id: Mapped[str | None] = mapped_column(ForeignKey("tasks.id"), nullable=True, index=True)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    content_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    snippet: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(64), nullable=False, default="READY", index=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class WebResearchAttempt(Base):
    __tablename__ = "web_research_attempts"
    __table_args__ = (
        UniqueConstraint("run_id", "call_slot", name="web_research_attempts_run_slot_uidx"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    run_id: Mapped[str] = mapped_column(ForeignKey("tasks.id"), nullable=False, index=True)
    retrieval_session_id: Mapped[str] = mapped_column(
        ForeignKey("retrieval_sessions.id"),
        nullable=False,
        index=True,
    )
    organization_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    agent_id: Mapped[str] = mapped_column(ForeignKey("agents.id"), nullable=False, index=True)
    provider: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    call_slot: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(64), nullable=False, default="RESERVED", index=True)
    metadata_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class RetrievalHit(Base):
    __tablename__ = "retrieval_hits"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    retrieval_session_id: Mapped[str] = mapped_column(
        ForeignKey("retrieval_sessions.id"),
        nullable=False,
        index=True,
    )
    chunk_id: Mapped[str | None] = mapped_column(
        ForeignKey("knowledge_chunks.id"),
        nullable=True,
        index=True,
    )
    web_source_id: Mapped[str | None] = mapped_column(
        ForeignKey("web_research_sources.id"),
        nullable=True,
        index=True,
    )
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    score: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    source_kind: Mapped[str] = mapped_column(String(64), nullable=False)
    document_id: Mapped[str | None] = mapped_column(
        ForeignKey("knowledge_documents.id"),
        nullable=True,
        index=True,
    )
    document_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    snippet: Mapped[str] = mapped_column(Text, nullable=False)
    metadata_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class CitationRecord(Base):
    __tablename__ = "citation_records"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    retrieval_session_id: Mapped[str] = mapped_column(
        ForeignKey("retrieval_sessions.id"),
        nullable=False,
        index=True,
    )
    retrieval_hit_id: Mapped[str] = mapped_column(
        ForeignKey("retrieval_hits.id"),
        nullable=False,
        index=True,
    )
    run_id: Mapped[str | None] = mapped_column(ForeignKey("tasks.id"), nullable=True, index=True)
    message_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    citation_key: Mapped[str] = mapped_column(Text, nullable=False)
    source_kind: Mapped[str] = mapped_column(String(64), nullable=False)
    chunk_id: Mapped[str | None] = mapped_column(ForeignKey("knowledge_chunks.id"), nullable=True)
    web_source_id: Mapped[str | None] = mapped_column(
        ForeignKey("web_research_sources.id"),
        nullable=True,
    )
    claim_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    quoted_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    metadata_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class AgentMemoryRecord(Base):
    __tablename__ = "agent_memory_records"
    __table_args__ = (
        CheckConstraint(
            "scope IN ('org', 'agent', 'user', 'run')",
            name="agent_memory_records_scope_check",
        ),
        CheckConstraint(
            "lifecycle_status IN ('active', 'disabled', 'archived', 'deleted', 'expired')",
            name="agent_memory_records_lifecycle_check",
        ),
        CheckConstraint(
            "scope != 'user' OR owner_user_id IS NOT NULL",
            name="agent_memory_records_user_owner_check",
        ),
        CheckConstraint(
            "scope != 'run' OR run_id IS NOT NULL",
            name="agent_memory_records_run_id_check",
        ),
        Index(
            "ix_agent_memory_records_scope_lookup",
            "organization_id",
            "agent_id",
            "owner_user_id",
            "scope",
            "lifecycle_status",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    organization_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    agent_id: Mapped[str | None] = mapped_column(ForeignKey("agents.id"), nullable=True, index=True)
    owner_user_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    run_id: Mapped[str | None] = mapped_column(ForeignKey("tasks.id"), nullable=True, index=True)
    message_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    scope: Mapped[str] = mapped_column(String(16), nullable=False, default="agent", index=True)
    source_type: Mapped[str] = mapped_column(String(64), nullable=False, default="manual")
    canonical_text: Mapped[str] = mapped_column(Text, nullable=False)
    content_sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    content_length: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    score: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    policy_flags_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    metadata_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    lifecycle_status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="active",
        index=True,
    )
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    updated_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class PromptAssemblyManifest(Base):
    __tablename__ = "prompt_assembly_manifests"
    __table_args__ = (
        UniqueConstraint(
            "id",
            "run_id",
            "grounding_correlation_id",
            name="prompt_assembly_manifests_binding_uidx",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    retrieval_session_id: Mapped[str] = mapped_column(
        ForeignKey("retrieval_sessions.id"),
        nullable=False,
        index=True,
    )
    run_id: Mapped[str | None] = mapped_column(ForeignKey("tasks.id"), nullable=True, index=True)
    organization_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    agent_id: Mapped[str] = mapped_column(ForeignKey("agents.id"), nullable=False, index=True)
    grounding_correlation_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    query: Mapped[str] = mapped_column(Text, nullable=False)
    included_retrieval_hit_ids_json: Mapped[list] = mapped_column(
        JSON,
        nullable=False,
        default=list,
    )
    omitted_candidates_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    source_snapshots_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    token_budget_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    prompt_sections_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    evidence_text_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    metadata_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class ContextAssemblyManifest(Base):
    __tablename__ = "context_assembly_manifests"
    __table_args__ = (
        Index("ix_context_assembly_manifests_org_created", "organization_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    organization_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    agent_id: Mapped[str] = mapped_column(ForeignKey("agents.id"), nullable=False, index=True)
    run_id: Mapped[str | None] = mapped_column(ForeignKey("tasks.id"), nullable=True, index=True)
    retrieval_session_id: Mapped[str | None] = mapped_column(
        ForeignKey("retrieval_sessions.id"),
        nullable=True,
        index=True,
    )
    prompt_manifest_id: Mapped[str | None] = mapped_column(
        ForeignKey("prompt_assembly_manifests.id"),
        nullable=True,
        index=True,
    )
    active_branch_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    active_leaf_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    mode: Mapped[str] = mapped_column(String(32), nullable=False, default="shadow", index=True)
    token_budget_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    sections_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    included_refs_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    omitted_refs_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    policy_decisions_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    tombstoned_refs_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    context_text_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    metadata_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class ContextAssemblyManifestLifecycle(Base):
    __tablename__ = "context_assembly_manifest_lifecycle"
    __table_args__ = (
        CheckConstraint(
            "lifecycle_status IN ('active', 'tombstoned', 'expired')",
            name="context_assembly_manifest_lifecycle_status_check",
        ),
        Index(
            "ix_context_assembly_manifest_lifecycle_org_expires",
            "organization_id",
            "expires_at",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    context_manifest_id: Mapped[str] = mapped_column(
        ForeignKey("context_assembly_manifests.id"),
        nullable=False,
        index=True,
    )
    organization_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    lifecycle_status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    tombstoned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class WorkspaceContextCache(Base):
    __tablename__ = "workspace_context_caches"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "cache_source",
            "cache_key_hash",
            name="workspace_context_caches_org_source_key_uidx",
        ),
        Index(
            "ix_workspace_context_caches_org_source_agent",
            "organization_id",
            "cache_source",
            "agent_id",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    organization_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    agent_id: Mapped[str | None] = mapped_column(ForeignKey("agents.id"), nullable=True, index=True)
    owner_user_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    cache_source: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    cache_key_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    schema_version: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active", index=True)
    payload_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    metadata_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    hit_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    miss_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    stale_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    estimated_saved_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_hit_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class KnowledgePolicyAudit(Base):
    __tablename__ = "knowledge_policy_audits"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    retrieval_session_id: Mapped[str] = mapped_column(
        ForeignKey("retrieval_sessions.id"),
        nullable=False,
        index=True,
    )
    run_id: Mapped[str | None] = mapped_column(ForeignKey("tasks.id"), nullable=True, index=True)
    organization_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    agent_id: Mapped[str] = mapped_column(ForeignKey("agents.id"), nullable=False, index=True)
    decision: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    source_kind: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source_ref_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    safe_metadata_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


def _reject_audit_update(_mapper, _connection, target) -> None:
    raise ValueError(f"{target.__class__.__name__} is append-only")


event.listen(PromptAssemblyManifest, "before_update", _reject_audit_update)
event.listen(PromptAssemblyManifest, "before_delete", _reject_audit_update)
event.listen(ContextAssemblyManifest, "before_update", _reject_audit_update)
event.listen(ContextAssemblyManifest, "before_delete", _reject_audit_update)
event.listen(KnowledgePolicyAudit, "before_update", _reject_audit_update)
event.listen(KnowledgePolicyAudit, "before_delete", _reject_audit_update)


class EvalDataset(Base):
    __tablename__ = "eval_datasets"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    organization_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    status: Mapped[str] = mapped_column(String(64), nullable=False, default="ACTIVE", index=True)
    baseline_run_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("eval_runs.id"), nullable=True
    )
    created_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class EvalCase(Base):
    __tablename__ = "eval_cases"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    dataset_id: Mapped[str] = mapped_column(
        ForeignKey("eval_datasets.id"),
        nullable=False,
        index=True,
    )
    source_task_id: Mapped[str | None] = mapped_column(
        ForeignKey("tasks.id"),
        nullable=True,
        index=True,
    )
    input_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    expected_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    capability_snapshot_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    tags_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class EvalRun(Base):
    __tablename__ = "eval_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    dataset_id: Mapped[str] = mapped_column(
        ForeignKey("eval_datasets.id"),
        nullable=False,
        index=True,
    )
    organization_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    agent_id: Mapped[str | None] = mapped_column(ForeignKey("agents.id"), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(64), nullable=False, default="PENDING", index=True)
    capability_snapshot_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    metrics_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class EvalResult(Base):
    __tablename__ = "eval_results"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    eval_run_id: Mapped[str] = mapped_column(
        ForeignKey("eval_runs.id"),
        nullable=False,
        index=True,
    )
    eval_case_id: Mapped[str] = mapped_column(
        ForeignKey("eval_cases.id"),
        nullable=False,
        index=True,
    )
    task_id: Mapped[str | None] = mapped_column(ForeignKey("tasks.id"), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(64), nullable=False)
    scores_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    grader_trace_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cost_usd: Mapped[str] = mapped_column(String(32), nullable=False, default="0")
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class EvalExperiment(Base):
    __tablename__ = "eval_experiments"
    __table_args__ = (Index("ix_eval_experiments_org_created", "organization_id", "created_at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    dataset_id: Mapped[str] = mapped_column(
        ForeignKey("eval_datasets.id"),
        nullable=False,
        index=True,
    )
    organization_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    status: Mapped[str] = mapped_column(String(64), nullable=False, default="COMPLETED", index=True)
    metadata_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class EvalExperimentArm(Base):
    __tablename__ = "eval_experiment_arms"
    __table_args__ = (
        UniqueConstraint(
            "experiment_id",
            "name",
            name="eval_experiment_arms_experiment_name_uidx",
        ),
        Index("ix_eval_experiment_arms_experiment_created", "experiment_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    experiment_id: Mapped[str] = mapped_column(
        ForeignKey("eval_experiments.id"),
        nullable=False,
        index=True,
    )
    dataset_id: Mapped[str] = mapped_column(
        ForeignKey("eval_datasets.id"),
        nullable=False,
        index=True,
    )
    eval_run_id: Mapped[str] = mapped_column(
        ForeignKey("eval_runs.id"),
        nullable=False,
        index=True,
    )
    organization_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    arm_type: Mapped[str] = mapped_column(String(64), nullable=False, default="candidate")
    status: Mapped[str] = mapped_column(String(64), nullable=False, default="COMPLETED", index=True)
    capability_hashes_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    metrics_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class ModelPricing(Base):
    __tablename__ = "model_pricing"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "provider",
            "model",
            name="model_pricing_org_provider_model_uidx",
        ),
        Index("ix_model_pricing_provider_model", "provider", "model"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=new_uuid)
    organization_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    model: Mapped[str] = mapped_column(String(128), nullable=False)
    prompt_per_1k_usd: Mapped[str] = mapped_column(String(32), nullable=False, default="0")
    completion_per_1k_usd: Mapped[str] = mapped_column(String(32), nullable=False, default="0")
    cache_prompt_per_1k_usd: Mapped[str] = mapped_column(String(32), nullable=False, default="0")
    currency: Mapped[str] = mapped_column(String(8), nullable=False, default="USD")
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    source: Mapped[str] = mapped_column(String(32), nullable=False, default="manual")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class WarmPoolBenchmarkRun(Base):
    __tablename__ = "warm_pool_benchmark_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    organization_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    mode: Mapped[str] = mapped_column(String(64), nullable=False, default="projection")
    status: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    target_startup_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=50)
    iteration_count: Mapped[int] = mapped_column(Integer, nullable=False, default=5)
    warm_avg_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    warm_p95_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cold_avg_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    hit_rate: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    report_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_by: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class AdminAuditEvent(Base):
    __tablename__ = "admin_audit_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    organization_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    actor_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    event_type: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    resource_type: Mapped[str] = mapped_column(String(128), nullable=False)
    resource_id: Mapped[str] = mapped_column(Text, nullable=False)
    action: Mapped[str] = mapped_column(String(128), nullable=False)
    payload_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class ObservabilityExportRecord(Base):
    __tablename__ = "observability_export_records"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    organization_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    actor_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    export_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    filename: Mapped[str] = mapped_column(Text, nullable=False)
    content_type: Mapped[str] = mapped_column(Text, nullable=False)
    format: Mapped[str] = mapped_column(String(32), nullable=False)
    source: Mapped[str] = mapped_column(String(64), nullable=False)
    row_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    filter_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    storage_driver: Mapped[str] = mapped_column(String(64), nullable=False, default="local_file")
    storage_uri: Mapped[str] = mapped_column(Text, nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class OtelSpan(Base):
    __tablename__ = "otel_spans"
    __table_args__ = (
        UniqueConstraint("trace_id", "span_id", name="otel_spans_trace_span_uidx"),
        Index("ix_otel_spans_trace_start", "trace_id", "start_time"),
        Index("ix_otel_spans_task_start", "task_id", "start_time"),
        Index("ix_otel_spans_org_start", "organization_id", "start_time"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    organization_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    trace_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    span_id: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    parent_span_id: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    kind: Mapped[str] = mapped_column(String(32), nullable=False, default="internal", index=True)
    start_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    end_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    attributes_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="OK", index=True)
    task_id: Mapped[str | None] = mapped_column(ForeignKey("tasks.id"), nullable=True, index=True)
    agent_run_id: Mapped[str | None] = mapped_column(
        ForeignKey("agent_runs.id"),
        nullable=True,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class AlertRule(Base):
    __tablename__ = "alert_rules"
    __table_args__ = (
        UniqueConstraint("organization_id", "name", name="alert_rules_org_name_uidx"),
        CheckConstraint(
            "comparator IN ('>', '<', '>=', '<=', '==')",
            name="alert_rules_comparator_chk",
        ),
        CheckConstraint(
            "severity IN ('info', 'warning', 'critical')",
            name="alert_rules_severity_chk",
        ),
        Index("ix_alert_rules_org_enabled", "organization_id", "enabled"),
    )

    id: Mapped[str] = mapped_column(String(128), primary_key=True, default=new_uuid)
    organization_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    metric: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    comparator: Mapped[str] = mapped_column(String(2), nullable=False)
    threshold: Mapped[float] = mapped_column(Float, nullable=False)
    window_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=300)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    severity: Mapped[str] = mapped_column(String(16), nullable=False, default="warning")
    notification_channels_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class AlertEvent(Base):
    __tablename__ = "alert_events"
    __table_args__ = (
        Index("ix_alert_events_org_triggered", "organization_id", "triggered_at"),
        Index("ix_alert_events_rule_triggered", "rule_id", "triggered_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    organization_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    rule_id: Mapped[str] = mapped_column(ForeignKey("alert_rules.id"), nullable=False, index=True)
    rule_name: Mapped[str] = mapped_column(String(128), nullable=False)
    metric: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    comparator: Mapped[str] = mapped_column(String(2), nullable=False)
    threshold: Mapped[float] = mapped_column(Float, nullable=False)
    observed_value: Mapped[float] = mapped_column(Float, nullable=False)
    severity: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active", index=True)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    context_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    triggered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class NotificationChannel(Base):
    __tablename__ = "notification_channels"
    __table_args__ = (
        CheckConstraint(
            "kind IN ('slack', 'email', 'webhook')",
            name="notification_channels_kind_chk",
        ),
        Index("ix_notification_channels_org_kind", "organization_id", "kind"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    organization_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    config_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    created_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class UserOnboardingState(Base):
    __tablename__ = "user_onboarding_state"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "user_id",
            name="user_onboarding_state_org_user_uidx",
        ),
        Index("ix_user_onboarding_state_org_completed", "organization_id", "completed"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    organization_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    current_step: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    completed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    skipped: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    demo_loaded: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    provider_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    agent_id: Mapped[str | None] = mapped_column(ForeignKey("agents.id"), nullable=True)
    demo_task_id: Mapped[str | None] = mapped_column(ForeignKey("tasks.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class FrontendError(Base):
    __tablename__ = "frontend_errors"
    __table_args__ = (
        Index("ix_frontend_errors_org_created", "organization_id", "created_at"),
        Index("ix_frontend_errors_user_created", "user_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    organization_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    error_message: Mapped[str] = mapped_column(Text, nullable=False)
    stack: Mapped[str | None] = mapped_column(Text, nullable=True)
    browser: Mapped[str] = mapped_column(Text, nullable=False, default="")
    metadata_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class SystemSetting(Base):
    __tablename__ = "system_settings"
    __table_args__ = (
        UniqueConstraint("organization_id", "key", name="system_settings_org_key_uidx"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    organization_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    key: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    value_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    updated_by: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class StoredSecret(Base):
    __tablename__ = "stored_secrets"
    __table_args__ = (
        CheckConstraint("scope IN ('user', 'org')", name="stored_secrets_scope_chk"),
        CheckConstraint(
            "status IN ('active', 'disabled')",
            name="stored_secrets_status_chk",
        ),
        CheckConstraint(
            "scope != 'user' OR owner_user_id IS NOT NULL",
            name="stored_secrets_user_owner_chk",
        ),
        CheckConstraint(
            "scope != 'org' OR owner_user_id IS NULL",
            name="stored_secrets_org_owner_chk",
        ),
        Index(
            "ix_stored_secrets_lookup",
            "organization_id",
            "owner_user_id",
            "provider",
            "purpose",
            "status",
        ),
        Index(
            "ix_stored_secrets_user_active_uidx",
            "organization_id",
            "owner_user_id",
            "provider",
            "purpose",
            unique=True,
            sqlite_where=text("scope = 'user' AND status = 'active'"),
            postgresql_where=text("scope = 'user' AND status = 'active'"),
        ),
        Index(
            "ix_stored_secrets_org_active_uidx",
            "organization_id",
            "provider",
            "purpose",
            unique=True,
            sqlite_where=text("scope = 'org' AND status = 'active'"),
            postgresql_where=text("scope = 'org' AND status = 'active'"),
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    organization_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    owner_user_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    scope: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    provider: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    purpose: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    secret_ref: Mapped[str | None] = mapped_column(Text, nullable=True)
    encrypted_value: Mapped[str] = mapped_column(Text, nullable=False)
    encryption_key_id: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active", index=True)
    created_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    updated_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
