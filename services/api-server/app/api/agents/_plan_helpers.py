"""Agent plan/run helper functions."""

# ruff: noqa: F401,F403,F405,I001,UP037
from .common import *

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
    steps = []
    for raw_step in plan.plan_json.get("steps", []):
        step_key = str(raw_step.get("key", ""))
        steps.append(
            TaskPlanStepState(
                step_key=step_key,
                description=str(raw_step.get("description", "")),
                depends_on=_string_list(raw_step.get("depends_on")),
                execution_mode=str(raw_step.get("execution_mode", "")),
                requires_sandbox=bool(raw_step.get("requires_sandbox", False)),
                can_spawn_subagent=bool(raw_step.get("can_spawn_subagent", False)),
                tool_hints=_string_list(raw_step.get("tool_hints")),
                acceptance_criteria=_string_list(raw_step.get("acceptance_criteria")),
                risk_level=str(raw_step.get("risk_level") or "low"),
                artifact_expectations=_string_list(raw_step.get("artifact_expectations")),
                quality_notes=_string_list(raw_step.get("quality_notes")),
                status="PENDING",
                assigned_agent_id=None,
                error_message=None,
                trace_summary=None,
                last_event_sequence=None,
                execution_trace=[],
            )
        )
    return TaskPlanResponse(
        id=plan.id,
        task_id=plan.task_id,
        version=plan.version,
        status=plan.status,
        summary=plan.plan_json.get("summary"),
        planner_source=str(plan.plan_json.get("planner_source", "deterministic")),
        planner_attempts=int(plan.plan_json.get("planner_attempts", 1) or 1),
        planner_prompt_version=str(plan.plan_json.get("planner_prompt_version") or "1.1.0"),
        quality_score=int(plan.plan_json.get("quality_score", 100) or 100),
        validation_warnings=_string_list(plan.plan_json.get("validation_warnings")),
        quality_gates=(
            plan.plan_json.get("quality_gates")
            if isinstance(plan.plan_json.get("quality_gates"), dict)
            else {}
        ),
        plan_json=plan.plan_json,
        steps=steps,
        created_at=plan.created_at,
    )


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
