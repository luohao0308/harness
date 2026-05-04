from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def new_uuid() -> str:
    return str(uuid4())


def utc_now() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    organization_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
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
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    events: Mapped[list[AgentEvent]] = relationship(back_populates="task")


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
    context_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    timeout_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


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


class TaskSnapshot(Base):
    __tablename__ = "task_snapshots"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    task_id: Mapped[str] = mapped_column(ForeignKey("tasks.id"), nullable=False, index=True)
    sequence: Mapped[int] = mapped_column(BigInteger, nullable=False)
    state_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
