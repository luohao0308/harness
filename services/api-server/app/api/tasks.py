from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.agents.context_router import RunContextRouter
from app.agents.executor import Executor
from app.api.schemas import (
    ModelCallPage,
    ReplayRequest,
    ReplayResponse,
    RunContextResponse,
    StepResumeRequest,
    StepResumeResponse,
    TaskArtifact,
    TaskCreateRequest,
    TaskPage,
    TaskPlanDiffResponse,
    TaskPlanResponse,
    TaskPlanStepDiff,
    TaskPlanStepState,
    TaskPlanVersionPage,
    TaskPlanVersionSummary,
    TaskResponse,
    TaskResultResponse,
    TaskStepPage,
    TaskSubagentResult,
    ToolApprovalDecisionRequest,
    ToolApprovalModifyRequest,
    ToolApprovalPage,
    ToolCallPage,
    ToolCallResponse,
    ToolExecuteRequest,
    ToolExecuteResponse,
)
from app.db.models import (
    AgentEvent,
    AgentRun,
    ExecutionPlan,
    ModelCall,
    SandboxInstance,
    Task,
    TaskStep,
    ToolApproval,
    ToolCall,
    utc_now,
)
from app.db.session import get_db_session
from app.events.event_store import EventStore
from app.events.event_types import EventType
from app.events.replay import EventReplay
from app.observability.metrics import (
    agent_task_resume_total,
    agent_tasks_running,
    agent_tasks_total,
)
from app.sandbox.docker_manager import DockerManager
from app.security.auth import Principal, require_role
from app.tools.runner import ToolRunner

RUN_COMPATIBILITY_DESCRIPTION = (
    "内部兼容接口；产品主入口使用 /api/agents/{agent_id}/runs "
    "和 /api/agents/runs/*。"
)

router = APIRouter(
    prefix="/tasks",
    tags=["agent-run-compatibility"],
    deprecated=True,
)
DbSession = Annotated[Session, Depends(get_db_session)]
SUBAGENT_TERMINAL_STATUSES = {"SUCCESS", "FAILED", "TIMEOUT", "CANCELLED"}


def get_owned_task(task_id: str, session: Session, organization_id: str) -> Task:
    task = session.execute(
        select(Task).where(Task.id == task_id, Task.organization_id == organization_id)
    ).scalar_one_or_none()
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="任务未找到")
    return task


@router.post(
    "",
    response_model=TaskResponse,
    status_code=status.HTTP_201_CREATED,
    summary="兼容层：创建 Agent Run 记录",
    description=(
        f"{RUN_COMPATIBILITY_DESCRIPTION} 创建一条 Agent Run 兼容记录，"
        "并写入 TASK_CREATED 事件。"
    ),
)
def create_task(
    request: TaskCreateRequest,
    session: DbSession,
    principal: Principal,
) -> Task:
    task = Task(
        organization_id=principal.organization_id,
        created_by=principal.user_id,
        title=request.title,
        goal=request.goal,
        status="CREATED",
        model_provider=request.model_provider,
        model_name=request.model_name,
        max_runtime_seconds=request.max_runtime_seconds,
        max_subagents=request.max_subagents,
        enable_sandbox=request.enable_sandbox,
        enable_network=request.enable_network,
        created_at=utc_now(),
        updated_at=utc_now(),
    )
    session.add(task)
    session.flush()
    agent_tasks_total.inc()
    EventStore(session).append(
        task_id=task.id,
        event_type=EventType.TASK_CREATED,
        payload_json={"task_id": task.id, "title": task.title, "goal": task.goal},
    )
    session.commit()
    session.refresh(task)
    return task


@router.get(
    "",
    response_model=TaskPage,
    summary="兼容层：查询 Agent Run 列表",
    description=(
        f"{RUN_COMPATIBILITY_DESCRIPTION} 按组织查询 Agent Run 列表，"
        "支持状态过滤和分页大小。"
    ),
)
def list_tasks(
    session: DbSession,
    principal: Principal,
    status_filter: Annotated[str | None, Query(alias="status")] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> TaskPage:
    statement = select(Task).where(Task.organization_id == principal.organization_id)
    if status_filter is not None:
        statement = statement.where(Task.status == status_filter)
    statement = statement.order_by(Task.created_at.desc()).limit(limit)
    tasks = list(session.execute(statement).scalars())
    return TaskPage(items=tasks)


@router.get(
    "/{task_id}",
    response_model=TaskResponse,
    summary="兼容层：查询 Agent Run 详情",
    description=f"{RUN_COMPATIBILITY_DESCRIPTION} 返回指定 Agent Run 的完整基础信息。",
)
def get_task(task_id: str, session: DbSession, principal: Principal) -> Task:
    return get_owned_task(task_id, session, principal.organization_id)


@router.post(
    "/{task_id}/start",
    response_model=TaskResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="兼容层：启动 Agent Run",
    description=f"{RUN_COMPATIBILITY_DESCRIPTION} 将 CREATED 或 FAILED Agent Run 启动为运行态。",
)
def start_task(task_id: str, session: DbSession, principal: Principal) -> Task:
    task = get_owned_task(task_id, session, principal.organization_id)
    if task.status not in {"CREATED", "FAILED"}:
        plan_exists = session.execute(
            select(ExecutionPlan.id)
            .where(ExecutionPlan.task_id == task.id)
            .limit(1)
        ).scalar_one_or_none()
        # Workspace chat/markdown_plan can produce a COMPLETED run without a plan DAG.
        # Allow one-way promotion into full Harness execution on the same run identity.
        if not (task.status == "COMPLETED" and plan_exists is None):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="任务无法启动")

    started = Executor(session).start_task(task)
    if started.status == "RUNNING":
        agent_tasks_running.inc()
    session.commit()
    session.refresh(started)
    return started


