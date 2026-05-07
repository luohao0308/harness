from datetime import UTC, datetime
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.subagent_manager import SubagentLimitExceededError, SubagentManager
from app.agents.subagent_recovery_history import (
    persist_recovery_batch,
    recovery_action_counts,
)
from app.api.schemas import (
    SubagentCreateRequest,
    SubagentListItemResponse,
    SubagentListPage,
    SubagentPage,
    SubagentRecoverRequest,
    SubagentRecoveryBatchPage,
    SubagentRecoveryResponse,
    SubagentRecoverySummaryResponse,
    SubagentRecoveryTaskSummary,
    SubagentResponse,
)
from app.api.tasks import get_owned_task
from app.db.models import AgentRun, SubagentRecoveryBatch, Task
from app.db.session import get_db_session
from app.security.auth import Principal

router = APIRouter(tags=["subagents"])
DbSession = Annotated[Session, Depends(get_db_session)]


@router.get(
    "/tasks/{task_id}/subagents",
    response_model=SubagentPage,
    summary="查询任务子 Agent",
    description="返回指定任务派生出的子 Agent 列表。",
)
def list_task_subagents(task_id: str, session: DbSession, principal: Principal) -> SubagentPage:
    get_owned_task(task_id, session, principal.organization_id)
    statement = (
        select(AgentRun)
        .where(AgentRun.task_id == task_id, AgentRun.agent_type == "subagent")
        .order_by(AgentRun.started_at.asc().nullsfirst(), AgentRun.id.asc())
    )
    return SubagentPage(items=list(session.execute(statement).scalars()))


@router.get(
    "/subagents",
    response_model=SubagentListPage,
    summary="查询组织子 Agent 列表",
    description="返回当前组织全部子 Agent，支持按状态筛选，用于批量运营视图。",
)
def list_subagents(
    session: DbSession,
    principal: Principal,
    status_filter: str | None = Query(default=None, alias="status", description="子 Agent 状态"),
    limit: int = Query(default=100, ge=1, le=500, description="返回数量"),
) -> SubagentListPage:
    statement = (
        select(AgentRun, Task)
        .join(Task, Task.id == AgentRun.task_id)
        .where(
            Task.organization_id == principal.organization_id,
            AgentRun.agent_type == "subagent",
        )
        .order_by(AgentRun.started_at.desc(), AgentRun.id.desc())
        .limit(limit)
    )
    if status_filter:
        statement = statement.where(AgentRun.status == status_filter)
    rows = session.execute(statement).all()
    return SubagentListPage(
        items=[
            SubagentListItemResponse(
                id=agent_run.id,
                task_id=agent_run.task_id,
                parent_agent_id=agent_run.parent_agent_id,
                agent_type=agent_run.agent_type,
                status=agent_run.status,
                context_json=agent_run.context_json,
                started_at=agent_run.started_at,
                completed_at=agent_run.completed_at,
                timeout_at=agent_run.timeout_at,
                task_title=task.title,
                task_status=task.status,
                step_key=_subagent_step_key(agent_run),
            )
            for agent_run, task in rows
        ],
        next_cursor=None,
    )


def _subagent_step_key(agent_run: AgentRun) -> str | None:
    step_key = agent_run.context_json.get("step_key")
    return str(step_key) if step_key is not None else None


@router.post(
    "/tasks/{task_id}/subagents",
    response_model=SubagentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="创建任务子 Agent",
    description="为指定任务派生一个子 Agent，并写入 SUBAGENT_SPAWNED 事件。",
)
def create_task_subagent(
    task_id: str,
    request: SubagentCreateRequest,
    session: DbSession,
    principal: Principal,
) -> AgentRun:
    task = get_owned_task(task_id, session, principal.organization_id)
    try:
        agent_run = SubagentManager(session).spawn(
            task=task,
            assignment=request.assignment,
            parent_agent_id=request.parent_agent_id,
            timeout_seconds=request.timeout_seconds,
            enqueue=request.enqueue,
        )
    except SubagentLimitExceededError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="子 Agent 并发数量已达到上限",
        ) from exc
    session.commit()
    session.refresh(agent_run)
    return agent_run


@router.post(
    "/tasks/{task_id}/subagents/recover",
    response_model=SubagentRecoveryResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="恢复任务子 Agent",
    description="基于 Replay 状态恢复超时或卡住的子 Agent，并按需重新入队。",
)
def recover_task_subagents(
    task_id: str,
    request: SubagentRecoverRequest,
    session: DbSession,
    principal: Principal,
) -> SubagentRecoveryResponse:
    task = get_owned_task(task_id, session, principal.organization_id)
    replay_sequence, recovered, scanned_count = SubagentManager(session).recover_for_task(
        task=task,
        stale_after_seconds=request.stale_after_seconds,
        enqueue=request.enqueue,
    )
    response = SubagentRecoveryResponse(
        batch_id=f"manual-{uuid4()}",
        task_id=task.id,
        trigger="manual",
        replay_sequence=replay_sequence,
        stale_after_seconds=request.stale_after_seconds,
        enqueue=request.enqueue,
        scanned_count=scanned_count,
        recovered_count=len(recovered),
        action_counts=recovery_action_counts(recovered),
        recovered=recovered,
        completed_at=datetime.now(UTC),
    )
    persist_recovery_batch(
        session=session,
        organization_id=task.organization_id,
        payload={
            **response.model_dump(),
            "lock_acquired": True,
            "task_count": 1,
            "recovered_by_task": [
                {
                    "task_id": task.id,
                    "replay_sequence": replay_sequence,
                    "scanned_count": scanned_count,
                    "recovered_count": len(recovered),
                    "recovered": recovered,
                }
            ]
            if recovered
            else [],
        },
    )
    session.commit()
    return response


