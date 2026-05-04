from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.schemas import TaskCreateRequest, TaskPage, TaskResponse
from app.db.models import Task, utc_now
from app.db.session import get_db_session
from app.events.event_store import EventStore
from app.events.event_types import EventType

router = APIRouter(prefix="/tasks", tags=["tasks"])
DbSession = Annotated[Session, Depends(get_db_session)]


@router.post("", response_model=TaskResponse, status_code=status.HTTP_201_CREATED)
def create_task(
    request: TaskCreateRequest,
    session: DbSession,
) -> Task:
    task = Task(
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
    status_filter: Annotated[str | None, Query(alias="status")] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> TaskPage:
    statement = select(Task)
    if status_filter is not None:
        statement = statement.where(Task.status == status_filter)
    statement = statement.order_by(Task.created_at.desc()).limit(limit)
    tasks = list(session.execute(statement).scalars())
    return TaskPage(items=tasks)


@router.get("/{task_id}", response_model=TaskResponse)
def get_task(task_id: str, session: DbSession) -> Task:
    task = session.get(Task, task_id)
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    return task
