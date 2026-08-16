from __future__ import annotations

from collections.abc import Callable
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


def default_runtime_job_handlers() -> dict[str, RuntimeJobHandler]:
    return {
        "agent_assignment": execute_agent_assignment,
        "subagent": execute_subagent,
        "team_runtime_tick": tick_team_runtime,
        "alert_evaluation": evaluate_alerts,
        "subagent_recovery": recover_subagents,
    }
