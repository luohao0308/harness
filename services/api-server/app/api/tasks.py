import re
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.agents.context_router import RunContextRouter
from app.agents.executor import Executor
from app.api.pagination import cursor_paginate
from app.api.plan_projection import build_plan_response
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
    LocalAgentBridgeTask,
    LocalAgentCommand,
    LocalAgentConnection,
    LocalAgentPendingChange,
    LocalAgentToolRequest,
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
from app.tools.capabilities import CapabilityRegistry, redact_secrets, stable_json_sha256
from app.tools.runner import ToolRunner

RUN_COMPATIBILITY_DESCRIPTION = (
    "内部兼容接口；产品主入口使用 /api/agents/{agent_id}/runs 和 /api/agents/runs/*。"
)

router = APIRouter(
    prefix="/tasks",
    tags=["agent-run-compatibility"],
    deprecated=True,
)
DbSession = Annotated[Session, Depends(get_db_session)]
SUBAGENT_TERMINAL_STATUSES = {"SUCCESS", "FAILED", "TIMEOUT", "CANCELLED", "BUDGET_EXCEEDED"}
LOCAL_AGENT_TOOL_ACTIVE_STATUSES = {"approval_required", "approved", "allowed", "running"}
LOCAL_AGENT_COMMAND_ACTIVE_STATUSES = {"pending", "running"}
LOCAL_AGENT_PENDING_CHANGE_ACTIVE_STATUSES = {
    "previewed",
    "approval_required",
    "approved",
    "allowed",
}
LOCAL_AGENT_COMMAND_TOOLS = {"run_shell", "run_tests", "git"}
LOCAL_AGENT_NETWORK_PATTERNS = re.compile(
    r"\b(curl|wget|ssh|scp|git\s+remote|npm\s+install|pip\s+install|pnpm\s+install|yarn\s+add)\b",
    re.IGNORECASE,
)
LOCAL_AGENT_SECRET_PATTERNS = re.compile(
    r"\b(secret|token|api[_-]?key|printenv|cat\s+\.env)\b",
    re.IGNORECASE,
)


def get_owned_task(task_id: str, session: Session, organization_id: str) -> Task:
    task = session.execute(
        select(Task).where(Task.id == task_id, Task.organization_id == organization_id)
    ).scalar_one_or_none()
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="任务未找到")
    return task


def _is_sqlite_lock_error(exc: OperationalError) -> bool:
    return "database is locked" in str(exc).lower() or "database is busy" in str(exc).lower()


@router.post(
    "",
    response_model=TaskResponse,
    status_code=status.HTTP_201_CREATED,
    summary="兼容层：创建 Agent Run 记录",
    description=(
        f"{RUN_COMPATIBILITY_DESCRIPTION} 创建一条 Agent Run 兼容记录，并写入 TASK_CREATED 事件。"
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
        f"{RUN_COMPATIBILITY_DESCRIPTION} 按组织查询 Agent Run 列表，支持状态过滤和分页大小。"
    ),
)
def list_tasks(
    session: DbSession,
    principal: Principal,
    status_filter: Annotated[str | None, Query(alias="status")] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    cursor: str | None = None,
) -> TaskPage:
    statement = select(Task).where(Task.organization_id == principal.organization_id)
    if status_filter is not None:
        statement = statement.where(Task.status == status_filter)
    page = cursor_paginate(
        session=session,
        statement=statement,
        model=Task,
        cursor=cursor,
        limit=limit,
    )
    return TaskPage(items=page.items, next_cursor=page.next_cursor)


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
            select(ExecutionPlan.id).where(ExecutionPlan.task_id == task.id).limit(1)
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
    # A stream can briefly hold a SQLite write transaction while its first
    # frame is being assembled. Retry only that bounded, transient condition;
    # all other database errors still surface as server failures.
    for attempt in range(4):
        try:
            task = get_owned_task(task_id, session, principal.organization_id)
            if task.status not in {
                "CREATED",
                "PLANNING",
                "RUNNING",
                "WAITING_APPROVAL",
                "WAITING_SUBAGENTS",
                "FAILED",
            }:
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="任务无法取消")

            now = utc_now()
            _cancel_local_agent_state_for_task(
                task=task,
                session=session,
                reason="task cancelled",
                actor_id=principal.user_id,
                now=now,
            )
            _cancel_active_model_calls_for_task(
                task=task,
                session=session,
                now=now,
            )
            task.status = "CANCELLED"
            task.updated_at = now
            task.completed_at = now
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
        except OperationalError as exc:
            session.rollback()
            if not _is_sqlite_lock_error(exc) or attempt == 3:
                raise
            time.sleep(0.05 * (2**attempt))

    raise RuntimeError("unreachable cancellation retry state")


