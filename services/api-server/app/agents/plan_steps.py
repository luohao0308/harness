from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import AgentRun, ExecutionPlan, TaskStep, utc_now

SUBAGENT_SUCCESS_STATUSES = {"SUCCESS"}
SUBAGENT_FAILURE_STATUSES = {"FAILED", "TIMEOUT", "CANCELLED", "BUDGET_EXCEEDED"}
SUBAGENT_TERMINAL_STATUSES = SUBAGENT_SUCCESS_STATUSES | SUBAGENT_FAILURE_STATUSES


def sync_subagent_plan_step(
    *,
    session: Session,
    agent_run: AgentRun,
    summary: str | None = None,
) -> TaskStep | None:
    step_key = agent_run.context_json.get("step_key")
    if not isinstance(step_key, str) or not step_key:
        return None
    if agent_run.status not in SUBAGENT_TERMINAL_STATUSES:
        return None

    plan = session.execute(
        select(ExecutionPlan)
        .where(ExecutionPlan.task_id == agent_run.task_id)
        .order_by(ExecutionPlan.version.desc())
        .limit(1)
    ).scalar_one_or_none()
    if plan is None:
        return None

    step = _plan_step(plan=plan, step_key=step_key)
    if step is None:
        return None

    step_row = session.execute(
        select(TaskStep)
        .where(
            TaskStep.task_id == agent_run.task_id,
            TaskStep.plan_id == plan.id,
            TaskStep.step_key == step_key,
        )
        .order_by(TaskStep.started_at.desc(), TaskStep.completed_at.desc(), TaskStep.id.desc())
        .limit(1)
    ).scalar_one_or_none()
    now = utc_now()
    if step_row is None:
        step_row = TaskStep(
            task_id=agent_run.task_id,
            plan_id=plan.id,
            step_key=step_key,
            description=str(step.get("description") or step_key),
            status="RUNNING",
            execution_mode=str(step.get("execution_mode") or "async"),
            assigned_agent_id=agent_run.id,
            started_at=agent_run.started_at or now,
        )
        session.add(step_row)
    elif step_row.assigned_agent_id is None:
        step_row.assigned_agent_id = agent_run.id

    if agent_run.status in SUBAGENT_SUCCESS_STATUSES:
        step_row.status = "STEP_COMPLETED"
        step_row.error_message = None
    else:
        step_row.status = "STEP_FAILED"
        step_row.error_message = summary or _subagent_error_message(agent_run.status)
    step_row.completed_at = agent_run.completed_at or now
    session.flush()
    return step_row


def _plan_step(*, plan: ExecutionPlan, step_key: str) -> dict | None:
    steps = plan.plan_json.get("steps", [])
    if not isinstance(steps, list):
        return None
    for step in steps:
        if isinstance(step, dict) and step.get("key") == step_key:
            return step
    return None


def _subagent_error_message(status: str) -> str:
    if status == "TIMEOUT":
        return "Subagent timed out"
    if status == "CANCELLED":
        return "Subagent was cancelled"
    if status == "BUDGET_EXCEEDED":
        return "Subagent budget exceeded"
    return "Subagent execution failed"
