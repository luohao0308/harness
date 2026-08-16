"""Agent plan/run helper functions."""

# ruff: noqa: F401,F403,F405,I001,UP037
from .common import *
from app.api.plan_projection import build_plan_response

def _complete_plan_prompt(*, task: Task, session: Session) -> str:
    response = AuditedModelGateway(session=session, task_id=task.id).complete(
        ModelRequest(
            model_provider=task.model_provider,
            model_name=task.model_name,
            messages=[
                ModelMessage(role="system", content=PLANNER_SYSTEM_PROMPT),
                ModelMessage(
                    role="user",
                    content=(
                        f"Agent Plan mode only. Do not execute tools.\n\n"
                        f"Task title:\n{task.title}\n\n"
                        f"Task goal:\n{task.goal}\n\n"
                        f"Max subagents: {task.max_subagents}\n"
                        f"Sandbox enabled: {task.enable_sandbox}\n"
                        f"Network enabled: {task.enable_network}"
                    ),
                ),
            ],
        )
    )
    return response.content


def _repair_plan_prompt(*, task: Task, invalid_content: str, session: Session) -> str | None:
    try:
        response = AuditedModelGateway(session=session, task_id=task.id).complete(
            ModelRequest(
                model_provider=task.model_provider,
                model_name=task.model_name,
                messages=[
                    ModelMessage(
                        role="system",
                        content=(
                            f"{PLANNER_SYSTEM_PROMPT}\nRepair the previous Planner output. "
                            "Return one valid JSON object that matches the required schema."
                        ),
                    ),
                    ModelMessage(
                        role="user",
                        content=(
                            f"Task goal:\n{task.goal}\n\nInvalid Planner output:\n{invalid_content}"
                        ),
                    ),
                ],
            )
        )
    except ModelGatewayError:
        return None
    return response.content

def _plan_response(plan: ExecutionPlan) -> TaskPlanResponse:
    return build_plan_response(plan)


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if isinstance(item, str)]


def _title_from_goal(goal: str) -> str:
    title = " ".join(goal.strip().split())
    if len(title) <= 48:
        return title or "Agent Plan"
    return title[:45] + "..."


def _owned_run(*, run_id: str, session: Session, principal: Principal) -> Task:
    run = session.execute(
        select(Task).where(
            Task.id == run_id,
            Task.organization_id == principal.organization_id,
        )
    ).scalar_one_or_none()
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent Run 未找到")
    return run


def _latest_plan(*, run_id: str, session: Session) -> ExecutionPlan | None:
    return session.execute(
        select(ExecutionPlan)
        .where(ExecutionPlan.task_id == run_id)
        .order_by(ExecutionPlan.version.desc())
        .limit(1)
    ).scalar_one_or_none()


def _latest_model_call_id(run_id: str, *, session: Session) -> str | None:
    model_call = (
        session.execute(
            select(ModelCall)
            .where(ModelCall.task_id == run_id)
            .order_by(ModelCall.created_at.desc(), ModelCall.id.desc())
        )
        .scalars()
        .first()
    )
    return model_call.id if model_call is not None else None


def _run_status(run_id: str, *, fallback: str, session: Session) -> str:
    run = session.get(Task, run_id)
    return run.status if run is not None else fallback


def _agent_plan_response_from_run(
    *,
    agent_id: str,
    run: Task,
    session: Session,
    message_prefix: str,
) -> AgentPlanResponse:
    plan = _latest_plan(run_id=run.id, session=session)
    if plan is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Agent Run 尚未规划")
    return AgentPlanResponse(
        agent_id=agent_id,
        run_id=run.id,
        task=run,
        plan=_plan_response(plan),
        message=f"{message_prefix} {run.id}，当前未执行新的规划。",
    )

__all__ = [name for name in globals() if not name.startswith("__") and name != "annotations"]