def _cancel_active_model_calls_for_task(
    *,
    task: Task,
    session: Session,
    now: datetime,
) -> None:
    active_calls = list(
        session.execute(
            select(ModelCall)
            .where(ModelCall.task_id == task.id, ModelCall.status == "RUNNING")
            .order_by(ModelCall.created_at.asc(), ModelCall.id.asc())
        ).scalars()
    )
    for model_call in active_calls:
        created_at = model_call.created_at
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=UTC)
        model_call.status = "FAILED"
        model_call.terminal_status = "stream_aborted"
        model_call.duration_ms = max(
            int(model_call.duration_ms or 0),
            max(0, int((now - created_at).total_seconds() * 1000)),
        )
        model_call.error_message = "stream closed before completion"
        EventStore(session).append(
            task_id=task.id,
            agent_run_id=model_call.agent_run_id,
            event_type=EventType.MODEL_CALL_FAILED,
            payload_json={
                "model_call_id": model_call.id,
                "model_provider": model_call.model_provider,
                "model_name": model_call.model_name,
                "error": model_call.error_message,
                "streaming": True,
                "cancelled": True,
                "grounding_correlation_id": model_call.grounding_correlation_id,
                "prompt_manifest_id": model_call.prompt_manifest_id,
                "context_manifest_id": model_call.context_manifest_id,
                "attempt_index": model_call.attempt_index,
                "terminal_status": model_call.terminal_status,
            },
        )


def _cancel_local_agent_state_for_task(
    *,
    task: Task,
    session: Session,
    reason: str,
    actor_id: str | None,
    now: datetime,
) -> None:
    local_requests = list(
        session.execute(
            select(LocalAgentToolRequest)
            .where(
                LocalAgentToolRequest.task_id == task.id,
                LocalAgentToolRequest.status.in_(LOCAL_AGENT_TOOL_ACTIVE_STATUSES),
            )
            .order_by(LocalAgentToolRequest.created_at.asc(), LocalAgentToolRequest.id.asc())
        ).scalars()
    )
    for local_request in local_requests:
        local_request.status = "cancelled"
        local_request.completed_at = local_request.completed_at or now
        local_request.updated_at = now
        decision_json = (
            local_request.decision_json
            if isinstance(local_request.decision_json, dict)
            else {}
        )
        local_request.decision_json = {
            **decision_json,
            "terminal_status": "cancelled",
            "terminal_reason": reason,
            "terminalized_at": now.isoformat(),
            "server_execution": False,
        }
        local_request.result_json = {
            "status": "CANCELLED",
            "reason": reason,
            "server_execution": False,
        }
        approval = (
            session.get(ToolApproval, local_request.approval_id)
            if local_request.approval_id
            else None
        )
        if approval is not None and approval.status == "PENDING":
            approval.status = "DENIED"
            approval.decided_by = actor_id
            approval.decided_at = now
            approval.decision_json = {
                "decision": "CANCELLED",
                "reason": reason,
                "server_execution": False,
            }
        tool_call = session.get(ToolCall, local_request.tool_call_id)
        if tool_call is not None and tool_call.status not in {
            "SUCCESS",
            "FAILED",
            "TIMEOUT",
            "DENIED",
            "CANCELLED",
        }:
            tool_call.status = "CANCELLED"
            tool_call.error_message = reason
            tool_call.output_json = {
                "status": "CANCELLED",
                "reason": reason,
                "server_execution": False,
                "tool_request_id": local_request.tool_request_id,
            }
        pending_changes = list(
            session.execute(
                select(LocalAgentPendingChange).where(
                    LocalAgentPendingChange.local_agent_tool_request_id == local_request.id,
                    LocalAgentPendingChange.status.in_(
                        LOCAL_AGENT_PENDING_CHANGE_ACTIVE_STATUSES
                    ),
                )
            ).scalars()
        )
        for change in pending_changes:
            change.status = "denied"
            change.denied_at = change.denied_at or now
            change.error_message = reason
            change.updated_at = now
        active_commands = list(
            session.execute(
                select(LocalAgentCommand).where(
                    LocalAgentCommand.local_agent_tool_request_id == local_request.id,
                    LocalAgentCommand.status.in_(LOCAL_AGENT_COMMAND_ACTIVE_STATUSES),
                )
            ).scalars()
        )
        for command in active_commands:
            command.status = "cancelled"
            command.finished_at = command.finished_at or now
            command.error_message = reason
            command.updated_at = now
        EventStore(session).append(
            task_id=task.id,
            event_type=EventType.LOCAL_AGENT_COMMAND_CANCELLED,
            payload_json={
                "source": "local_agent_bridge",
                "connection_id": local_request.connection_id,
                "bridge_task_id": local_request.bridge_task_id,
                "tool_request_id": local_request.tool_request_id,
                "tool_call_id": local_request.tool_call_id,
                "tool_name": local_request.tool_name,
                "status": "CANCELLED",
                "terminal_status": "cancelled",
                "reason": reason,
                "server_execution": False,
            },
            actor_type="user",
            actor_id=actor_id,
        )
    bridge_tasks = list(
        session.execute(
            select(LocalAgentBridgeTask).where(
                LocalAgentBridgeTask.task_id == task.id,
                ~LocalAgentBridgeTask.status.in_(("completed", "failed", "cancelled")),
            )
        ).scalars()
    )
    for bridge_task in bridge_tasks:
        bridge_task.status = "cancelled"
        bridge_task.completed_at = bridge_task.completed_at or now
        bridge_task.updated_at = now


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
    subagent_runs.sort(key=_subagent_result_sort_key)
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
        f"{RUN_COMPATIBILITY_DESCRIPTION} 返回 Agent Run 最新执行计划，并合并已落库步骤的当前状态。"
    ),
)
def get_task_plan(task_id: str, session: DbSession, principal: Principal) -> TaskPlanResponse:
    get_owned_task(task_id, session, principal.organization_id)
    plan = _latest_plan(task_id=task_id, session=session)
    if plan is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="执行计划未找到")
    return build_plan_response(plan, session=session)