@router.post(
    "/{task_id}/cancel",
    response_model=TaskResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="兼容层：取消 Agent Run",
    description=(
        f"{RUN_COMPATIBILITY_DESCRIPTION} 将当前 Agent Run 状态切换为 CANCELLED，"
        "并写入 TASK_CANCELLED 事件。"
    ),
)
def cancel_task(task_id: str, session: DbSession, principal: Principal) -> Task:
    task = get_owned_task(task_id, session, principal.organization_id)
    if task.status not in {"CREATED", "PLANNING", "RUNNING", "WAITING_SUBAGENTS", "FAILED"}:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="任务无法取消")

    task.status = "CANCELLED"
    task.updated_at = utc_now()
    task.completed_at = utc_now()
    EventStore(session).append(
        task_id=task.id,
        event_type=EventType.TASK_CANCELLED,
        payload_json={"task_id": task.id, "cancelled_by": principal.user_id},
        actor_type="user",
        actor_id=principal.user_id,
    )
    session.commit()
    session.refresh(task)
    return task


@router.post(
    "/{task_id}/resume",
    response_model=TaskResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="兼容层：恢复 Agent Run",
    description=(
        f"{RUN_COMPATIBILITY_DESCRIPTION} 将 FAILED 或 CANCELLED Agent Run 恢复为 RUNNING，"
        "并写入 TASK_RESUMED 事件。"
    ),
)
def resume_task(task_id: str, session: DbSession, principal: Principal) -> Task:
    task = get_owned_task(task_id, session, principal.organization_id)
    if task.status not in {"FAILED", "CANCELLED"}:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="任务无法恢复")

    task.status = "RUNNING"
    task.updated_at = utc_now()
    task.completed_at = None
    EventStore(session).append(
        task_id=task.id,
        event_type=EventType.TASK_RESUMED,
        payload_json={"task_id": task.id, "resumed_by": principal.user_id},
        actor_type="user",
        actor_id=principal.user_id,
    )
    agent_task_resume_total.inc()
    resumed = Executor(session).resume_task(task)
    session.commit()
    session.refresh(resumed)
    return resumed


@router.post(
    "/{task_id}/steps/resume",
    response_model=StepResumeResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="兼容层：从指定步骤续跑 Agent Run",
    description=(
        f"{RUN_COMPATIBILITY_DESCRIPTION} 将 FAILED 或 CANCELLED Agent Run 按最新执行计划恢复，"
        "从请求中最靠前的步骤键开始续跑，已完成步骤写入 STEP_SKIPPED。"
    ),
)
def resume_task_steps(
    task_id: str,
    request: StepResumeRequest,
    session: DbSession,
    principal: Principal,
) -> StepResumeResponse:
    task = get_owned_task(task_id, session, principal.organization_id)
    if task.status not in {"FAILED", "CANCELLED"}:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="任务步骤无法续跑")
    plan = _latest_plan(task_id=task_id, session=session)
    if plan is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="执行计划未找到")
    requested_step_keys = list(dict.fromkeys(request.step_keys))
    plan_step_keys = [
        str(raw_step.get("key", ""))
        for raw_step in plan.plan_json.get("steps", [])
        if isinstance(raw_step, dict)
    ]
    plan_step_key_set = set(plan_step_keys)
    unknown_step_keys = [
        step_key for step_key in requested_step_keys if step_key not in plan_step_key_set
    ]
    if unknown_step_keys:
        raise HTTPException(
            status_code=422,
            detail={"message": "步骤键不存在", "unknown_step_keys": unknown_step_keys},
        )

    EventStore(session).append(
        task_id=task.id,
        event_type=EventType.TASK_RESUMED,
        payload_json={
            "task_id": task.id,
            "resumed_by": principal.user_id,
            "resume_mode": request.resume_mode,
            "requested_step_keys": requested_step_keys,
        },
        actor_type="user",
        actor_id=principal.user_id,
    )
    agent_task_resume_total.inc()
    outcome = Executor(session).resume_steps(
        task,
        step_keys=requested_step_keys,
        resume_mode=request.resume_mode,
    )
    session.commit()
    session.refresh(outcome.task)
    return StepResumeResponse(
        task_id=outcome.task.id,
        status=outcome.task.status,
        plan_id=outcome.plan_id,
        resume_mode=outcome.resume_mode,
        resume_from_step_key=outcome.resume_from_step_key,
        requested_step_keys=outcome.requested_step_keys,
        skipped_step_keys=outcome.skipped_step_keys,
        resumed_step_keys=outcome.resumed_step_keys,
        completed_step_keys=outcome.completed_step_keys,
        pending_step_keys=outcome.pending_step_keys,
        failed_step_key=outcome.failed_step_key,
        error_message=outcome.error_message,
        last_sequence=outcome.last_sequence,
    )


