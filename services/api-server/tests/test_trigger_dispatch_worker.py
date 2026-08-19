from __future__ import annotations

from datetime import timedelta

from sqlalchemy.orm import Session

from app.db.models import RuntimeJob, utc_now
from app.runtime_jobs.repository import RuntimeJobRepository
from app.workers import trigger_dispatch_worker, trigger_invocation_worker


def _enqueue_dispatch(session: Session, *, invocation_id: str = "inv-1") -> RuntimeJob:
    job = RuntimeJobRepository(session).enqueue(
        kind=trigger_dispatch_worker.TRIGGER_DISPATCH_JOB_KIND,
        payload={"invocation_id": invocation_id},
        dedupe_key=f"trigger-dispatch:{invocation_id}",
        max_attempts=10,
    )
    session.commit()
    return job


def test_dispatch_failure_returns_to_queue_then_success_completes(
    db_session: Session,
    monkeypatch,
) -> None:
    job = _enqueue_dispatch(db_session)
    sends: list[str] = []

    def fail_send(invocation_id: str) -> None:
        sends.append(invocation_id)
        raise RuntimeError("broker unavailable")

    monkeypatch.setattr(trigger_invocation_worker.run_trigger_invocation, "send", fail_send)
    failed = trigger_dispatch_worker.dispatch_pending_trigger_invocations(
        session=db_session,
        limit=1,
    )

    db_session.refresh(job)
    assert failed == {"dispatched": 0, "failed": 1}
    assert sends == ["inv-1"]
    assert job.status == "queued"
    assert job.attempt == 1
    assert job.error == "broker unavailable"
    assert job.lease_owner is None
    assert job.lease_until is None

    job.available_at = utc_now() - timedelta(seconds=1)
    db_session.commit()
    monkeypatch.setattr(
        trigger_invocation_worker.run_trigger_invocation,
        "send",
        lambda invocation_id: sends.append(invocation_id),
    )
    succeeded = trigger_dispatch_worker.dispatch_pending_trigger_invocations(
        session=db_session,
        limit=1,
    )

    db_session.refresh(job)
    assert succeeded == {"dispatched": 1, "failed": 0}
    assert sends == ["inv-1", "inv-1"]
    assert job.status == "succeeded"
    assert job.attempt == 2
    assert job.result_json == {"dispatched": True}
    assert job.finished_at is not None


def test_expired_dispatch_lease_can_be_reclaimed_and_fences_stale_owner(
    db_session: Session,
) -> None:
    job = _enqueue_dispatch(db_session, invocation_id="inv-fenced")
    first_claim = trigger_dispatch_worker._claim_dispatch(db_session, owner="worker-a")
    assert first_claim is not None

    job = db_session.get(RuntimeJob, job.id)
    assert job is not None
    job.lease_until = utc_now() - timedelta(seconds=1)
    db_session.commit()
    second_claim = trigger_dispatch_worker._claim_dispatch(db_session, owner="worker-b")

    assert second_claim is not None
    assert second_claim.id == first_claim.id
    assert second_claim.lease_generation == first_claim.lease_generation + 1
    repository = RuntimeJobRepository(db_session)
    assert repository.complete(first_claim, result_json={"stale": True}) is False
    db_session.rollback()
    assert repository.complete(second_claim, result_json={"dispatched": True}) is True
    db_session.commit()

    db_session.refresh(job)
    assert job.status == "succeeded"
    assert job.lease_owner is None
    assert job.result_json == {"dispatched": True}
