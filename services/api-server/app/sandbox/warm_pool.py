from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.db.models import SandboxInstance, utc_now
from app.sandbox.docker_manager import DockerManager
from app.sandbox.policies import DEFAULT_SANDBOX_IMAGE

WARM_POOL_MIN_SIZE = 3
WARM_POOL_MAX_SIZE = 10
WARM_POOL_IDLE_TTL_SECONDS = 600


@dataclass
class WarmPoolContainer:
    container_id: str
    image: str = DEFAULT_SANDBOX_IMAGE
    idle_since_epoch: float = field(default_factory=lambda: utc_now().timestamp())


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
        self._idle: list[WarmPoolContainer] = []
        self._busy: dict[str, str] = {}
        self._failed = 0
        self._hit_total = 0
        self._miss_total = 0

    def prewarm(self) -> None:
        self._prune_expired()
        while self.idle_count < self.min_size and self.total_count < self.max_size:
            container = self.docker_manager.create_container(task_id="warm-pool")
            self._idle.append(WarmPoolContainer(container_id=container.id))

    def acquire(
        self,
        *,
        session: Session,
        task_id: str,
        agent_run_id: str | None = None,
    ) -> SandboxInstance:
        self._prune_expired()
        if self._idle:
            pooled = self._idle.pop(0)
            self._hit_total += 1
            sandbox = self.docker_manager.record_allocated_container(
                session=session,
                task_id=task_id,
                agent_run_id=agent_run_id,
                container_id=pooled.container_id,
                image=pooled.image,
                warm_pool_reused=True,
            )
            self._busy[sandbox.id] = pooled.container_id
            return sandbox

        self._miss_total += 1
        sandbox = self.docker_manager.create_sandbox(
            session=session,
            task_id=task_id,
            agent_run_id=agent_run_id,
        )
        self._busy[sandbox.id] = sandbox.container_id
        return sandbox

    def release(self, *, session: Session, sandbox: SandboxInstance) -> SandboxInstance:
        released = self.docker_manager.release_sandbox(session=session, sandbox=sandbox)
        self._busy.pop(sandbox.id, None)
        if self.idle_count < self.max_size:
            self._idle.append(
                WarmPoolContainer(container_id=sandbox.container_id, image=sandbox.image)
            )
        return released

    def status(self) -> WarmPoolStatus:
        self._prune_expired()
        return WarmPoolStatus(
            enabled=True,
            min_size=self.min_size,
            max_size=self.max_size,
            idle=self.idle_count,
            busy=self.busy_count,
            failed=self._failed,
            hit_total=self._hit_total,
            miss_total=self._miss_total,
        )

    @property
    def idle_count(self) -> int:
        return len(self._idle)

    @property
    def busy_count(self) -> int:
        return len(self._busy)

    @property
    def total_count(self) -> int:
        return self.idle_count + self.busy_count

    def _prune_expired(self) -> None:
        now = utc_now().timestamp()
        active: list[WarmPoolContainer] = []
        for container in self._idle:
            if now - container.idle_since_epoch <= self.idle_ttl_seconds:
                active.append(container)
            else:
                self._failed += 1
        self._idle = active