@router.get(
    "/{task_id}/result",
    response_model=TaskResultResponse,
    summary="兼容层：查询 Agent Run 结果",
    description=(
        f"{RUN_COMPATIBILITY_DESCRIPTION} 返回 Agent Run 状态、摘要、执行计划、"
        "产物列表和最后事件序号。"
    ),
)
def get_task_result(task_id: str, session: DbSession, principal: Principal) -> TaskResultResponse:
    task = get_owned_task(task_id, session, principal.organization_id)
    plan = session.execute(
        select(ExecutionPlan)
        .where(ExecutionPlan.task_id == task.id)
        .order_by(ExecutionPlan.version.desc())
        .limit(1)
    ).scalar_one_or_none()
    last_sequence = session.execute(
        select(func.max(AgentEvent.sequence)).where(AgentEvent.task_id == task.id)
    ).scalar_one_or_none()
    artifacts = [
        TaskArtifact(
            name="result.md",
            artifact_type="markdown",
            description="最终任务结果",
            status="ready" if task.status == "COMPLETED" else "pending",
        )
    ]
    subagent_runs = list(
        session.execute(
            select(AgentRun)
            .where(AgentRun.task_id == task.id, AgentRun.agent_type == "subagent")
            .order_by(AgentRun.started_at.asc(), AgentRun.id.asc())
        ).scalars()
    )
    subagent_results = [_to_subagent_result(agent_run) for agent_run in subagent_runs]
    if subagent_runs:
        artifacts.append(
            TaskArtifact(
                name="subagent-results.json",
                artifact_type="json",
                description="异步子 Agent 结果聚合",
                status=(
                    "ready"
                    if all(run.status in SUBAGENT_TERMINAL_STATUSES for run in subagent_runs)
                    else "pending"
                ),
            )
        )
    for subagent_result in subagent_results:
        for artifact in subagent_result.artifacts:
            prefix = subagent_result.step_key or subagent_result.id[:8]
            artifacts.append(
                TaskArtifact(
                    name=f"{prefix}/{artifact.name}",
                    artifact_type=artifact.artifact_type,
                    description=f"子 Agent 产物：{artifact.description}",
                    status=artifact.status,
                )
            )
    summary_parts = []
    if task.status == "COMPLETED":
        summary_parts.append(f"任务《{task.title}》已完成。")
    if task.status == "FAILED":
        summary_parts.append(f"任务《{task.title}》已失败。")
    subagent_summary = _subagent_result_summary(subagent_results)
    if subagent_summary is not None:
        summary_parts.append(subagent_summary)
    return TaskResultResponse(
        task_id=task.id,
        status=task.status,
        summary=" ".join(summary_parts) if summary_parts else None,
        execution_plan=plan.plan_json if plan is not None else None,
        artifacts=artifacts,
        subagent_results=subagent_results,
        last_sequence=last_sequence or 0,
        pending=task.status not in {"COMPLETED", "FAILED", "CANCELLED"},
    )


@router.get(
    "/{task_id}/plan",
    response_model=TaskPlanResponse,
    summary="兼容层：查询 Agent Run Plan",
    description=(
        f"{RUN_COMPATIBILITY_DESCRIPTION} 返回 Agent Run 最新执行计划，"
        "并合并已落库步骤的当前状态。"
    ),
)
def get_task_plan(task_id: str, session: DbSession, principal: Principal) -> TaskPlanResponse:
    get_owned_task(task_id, session, principal.organization_id)
    plan = _latest_plan(task_id=task_id, session=session)
    if plan is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="执行计划未找到")
    step_rows = {
        step.step_key: step
        for step in session.execute(
            select(TaskStep)
            .where(TaskStep.task_id == task_id, TaskStep.plan_id == plan.id)
            .order_by(TaskStep.started_at.asc(), TaskStep.completed_at.asc(), TaskStep.id.asc())
        ).scalars()
    }
    step_events = _step_events_by_key(task_id=task_id, session=session)
    steps = []
    for raw_step in plan.plan_json.get("steps", []):
        step_key = str(raw_step.get("key", ""))
        step_row = step_rows.get(step_key)
        execution_trace = step_events.get(step_key, [])
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
                status=step_row.status if step_row is not None else "PENDING",
                assigned_agent_id=step_row.assigned_agent_id if step_row is not None else None,
                error_message=step_row.error_message if step_row is not None else None,
                trace_summary=_last_trace_summary(execution_trace),
                last_event_sequence=(
                    int(execution_trace[-1]["sequence"]) if execution_trace else None
                ),
                execution_trace=execution_trace,
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
        planner_prompt_version=str(
            plan.plan_json.get("planner_prompt_version") or "1.1.0"
        ),
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


@router.get(
    "/{task_id}/plans",
    response_model=TaskPlanVersionPage,
    summary="兼容层：查询 Agent Run Plan 版本",
    description=(
        f"{RUN_COMPATIBILITY_DESCRIPTION} 返回 Agent Run 全部执行计划版本，"
        "用于计划变更对比。"
    ),
)
def list_task_plan_versions(
    task_id: str,
    session: DbSession,
    principal: Principal,
) -> TaskPlanVersionPage:
    get_owned_task(task_id, session, principal.organization_id)
    plans = list(
        session.execute(
            select(ExecutionPlan)
            .where(ExecutionPlan.task_id == task_id)
            .order_by(ExecutionPlan.version.desc())
        ).scalars()
    )
    return TaskPlanVersionPage(items=[_plan_version_summary(plan) for plan in plans])


@router.get(
    "/{task_id}/plans/diff",
    response_model=TaskPlanDiffResponse,
    summary="兼容层：对比 Agent Run Plan 版本",
    description=(
        f"{RUN_COMPATIBILITY_DESCRIPTION} 按两个 Agent Run 计划版本对比步骤新增、"
        "移除和变更。"
    ),
)
def diff_task_plan_versions(
    task_id: str,
    from_version: Annotated[int, Query(ge=1)],
    to_version: Annotated[int, Query(ge=1)],
    session: DbSession,
    principal: Principal,
) -> TaskPlanDiffResponse:
    get_owned_task(task_id, session, principal.organization_id)
    from_plan = _plan_by_version(task_id=task_id, version=from_version, session=session)
    to_plan = _plan_by_version(task_id=task_id, version=to_version, session=session)
    if from_plan is None or to_plan is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="计划版本未找到")
    return _plan_diff_response(task_id=task_id, from_plan=from_plan, to_plan=to_plan)


@router.get(
    "/{task_id}/steps",
    response_model=TaskStepPage,
    summary="兼容层：查询 Agent Run 步骤",
    description=f"{RUN_COMPATIBILITY_DESCRIPTION} 返回 Agent Run 已执行或已派生的步骤状态列表。",
)
def list_task_steps(task_id: str, session: DbSession, principal: Principal) -> TaskStepPage:
    get_owned_task(task_id, session, principal.organization_id)
    steps = list(
        session.execute(
            select(TaskStep).where(TaskStep.task_id == task_id).order_by(TaskStep.started_at.asc())
        ).scalars()
    )
    return TaskStepPage(items=steps)


