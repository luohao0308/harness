from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.agents.registry import ensure_default_agents
from app.api.schemas import (
    AgentVersionCreateRequest,
    AgentVersionPage,
    AgentVersionResponse,
)
from app.db.models import Agent, AgentVersion, utc_now
from app.db.session import get_db_session
from app.security.auth import Principal, require_permission_value
from app.security.rbac import Permission

router = APIRouter(tags=["agent-versions"])
DbSession = Annotated[Session, Depends(get_db_session)]

_SNAPSHOT_FIELDS = (
    "id",
    "name",
    "description",
    "role",
    "status",
    "model_provider",
    "model_name",
    "system_prompt",
    "tools_json",
    "routing_tags",
    "max_parallel_assignments",
)


@router.get(
    "/agents/{agent_id}/versions",
    response_model=AgentVersionPage,
    summary="List Agent versions",
)
def list_agent_versions(
    agent_id: str,
    session: DbSession,
    principal: Principal,
) -> AgentVersionPage:
    require_permission_value(principal, Permission.AGENT_READ)
    _owned_agent(agent_id=agent_id, session=session, principal=principal)
    versions = list(
        session.execute(
            select(AgentVersion)
            .where(
                AgentVersion.organization_id == principal.organization_id,
                AgentVersion.agent_id == agent_id,
            )
            .order_by(AgentVersion.version_number.desc(), AgentVersion.created_at.desc())
        ).scalars()
    )
    return AgentVersionPage(items=[_version_response(version) for version in versions])


@router.post(
    "/agents/{agent_id}/versions",
    response_model=AgentVersionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create Agent version snapshot",
)
def create_agent_version(
    agent_id: str,
    request: AgentVersionCreateRequest,
    session: DbSession,
    principal: Principal,
) -> AgentVersionResponse:
    require_permission_value(principal, Permission.AGENT_CREATE)
    agent = _owned_agent(agent_id=agent_id, session=session, principal=principal)
    next_number = _next_version_number(
        agent_id=agent_id,
        session=session,
        organization_id=principal.organization_id,
    )
    if request.activate:
        _mark_versions_inactive(
            agent_id=agent_id,
            session=session,
            organization_id=principal.organization_id,
        )
    version = AgentVersion(
        organization_id=principal.organization_id,
        agent_id=agent_id,
        version_number=next_number,
        config_snapshot=_agent_config_snapshot(agent),
        created_by=principal.user_id,
        created_at=utc_now(),
        is_active=request.activate,
    )
    session.add(version)
    agent.updated_at = utc_now()
    session.commit()
    session.refresh(version)
    return _version_response(version)


@router.patch(
    "/agents/{agent_id}/versions/{version_id}/activate",
    response_model=AgentVersionResponse,
    summary="Activate Agent version",
)
def activate_agent_version(
    agent_id: str,
    version_id: str,
    session: DbSession,
    principal: Principal,
) -> AgentVersionResponse:
    require_permission_value(principal, Permission.AGENT_CREATE)
    agent = _owned_agent(agent_id=agent_id, session=session, principal=principal)
    version = session.execute(
        select(AgentVersion).where(
            AgentVersion.id == version_id,
            AgentVersion.agent_id == agent_id,
            AgentVersion.organization_id == principal.organization_id,
        )
    ).scalar_one_or_none()
    if version is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent version not found")
    _apply_snapshot(agent, version.config_snapshot)
    _mark_versions_inactive(
        agent_id=agent_id,
        session=session,
        organization_id=principal.organization_id,
    )
    version.is_active = True
    agent.updated_at = utc_now()
    session.commit()
    session.refresh(version)
    return _version_response(version)


def _owned_agent(*, agent_id: str, session: Session, principal: Principal) -> Agent:
    ensure_default_agents(session, principal.organization_id)
    session.flush()
    agent = session.execute(
        select(Agent).where(
            Agent.id == agent_id,
            or_(
                Agent.organization_id == principal.organization_id,
                Agent.organization_id.is_(None),
            ),
        )
    ).scalar_one_or_none()
    if agent is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found")
    return agent


def _next_version_number(*, agent_id: str, session: Session, organization_id: str) -> int:
    current = session.execute(
        select(func.max(AgentVersion.version_number)).where(
            AgentVersion.organization_id == organization_id,
            AgentVersion.agent_id == agent_id,
        )
    ).scalar_one_or_none()
    return int(current or 0) + 1


def _mark_versions_inactive(*, agent_id: str, session: Session, organization_id: str) -> None:
    versions = session.execute(
        select(AgentVersion).where(
            AgentVersion.organization_id == organization_id,
            AgentVersion.agent_id == agent_id,
            AgentVersion.is_active.is_(True),
        )
    ).scalars()
    for version in versions:
        version.is_active = False


def _agent_config_snapshot(agent: Agent) -> dict:
    snapshot = {field: getattr(agent, field) for field in _SNAPSHOT_FIELDS}
    snapshot["tools_json"] = list(agent.tools_json or [])
    snapshot["routing_tags"] = list(agent.routing_tags or [])
    return snapshot


def _apply_snapshot(agent: Agent, snapshot: dict) -> None:
    for field in _SNAPSHOT_FIELDS:
        if field == "id" or field not in snapshot:
            continue
        value = snapshot[field]
        if field in {"tools_json", "routing_tags"}:
            value = list(value or [])
        setattr(agent, field, value)


def _version_response(version: AgentVersion) -> AgentVersionResponse:
    return AgentVersionResponse.model_validate(version)
