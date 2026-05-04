from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.executor import Executor
from app.api.schemas import TaskCreateRequest, TaskPage, TaskResponse
from app.db.models import Task, utc_now
from app.db.session import get_db_session
from app.events.event_store import EventStore
from app.events.event_types import EventType
from app.observability.metrics import agent_tasks_running, agent_tasks_total
from app.security.auth import Principal

router = APIRouter(prefix="/tasks", tags=["tasks"])
DbSession = Annotated[Session, Depends(get_db_session)]


def get_owned_task(task_id: str, session: Session, organization_id: str) -> Task:
    task = session.execute(
        select(Task).where(Task.id == task_id, Task.organization_id == organization_id)
    ).scalar_one_or_none()
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    return task


@router.post("", response_model=TaskResponse, status_code=status.HTTP_201_CREATED)
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


@router.get("", response_model=TaskPage)
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


@router.get("/{task_id}", response_model=TaskResponse)
def get_task(task_id: str, session: DbSession, principal: Principal) -> Task:
    return get_owned_task(task_id, session, principal.organization_id)


@router.post("/{task_id}/start", response_model=TaskResponse, status_code=status.HTTP_202_ACCEPTED)
def start_task(task_id: str, session: DbSession, principal: Principal) -> Task:
    task = get_owned_task(task_id, session, principal.organization_id)
    if task.status not in {"CREATED", "FAILED"}:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Task cannot be started")

    started = Executor(session).start_task(task)
    if started.status == "RUNNING":
        agent_tasks_running.inc()
    session.commit()
    session.refresh(started)
    return started