@router.post(
    "/{task_id}/replay",
    response_model=ReplayResponse,
    summary="兼容层：Replay Agent Run",
    description=(
        f"{RUN_COMPATIBILITY_DESCRIPTION} 根据事件流和快照重放 Agent Run 状态，"
        "返回故障点和诊断摘要。"
    ),
)
def replay_task(
    task_id: str,
    request: ReplayRequest,
    session: DbSession,
    principal: Principal,
) -> ReplayResponse:
    get_owned_task(task_id, session, principal.organization_id)
    replay = EventReplay(session).replay_task(task_id=task_id, sequence=request.sequence)
    return ReplayResponse(
        task_id=replay.task_id,
        sequence=replay.sequence,
        state_summary=replay.state_summary,
        failure_point=replay.failure_point,
        diagnosis=replay.diagnosis,
        requires_manual_review=replay.requires_manual_review,
    )


@router.get(
    "/{task_id}/context",
    response_model=RunContextResponse,
    summary="兼容层：查询 Agent Run 记忆与模型路由",
    description=(
        f"{RUN_COMPATIBILITY_DESCRIPTION} 返回工作记忆、产物记忆、Trace 压缩"
        "和模型路由投影；本接口不写事件。"
    ),
)
def get_task_context(task_id: str, session: DbSession, principal: Principal) -> dict:
    task = get_owned_task(task_id, session, principal.organization_id)
    return RunContextRouter(session).build(task=task)


@router.post(
    "/{task_id}/context/route",
    response_model=RunContextResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="兼容层：刷新 Agent Run 上下文路由",
    description=(
        f"{RUN_COMPATIBILITY_DESCRIPTION} 重新生成上下文压缩和模型路由决策，"
        "并写入 CONTEXT_COMPRESSED / MODEL_ROUTED 事件。"
    ),
)
def route_task_context(task_id: str, session: DbSession, principal: Principal) -> dict:
    task = get_owned_task(task_id, session, principal.organization_id)
    context = RunContextRouter(session).build(
        task=task,
        persist_events=True,
        actor_id=principal.user_id,
    )
    session.commit()
    return context


@router.get(
    "/{task_id}/model-calls",
    response_model=ModelCallPage,
    summary="兼容层：查询模型调用",
    description=f"{RUN_COMPATIBILITY_DESCRIPTION} 返回当前 Agent Run 关联的模型调用审计列表。",
)
def list_model_calls(task_id: str, session: DbSession, principal: Principal) -> ModelCallPage:
    get_owned_task(task_id, session, principal.organization_id)
    calls = list(
        session.execute(
            select(ModelCall)
            .where(ModelCall.task_id == task_id)
            .order_by(ModelCall.created_at.desc())
        ).scalars()
    )
    trace_ids = _model_call_trace_ids(
        task_id=task_id,
        model_call_ids=[call.id for call in calls],
        session=session,
    )
    return ModelCallPage(
        items=[
            _to_model_call_response(call, trace_id=trace_ids.get(call.id))
            for call in calls
        ]
    )


@router.get(
    "/{task_id}/tool-calls",
    response_model=ToolCallPage,
    summary="兼容层：查询工具调用",
    description=f"{RUN_COMPATIBILITY_DESCRIPTION} 返回当前 Agent Run 关联的工具调用审计列表。",
)
def list_tool_calls(
    task_id: str,
    session: DbSession,
    principal: Principal,
    tool_name: str | None = Query(default=None, description="工具名称，支持包含匹配"),
    status_filter: str | None = Query(default=None, alias="status", description="调用状态"),
    risk_level: str | None = Query(default=None, description="风险等级"),
    trace_id: str | None = Query(default=None, description="Trace ID"),
    limit: int = Query(default=100, ge=1, le=500, description="返回数量"),
) -> ToolCallPage:
    get_owned_task(task_id, session, principal.organization_id)
    statement = select(ToolCall).where(ToolCall.task_id == task_id)
    if tool_name is not None:
        statement = statement.where(ToolCall.tool_name.ilike(f"%{tool_name}%"))
    if status_filter is not None:
        statement = statement.where(ToolCall.status == status_filter)
    if risk_level is not None:
        statement = statement.where(ToolCall.risk_level == risk_level)
    if trace_id is not None:
        tool_call_ids = _tool_call_ids_for_trace(
            task_id=task_id,
            trace_id=trace_id,
            session=session,
        )
        if not tool_call_ids:
            return ToolCallPage(items=[])
        statement = statement.where(ToolCall.id.in_(tool_call_ids))
    calls = list(
        session.execute(statement.order_by(ToolCall.created_at.desc()).limit(limit)).scalars()
    )
    trace_ids = _tool_call_trace_ids(
        task_id=task_id,
        tool_call_ids=[call.id for call in calls],
        session=session,
    )
    return ToolCallPage(
        items=[
            _to_tool_call_response(call, trace_id=trace_ids.get(call.id))
            for call in calls
        ]
    )


@router.post(
    "/{task_id}/tools/execute",
    response_model=ToolExecuteResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="兼容层：执行工具",
    description=(
        f"{RUN_COMPATIBILITY_DESCRIPTION} 按工具注册表和策略执行工具，"
        "并写入工具调用审计与事件流。"
    ),
)
def execute_task_tool(
    task_id: str,
    request: ToolExecuteRequest,
    session: DbSession,
    principal: Principal,
) -> ToolExecuteResponse:
    task = get_owned_task(task_id, session, principal.organization_id)
    sandbox = _resolve_tool_sandbox(
        task=task,
        request=request,
        session=session,
    )
    execution = ToolRunner(
        session=session,
        workspace_root=Path(__file__).resolve().parents[2],
    ).execute(
        task_id=task.id,
        tool_name=request.tool_name,
        input_json=request.input_json,
        roles=principal.roles,
        sandbox=sandbox,
    )
    session.commit()
    session.refresh(execution.tool_call)
    return ToolExecuteResponse(
        tool_call=_to_tool_call_response(execution.tool_call),
        allowed=execution.allowed,
        output=execution.output,
    )