@router.get(
    "/{task_id}/plans",
    response_model=TaskPlanVersionPage,
    summary="兼容层：查询 Agent Run Plan 版本",
    description=(
        f"{RUN_COMPATIBILITY_DESCRIPTION} 返回 Agent Run 全部执行计划版本，用于计划变更对比。"
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
        f"{RUN_COMPATIBILITY_DESCRIPTION} 按两个 Agent Run 计划版本对比步骤新增、移除和变更。"
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
            .order_by(ModelCall.created_at.desc(), ModelCall.id.desc())
        ).scalars()
    )
    trace_ids = _model_call_trace_ids(
        task_id=task_id,
        model_call_ids=[call.id for call in calls],
        session=session,
    )
    return ModelCallPage(
        items=[_to_model_call_response(call, trace_id=trace_ids.get(call.id)) for call in calls]
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
        session.execute(
            statement.order_by(ToolCall.created_at.desc(), ToolCall.id.desc()).limit(limit)
        ).scalars()
    )
    trace_ids = _tool_call_trace_ids(
        task_id=task_id,
        tool_call_ids=[call.id for call in calls],
        session=session,
    )
    return ToolCallPage(
        items=[_to_tool_call_response(call, trace_id=trace_ids.get(call.id)) for call in calls]
    )


