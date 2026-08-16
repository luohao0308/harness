from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import Engine, and_, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models import RuntimeJob, utc_now

ACTIVE_STATUSES = ("queued", "running")


@dataclass(frozen=True)
class ClaimedRuntimeJob:
    id: str
    kind: str
    payload: dict[str, Any]
    attempt: int
    max_attempts: int
    lease_owner: str
    lease_generation: int
    lease_until: datetime


class RuntimeJobRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def enqueue(
        self,
        *,
        kind: str,
        payload: dict[str, Any],
        dedupe_key: str | None = None,
        max_attempts: int = 3,
        available_at: datetime | None = None,
    ) -> RuntimeJob:
        if max_attempts < 1:
            raise ValueError("max_attempts must be at least 1")
        if dedupe_key is not None:
            existing = self.session.execute(
                select(RuntimeJob).where(
                    RuntimeJob.dedupe_key == dedupe_key,
                    RuntimeJob.status.in_(ACTIVE_STATUSES),
                )
            ).scalar_one_or_none()
            if existing is not None:
                return existing
        job = RuntimeJob(
            kind=kind,
            payload=payload,
            dedupe_key=dedupe_key,
            max_attempts=max_attempts,
            available_at=available_at or utc_now(),
        )
        if dedupe_key is None:
            self.session.add(job)
            self.session.flush()
            return job
        try:
            with self.session.begin_nested():
                self.session.add(job)
                self.session.flush()
        except IntegrityError:
            existing = self.session.execute(
                select(RuntimeJob).where(
                    RuntimeJob.dedupe_key == dedupe_key,
                    RuntimeJob.status.in_(ACTIVE_STATUSES),
                )
            ).scalar_one()
            return existing
        return job

    def request_cancel(self, job_id: str, *, now: datetime | None = None) -> bool:
        requested_at = now or utc_now()
        job = self.session.get(RuntimeJob, job_id)
        if job is None or job.status not in ACTIVE_STATUSES:
            return False
        job.cancel_requested_at = requested_at
        job.updated_at = requested_at
        if job.status == "queued":
            job.status = "cancelled"
            job.finished_at = requested_at
        self.session.flush()
        return True

    @staticmethod
    def claim_next(
        engine: Engine,
        *,
        lease_owner: str,
        lease_seconds: float,
        now: datetime | None = None,
    ) -> ClaimedRuntimeJob | None:
        if engine.dialect.name != "sqlite":
            raise ValueError("RuntimeJobRepository.claim_next requires SQLite")
        claimed_at = now or utc_now()
        lease_until = claimed_at + timedelta(seconds=lease_seconds)
        table = RuntimeJob.__table__
        with engine.connect() as connection:
            connection.exec_driver_sql("BEGIN IMMEDIATE")
            try:
                while True:
                    row = connection.execute(
                        select(table).where(
                            or_(
                                and_(
                                    table.c.status == "queued",
                                    table.c.available_at <= claimed_at,
                                ),
                                and_(
                                    table.c.status == "running",
                                    table.c.lease_until <= claimed_at,
                                ),
                            )
                        ).order_by(table.c.available_at, table.c.created_at, table.c.id).limit(1)
                    ).mappings().first()
                    if row is None:
                        connection.commit()
                        return None
                    if row["cancel_requested_at"] is not None:
                        connection.execute(
                            update(table)
                            .where(
                                table.c.id == row["id"],
                                table.c.status == row["status"],
                                table.c.lease_generation == row["lease_generation"],
                            )
                            .values(
                                status="cancelled",
                                finished_at=claimed_at,
                                lease_until=None,
                                lease_owner=None,
                                updated_at=claimed_at,
                            )
                        )
                        continue
                    next_attempt = int(row["attempt"]) + 1
                    if next_attempt > int(row["max_attempts"]):
                        connection.execute(
                            update(table)
                            .where(
                                table.c.id == row["id"],
                                table.c.status == row["status"],
                                table.c.lease_generation == row["lease_generation"],
                            )
                            .values(
                                status="failed",
                                finished_at=claimed_at,
                                lease_until=None,
                                lease_owner=None,
                                error="lease expired after maximum attempts",
                                updated_at=claimed_at,
                            )
                        )
                        continue
                    next_generation = int(row["lease_generation"]) + 1
                    result = connection.execute(
                        update(table)
                        .where(
                            table.c.id == row["id"],
                            table.c.status == row["status"],
                            table.c.lease_generation == row["lease_generation"],
                        )
                        .values(
                            status="running",
                            attempt=next_attempt,
                            lease_owner=lease_owner,
                            lease_generation=next_generation,
                            lease_until=lease_until,
                            heartbeat_at=claimed_at,
                            updated_at=claimed_at,
                        )
                    )
                    if result.rowcount != 1:
                        continue
                    connection.commit()
                    return ClaimedRuntimeJob(
                        id=str(row["id"]),
                        kind=str(row["kind"]),
                        payload=dict(row["payload"]),
                        attempt=next_attempt,
                        max_attempts=int(row["max_attempts"]),
                        lease_owner=lease_owner,
                        lease_generation=next_generation,
                        lease_until=lease_until,
                    )
            except BaseException:
                connection.rollback()
                raise

    def recover_expired(self, *, now: datetime | None = None) -> dict[str, int]:
        recovered_at = now or utc_now()
        jobs = list(
            self.session.execute(
                select(RuntimeJob).where(
                    RuntimeJob.status == "running",
                    RuntimeJob.lease_until <= recovered_at,
                )
            ).scalars()
        )
        counts = {"queued": 0, "failed": 0, "cancelled": 0}
        for job in jobs:
            if job.cancel_requested_at is not None:
                job.status = "cancelled"
                job.finished_at = recovered_at
            elif job.attempt >= job.max_attempts:
                job.status = "failed"
                job.error = "lease expired after maximum attempts"
                job.finished_at = recovered_at
            else:
                job.status = "queued"
                job.available_at = recovered_at
            counts[job.status] += 1
            job.lease_owner = None
            job.lease_until = None
            job.updated_at = recovered_at
        self.session.flush()
        return counts

    def heartbeat(
        self,
        claim: ClaimedRuntimeJob,
        *,
        lease_seconds: float,
        now: datetime | None = None,
    ) -> bool:
        heartbeat_at = now or utc_now()
        result = self.session.execute(
            update(RuntimeJob)
            .where(*self._lease_fence(claim), RuntimeJob.cancel_requested_at.is_(None))
            .values(
                heartbeat_at=heartbeat_at,
                lease_until=heartbeat_at + timedelta(seconds=lease_seconds),
                updated_at=heartbeat_at,
            )
        )
        self.session.flush()
        return result.rowcount == 1

    def owns_current_lease(
        self,
        claim: ClaimedRuntimeJob,
        *,
        now: datetime | None = None,
    ) -> bool:
        checked_at = now or utc_now()
        return (
            self.session.execute(
                select(RuntimeJob.id).where(
                    *self._lease_fence(claim),
                    RuntimeJob.cancel_requested_at.is_(None),
                    RuntimeJob.lease_until > checked_at,
                )
            ).scalar_one_or_none()
            is not None
        )

    def complete(
        self,
        claim: ClaimedRuntimeJob,
        *,
        result_json: dict[str, Any] | None = None,
        now: datetime | None = None,
    ) -> bool:
        finished_at = now or utc_now()
        result = self.session.execute(
            update(RuntimeJob)
            .where(*self._lease_fence(claim), RuntimeJob.cancel_requested_at.is_(None))
            .values(
                status="succeeded",
                result_json=result_json,
                error=None,
                finished_at=finished_at,
                lease_owner=None,
                lease_until=None,
                updated_at=finished_at,
            )
        )
        self.session.flush()
        return result.rowcount == 1

    def fail(
        self,
        claim: ClaimedRuntimeJob,
        *,
        error: str,
        retry_delay_seconds: float = 0,
        now: datetime | None = None,
    ) -> bool:
        failed_at = now or utc_now()
        job = self.session.execute(
            select(RuntimeJob).where(*self._lease_fence(claim))
        ).scalar_one_or_none()
        if job is None:
            return False
        if job.cancel_requested_at is not None:
            job.status = "cancelled"
            job.finished_at = failed_at
        elif job.attempt < job.max_attempts:
            job.status = "queued"
            job.available_at = failed_at + timedelta(seconds=retry_delay_seconds)
        else:
            job.status = "failed"
            job.finished_at = failed_at
        job.error = error[:4000]
        job.lease_owner = None
        job.lease_until = None
        job.updated_at = failed_at
        self.session.flush()
        return True

    @staticmethod
    def _lease_fence(claim: ClaimedRuntimeJob) -> tuple[Any, ...]:
        return (
            RuntimeJob.id == claim.id,
            RuntimeJob.status == "running",
            RuntimeJob.lease_owner == claim.lease_owner,
            RuntimeJob.lease_generation == claim.lease_generation,
        )