@router.get(
    "/{task_id}/tool-approvals",
    response_model=ToolApprovalPage,
    summary="兼容层：查询工具审批",
    description=f"{RUN_COMPATIBILITY_DESCRIPTION} 返回当前 Agent Run 的工具审批请求。",
)
def list_task_tool_approvals(
    task_id: str,
    session: DbSession,
    principal: Principal,
    status_filter: Annotated[str | None, Query(alias="status")] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> ToolApprovalPage:
    task = get_owned_task(task_id, session, principal.organization_id)
    statement = select(ToolApproval).where(ToolApproval.task_id == task.id)
    if status_filter is not None:
        statement = statement.where(ToolApproval.status == status_filter)
    approvals = list(
        session.execute(statement.order_by(ToolApproval.created_at.desc()).limit(limit)).scalars()
    )
    return ToolApprovalPage(items=approvals)


@router.post(
    "/{task_id}/tool-approvals/{approval_id}/approve",
    response_model=ToolApprovalPage,
    status_code=status.HTTP_202_ACCEPTED,
    summary="兼容层：批准工具审批",
    description=(
        f"{RUN_COMPATIBILITY_DESCRIPTION} 仅 admin 可批准高风险工具调用，"
        "本接口更新审批和 ToolCall 状态并写入事件。"
    ),
)
def approve_tool_approval(
    task_id: str,
    approval_id: str,
    request: ToolApprovalDecisionRequest,
    session: DbSession,
    principal: Principal,
) -> ToolApprovalPage:
    return _decide_tool_approval(
        task_id=task_id,
        approval_id=approval_id,
        decision="APPROVED",
        request=request,
        session=session,
        principal=principal,
    )


@router.post(
    "/{task_id}/tool-approvals/{approval_id}/reject",
    response_model=ToolApprovalPage,
    status_code=status.HTTP_202_ACCEPTED,
    summary="兼容层：拒绝工具审批",
    description=(
        f"{RUN_COMPATIBILITY_DESCRIPTION} 仅 admin 可拒绝高风险工具调用，"
        "本接口更新审批和 ToolCall 状态并写入事件。"
    ),
)
def reject_tool_approval(
    task_id: str,
    approval_id: str,
    request: ToolApprovalDecisionRequest,
    session: DbSession,
    principal: Principal,
) -> ToolApprovalPage:
    return _decide_tool_approval(
        task_id=task_id,
        approval_id=approval_id,
        decision="REJECTED",
        request=request,
        session=session,
        principal=principal,
    )


@router.post(
    "/{task_id}/tool-approvals/{approval_id}/modify",
    response_model=ToolApprovalPage,
    status_code=status.HTTP_202_ACCEPTED,
    summary="兼容层：修改并批准工具审批",
    description=(
        f"{RUN_COMPATIBILITY_DESCRIPTION} 仅 admin 可修改高风险工具输入并批准，"
        "本接口会同步更新审批 request_json、ToolCall input_json 和审批事件。"
    ),
)
def modify_tool_approval(
    task_id: str,
    approval_id: str,
    request: ToolApprovalModifyRequest,
    session: DbSession,
    principal: Principal,
) -> ToolApprovalPage:
    return _decide_tool_approval(
        task_id=task_id,
        approval_id=approval_id,
        decision="APPROVED",
        request=ToolApprovalDecisionRequest(reason=request.reason),
        session=session,
        principal=principal,
        modified_input_json=request.modified_input_json,
    )


def _to_model_call_response(
    model_call: ModelCall,
    trace_id: str | None = None,
):
    return {
        "id": model_call.id,
        "task_id": model_call.task_id,
        "agent_run_id": model_call.agent_run_id,
        "trace_id": trace_id,
        "model_provider": model_call.model_provider,
        "model_name": model_call.model_name,
        "status": model_call.status,
        "prompt_tokens": model_call.prompt_tokens,
        "completion_tokens": model_call.completion_tokens,
        "duration_ms": model_call.duration_ms,
        "grounding_correlation_id": model_call.grounding_correlation_id,
        "prompt_manifest_id": model_call.prompt_manifest_id,
        "context_manifest_id": model_call.context_manifest_id,
        "model_request_sha256": model_call.model_request_sha256,
        "attempt_index": model_call.attempt_index,
        "terminal_status": model_call.terminal_status,
        "request_json": model_call.request_json,
        "response_json": model_call.response_json,
        "error_message": model_call.error_message,
        "created_at": model_call.created_at,
    }


def _decide_tool_approval(
    *,
    task_id: str,
    approval_id: str,
    decision: str,
    request: ToolApprovalDecisionRequest,
    session: Session,
    principal,
    modified_input_json: dict | None = None,
) -> ToolApprovalPage:
    require_role(principal, {"admin"})
    task = get_owned_task(task_id, session, principal.organization_id)
    approval = session.execute(
        select(ToolApproval).where(
            ToolApproval.id == approval_id,
            ToolApproval.task_id == task.id,
            ToolApproval.organization_id == principal.organization_id,
        )
    ).scalar_one_or_none()
    if approval is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="工具审批未找到")
    if approval.status != "PENDING":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="工具审批已处理")
    tool_call = session.get(ToolCall, approval.tool_call_id)
    if tool_call is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="工具调用未找到")

    if modified_input_json is not None:
        request_json = approval.request_json if isinstance(approval.request_json, dict) else {}
        approval.request_json = {
            **request_json,
            "input_json": modified_input_json,
            "modified": True,
        }
        tool_call.input_json = modified_input_json

    approval.status = decision
    approval.decided_by = principal.user_id
    approval.decided_at = utc_now()
    approval.decision_json = {
        "reason": request.reason,
        "decision": decision,
        "modified": modified_input_json is not None,
    }
    tool_call.status = "APPROVED" if decision == "APPROVED" else "DENIED"
    tool_call.error_message = None if decision == "APPROVED" else request.reason or approval.reason
    event_type = (
        EventType.TOOL_APPROVAL_APPROVED
        if decision == "APPROVED"
        else EventType.TOOL_APPROVAL_REJECTED
    )
    EventStore(session).append(
        task_id=task.id,
        event_type=event_type,
        payload_json={
            "tool_approval_id": approval.id,
            "tool_call_id": tool_call.id,
            "tool_name": tool_call.tool_name,
            "decision": decision,
            "reason": request.reason,
            "modified": modified_input_json is not None,
        },
        actor_type="user",
        actor_id=principal.user_id,
    )
    session.commit()
    approvals = list(
        session.execute(
            select(ToolApproval)
            .where(ToolApproval.task_id == task.id)
            .order_by(ToolApproval.created_at.desc())
        ).scalars()
    )
    return ToolApprovalPage(items=approvals)


