from __future__ import annotations

from datetime import timedelta

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import Trigger, TriggerInvocation, utc_now
from app.db.session import SessionLocal
from app.runtime_jobs.profile import is_local_runtime_profile
from app.triggers.service import TriggerInvocationLeaseBusy, execute_trigger_invocation
from app.workers.actor_registration import register_server_actor

SERVER_TRIGGER_MAX_RETRIES = 10_000
SERVER_TRIGGER_EXPIRY = timedelta(hours=24)


def execute_server_trigger_invocation(
    invocation_id: str,
    session: Session | None = None,
) -> str:
    if session is not None:
        return _execute_with_session(invocation_id=invocation_id, session=session)
    with SessionLocal() as worker_session:
        return _execute_with_session(invocation_id=invocation_id, session=worker_session)


def _execute_with_session(*, invocation_id: str, session: Session) -> str:
    invocation = session.get(TriggerInvocation, invocation_id)
    trigger = session.get(Trigger, invocation.trigger_id) if invocation is not None else None
    if invocation is None or trigger is None or trigger.type != "webhook":
        raise ValueError("server webhook trigger invocation not found")
    if is_local_runtime_profile():
        raise RuntimeError("server trigger worker is unavailable in the local profile")
    if not get_settings().trigger_automation_enabled:
        if utc_now() - invocation.created_at >= SERVER_TRIGGER_EXPIRY:
            invocation.status = "FAILED"
            invocation.error = "Trigger invocation expired while automation was paused"
            invocation.completed_at = utc_now()
            invocation.updated_at = utc_now()
            session.commit()
            return invocation.status
        raise RuntimeError("Trigger automation is paused")

    session.info["runtime_job_step_checkpoint"] = session.commit
    try:
        result = execute_trigger_invocation(invocation_id=invocation_id, session=session)
        session.commit()
        return result.status
    except TriggerInvocationLeaseBusy:
        session.rollback()
        raise
    except Exception:
        session.rollback()
        invocation = session.get(TriggerInvocation, invocation_id)
        trigger = session.get(Trigger, invocation.trigger_id) if invocation is not None else None
        if invocation is None or trigger is None:
            raise
        max_attempts = max(1, min(int((trigger.config_json or {}).get("max_attempts", 3)), 10))
        attempt = max(1, invocation.attempt)
        invocation.error = f"Trigger execution attempt {attempt} failed"
        invocation.updated_at = utc_now()
        if attempt >= max_attempts:
            invocation.status = "FAILED"
            invocation.completed_at = utc_now()
            session.commit()
            return invocation.status
        invocation.attempt = attempt + 1
        invocation.status = "PLANNED"
        invocation.completed_at = None
        session.commit()
        raise


def run_trigger_invocation(invocation_id: str) -> None:
    execute_server_trigger_invocation(invocation_id)


if not is_local_runtime_profile():
    run_trigger_invocation = register_server_actor(
        run_trigger_invocation,
        max_retries=SERVER_TRIGGER_MAX_RETRIES,
        min_backoff=1_000,
        max_backoff=60_000,
        queue_name="triggers",
    )
