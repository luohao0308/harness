from datetime import UTC, datetime
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.subagent_manager import SubagentLimitExceededError, SubagentManager
from app.api.schemas import (
    SubagentCreateRequest,
    SubagentPage,
    SubagentRecoverRequest,
    SubagentRecoveryResponse,
    SubagentResponse,
)
from app.api.tasks import get_owned_task
from app.db.models import AgentRun, Task
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
    session.commit()
    return SubagentRecoveryResponse(
        batch_id=f"manual-{uuid4()}",
        task_id=task.id,
        trigger="manual",
        replay_sequence=replay_sequence,
        stale_after_seconds=request.stale_after_seconds,
        enqueue=request.enqueue,
        scanned_count=scanned_count,
        recovered_count=len(recovered),
        action_counts=_recovery_action_counts(recovered),
        recovered=recovered,
        completed_at=datetime.now(UTC),
    )


def _recovery_action_counts(recovered: list[dict]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in recovered:
        action = str(item.get("action") or "unknown")
        counts[action] = counts.get(action, 0) + 1
    return counts


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