def _model_call_trace_ids(
    *,
    task_id: str,
    model_call_ids: list[str],
    session: Session,
) -> dict[str, str]:
    if not model_call_ids:
        return {}
    events = session.execute(
        select(AgentEvent).where(
            AgentEvent.task_id == task_id,
            AgentEvent.event_type.in_(
                [
                    EventType.MODEL_CALLED.value,
                    EventType.MODEL_RESPONSE_RECEIVED.value,
                    EventType.MODEL_CALL_FAILED.value,
                ]
            ),
        )
    ).scalars()
    trace_ids: dict[str, str] = {}
    model_call_id_set = set(model_call_ids)
    for event in events:
        model_call_id = event.payload_json.get("model_call_id")
        if (
            isinstance(model_call_id, str)
            and model_call_id in model_call_id_set
            and isinstance(event.trace_id, str)
            and model_call_id not in trace_ids
        ):
            trace_ids[model_call_id] = event.trace_id
    return trace_ids


def _to_tool_call_response(tool_call: ToolCall, trace_id: str | None = None) -> ToolCallResponse:
    return ToolCallResponse(
        id=tool_call.id,
        task_id=tool_call.task_id,
        agent_run_id=tool_call.agent_run_id,
        trace_id=trace_id,
        tool_name=tool_call.tool_name,
        status=tool_call.status,
        risk_level=tool_call.risk_level,
        requires_sandbox=tool_call.requires_sandbox,
        sandbox_id=tool_call.sandbox_id,
        duration_ms=tool_call.duration_ms,
        input_json=tool_call.input_json,
        output_json=tool_call.output_json,
        output_kind=_tool_output_kind(tool_call),
        output_summary=_tool_output_summary(tool_call),
        timeout_category=_tool_timeout_category(tool_call),
        error_message=tool_call.error_message,
        created_at=tool_call.created_at,
    )


def _tool_call_ids_for_trace(*, task_id: str, trace_id: str, session: Session) -> set[str]:
    events = session.execute(
        select(AgentEvent).where(
            AgentEvent.task_id == task_id,
            AgentEvent.trace_id == trace_id,
            AgentEvent.event_type.in_(
                [
                    EventType.TOOL_CALLED.value,
                    EventType.TOOL_RESULT_RECEIVED.value,
                    EventType.TOOL_FAILED.value,
                    EventType.TOOL_TIMEOUT.value,
                    EventType.TOOL_DENIED_BY_POLICY.value,
                ]
            ),
        )
    ).scalars()
    tool_call_ids: set[str] = set()
    for event in events:
        tool_call_id = event.payload_json.get("tool_call_id")
        if isinstance(tool_call_id, str):
            tool_call_ids.add(tool_call_id)
    return tool_call_ids


def _tool_call_trace_ids(
    *,
    task_id: str,
    tool_call_ids: list[str],
    session: Session,
) -> dict[str, str]:
    if not tool_call_ids:
        return {}
    events = session.execute(
        select(AgentEvent).where(
            AgentEvent.task_id == task_id,
            AgentEvent.event_type.in_(
                [
                    EventType.TOOL_CALLED.value,
                    EventType.TOOL_RESULT_RECEIVED.value,
                    EventType.TOOL_FAILED.value,
                    EventType.TOOL_TIMEOUT.value,
                    EventType.TOOL_DENIED_BY_POLICY.value,
                ]
            ),
        )
    ).scalars()
    trace_ids: dict[str, str] = {}
    tool_call_id_set = set(tool_call_ids)
    for event in events:
        tool_call_id = event.payload_json.get("tool_call_id")
        if (
            isinstance(tool_call_id, str)
            and tool_call_id in tool_call_id_set
            and isinstance(event.trace_id, str)
            and tool_call_id not in trace_ids
        ):
            trace_ids[tool_call_id] = event.trace_id
    return trace_ids


def _tool_output_kind(tool_call: ToolCall) -> str:
    output = tool_call.output_json if isinstance(tool_call.output_json, dict) else {}
    if tool_call.status == "DENIED":
        return "policy_denied"
    if tool_call.status == "TIMEOUT":
        return "timeout"
    if "content" in output:
        return "file_content"
    if "files" in output:
        return "file_list"
    if "exit_code" in output:
        return "shell_result"
    if "status_code" in output:
        return "http_response"
    if "path" in output and "bytes_written" in output:
        return "file_write"
    if tool_call.status == "FAILED":
        return "error"
    return "empty" if not output else "json"