@router.post(
    "/{task_id}/tools/execute",
    response_model=ToolExecuteResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="兼容层：执行工具",
    description=(
        f"{RUN_COMPATIBILITY_DESCRIPTION} 按工具注册表和策略执行工具，并写入工具调用审计与事件流。"
    ),
)
def execute_task_tool(
    task_id: str,
    request: ToolExecuteRequest,
    session: DbSession,
    principal: Principal,
) -> ToolExecuteResponse:
    task = get_owned_task(task_id, session, principal.organization_id)
    workspace_root = Path(__file__).resolve().parents[2]
    sandbox = _resolve_tool_sandbox(
        task=task,
        request=request,
        session=session,
        workspace_root=workspace_root,
    )
    execution = ToolRunner(
        session=session,
        workspace_root=workspace_root,
        agent_id=task.agent_id or "__missing_agent__",
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

    local_tool_request = _local_agent_tool_request_for_approval(
        approval=approval,
        tool_call=tool_call,
        session=session,
    )
    if local_tool_request is not None:
        if task.status == "CANCELLED":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Local Agent tool request cannot be approved after task cancellation",
            )
        _expire_local_agent_approval_if_needed(
            task=task,
            tool_call=tool_call,
            approval=approval,
            local_tool_request=local_tool_request,
            session=session,
        )
    if modified_input_json is not None:
        if local_tool_request is not None:
            _validate_local_agent_approval_modify(
                approval=approval,
                local_tool_request=local_tool_request,
                modified_input_json=modified_input_json,
                session=session,
            )
        safe_modified_input_json = redact_secrets(modified_input_json)
        request_json = approval.request_json if isinstance(approval.request_json, dict) else {}
        approval.request_json = {
            **request_json,
            "input_json": safe_modified_input_json,
            "executable_input_sha256": stable_json_sha256(safe_modified_input_json),
            "modified": True,
        }
        tool_call.input_json = safe_modified_input_json

    approval.status = decision
    approval.decided_by = principal.user_id
    approval.decided_at = utc_now()
    approval.decision_json = {
        "reason": request.reason,
        "decision": decision,
        "modified": modified_input_json is not None,
        "server_execution": False if local_tool_request is not None else True,
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
            "server_execution": False if local_tool_request is not None else True,
        },
        actor_type="user",
        actor_id=principal.user_id,
    )
    if local_tool_request is not None:
        _decide_local_agent_tool_request(
            task=task,
            tool_call=tool_call,
            approval=approval,
            local_tool_request=local_tool_request,
            decision=decision,
            reason=request.reason,
            modified_input_json=modified_input_json,
            session=session,
            principal=principal,
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
    if decision == "APPROVED":
        _execute_approved_tool_call(
            task=task,
            tool_call=tool_call,
            approval=approval,
            session=session,
            principal=principal,
        )
    else:
        _advance_task_after_tool_approval(
            task=task,
            tool_call=tool_call,
            approval=approval,
            step_completed=False,
            session=session,
            principal=principal,
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


def _local_agent_tool_request_for_approval(
    *,
    approval: ToolApproval,
    tool_call: ToolCall,
    session: Session,
) -> LocalAgentToolRequest | None:
    snapshot = tool_call.capability_snapshot_json
    if not isinstance(snapshot, dict) or snapshot.get("source") != "local_agent_bridge":
        return None
    return session.execute(
        select(LocalAgentToolRequest).where(
            LocalAgentToolRequest.tool_call_id == tool_call.id,
            LocalAgentToolRequest.approval_id == approval.id,
        )
    ).scalar_one_or_none()


def _as_aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _expire_local_agent_approval_if_needed(
    *,
    task: Task,
    tool_call: ToolCall,
    approval: ToolApproval,
    local_tool_request: LocalAgentToolRequest,
    session: Session,
) -> None:
    if local_tool_request.decision_expires_at is None:
        return
    now = utc_now()
    if _as_aware_utc(local_tool_request.decision_expires_at) >= _as_aware_utc(now):
        return
    reason = "local tool decision expired"
    local_tool_request.status = "expired"
    local_tool_request.completed_at = now
    local_tool_request.updated_at = now
    decision_json = (
        local_tool_request.decision_json
        if isinstance(local_tool_request.decision_json, dict)
        else {}
    )
    local_tool_request.decision_json = {
        **decision_json,
        "terminal_status": "expired",
        "terminal_reason": reason,
        "terminalized_at": now.isoformat(),
        "server_execution": False,
    }
    local_tool_request.result_json = {
        "status": "DENIED",
        "reason": reason,
        "server_execution": False,
    }
    tool_call.status = "DENIED"
    tool_call.error_message = reason
    tool_call.output_json = {
        "status": "DENIED",
        "reason": reason,
        "server_execution": False,
        "tool_request_id": local_tool_request.tool_request_id,
    }
    approval.status = "EXPIRED"
    approval.decided_at = now
    approval.decision_json = {
        "decision": "EXPIRED",
        "reason": reason,
        "server_execution": False,
    }
    pending_changes = list(
        session.execute(
            select(LocalAgentPendingChange).where(
                LocalAgentPendingChange.local_agent_tool_request_id == local_tool_request.id,
                LocalAgentPendingChange.status.in_(
                    ("previewed", "approval_required", "approved", "allowed")
                ),
            )
        ).scalars()
    )
    for change in pending_changes:
        change.status = "denied"
        change.denied_at = now
        change.error_message = reason
        change.updated_at = now
    task.status = "RUNNING"
    task.completed_at = None
    task.updated_at = now
    EventStore(session).append(
        task_id=task.id,
        event_type=EventType.TOOL_DENIED_BY_POLICY,
        payload_json={
            "source": "local_agent_bridge",
            "tool_request_id": local_tool_request.tool_request_id,
            "tool_call_id": tool_call.id,
            "approval_id": approval.id,
            "status": "DENIED",
            "terminal_status": "expired",
            "reason": reason,
            "server_execution": False,
        },
        actor_type="system",
        actor_id=None,
    )
    session.commit()
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail="Local Agent tool decision expired",
    )


def _validate_local_agent_approval_modify(
    *,
    approval: ToolApproval,
    local_tool_request: LocalAgentToolRequest,
    modified_input_json: dict,
    session: Session,
) -> None:
    request_json = approval.request_json if isinstance(approval.request_json, dict) else {}
    original_input = request_json.get("input_json")
    if not isinstance(original_input, dict):
        original_input = local_tool_request.input_json
    if not isinstance(original_input, dict):
        original_input = {}
    modified_keys = {str(key) for key in modified_input_json}
    original_keys = {str(key) for key in original_input}
    added_keys = modified_keys - original_keys
    if added_keys:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Local Agent approval modify cannot add new input keys",
        )
    allow_narrowed_execution = _local_agent_supports_narrowed_modified_execution(
        local_tool_request=local_tool_request,
        session=session,
    )
    protected_keys = {
        "args",
        "capability_id",
        "capability_type",
        "capability_version_id",
        "change_id",
        "cmd",
        "command",
        "cwd",
        "diff",
        "diff_hash",
        "diff_sha256",
        "execution_target",
        "patch",
        "path",
        "paths",
        "permission_mode",
        "requires_network",
        "requires_secret_read",
        "risk_level",
        "target_path",
        "target_paths",
        "tool_name",
        "workspace_root",
    }
    mutable_keys = _local_agent_mutable_input_keys(
        tool_name=local_tool_request.tool_name,
        allow_narrowed_execution=allow_narrowed_execution,
    )
    protected_keys -= mutable_keys
    pending_change_preview = request_json.get("pending_change_preview")
    if (
        isinstance(pending_change_preview, dict)
        and pending_change_preview
        and "content" not in mutable_keys
    ):
        protected_keys.add("content")
    for key in protected_keys & modified_keys:
        if modified_input_json.get(key) != original_input.get(key):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Local Agent approval modify cannot change protected field: {key}",
            )
    changed_keys: set[str] = set()
    for key in modified_keys:
        original_value = original_input.get(key)
        modified_value = modified_input_json.get(key)
        if modified_value == original_value:
            continue
        if modified_value == redact_secrets(original_value):
            continue
        changed_keys.add(key)
    if not allow_narrowed_execution:
        if changed_keys:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Local Agent approval modify can only redact or preserve existing input",
            )
        return
    unexpected_keys = changed_keys - mutable_keys
    if unexpected_keys:
        detail = ", ".join(sorted(unexpected_keys))
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Local Agent approval modify cannot change protected field: {detail}",
        )
    _validate_narrowed_local_agent_modified_input(
        approval=approval,
        local_tool_request=local_tool_request,
        original_input=original_input,
        modified_input_json=modified_input_json,
    )


