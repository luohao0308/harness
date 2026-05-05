from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import SandboxInstance, WarmPoolContainer, utc_now
from app.db.session import SessionLocal
from app.observability.metrics import (
    warm_pool_busy_containers,
    warm_pool_hit_total,
    warm_pool_idle_containers,
    warm_pool_miss_total,
)
from app.sandbox.docker_manager import DockerManager
from app.sandbox.policies import (
    DEFAULT_SANDBOX_IMAGE,
    DEFAULT_SANDBOX_NETWORK,
    SandboxPolicyResolver,
)

WARM_POOL_MIN_SIZE = 3
WARM_POOL_MAX_SIZE = 10
WARM_POOL_IDLE_TTL_SECONDS = 600


@dataclass(frozen=True)
class WarmPoolStatus:
    enabled: bool
    min_size: int
    max_size: int
    idle: int
    busy: int
    failed: int
    hit_total: int
    miss_total: int


class WarmPoolManager:
    def __init__(
        self,
        docker_manager: DockerManager | None = None,
        *,
        min_size: int = WARM_POOL_MIN_SIZE,
        max_size: int = WARM_POOL_MAX_SIZE,
        idle_ttl_seconds: int = WARM_POOL_IDLE_TTL_SECONDS,
    ) -> None:
        self.docker_manager = docker_manager or DockerManager()
        self.min_size = min_size
        self.max_size = max_size
        self.idle_ttl_seconds = idle_ttl_seconds
        self._hit_total = 0
        self._miss_total = 0

    def prewarm(self, session: Session | None = None) -> None:
        if session is None:
            with SessionLocal() as owned_session:
                self.prewarm(session=owned_session)
                owned_session.commit()
            return

        self._prune_expired(session)
        while (
            self._idle_count(session) < self.min_size
            and self._total_count(session) < self.max_size
        ):
            container = self.docker_manager.create_container(task_id="warm-pool")
            row = WarmPoolContainer(
                container_id=container.id,
                image=DEFAULT_SANDBOX_IMAGE,
                status="IDLE",
                idle_since=utc_now(),
                created_at=utc_now(),
                updated_at=utc_now(),
            )
            session.add(row)
            session.flush()

    def acquire(
        self,
        *,
        session: Session,
        task_id: str,
        agent_run_id: str | None = None,
    ) -> SandboxInstance:
        self._prune_expired(session)
        runtime_policy = SandboxPolicyResolver(session).runtime_for_task(task_id)
        if runtime_policy.network_mode != DEFAULT_SANDBOX_NETWORK:
            self._miss_total += 1
            warm_pool_miss_total.inc()
            return self.docker_manager.create_sandbox(
                session=session,
                task_id=task_id,
                agent_run_id=agent_run_id,
            )
        pooled = self._next_idle(session)
        if pooled is not None:
            self._hit_total += 1
            warm_pool_hit_total.inc()
            locked_by = str(uuid4())
            pooled.status = "BUSY"
            pooled.locked_by = locked_by
            pooled.task_id = task_id
            pooled.updated_at = utc_now()
            session.flush()
            sandbox = self.docker_manager.record_allocated_container(
                session=session,
                task_id=task_id,
                agent_run_id=agent_run_id,
                container_id=pooled.container_id,
                image=pooled.image,
                warm_pool_reused=True,
                runtime_policy=runtime_policy,
            )
            pooled.sandbox_id = sandbox.id
            pooled.updated_at = utc_now()
            session.flush()
            return sandbox

        self._miss_total += 1
        warm_pool_miss_total.inc()
        sandbox = self.docker_manager.create_sandbox(
            session=session,
            task_id=task_id,
            agent_run_id=agent_run_id,
        )
        return sandbox

    def release(self, *, session: Session, sandbox: SandboxInstance) -> SandboxInstance:
        released = self.docker_manager.release_sandbox(session=session, sandbox=sandbox)
        row = session.execute(
            select(WarmPoolContainer).where(WarmPoolContainer.sandbox_id == sandbox.id)
        ).scalar_one_or_none()
        if row is not None:
            row.status = "IDLE"
            row.locked_by = None
            row.task_id = None
            row.sandbox_id = None
            row.idle_since = utc_now()
            row.updated_at = utc_now()
            session.flush()
        return released

    def status(self, session: Session | None = None) -> WarmPoolStatus:
        if session is None:
            with SessionLocal() as owned_session:
                return self.status(session=owned_session)

        self._prune_expired(session)
        idle = self._count_by_status(session, "IDLE")
        busy = self._count_by_status(session, "BUSY")
        failed = self._count_by_status(session, "FAILED")
        warm_pool_idle_containers.set(idle)
        warm_pool_busy_containers.set(busy)
        return WarmPoolStatus(
            enabled=True,
            min_size=self.min_size,
            max_size=self.max_size,
            idle=idle,
            busy=busy,
            failed=failed,
            hit_total=self._hit_total,
            miss_total=self._miss_total,
        )

    def _next_idle(self, session: Session) -> WarmPoolContainer | None:
        statement = (
            select(WarmPoolContainer)
            .where(WarmPoolContainer.status == "IDLE")
            .order_by(WarmPoolContainer.idle_since.asc().nullsfirst())
            .limit(1)
            .with_for_update(skip_locked=True)
        )
        return session.execute(statement).scalar_one_or_none()

    def _prune_expired(self, session: Session) -> None:
        now = utc_now()
        rows = session.execute(
            select(WarmPoolContainer).where(WarmPoolContainer.status == "IDLE")
        ).scalars()
        for row in rows:
            if row.idle_since is None:
                continue
            idle_since = self._as_utc(row.idle_since)
            if now.timestamp() - idle_since.timestamp() > self.idle_ttl_seconds:
                row.status = "FAILED"
                row.updated_at = now
        session.flush()

    def _as_utc(self, value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)

    def _count_by_status(self, session: Session, status: str) -> int:
        return int(
            session.execute(
                select(func.count(WarmPoolContainer.id)).where(WarmPoolContainer.status == status)
            ).scalar_one()
        )

    def _idle_count(self, session: Session) -> int:
        return self._count_by_status(session, "IDLE")

    def _busy_count(self, session: Session) -> int:
        return self._count_by_status(session, "BUSY")

    def _total_count(self, session: Session) -> int:
        return int(
            session.execute(
                select(func.count(WarmPoolContainer.id)).where(
                    WarmPoolContainer.status.in_(["IDLE", "BUSY"])
                )
            ).scalar_one()
        )
