from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.schemas import SandboxPage, SandboxResponse, WarmPoolResponse
from app.db.models import SandboxInstance, Task
from app.db.session import get_db_session
from app.sandbox.docker_manager import DockerManager
from app.sandbox.warm_pool import WarmPoolManager
from app.security.auth import Principal

router = APIRouter(tags=["sandboxes"])
DbSession = Annotated[Session, Depends(get_db_session)]

docker_manager = DockerManager()
warm_pool_manager = WarmPoolManager(docker_manager=docker_manager)


@router.get("/sandboxes", response_model=SandboxPage)
def list_sandboxes(session: DbSession, principal: Principal) -> SandboxPage:
    statement = (
        select(SandboxInstance)
        .join(Task, Task.id == SandboxInstance.task_id)
        .where(Task.organization_id == principal.organization_id)
        .order_by(SandboxInstance.created_at.desc())
    )
    return SandboxPage(items=list(session.execute(statement).scalars()))


@router.get("/sandboxes/warm-pool", response_model=WarmPoolResponse)
def get_warm_pool(session: DbSession, principal: Principal) -> WarmPoolResponse:
    _ = principal
    return WarmPoolResponse.model_validate(warm_pool_manager.status(session=session).__dict__)


def get_owned_sandbox(sandbox_id: str, session: Session, principal: Principal) -> SandboxInstance:
    statement = (
        select(SandboxInstance)
        .join(Task, Task.id == SandboxInstance.task_id)
        .where(
            SandboxInstance.id == sandbox_id,
            Task.organization_id == principal.organization_id,
        )
    )
    sandbox = session.execute(statement).scalar_one_or_none()
    if sandbox is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sandbox not found")
    return sandbox


@router.get("/sandboxes/{sandbox_id}", response_model=SandboxResponse)
def get_sandbox(sandbox_id: str, session: DbSession, principal: Principal) -> SandboxInstance:
    return get_owned_sandbox(sandbox_id, session, principal)


@router.post(
    "/sandboxes/{sandbox_id}/terminate",
    response_model=SandboxResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def terminate_sandbox(sandbox_id: str, session: DbSession, principal: Principal) -> SandboxInstance:
    sandbox = get_owned_sandbox(sandbox_id, session, principal)
    terminated = docker_manager.destroy_sandbox(session=session, sandbox=sandbox)
    session.commit()
    session.refresh(terminated)
    return terminated