def _local_agent_supports_narrowed_modified_execution(
    *,
    local_tool_request: LocalAgentToolRequest,
    session: Session,
) -> bool:
    connection = session.get(LocalAgentConnection, local_tool_request.connection_id)
    if connection is None or connection.adapter_kind != "claude_code":
        return False
    metadata = connection.metadata_json if isinstance(connection.metadata_json, dict) else {}
    capabilities = (
        connection.capabilities_json if isinstance(connection.capabilities_json, dict) else {}
    )
    return (
        metadata.get("server_permission_bridge_entitlement") == "sdk"
        and capabilities.get("enabled_in_v6") is True
        and capabilities.get("host_tools_authorized") is True
        and capabilities.get("permission_bridge") == "harness_local_tool_request_v1"
        and capabilities.get("execution_mode") == "agent_sdk_intent_capture_harness_executor"
        and capabilities.get("permission_bridge_execution") == "harness_owned_executor"
        and capabilities.get("sdk_native_tool_execution_enabled") is False
    )


def _local_agent_mutable_input_keys(
    *,
    tool_name: str,
    allow_narrowed_execution: bool,
) -> set[str]:
    if not allow_narrowed_execution:
        return set()
    if tool_name in LOCAL_AGENT_COMMAND_TOOLS:
        return {"command", "cmd"}
    if tool_name == "write_file":
        return {"path", "content"}
    if tool_name == "apply_patch":
        return {"patch"}
    return set()


def _validate_narrowed_local_agent_modified_input(
    *,
    approval: ToolApproval,
    local_tool_request: LocalAgentToolRequest,
    original_input: dict,
    modified_input_json: dict,
) -> None:
    tool_name = local_tool_request.tool_name
    policy_decision = (
        local_tool_request.policy_decision_json
        if isinstance(local_tool_request.policy_decision_json, dict)
        else {}
    )
    if tool_name in LOCAL_AGENT_COMMAND_TOOLS:
        command = _normalized_modified_command(tool_name=tool_name, input_json=modified_input_json)
        if not command:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Local Agent approval modify command cannot be empty",
            )
        if LOCAL_AGENT_NETWORK_PATTERNS.search(command) and not bool(
            policy_decision.get("requires_network")
        ):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Local Agent approval modify cannot add network scope",
            )
        if LOCAL_AGENT_SECRET_PATTERNS.search(command) and not bool(
            policy_decision.get("requires_secret_read")
        ):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Local Agent approval modify cannot add secret-read scope",
            )
        return
    original_target_paths = _local_agent_original_target_paths(
        approval=approval,
        local_tool_request=local_tool_request,
        original_input=original_input,
    )
    modified_target_paths = _local_agent_modified_target_paths(
        tool_name=tool_name,
        input_json=modified_input_json,
    )
    if tool_name == "write_file":
        path = str(modified_input_json.get("path") or "").strip()
        if not path:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Local Agent approval modify path cannot be empty",
            )
        _validate_local_agent_modified_target_scope(
            original_target_paths=original_target_paths,
            modified_target_paths=modified_target_paths,
        )
        return
    if tool_name == "apply_patch":
        patch = str(modified_input_json.get("patch") or "").strip()
        if not patch:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Local Agent approval modify patch cannot be empty",
            )
        if not modified_target_paths:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Local Agent approval modify patch must keep target paths",
            )
        _validate_local_agent_modified_target_scope(
            original_target_paths=original_target_paths,
            modified_target_paths=modified_target_paths,
        )
        return
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail="Local Agent approval modify is not supported for this tool",
    )