def _tool_output_summary(tool_call: ToolCall) -> str:
    output = tool_call.output_json if isinstance(tool_call.output_json, dict) else {}
    if tool_call.error_message and tool_call.status in {"DENIED", "FAILED", "TIMEOUT"}:
        return tool_call.error_message[:300]
    if "content" in output:
        content = str(output.get("content") or "")
        size_bytes = output.get("size_bytes")
        return f"文件内容 {len(content)} 字符，{size_bytes or 0} bytes"
    if "files" in output and isinstance(output.get("files"), list):
        return f"文件列表 {len(output['files'])} 项"
    if "exit_code" in output:
        stdout = str(output.get("stdout_preview") or "")
        stderr = str(output.get("stderr_preview") or "")
        return (
            f"命令退出码 {output.get('exit_code')}，"
            f"stdout {len(stdout)} 字符，stderr {len(stderr)} 字符"
        )
    if "status_code" in output:
        body = str(output.get("body_preview") or "")
        return f"HTTP {output.get('status_code')}，响应预览 {len(body)} 字符"
    if "path" in output and "bytes_written" in output:
        return f"写入 {output.get('path')}，{output.get('bytes_written')} bytes"
    if not output:
        return "无输出"
    return f"JSON 输出字段 {len(output)} 个"


def _tool_timeout_category(tool_call: ToolCall) -> str | None:
    if tool_call.status != "TIMEOUT":
        return None
    message = (tool_call.error_message or "").lower()
    if "sandbox command timed out" in message:
        return "sandbox_command_timeout"
    if "timed out" in message or "timeout" in message:
        return "tool_timeout"
    return "unknown_timeout"


def _latest_plan(task_id: str, session: Session) -> ExecutionPlan | None:
    return session.execute(
        select(ExecutionPlan)
        .where(ExecutionPlan.task_id == task_id)
        .order_by(ExecutionPlan.version.desc())
        .limit(1)
    ).scalar_one_or_none()


def _plan_by_version(
    *,
    task_id: str,
    version: int,
    session: Session,
) -> ExecutionPlan | None:
    return session.execute(
        select(ExecutionPlan).where(
            ExecutionPlan.task_id == task_id,
            ExecutionPlan.version == version,
        )
    ).scalar_one_or_none()


def _plan_version_summary(plan: ExecutionPlan) -> TaskPlanVersionSummary:
    steps = plan.plan_json.get("steps", [])
    return TaskPlanVersionSummary(
        id=plan.id,
        task_id=plan.task_id,
        version=plan.version,
        status=plan.status,
        summary=plan.plan_json.get("summary"),
        planner_source=str(plan.plan_json.get("planner_source", "deterministic")),
        planner_attempts=int(plan.plan_json.get("planner_attempts", 1) or 1),
        step_count=len(steps) if isinstance(steps, list) else 0,
        created_at=plan.created_at,
    )


def _string_list(value: object) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value if str(item)]
    if isinstance(value, str) and value:
        return [value]
    return []


def _step_events_by_key(*, task_id: str, session: Session) -> dict[str, list[dict]]:
    events = session.execute(
        select(AgentEvent)
        .where(
            AgentEvent.task_id == task_id,
            AgentEvent.event_type.in_(
                [
                    EventType.STEP_STARTED.value,
                    EventType.STEP_COMPLETED.value,
                    EventType.STEP_FAILED.value,
                    EventType.STEP_RETRIED.value,
                    EventType.STEP_SKIPPED.value,
                ]
            ),
        )
        .order_by(AgentEvent.sequence.asc())
    ).scalars()
    grouped: dict[str, list[dict]] = {}
    for event in events:
        step_key = event.payload_json.get("step_key")
        if not isinstance(step_key, str) or not step_key:
            continue
        grouped.setdefault(step_key, []).append(
            {
                "sequence": event.sequence,
                "event_type": event.event_type,
                "trace_id": event.trace_id,
                "summary": event.payload_json.get("trace_summary")
                or event.payload_json.get("summary"),
                "payload_json": event.payload_json,
                "created_at": event.created_at.isoformat(),
            }
        )
    return grouped


def _last_trace_summary(execution_trace: list[dict]) -> str | None:
    for item in reversed(execution_trace):
        summary = item.get("summary")
        if isinstance(summary, str) and summary:
            return summary
    return None


def _plan_diff_response(
    *,
    task_id: str,
    from_plan: ExecutionPlan,
    to_plan: ExecutionPlan,
) -> TaskPlanDiffResponse:
    from_steps = _steps_by_key(from_plan.plan_json)
    to_steps = _steps_by_key(to_plan.plan_json)
    step_diffs = []
    for step_key in sorted(set(from_steps) | set(to_steps)):
        from_step = from_steps.get(step_key)
        to_step = to_steps.get(step_key)
        if from_step is None:
            change_type = "added"
        elif to_step is None:
            change_type = "removed"
        elif _normalized_step(from_step) != _normalized_step(to_step):
            change_type = "changed"
        else:
            change_type = "unchanged"
        step_diffs.append(
            TaskPlanStepDiff(
                step_key=step_key,
                change_type=change_type,
                from_step=from_step,
                to_step=to_step,
            )
        )
    counts = {key: 0 for key in ["added", "removed", "changed", "unchanged"]}
    for diff in step_diffs:
        counts[diff.change_type] += 1
    return TaskPlanDiffResponse(
        task_id=task_id,
        from_version=from_plan.version,
        to_version=to_plan.version,
        added=counts["added"],
        removed=counts["removed"],
        changed=counts["changed"],
        unchanged=counts["unchanged"],
        step_diffs=step_diffs,
    )


def _steps_by_key(plan_json: dict) -> dict[str, dict]:
    steps = plan_json.get("steps", [])
    if not isinstance(steps, list):
        return {}
    result = {}
    for step in steps:
        if not isinstance(step, dict):
            continue
        step_key = step.get("key") or step.get("step_key")
        if isinstance(step_key, str) and step_key:
            result[step_key] = step
    return result