@router.get(
    "/tasks/{task_id}/subagents/recovery-batches",
    response_model=SubagentRecoveryBatchPage,
    summary="查询子 Agent 恢复批次",
    description="返回指定任务最近的子 Agent 恢复批次历史。",
)
def list_task_subagent_recovery_batches(
    task_id: str,
    session: DbSession,
    principal: Principal,
    limit: int = 20,
) -> SubagentRecoveryBatchPage:
    task = get_owned_task(task_id, session, principal.organization_id)
    capped_limit = max(1, min(limit, 100))
    statement = (
        select(SubagentRecoveryBatch)
        .where(
            SubagentRecoveryBatch.organization_id == principal.organization_id,
            SubagentRecoveryBatch.task_id == task.id,
        )
        .order_by(SubagentRecoveryBatch.completed_at.desc(), SubagentRecoveryBatch.id.desc())
        .limit(capped_limit)
    )
    return SubagentRecoveryBatchPage(items=list(session.execute(statement).scalars()))


@router.get(
    "/subagents/recovery/summary",
    response_model=SubagentRecoverySummaryResponse,
    summary="查询子 Agent 恢复运营摘要",
    description="按当前组织聚合最近的子 Agent 自动恢复与手动恢复批次，用于运营视图。",
)
def get_subagent_recovery_summary(
    session: DbSession,
    principal: Principal,
    limit: int = 20,
) -> SubagentRecoverySummaryResponse:
    capped_limit = max(1, min(limit, 100))
    statement = (
        select(SubagentRecoveryBatch)
        .where(SubagentRecoveryBatch.organization_id == principal.organization_id)
        .order_by(SubagentRecoveryBatch.completed_at.desc(), SubagentRecoveryBatch.id.desc())
        .limit(capped_limit)
    )
    batches = list(session.execute(statement).scalars())
    batch_ids = {batch.batch_id for batch in batches}
    task_ids = {batch.task_id for batch in batches if batch.task_id}
    action_counts: dict[str, int] = {}
    action_counted_batch_ids: set[str] = set()
    for batch in batches:
        if batch.batch_id in action_counted_batch_ids:
            continue
        action_counted_batch_ids.add(batch.batch_id)
        for action, count in (batch.action_counts or {}).items():
            action_counts[str(action)] = action_counts.get(str(action), 0) + int(count)
    task_summaries = _recovery_task_summaries(batches)
    return SubagentRecoverySummaryResponse(
        organization_id=principal.organization_id,
        batch_total=len(batch_ids),
        task_total=len(task_ids),
        scanned_total=sum(batch.scanned_count for batch in batches),
        recovered_total=sum(batch.recovered_count for batch in batches),
        lock_skipped_total=sum(1 for batch in batches if not batch.lock_acquired),
        action_counts=action_counts,
        latest_completed_at=batches[0].completed_at if batches else None,
        tasks=task_summaries,
        recent_batches=batches,
    )


def _recovery_task_summaries(
    batches: list[SubagentRecoveryBatch],
) -> list[SubagentRecoveryTaskSummary]:
    summaries: dict[str, dict] = {}
    for batch in batches:
        if not batch.task_id:
            continue
        summary = summaries.setdefault(
            batch.task_id,
            {
                "task_id": batch.task_id,
                "scanned_count": 0,
                "recovered_count": 0,
                "latest_batch_id": batch.batch_id,
                "latest_completed_at": batch.completed_at,
                "latest_replay_sequence": batch.replay_sequence,
            },
        )
        summary["scanned_count"] += batch.scanned_count
        summary["recovered_count"] += batch.recovered_count
        if batch.completed_at > summary["latest_completed_at"]:
            summary["latest_batch_id"] = batch.batch_id
            summary["latest_completed_at"] = batch.completed_at
            summary["latest_replay_sequence"] = batch.replay_sequence
    return [
        SubagentRecoveryTaskSummary(**summary)
        for summary in sorted(
            summaries.values(),
            key=lambda item: (item["recovered_count"], item["latest_completed_at"]),
            reverse=True,
        )
    ]


def get_owned_subagent(subagent_id: str, session: Session, principal: Principal) -> AgentRun:
    statement = (
        select(AgentRun)
        .join(Task, Task.id == AgentRun.task_id)
        .where(
            AgentRun.id == subagent_id,
            AgentRun.agent_type == "subagent",
            Task.organization_id == principal.organization_id,
        )
    )
    agent_run = session.execute(statement).scalar_one_or_none()
    if agent_run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="子 Agent 未找到")
    return agent_run


@router.get(
    "/subagents/{subagent_id}",
    response_model=SubagentResponse,
    summary="查询子 Agent 详情",
    description="返回单个子 Agent 的状态与上下文。",
)
def get_subagent(subagent_id: str, session: DbSession, principal: Principal) -> AgentRun:
    return get_owned_subagent(subagent_id, session, principal)


@router.post(
    "/subagents/{subagent_id}/cancel",
    response_model=SubagentResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="取消子 Agent",
    description="取消仍在运行或等待中的子 Agent。",
)
def cancel_subagent(subagent_id: str, session: DbSession, principal: Principal) -> AgentRun:
    agent_run = get_owned_subagent(subagent_id, session, principal)
    cancelled = SubagentManager(session).cancel(agent_run)
    session.commit()
    session.refresh(cancelled)
    return cancelled