def _local_agent_original_target_paths(
    *,
    approval: ToolApproval,
    local_tool_request: LocalAgentToolRequest,
    original_input: dict,
) -> list[str]:
    request_json = approval.request_json if isinstance(approval.request_json, dict) else {}
    pending_change_preview = request_json.get("pending_change_preview")
    if isinstance(pending_change_preview, dict):
        target_paths = pending_change_preview.get("target_paths")
        if isinstance(target_paths, list):
            return [str(path) for path in target_paths if str(path).strip()]
    policy_decision = (
        local_tool_request.policy_decision_json
        if isinstance(local_tool_request.policy_decision_json, dict)
        else {}
    )
    target_paths = policy_decision.get("target_paths")
    if isinstance(target_paths, list):
        return [str(path) for path in target_paths if str(path).strip()]
    return _local_agent_modified_target_paths(
        tool_name=local_tool_request.tool_name,
        input_json=original_input,
    )


def _local_agent_modified_target_paths(*, tool_name: str, input_json: dict) -> list[str]:
    if tool_name == "write_file":
        path = str(input_json.get("path") or "").strip()
        return [path] if path else []
    if tool_name == "apply_patch":
        patch = str(input_json.get("patch") or "")
        return _patch_target_paths_from_text(patch)
    return []


def _validate_local_agent_modified_target_scope(
    *,
    original_target_paths: list[str],
    modified_target_paths: list[str],
) -> None:
    if not modified_target_paths:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Local Agent approval modify must keep target scope",
        )
    if original_target_paths and len(modified_target_paths) > len(original_target_paths):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Local Agent approval modify cannot expand target paths",
        )
    original_has_absolute = any(path.startswith(("~", "/")) for path in original_target_paths)
    modified_has_absolute = any(path.startswith(("~", "/")) for path in modified_target_paths)
    if modified_has_absolute and not original_has_absolute:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Local Agent approval modify cannot expand to absolute or home paths",
        )


def _patch_target_paths_from_text(patch: str) -> list[str]:
    paths: list[str] = []
    for line in patch.splitlines():
        if not line.startswith(("--- ", "+++ ")):
            continue
        raw = line[4:].strip()
        if raw == "/dev/null":
            continue
        if raw.startswith(("a/", "b/")):
            raw = raw[2:]
        path = raw.split("\t", 1)[0].strip()
        if path and path not in paths:
            paths.append(path)
    return paths


def _normalized_modified_command(*, tool_name: str, input_json: dict) -> str:
    command = str(input_json.get("command") or input_json.get("cmd") or "").strip()
    if tool_name == "run_tests":
        return command or "pytest"
    if tool_name == "git":
        if not command:
            args = input_json.get("args") if isinstance(input_json.get("args"), list) else []
            command = f"git {' '.join(map(str, args))}".strip()
        elif not command.startswith("git"):
            command = f"git {command}"
    return command


def _decide_local_agent_tool_request(
    *,
    task: Task,
    tool_call: ToolCall,
    approval: ToolApproval,
    local_tool_request: LocalAgentToolRequest,
    decision: str,
    reason: str,
    modified_input_json: dict | None,
    session: Session,
    principal,
) -> None:
    now = utc_now()
    if local_tool_request.status not in {"approval_required"}:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Local Agent tool request is not waiting for approval",
        )
    request_json = approval.request_json if isinstance(approval.request_json, dict) else {}
    original_input = request_json.get("input_json")
    if not isinstance(original_input, dict):
        original_input = local_tool_request.input_json
    executable_input = (
        redact_secrets(modified_input_json) if modified_input_json is not None else original_input
    )
    executable_input_sha256 = stable_json_sha256(
        executable_input if isinstance(executable_input, dict) else {}
    )
    previous_decision_json = (
        local_tool_request.decision_json
        if isinstance(local_tool_request.decision_json, dict)
        else {}
    )
    metadata = previous_decision_json.get("metadata")
    if not isinstance(metadata, dict):
        metadata = (
            request_json.get("metadata") if isinstance(request_json.get("metadata"), dict) else {}
        )
    pending_change_preview = previous_decision_json.get("pending_change_preview")
    if not isinstance(pending_change_preview, dict):
        pending_change_preview = (
            request_json.get("pending_change_preview")
            if isinstance(request_json.get("pending_change_preview"), dict)
            else {}
        )
    local_status = "approved" if decision == "APPROVED" else "denied"
    local_tool_request.status = local_status
    local_tool_request.input_json = executable_input
    local_tool_request.decision_json = {
        "decision": "approved" if decision == "APPROVED" else "denied",
        "reason": reason,
        "modified": modified_input_json is not None,
        "server_execution": False,
        "input_json": executable_input,
        "executable_input_sha256": executable_input_sha256,
        "approval_id": approval.id,
        "metadata": metadata,
        "pending_change_preview": pending_change_preview,
        "decided_by": principal.user_id,
        "decided_at": now.isoformat(),
        "expires_at": local_tool_request.decision_expires_at.isoformat()
        if local_tool_request.decision_expires_at is not None
        else None,
    }
    local_tool_request.updated_at = now
    pending_changes = list(
        session.execute(
            select(LocalAgentPendingChange).where(
                LocalAgentPendingChange.local_agent_tool_request_id == local_tool_request.id,
                LocalAgentPendingChange.status.in_(("previewed", "approval_required")),
            )
        ).scalars()
    )
    for change in pending_changes:
        if decision == "APPROVED":
            change.status = "approved"
            change.approval_id = approval.id
            if (
                modified_input_json is not None
                and local_tool_request.tool_name in {"write_file", "apply_patch"}
            ):
                target_paths = _local_agent_modified_target_paths(
                    tool_name=local_tool_request.tool_name,
                    input_json=executable_input,
                )
                change.diff_sha256 = ""
                change.target_paths_json = target_paths
                change.preview_json = {
                    **(
                        change.preview_json
                        if isinstance(change.preview_json, dict)
                        else {}
                    ),
                    "change_id": change.change_id,
                    "target_paths": target_paths,
                    "diff_sha256": "",
                    "refresh_required": True,
                }
                pending_change_preview = change.preview_json
        else:
            change.status = "denied"
            change.denied_at = now
        change.updated_at = now
    task.status = "RUNNING"
    task.completed_at = None
    task.updated_at = now
    EventStore(session).append(
        task_id=task.id,
        event_type=EventType.LOCAL_AGENT_TOOL_DECISION_READY,
        payload_json={
            "source": "local_agent_bridge",
            "tool_request_id": local_tool_request.tool_request_id,
            "tool_call_id": tool_call.id,
            "approval_id": approval.id,
            "decision": local_tool_request.status,
            "server_execution": False,
            "modified": modified_input_json is not None,
        },
        actor_type="user",
        actor_id=principal.user_id,
    )
    session.flush()