def _normalized_step(step: dict) -> dict:
    return {
        "description": step.get("description"),
        "execution_mode": step.get("execution_mode"),
        "requires_sandbox": bool(step.get("requires_sandbox", False)),
        "can_spawn_subagent": bool(step.get("can_spawn_subagent", False)),
    }


def _to_subagent_result(agent_run: AgentRun) -> TaskSubagentResult:
    result = agent_run.context_json.get("result")
    summary = None
    tool_results = []
    react_trace = []
    context_summary = {}
    if isinstance(result, dict):
        raw_summary = result.get("summary")
        if raw_summary is not None:
            summary = str(raw_summary)
        raw_tool_results = result.get("tool_results", [])
        if isinstance(raw_tool_results, list):
            tool_results = [item for item in raw_tool_results if isinstance(item, dict)]
        raw_react_trace = result.get("react_trace", [])
        if isinstance(raw_react_trace, list):
            react_trace = [item for item in raw_react_trace if isinstance(item, dict)]
        raw_context_summary = result.get("context_summary", {})
        if isinstance(raw_context_summary, dict):
            context_summary = raw_context_summary
    raw_step_key = agent_run.context_json.get("step_key")
    return TaskSubagentResult(
        id=agent_run.id,
        step_key=str(raw_step_key) if raw_step_key is not None else None,
        status=agent_run.status,
        summary=summary,
        tool_results=tool_results,
        artifacts=_subagent_artifacts(tool_results),
        react_trace=react_trace,
        context_summary=context_summary,
        completed_at=agent_run.completed_at,
    )


def _subagent_artifacts(tool_results: list[dict]) -> list[dict]:
    artifacts = []
    for index, tool_result in enumerate(tool_results, start=1):
        if tool_result.get("status") != "SUCCESS":
            continue
        artifact = _subagent_artifact_from_tool_result(tool_result, index)
        if artifact is not None:
            artifacts.append(artifact)
    return artifacts


def _subagent_artifact_from_tool_result(tool_result: dict, index: int) -> dict | None:
    tool_name = str(tool_result.get("tool_name") or "tool")
    output = tool_result.get("output") if isinstance(tool_result.get("output"), dict) else {}
    input_json = (
        tool_result.get("input_json") if isinstance(tool_result.get("input_json"), dict) else {}
    )
    if tool_name == "read_file":
        name = str(input_json.get("path") or f"read-file-{index}.txt")
        return {
            "name": name,
            "artifact_type": "file",
            "source_tool": tool_name,
            "description": f"读取文件，大小 {int(output.get('size_bytes', 0) or 0)} 字节",
            "status": "ready",
            "preview": str(output.get("content", ""))[:500] or None,
        }
    if tool_name == "list_files":
        files = output.get("files", [])
        count = len(files) if isinstance(files, list) else 0
        return {
            "name": f"file-list-{index}.json",
            "artifact_type": "json",
            "source_tool": tool_name,
            "description": f"文件列表，共 {count} 项",
            "status": "ready",
            "preview": str(files[:20]) if isinstance(files, list) else None,
        }
    if tool_name == "write_file":
        return {
            "name": str(output.get("path") or input_json.get("path") or f"write-file-{index}"),
            "artifact_type": "file",
            "source_tool": tool_name,
            "description": f"写入文件，大小 {int(output.get('bytes_written', 0) or 0)} 字节",
            "status": "ready",
            "preview": str(input_json.get("content", ""))[:500] or None,
        }
    if tool_name in {"run_tests", "run_shell", "git_command"}:
        preview = str(output.get("stdout_preview") or output.get("stderr_preview") or "")[:500]
        return {
            "name": f"{tool_name}-{index}.log",
            "artifact_type": "log",
            "source_tool": tool_name,
            "description": f"命令退出码 {output.get('exit_code', 'unknown')}",
            "status": "ready",
            "preview": preview or None,
        }
    if tool_name == "network_request":
        return {
            "name": f"http-response-{index}.json",
            "artifact_type": "json",
            "source_tool": tool_name,
            "description": f"HTTP 状态 {output.get('status_code', 'unknown')}",
            "status": "ready",
            "preview": str(output.get("body_preview", ""))[:500] or None,
        }
    return None


def _subagent_result_summary(subagent_results: list[TaskSubagentResult]) -> str | None:
    if not subagent_results:
        return None
    counts = {status: 0 for status in SUBAGENT_TERMINAL_STATUSES}
    running = 0
    for result in subagent_results:
        if result.status in counts:
            counts[result.status] += 1
        else:
            running += 1
    parts = [
        f"共 {len(subagent_results)} 个子 Agent",
        f"成功 {counts['SUCCESS']} 个",
        f"失败 {counts['FAILED']} 个",
        f"超时 {counts['TIMEOUT']} 个",
        f"取消 {counts['CANCELLED']} 个",
    ]
    if running > 0:
        parts.append(f"运行中 {running} 个")
    completed_summaries = [
        result.summary
        for result in subagent_results
        if result.status == "SUCCESS" and result.summary
    ]
    if completed_summaries:
        parts.append("异步摘要：" + "；".join(completed_summaries[:3]))
    return "子 Agent 结果：" + "，".join(parts) + "。"


def _resolve_tool_sandbox(
    *,
    task: Task,
    request: ToolExecuteRequest,
    session: Session,
) -> SandboxInstance | None:
    if request.sandbox_id is None:
        if not request.create_sandbox:
            return None
        sandbox = DockerManager().create_sandbox(session=session, task_id=task.id)
        session.flush()
        return sandbox
    sandbox = session.execute(
        select(SandboxInstance).where(
            SandboxInstance.id == request.sandbox_id,
            SandboxInstance.task_id == task.id,
        )
    ).scalar_one_or_none()
    if sandbox is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="沙箱未找到")
    return sandbox
