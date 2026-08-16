from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Mapping
from contextlib import suppress
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

from sqlalchemy import Engine
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session, sessionmaker

from app.runtime_jobs.handlers import RuntimeJobHandler, default_runtime_job_handlers
from app.runtime_jobs.repository import ClaimedRuntimeJob, RuntimeJobRepository

logger = logging.getLogger(__name__)

DEFAULT_ALERT_EVALUATION_INTERVAL_SECONDS = 60
DEFAULT_SUBAGENT_RECOVERY_INTERVAL_SECONDS = 30


class RuntimeJobLeaseLostError(RuntimeError):
    pass


class _RuntimeJobSession(Session):
    """Keep handler-owned commits inside the coordinator's fenced transaction."""

    def commit(self) -> None:
        if self.info.get("runtime_job_managed_transaction"):
            self.flush()
            return
        super().commit()


@dataclass(frozen=True)
class _PeriodicRuntimeJob:
    kind: str
    payload: dict[str, Any]
    dedupe_key: str
    interval_seconds: float
    max_attempts: int = 3


class RuntimeJobCoordinator:
    def __init__(
        self,
        *,
        engine: Engine,
        handlers: Mapping[str, RuntimeJobHandler] | None = None,
        owner: str | None = None,
        poll_interval_seconds: float = 0.25,
        lease_seconds: float = 30,
        heartbeat_interval_seconds: float = 10,
        max_concurrency: int = 1,
        team_tick_interval_seconds: float = 5,
        alert_evaluation_interval_seconds: float = DEFAULT_ALERT_EVALUATION_INTERVAL_SECONDS,
        subagent_recovery_interval_seconds: float = DEFAULT_SUBAGENT_RECOVERY_INTERVAL_SECONDS,
    ) -> None:
        self.engine = engine
        self.handlers = dict(
            default_runtime_job_handlers() if handlers is None else handlers
        )
        self.owner = owner or f"harnessd-{uuid4()}"
        self.poll_interval_seconds = poll_interval_seconds
        self.lease_seconds = lease_seconds
        self.heartbeat_interval_seconds = heartbeat_interval_seconds
        self.max_concurrency = max(1, max_concurrency)
        self._periodic_jobs = (
            _PeriodicRuntimeJob(
                kind="team_runtime_tick",
                payload={},
                dedupe_key="team-runtime-tick",
                interval_seconds=team_tick_interval_seconds,
            ),
            _PeriodicRuntimeJob(
                kind="alert_evaluation",
                payload={"organization_id": None},
                dedupe_key="alert-evaluation:global",
                interval_seconds=alert_evaluation_interval_seconds,
            ),
            _PeriodicRuntimeJob(
                kind="subagent_recovery",
                payload={},
                dedupe_key="subagent-recovery",
                interval_seconds=subagent_recovery_interval_seconds,
            ),
        )
        self._session_factory = sessionmaker(
            bind=engine,
            class_=_RuntimeJobSession,
            autoflush=False,
            expire_on_commit=False,
        )
        self._loop_task: asyncio.Task[None] | None = None
        self._running: set[asyncio.Task[None]] = set()
        self._stopping = False
        self._next_periodic_at: dict[str, float] = {}

    async def start(self) -> None:
        if self._loop_task is not None:
            return
        if self.engine.dialect.name != "sqlite":
            raise ValueError("The local runtime job coordinator requires SQLite")
        self._stopping = False
        with self._session_factory.begin() as session:
            RuntimeJobRepository(session).recover_expired()
        self._loop_task = asyncio.create_task(self._run(), name="runtime-job-coordinator")

    async def stop(self) -> None:
        self._stopping = True
        if self._loop_task is not None:
            self._loop_task.cancel()
            with suppress(asyncio.CancelledError):
                await self._loop_task
            self._loop_task = None
        if self._running:
            await asyncio.gather(*self._running, return_exceptions=True)

    async def _run(self) -> None:
        while not self._stopping:
            self._running = {task for task in self._running if not task.done()}
            self._seed_periodic_jobs()
            while len(self._running) < self.max_concurrency:
                claim = RuntimeJobRepository.claim_next(
                    self.engine,
                    lease_owner=self.owner,
                    lease_seconds=self.lease_seconds,
                )
                if claim is None:
                    break
                task = asyncio.create_task(self._execute(claim), name=f"runtime-job-{claim.id}")
                self._running.add(task)
            await asyncio.sleep(self.poll_interval_seconds)

    def _seed_periodic_jobs(self) -> None:
        now = time.monotonic()
        scheduled: list[_PeriodicRuntimeJob] = []
        with self._session_factory.begin() as session:
            repository = RuntimeJobRepository(session)
            for job in self._periodic_jobs:
                if job.kind not in self.handlers or job.interval_seconds <= 0:
                    continue
                if now < self._next_periodic_at.get(job.kind, 0.0):
                    continue
                repository.enqueue(
                    kind=job.kind,
                    payload=job.payload,
                    dedupe_key=job.dedupe_key,
                    max_attempts=job.max_attempts,
                )
                scheduled.append(job)
        for job in scheduled:
            self._next_periodic_at[job.kind] = now + job.interval_seconds

    async def _execute(self, claim: ClaimedRuntimeJob) -> None:
        handler = self.handlers.get(claim.kind)
        if handler is None:
            self._record_failure(claim, f"unknown runtime job kind: {claim.kind}")
            return
        heartbeat = asyncio.create_task(self._heartbeat(claim))
        try:
            await asyncio.to_thread(self._execute_fenced_handler, claim, handler)
        except RuntimeJobLeaseLostError:
            logger.info(
                "Runtime job execution rejected by lease fence",
                extra={"event_type": "RUNTIME_JOB_FENCED", "job_id": claim.id},
            )
        except Exception as exc:
            logger.exception(
                "Runtime job failed",
                extra={"event_type": "RUNTIME_JOB_FAILED", "job_id": claim.id},
            )
            self._record_failure(claim, str(exc))
        finally:
            heartbeat.cancel()
            with suppress(asyncio.CancelledError):
                await heartbeat

    def _execute_fenced_handler(
        self,
        claim: ClaimedRuntimeJob,
        handler: RuntimeJobHandler,
    ) -> dict[str, Any] | None:
        with self._session_factory() as session:
            session.info["runtime_job_managed_transaction"] = True
            with session.begin():
                repository = RuntimeJobRepository(session)
                if not repository.owns_current_lease(claim):
                    raise RuntimeJobLeaseLostError(
                        "job handler rejected before execution by lease fence"
                    )
                result = handler(claim.payload, session)
                if not repository.complete(claim, result_json=result):
                    raise RuntimeJobLeaseLostError(
                        "job authoritative effects rejected by lease fence"
                    )
                return result

    async def _heartbeat(self, claim: ClaimedRuntimeJob) -> None:
        while True:
            await asyncio.sleep(self.heartbeat_interval_seconds)
            try:
                with self._session_factory.begin() as session:
                    if not RuntimeJobRepository(session).heartbeat(
                        claim,
                        lease_seconds=self.lease_seconds,
                    ):
                        return
            except OperationalError:
                logger.debug(
                    "Runtime job heartbeat deferred while SQLite writer is busy",
                    extra={"event_type": "RUNTIME_JOB_HEARTBEAT_BUSY", "job_id": claim.id},
                )

    def _record_failure(self, claim: ClaimedRuntimeJob, error: str) -> None:
        retry_delay = min(30.0, 2 ** max(0, claim.attempt - 1))
        with self._session_factory.begin() as session:
            RuntimeJobRepository(session).fail(
                claim,
                error=error,
                retry_delay_seconds=retry_delay,
            )