def _execute_approved_tool_call(
    *,
    task: Task,
    tool_call: ToolCall,
    approval: ToolApproval,
    session: Session,
    principal,
) -> None:
    sandbox = None
    workspace_root = Path(__file__).resolve().parents[2]
    if tool_call.requires_sandbox and task.enable_sandbox:
        sandbox = DockerManager().create_sandbox(
            session=session,
            task_id=task.id,
            workspace_root=str(workspace_root),
        )
        session.flush()
    execution = ToolRunner(
        session=session,
        workspace_root=workspace_root,
        agent_id=task.agent_id,
        capability_registry=CapabilityRegistry(session, task.organization_id),
    ).execute_approved_call(tool_call=tool_call, sandbox=sandbox)
    step_completed = False
    if execution.tool_call.status == "SUCCESS":
        step_completed = _complete_approved_tool_step(
            task=task,
            tool_call=execution.tool_call,
            approval=approval,
            session=session,
        )
    _advance_task_after_tool_approval(
        task=task,
        tool_call=execution.tool_call,
        approval=approval,
        step_completed=step_completed,
        session=session,
        principal=principal,
    )


def _complete_approved_tool_step(
    *,
    task: Task,
    tool_call: ToolCall,
    approval: ToolApproval,
    session: Session,
) -> bool:
    failed_step_event = _failed_step_event_for_tool_call(
        task_id=task.id,
        tool_call_id=tool_call.id,
        session=session,
    )
    if failed_step_event is None:
        return False
    payload = (
        failed_step_event.payload_json
        if isinstance(failed_step_event.payload_json, dict)
        else {}
    )
    step_id = payload.get("step_id")
    step_key = payload.get("step_key")
    if not isinstance(step_key, str):
        return False
    if isinstance(step_id, str):
        step_row = session.get(TaskStep, step_id)
        if step_row is not None:
            step_row.status = "STEP_COMPLETED"
            step_row.error_message = None
            step_row.completed_at = utc_now()
    EventStore(session).append(
        task_id=task.id,
        event_type=EventType.STEP_COMPLETED,
        payload_json={
            "step_id": step_id,
            "step_key": step_key,
            "tool_call_id": tool_call.id,
            "tool_approval_id": approval.id,
            "summary": _tool_output_summary(tool_call),
            "approval_resume": True,
            "trace_summary": "工具审批通过后，已执行挂起工具并完成步骤。",
        },
    )
    session.flush()
    return True


def _failed_step_event_for_tool_call(
    *,
    task_id: str,
    tool_call_id: str,
    session: Session,
) -> AgentEvent | None:
    events = list(
        session.execute(
            select(AgentEvent)
            .where(
                AgentEvent.task_id == task_id,
                AgentEvent.event_type == EventType.STEP_FAILED.value,
            )
            .order_by(AgentEvent.sequence.desc())
            .limit(100)
        ).scalars()
    )
    for event in events:
        payload = event.payload_json if isinstance(event.payload_json, dict) else {}
        if payload.get("tool_call_id") == tool_call_id:
            return event
    return None


