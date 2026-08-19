from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

RuntimeJobHandler = Callable[[dict[str, Any], Session], dict[str, Any] | None]


def execute_agent_assignment(payload: dict[str, Any], session: Session) -> dict[str, Any]:
    from app.workers.agent_assignment_worker import execute_agent_assignment as execute

    status = execute(str(payload["assignment_id"]), session=session)
    return {"status": status}


def execute_subagent(payload: dict[str, Any], session: Session) -> dict[str, Any]:
    from app.workers.subagent_worker import execute_subagent as execute

    status = execute(str(payload["agent_run_id"]), session=session)
    return {"status": status}


def tick_team_runtime(_payload: dict[str, Any], session: Session) -> dict[str, Any]:
    from app.workers.team_runtime_worker import tick_active_team_goals

    return tick_active_team_goals(session=session)


def evaluate_alerts(payload: dict[str, Any], session: Session) -> dict[str, Any]:
    from app.db.models import Organization
    from app.workers.alert_evaluator import evaluate_alerts_once

    organization_id = payload.get("organization_id")
    organization_ids = (
        [organization_id]
        if organization_id is not None
        else list(session.execute(select(Organization.id).order_by(Organization.id)).scalars())
    )
    if not organization_ids:
        organization_ids = [None]
    evaluations = [
        evaluation
        for current_organization_id in organization_ids
        for evaluation in evaluate_alerts_once(
            organization_id=current_organization_id,
            session=session,
        )
    ]
    return {"evaluations": evaluations}


def recover_subagents(payload: dict[str, Any], session: Session) -> dict[str, Any]:
    from app.workers.subagent_recovery_worker import (
        DEFAULT_RECOVERY_ENQUEUE,
        DEFAULT_RECOVERY_STALE_AFTER_SECONDS,
        recover_stalled_subagents,
    )

    return recover_stalled_subagents(
        stale_after_seconds=int(
            payload.get("stale_after_seconds", DEFAULT_RECOVERY_STALE_AFTER_SECONDS)
        ),
        enqueue=bool(payload.get("enqueue", DEFAULT_RECOVERY_ENQUEUE)),
        session=session,
    )


def execute_trigger_invocation(payload: dict[str, Any], session: Session) -> dict[str, Any]:
    """Execute one persisted invocation; never create a second Run locally.

    The Trigger service is intentionally imported lazily so the local runtime
    remains importable while the service migration is being rolled out.
    """
    invocation_id = str(payload.get("invocation_id", "")).strip()
    if not invocation_id:
        raise ValueError("trigger invocation_id is required")
    from app.core.config import get_settings
    from app.db.models import Trigger, TriggerInvocation, utc_now
    from app.runtime_jobs.errors import RuntimeJobDeferredError
    from app.runtime_jobs.profile import is_local_runtime_profile

    invocation = session.get(TriggerInvocation, invocation_id)
    trigger = session.get(Trigger, invocation.trigger_id) if invocation is not None else None
    if invocation is None or trigger is None:
        raise ValueError("trigger invocation not found")
    if not is_local_runtime_profile():
        raise RuntimeError("local trigger invocation handler requires the local runtime profile")
    expires_at_raw = str(payload.get("expires_at") or "").strip()
    if expires_at_raw:
        try:
            expires_at = datetime.fromisoformat(expires_at_raw)
        except ValueError as exc:
            raise ValueError("trigger invocation expires_at is invalid") from exc
        if expires_at <= utc_now():
            now = utc_now()
            invocation.status = "FAILED"
            invocation.error = "Trigger invocation expired before execution"
            invocation.updated_at = now
            invocation.completed_at = now
            session.flush()
            return {"status": "FAILED", "reason": "expired"}
    if not bool(getattr(get_settings(), "trigger_automation_enabled", False)):
        raise RuntimeJobDeferredError("Trigger automation is paused", delay_seconds=30)
    invocation.attempt = max(invocation.attempt, int(payload.get("_runtime_attempt", 1)))
    try:
        from app.triggers.service import TriggerInvocationLeaseBusy
        from app.triggers.service import execute_trigger_invocation as execute
    except ImportError as exc:
        raise RuntimeError("trigger invocation service is unavailable") from exc
    try:
        result = execute(invocation_id=invocation_id, session=session)
    except TriggerInvocationLeaseBusy as exc:
        raise RuntimeJobDeferredError(
            "Trigger invocation execution lease is busy",
            delay_seconds=exc.retry_after_seconds,
        ) from exc
    if isinstance(result, dict):
        return result
    if hasattr(result, "status"):
        return {
            "status": str(result.status),
            "invocation_id": str(getattr(result, "id", invocation_id)),
            "run_id": getattr(result, "run_id", None),
        }
    return {"status": str(result)}


def poll_trigger_sources(payload: dict[str, Any], session: Session) -> dict[str, Any]:
    from app.workers.trigger_source_worker import poll_local_trigger_sources

    return poll_local_trigger_sources(payload, session=session)


def default_runtime_job_handlers() -> dict[str, RuntimeJobHandler]:
    return {
        "agent_assignment": execute_agent_assignment,
        "subagent": execute_subagent,
        "team_runtime_tick": tick_team_runtime,
        "alert_evaluation": evaluate_alerts,
        "subagent_recovery": recover_subagents,
        "trigger_invocation": execute_trigger_invocation,
        "trigger_source_poll": poll_trigger_sources,
    }
