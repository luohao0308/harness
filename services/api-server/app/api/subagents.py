from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.subagent_manager import SubagentManager
from app.api.schemas import SubagentPage, SubagentResponse
from app.db.models import AgentRun
from app.db.session import get_db_session

router = APIRouter(tags=["subagents"])
DbSession = Annotated[Session, Depends(get_db_session)]


@router.get("/tasks/{task_id}/subagents", response_model=SubagentPage)
def list_task_subagents(task_id: str, session: DbSession) -> SubagentPage:
    statement = (
        select(AgentRun)
        .where(AgentRun.task_id == task_id, AgentRun.agent_type == "subagent")
        .order_by(AgentRun.started_at.asc().nullsfirst(), AgentRun.id.asc())
    )
    return SubagentPage(items=list(session.execute(statement).scalars()))


@router.get("/subagents/{subagent_id}", response_model=SubagentResponse)
def get_subagent(subagent_id: str, session: DbSession) -> AgentRun:
    agent_run = session.get(AgentRun, subagent_id)
    if agent_run is None or agent_run.agent_type != "subagent":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Subagent not found")
    return agent_run


@router.post(
    "/subagents/{subagent_id}/cancel",
    response_model=SubagentResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def cancel_subagent(subagent_id: str, session: DbSession) -> AgentRun:
    agent_run = session.get(AgentRun, subagent_id)
    if agent_run is None or agent_run.agent_type != "subagent":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Subagent not found")
    cancelled = SubagentManager(session).cancel(agent_run)
    session.commit()
    session.refresh(cancelled)
    return cancelled