def _advance_task_after_tool_approval(
    *,
    task: Task,
    tool_call: ToolCall,
    approval: ToolApproval,
    step_completed: bool,
    session: Session,
    principal,
) -> None:
    pending_approvals = session.execute(
        select(func.count(ToolApproval.id)).where(
            ToolApproval.task_id == task.id,
            ToolApproval.status == "PENDING",
        )
    ).scalar_one()
    if pending_approvals:
        task.status = "WAITING_APPROVAL"
        task.updated_at = utc_now()
        session.flush()
        return

    plan_exists = _latest_plan(task.id, session) is not None
    if plan_exists and step_completed and tool_call.status == "SUCCESS":
        task.status = "RUNNING"
        task.completed_at = None
        task.updated_at = utc_now()
        EventStore(session).append(
            task_id=task.id,
            event_type=EventType.TASK_RESUMED,
            payload_json={
                "task_id": task.id,
                "resumed_by": principal.user_id,
                "tool_approval_id": approval.id,
                "tool_call_id": tool_call.id,
                "mode": "tool_approval",
                "trace_summary": "工具审批通过，Run 自动从等待审批状态继续执行。",
            },
            actor_type="user",
            actor_id=principal.user_id,
        )
        Executor(session).resume_task(task)
        session.flush()
        return

    if plan_exists:
        task.status = "RUNNING" if tool_call.status == "SUCCESS" else "FAILED"
        task.updated_at = utc_now()
        session.flush()
        return

    if tool_call.status == "SUCCESS":
        task.status = "COMPLETED"
        task.completed_at = utc_now()
        EventStore(session).append(
            task_id=task.id,
            event_type=EventType.TASK_COMPLETED,
            payload_json={
                "task_id": task.id,
                "tool_approval_id": approval.id,
                "tool_call_id": tool_call.id,
                "mode": "tool_approval",
                "trace_summary": "工具审批通过后，已执行工具并完成 Run。",
            },
        )
    else:
        task.status = "FAILED"
        EventStore(session).append(
            task_id=task.id,
            event_type=EventType.TASK_FAILED,
            payload_json={
                "summary": tool_call.error_message or "approved tool execution failed",
                "tool_approval_id": approval.id,
                "tool_call_id": tool_call.id,
                "mode": "tool_approval",
            },
        )
    task.updated_at = utc_now()
    session.flush()


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
        capability_id=tool_call.capability_id,
        capability_version_id=tool_call.capability_version_id,
        capability_type=tool_call.capability_type,
        capability_content_sha256=tool_call.capability_content_sha256,
        capability_config_sha256=tool_call.capability_config_sha256,
        capability_schema_version=tool_call.capability_schema_version,
        capability_snapshot_json=tool_call.capability_snapshot_json,
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


def _optional_string(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _optional_int(value: object) -> int | None:
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.isdigit():
        return int(value)
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
    specialist = getattr(agent_run, "specialist", None)
    output = getattr(agent_run, "subagent_output", None)
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
        fanout_batch_id=_optional_string(agent_run.context_json.get("fanout_batch_id")),
        fanout_index=_optional_int(agent_run.context_json.get("fanout_index")),
        fanout_total=_optional_int(agent_run.context_json.get("fanout_total")),
        specialist_slug=specialist.slug
        if specialist is not None
        else _optional_string(agent_run.context_json.get("specialist_slug")),
        specialist_role=specialist.role
        if specialist is not None
        else _optional_string(agent_run.context_json.get("specialist_role")),
        specialist_output=output.output_json if output is not None else None,
        budget_consumed_json=output.budget_consumed_json
        if output is not None
        else agent_run.context_json.get("budget_consumed", {}),
        budget_exceeded_json=output.budget_exceeded_json
        if output is not None
        else agent_run.context_json.get("budget_exceeded", []),
        summary=summary,
        tool_results=tool_results,
        artifacts=_subagent_artifacts(tool_results),
        react_trace=react_trace,
        context_summary=context_summary,
        completed_at=agent_run.completed_at,
    )


def _subagent_result_sort_key(agent_run: AgentRun) -> tuple:
    return (
        _optional_string(agent_run.context_json.get("step_key")) or "",
        _optional_string(agent_run.context_json.get("fanout_batch_id")) or "",
        _optional_int(agent_run.context_json.get("fanout_index"))
        if _optional_int(agent_run.context_json.get("fanout_index")) is not None
        else 9999,
        agent_run.started_at or agent_run.timeout_at or utc_now(),
        agent_run.id,
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
    workspace_root: Path,
) -> SandboxInstance | None:
    if request.sandbox_id is None:
        if not request.create_sandbox:
            return None
        sandbox = DockerManager().create_sandbox(
            session=session,
            task_id=task.id,
            workspace_root=str(workspace_root),
        )
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
