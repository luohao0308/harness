from __future__ import annotations

import hmac
import json
import re
import secrets
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.agents.planner import PLANNER_PROMPT_VERSION, DeterministicPlanner
from app.agents.registry import ensure_default_agents
from app.api.schemas import (
    AgentTriggerCreateRequest,
    AgentTriggerCreateResponse,
    AgentTriggerPage,
    AgentTriggerResponse,
    AgentTriggerUpdateRequest,
    WebhookTriggerRequest,
    WebhookTriggerResponse,
)
from app.db.models import Agent, ExecutionPlan, Task, Trigger, utc_now
from app.db.session import get_db_session
from app.events.event_store import EventStore
from app.events.event_types import EventType
from app.security.auth import Principal, require_permission_value
from app.security.jwt_utils import hash_api_key
from app.security.rbac import Permission

router = APIRouter(tags=["triggers"])
DbSession = Annotated[Session, Depends(get_db_session)]

_ENDPOINT_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{2,127}$")
_MAX_PAYLOAD_PREVIEW = 1200


@router.get(
    "/agents/{agent_id}/triggers",
    response_model=AgentTriggerPage,
    summary="List Agent triggers",
)
def list_agent_triggers(
    agent_id: str,
    session: DbSession,
    principal: Principal,
) -> AgentTriggerPage:
    require_permission_value(principal, Permission.AGENT_READ)
    _owned_agent(agent_id=agent_id, session=session, principal=principal)
    items = list(
        session.execute(
            select(Trigger)
            .where(
                Trigger.organization_id == principal.organization_id,
                Trigger.agent_id == agent_id,
            )
            .order_by(Trigger.created_at.desc(), Trigger.id.asc())
        ).scalars()
    )
    return AgentTriggerPage(items=[_trigger_response(item) for item in items])


@router.post(
    "/agents/{agent_id}/triggers",
    response_model=AgentTriggerCreateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create Agent trigger",
)
def create_agent_trigger(
    agent_id: str,
    payload: AgentTriggerCreateRequest,
    session: DbSession,
    principal: Principal,
) -> AgentTriggerCreateResponse:
    require_permission_value(principal, Permission.AGENT_CREATE)
    _owned_agent(agent_id=agent_id, session=session, principal=principal)
    endpoint_path = _normalize_endpoint_path(payload.endpoint_path, agent_id=agent_id)
    secret = f"htrg_{secrets.token_urlsafe(32)}"
    now = utc_now()
    trigger = Trigger(
        organization_id=principal.organization_id,
        agent_id=agent_id,
        type=payload.type,
        endpoint_path=endpoint_path,
        secret_hash=hash_api_key(secret),
        enabled=payload.enabled,
        created_by=principal.user_id,
        created_at=now,
        updated_at=now,
    )
    session.add(trigger)
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Trigger endpoint path already exists",
        ) from exc
    session.refresh(trigger)
    return AgentTriggerCreateResponse(trigger=_trigger_response(trigger), secret=secret)


@router.patch(
    "/agents/{agent_id}/triggers/{trigger_id}",
    response_model=AgentTriggerResponse,
    summary="Update Agent trigger",
)
def update_agent_trigger(
    agent_id: str,
    trigger_id: str,
    payload: AgentTriggerUpdateRequest,
    session: DbSession,
    principal: Principal,
) -> AgentTriggerResponse:
    require_permission_value(principal, Permission.AGENT_CREATE)
    _owned_agent(agent_id=agent_id, session=session, principal=principal)
    trigger = _owned_trigger(
        agent_id=agent_id,
        trigger_id=trigger_id,
        session=session,
        organization_id=principal.organization_id,
    )
    if payload.enabled is not None:
        trigger.enabled = payload.enabled
    trigger.updated_at = utc_now()
    session.commit()
    session.refresh(trigger)
    return _trigger_response(trigger)


@router.delete(
    "/agents/{agent_id}/triggers/{trigger_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete Agent trigger",
)
def delete_agent_trigger(
    agent_id: str,
    trigger_id: str,
    session: DbSession,
    principal: Principal,
) -> None:
    require_permission_value(principal, Permission.AGENT_DELETE)
    _owned_agent(agent_id=agent_id, session=session, principal=principal)
    trigger = _owned_trigger(
        agent_id=agent_id,
        trigger_id=trigger_id,
        session=session,
        organization_id=principal.organization_id,
    )
    session.delete(trigger)
    session.commit()
    return None


@router.post(
    "/webhook/trigger/{endpoint_path}",
    response_model=WebhookTriggerResponse,
    summary="Invoke public webhook trigger",
)
async def invoke_webhook_trigger(
    endpoint_path: str,
    request_payload: WebhookTriggerRequest,
    request: Request,
    session: DbSession,
    x_harness_trigger_secret: Annotated[str | None, Header()] = None,
) -> WebhookTriggerResponse:
    trigger = session.execute(
        select(Trigger).where(Trigger.endpoint_path == endpoint_path)
    ).scalar_one_or_none()
    if trigger is None or not trigger.enabled:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Trigger not found")
    supplied_secret = (x_harness_trigger_secret or "").strip()
    if not supplied_secret or not hmac.compare_digest(
        hash_api_key(supplied_secret),
        trigger.secret_hash,
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid trigger secret",
        )
    agent = session.execute(
        select(Agent).where(
            Agent.id == trigger.agent_id,
            or_(
                Agent.organization_id == trigger.organization_id,
                Agent.organization_id.is_(None),
            ),
        )
    ).scalar_one_or_none()
    if agent is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found")
    run = _create_trigger_plan_run(
        trigger=trigger,
        agent=agent,
        request_payload=request_payload,
        source_host=request.client.host if request.client else None,
        session=session,
    )
    trigger.last_triggered_at = utc_now()
    trigger.updated_at = utc_now()
    session.commit()
    return WebhookTriggerResponse(
        run_id=run.id,
        agent_id=agent.id,
        status=run.status,
        trigger_id=trigger.id,
    )


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


