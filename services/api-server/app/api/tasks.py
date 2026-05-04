from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.agents.executor import Executor
from app.api.schemas import (
    ModelCallPage,
    ReplayRequest,
    ReplayResponse,
    TaskArtifact,
    TaskCreateRequest,
    TaskPage,
    TaskResponse,
    TaskResultResponse,
    ToolCallPage,
)
from app.db.models import AgentEvent, ExecutionPlan, ModelCall, Task, ToolCall, utc_now
from app.db.session import get_db_session
from app.events.event_store import EventStore
from app.events.event_types import EventType
from app.events.replay import EventReplay
from app.observability.metrics import (
    agent_task_resume_total,
    agent_tasks_running,
    agent_tasks_total,
)
from app.security.auth import Principal

router = APIRouter(prefix="/tasks", tags=["tasks"])
DbSession = Annotated[Session, Depends(get_db_session)]


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
    summary="创建任务",
    description="创建一条新的任务记录，并写入 TASK_CREATED 事件。",
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
    summary="查询任务列表",
    description="按组织查询任务列表，支持状态过滤和分页大小。",
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
    summary="查询任务详情",
    description="返回指定任务的完整基础信息。",
)
def get_task(task_id: str, session: DbSession, principal: Principal) -> Task:
    return get_owned_task(task_id, session, principal.organization_id)


@router.post(
    "/{task_id}/start",
    response_model=TaskResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="启动任务",
    description="将 CREATED 或 FAILED 任务启动为运行态。",
)
def start_task(task_id: str, session: DbSession, principal: Principal) -> Task:
    task = get_owned_task(task_id, session, principal.organization_id)
    if task.status not in {"CREATED", "FAILED"}:
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
    summary="取消任务",
    description="将当前任务状态切换为 CANCELLED，并写入 TASK_CANCELLED 事件。",
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
    summary="恢复任务",
    description="将 FAILED 或 CANCELLED 任务恢复为 RUNNING，并写入 TASK_RESUMED 事件。",
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
    resumed = Executor(session).start_task(task)
    session.commit()
    session.refresh(resumed)
    return resumed


@router.get(
    "/{task_id}/result",
    response_model=TaskResultResponse,
    summary="查询任务结果",
    description="返回任务状态、摘要、执行计划、产物列表和最后事件序号。",
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
    summary = None
    if task.status == "COMPLETED":
        summary = f"任务《{task.title}》已完成。"
    if task.status == "FAILED":
        summary = f"任务《{task.title}》已失败。"
    return TaskResultResponse(
        task_id=task.id,
        status=task.status,
        summary=summary,
        execution_plan=plan.plan_json if plan is not None else None,
        artifacts=artifacts,
        last_sequence=last_sequence or 0,
        pending=task.status not in {"COMPLETED", "FAILED", "CANCELLED"},
    )


@router.post(
    "/{task_id}/replay",
    response_model=ReplayResponse,
    summary="重放任务状态",
    description="根据事件流和快照重放任务状态，返回故障点和诊断摘要。",
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
    "/{task_id}/model-calls",
    response_model=ModelCallPage,
    summary="查询模型调用",
    description="返回当前任务关联的模型调用审计列表。",
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
    return ModelCallPage(items=calls)


@router.get(
    "/{task_id}/tool-calls",
    response_model=ToolCallPage,
    summary="查询工具调用",
    description="返回当前任务关联的工具调用审计列表。",
)
def list_tool_calls(task_id: str, session: DbSession, principal: Principal) -> ToolCallPage:
    get_owned_task(task_id, session, principal.organization_id)
    calls = list(
        session.execute(
            select(ToolCall).where(ToolCall.task_id == task_id).order_by(ToolCall.created_at.desc())
        ).scalars()
    )
    return ToolCallPage(items=calls)
