from __future__ import annotations

import time
from datetime import timedelta
from uuid import uuid4

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import RuntimeJob, utc_now
from app.db.session import SessionLocal
from app.runtime_jobs.profile import is_local_runtime_profile
from app.runtime_jobs.repository import ClaimedRuntimeJob, RuntimeJobRepository

TRIGGER_DISPATCH_JOB_KIND = "trigger_invocation_dispatch"
TRIGGER_DISPATCH_LEASE_SECONDS = 60


def dispatch_pending_trigger_invocations(
    *,
    session: Session | None = None,
    limit: int = 20,
) -> dict[str, int]:
    if is_local_runtime_profile():
        return {"dispatched": 0, "failed": 0}
    if not get_settings().trigger_automation_enabled:
        return {"dispatched": 0, "failed": 0}
    owns_session = session is None
    worker_session = session or SessionLocal()
    owner = f"trigger-dispatch:{uuid4()}"
    dispatched = 0
    failed = 0
    try:
        for _ in range(max(1, min(limit, 100))):
            claim = _claim_dispatch(worker_session, owner=owner)
            if claim is None:
                break
            try:
                from app.workers.trigger_invocation_worker import run_trigger_invocation

                run_trigger_invocation.send(str(claim.payload["invocation_id"]))
            except Exception as exc:
                RuntimeJobRepository(worker_session).fail(
                    claim,
                    error=str(exc),
                    retry_delay_seconds=min(60.0, 2 ** max(0, claim.attempt - 1)),
                )
                worker_session.commit()
                failed += 1
                continue
            if not RuntimeJobRepository(worker_session).complete(
                claim,
                result_json={"dispatched": True},
            ):
                worker_session.rollback()
                continue
            worker_session.commit()
            dispatched += 1
        return {"dispatched": dispatched, "failed": failed}
    finally:
        if owns_session:
            worker_session.close()


def _claim_dispatch(session: Session, *, owner: str) -> ClaimedRuntimeJob | None:
    now = utc_now()
    job = session.execute(
        select(RuntimeJob)
        .where(
            RuntimeJob.kind == TRIGGER_DISPATCH_JOB_KIND,
            or_(
                and_(RuntimeJob.status == "queued", RuntimeJob.available_at <= now),
                and_(RuntimeJob.status == "running", RuntimeJob.lease_until <= now),
            ),
        )
        .order_by(RuntimeJob.available_at, RuntimeJob.created_at, RuntimeJob.id)
        .with_for_update(skip_locked=True)
        .limit(1)
    ).scalar_one_or_none()
    if job is None:
        session.rollback()
        return None
    next_attempt = job.attempt + 1
    if next_attempt > job.max_attempts:
        job.status = "failed"
        job.error = "trigger dispatch attempts exhausted"
        job.finished_at = now
        job.updated_at = now
        job.lease_owner = None
        job.lease_until = None
        session.commit()
        return None
    job.status = "running"
    job.attempt = next_attempt
    job.lease_owner = owner
    job.lease_generation += 1
    job.lease_until = now + timedelta(seconds=TRIGGER_DISPATCH_LEASE_SECONDS)
    job.heartbeat_at = now
    job.updated_at = now
    claim = ClaimedRuntimeJob(
        id=job.id,
        kind=job.kind,
        payload=dict(job.payload),
        attempt=job.attempt,
        max_attempts=job.max_attempts,
        lease_owner=owner,
        lease_generation=job.lease_generation,
        lease_until=job.lease_until,
    )
    session.commit()
    return claim


def main() -> None:
    if is_local_runtime_profile():
        raise RuntimeError("trigger dispatcher requires the server runtime profile")
    while True:
        dispatch_pending_trigger_invocations()
        time.sleep(1)


if __name__ == "__main__":
    main()