def _owned_trigger(
    *,
    agent_id: str,
    trigger_id: str,
    session: Session,
    organization_id: str,
) -> Trigger:
    trigger = session.execute(
        select(Trigger).where(
            Trigger.id == trigger_id,
            Trigger.agent_id == agent_id,
            Trigger.organization_id == organization_id,
        )
    ).scalar_one_or_none()
    if trigger is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Trigger not found")
    return trigger


def _normalize_endpoint_path(value: str | None, *, agent_id: str) -> str:
    endpoint_path = (value or f"{agent_id}-{secrets.token_hex(4)}").strip().lower()
    endpoint_path = re.sub(r"[^a-z0-9-]+", "-", endpoint_path).strip("-")
    if not _ENDPOINT_PATTERN.fullmatch(endpoint_path):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="endpoint_path must use lowercase letters, numbers, and hyphens",
        )
    return endpoint_path


def _trigger_response(trigger: Trigger) -> AgentTriggerResponse:
    return AgentTriggerResponse.model_validate(trigger)


def _create_trigger_plan_run(
    *,
    trigger: Trigger,
    agent: Agent,
    request_payload: WebhookTriggerRequest,
    source_host: str | None,
    session: Session,
) -> Task:
    now = utc_now()
    goal = _run_goal(request_payload)
    run = Task(
        organization_id=trigger.organization_id,
        agent_id=agent.id,
        created_by=f"trigger:{trigger.id}",
        title=request_payload.title or f"Webhook trigger {trigger.endpoint_path}",
        goal=goal,
        status="CREATED",
        model_provider=agent.model_provider or "default",
        model_name=agent.model_name or "default",
        max_runtime_seconds=1800,
        max_subagents=5,
        enable_sandbox=True,
        enable_network=False,
        created_at=now,
        updated_at=now,
    )
    session.add(run)
    session.flush()
    event_store = EventStore(session)
    event_store.append(
        task_id=run.id,
        event_type=EventType.TASK_CREATED,
        payload_json={
            "task_id": run.id,
            "title": run.title,
            "goal": run.goal,
            "agent_id": agent.id,
            "mode": "webhook_trigger",
            "trigger_id": trigger.id,
        },
        actor_type="trigger",
        actor_id=trigger.id,
    )
    event_store.append(
        task_id=run.id,
        event_type=EventType.TRIGGER_INVOKED,
        payload_json={
            "trigger_id": trigger.id,
            "endpoint_path": trigger.endpoint_path,
            "agent_id": agent.id,
            "source_host": source_host,
            "payload_keys": sorted(request_payload.payload.keys()),
        },
        actor_type="trigger",
        actor_id=trigger.id,
    )
    run.status = "PLANNING"
    run.updated_at = utc_now()
    event_store.append(
        task_id=run.id,
        event_type=EventType.PLAN_REQUESTED,
        payload_json={
            "task_id": run.id,
            "goal": run.goal,
            "agent_id": agent.id,
            "mode": "webhook_trigger",
            "prompt_version": PLANNER_PROMPT_VERSION,
        },
        actor_type="trigger",
        actor_id=trigger.id,
    )
    plan = DeterministicPlanner().create_plan(run)
    plan_row = ExecutionPlan(
        task_id=run.id,
        version=1,
        status="GENERATED",
        plan_json=plan.model_dump(),
        created_at=utc_now(),
    )
    session.add(plan_row)
    session.flush()
    event_store.append(
        task_id=run.id,
        event_type=EventType.PLAN_GENERATED,
        payload_json={
            "plan_id": plan_row.id,
            "plan": plan.model_dump(),
            "agent_id": agent.id,
            "mode": "webhook_trigger",
            "prompt_version": PLANNER_PROMPT_VERSION,
            "trace_summary": "Webhook trigger created a planned Agent Run.",
        },
        actor_type="trigger",
        actor_id=trigger.id,
    )
    run.status = "PLANNED"
    run.updated_at = utc_now()
    session.flush()
    return run


def _run_goal(request_payload: WebhookTriggerRequest) -> str:
    base_goal = (request_payload.goal or "Handle webhook trigger payload").strip()
    if not request_payload.payload:
        return base_goal
    preview = json.dumps(
        request_payload.payload,
        ensure_ascii=False,
        sort_keys=True,
        default=str,
    )
    if len(preview) > _MAX_PAYLOAD_PREVIEW:
        preview = preview[: _MAX_PAYLOAD_PREVIEW - 3] + "..."
    return f"{base_goal}\n\nWebhook payload preview:\n{preview}"
