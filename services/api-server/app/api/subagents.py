from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.subagent_manager import SubagentManager
from app.api.schemas import SubagentPage, SubagentResponse
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
