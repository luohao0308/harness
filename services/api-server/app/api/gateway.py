from __future__ import annotations

import hmac
import json
import re
import secrets
import time
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.agents.planner import PLANNER_PROMPT_VERSION, DeterministicPlanner
from app.agents.registry import ensure_default_agents
from app.api.schemas import (
    AgentGatewayRouteCreateRequest,
    AgentGatewayRouteCreateResponse,
    AgentGatewayRoutePage,
    AgentGatewayRouteResponse,
    AgentGatewayRouteUpdateRequest,
    GatewayInvokeRequest,
    GatewayInvokeResponse,
)
from app.db.models import Agent, ApiGatewayRoute, ExecutionPlan, Task, utc_now
from app.db.session import get_db_session
from app.events.event_store import EventStore
from app.events.event_types import EventType
from app.security.auth import Principal, require_permission_value
from app.security.jwt_utils import hash_api_key
from app.security.rbac import Permission

router = APIRouter(tags=["api-gateway"])
DbSession = Annotated[Session, Depends(get_db_session)]

_SLUG_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{2,127}$")
_MAX_INPUT_PREVIEW = 1200
_RATE_WINDOW_SECONDS = 60
_rate_buckets: dict[str, list[float]] = {}


@router.get(
    "/agents/{agent_id}/gateway-routes",
    response_model=AgentGatewayRoutePage,
    summary="List Agent API Gateway routes",
)
def list_agent_gateway_routes(
    agent_id: str,
    session: DbSession,
    principal: Principal,
) -> AgentGatewayRoutePage:
    require_permission_value(principal, Permission.AGENT_READ)
    _owned_agent(agent_id=agent_id, session=session, principal=principal)
    items = list(
        session.execute(
            select(ApiGatewayRoute)
            .where(
                ApiGatewayRoute.organization_id == principal.organization_id,
                ApiGatewayRoute.agent_id == agent_id,
            )
            .order_by(ApiGatewayRoute.created_at.desc(), ApiGatewayRoute.id.asc())
        ).scalars()
    )
    return AgentGatewayRoutePage(items=[_route_response(item) for item in items])


@router.post(
    "/agents/{agent_id}/gateway-routes",
    response_model=AgentGatewayRouteCreateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create Agent API Gateway route",
)
def create_agent_gateway_route(
    agent_id: str,
    payload: AgentGatewayRouteCreateRequest,
    session: DbSession,
    principal: Principal,
) -> AgentGatewayRouteCreateResponse:
    require_permission_value(principal, Permission.AGENT_CREATE)
    _owned_agent(agent_id=agent_id, session=session, principal=principal)
    slug = _normalize_slug(payload.slug, agent_id=agent_id)
    api_key = f"hgw_{secrets.token_urlsafe(32)}"
    now = utc_now()
    route = ApiGatewayRoute(
        organization_id=principal.organization_id,
        agent_id=agent_id,
        slug=slug,
        api_key_hash=hash_api_key(api_key),
        rate_limit=payload.rate_limit,
        enabled=payload.enabled,
        description=payload.description.strip(),
        created_by=principal.user_id,
        created_at=now,
        updated_at=now,
    )
    session.add(route)
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="API Gateway route slug already exists",
        ) from exc
    session.refresh(route)
    return AgentGatewayRouteCreateResponse(route=_route_response(route), api_key=api_key)


@router.patch(
    "/agents/{agent_id}/gateway-routes/{route_id}",
    response_model=AgentGatewayRouteResponse,
    summary="Update Agent API Gateway route",
)
def update_agent_gateway_route(
    agent_id: str,
    route_id: str,
    payload: AgentGatewayRouteUpdateRequest,
    session: DbSession,
    principal: Principal,
) -> AgentGatewayRouteResponse:
    require_permission_value(principal, Permission.AGENT_CREATE)
    _owned_agent(agent_id=agent_id, session=session, principal=principal)
    route = _owned_route(
        agent_id=agent_id,
        route_id=route_id,
        session=session,
        organization_id=principal.organization_id,
    )
    if payload.description is not None:
        route.description = payload.description.strip()
    if payload.rate_limit is not None:
        route.rate_limit = payload.rate_limit
        _rate_buckets.pop(route.id, None)
    if payload.enabled is not None:
        route.enabled = payload.enabled
    route.updated_at = utc_now()
    session.commit()
    session.refresh(route)
    return _route_response(route)


@router.delete(
    "/agents/{agent_id}/gateway-routes/{route_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete Agent API Gateway route",
)
def delete_agent_gateway_route(
    agent_id: str,
    route_id: str,
    session: DbSession,
    principal: Principal,
) -> None:
    require_permission_value(principal, Permission.AGENT_DELETE)
    _owned_agent(agent_id=agent_id, session=session, principal=principal)
    route = _owned_route(
        agent_id=agent_id,
        route_id=route_id,
        session=session,
        organization_id=principal.organization_id,
    )
    _rate_buckets.pop(route.id, None)
    session.delete(route)
    session.commit()
    return None


@router.post(
    "/gateway/{slug}/invoke",
    response_model=GatewayInvokeResponse,
    summary="Invoke published Agent API Gateway route",
)
async def invoke_gateway_route(
    slug: str,
    request_payload: GatewayInvokeRequest,
    request: Request,
    session: DbSession,
    x_harness_gateway_key: Annotated[str | None, Header()] = None,
) -> GatewayInvokeResponse:
    route = session.execute(
        select(ApiGatewayRoute).where(ApiGatewayRoute.slug == slug)
    ).scalar_one_or_none()
    if route is None or not route.enabled:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Gateway route not found")
    supplied_key = (x_harness_gateway_key or "").strip()
    if not supplied_key or not hmac.compare_digest(hash_api_key(supplied_key), route.api_key_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid gateway key")
    if not _consume_rate_limit(route):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Gateway rate limit exceeded",
        )
    agent = session.execute(
        select(Agent).where(
            Agent.id == route.agent_id,
            or_(
                Agent.organization_id == route.organization_id,
                Agent.organization_id.is_(None),
            ),
        )
    ).scalar_one_or_none()
    if agent is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found")
    run = _create_gateway_plan_run(
        route=route,
        agent=agent,
        request_payload=request_payload,
        source_host=request.client.host if request.client else None,
        session=session,
    )
    route.last_invoked_at = utc_now()
    route.updated_at = utc_now()
    session.commit()
    return GatewayInvokeResponse(
        run_id=run.id,
        agent_id=agent.id,
        status=run.status,
        route_id=route.id,
        slug=route.slug,
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


def _owned_route(
    *,
    agent_id: str,
    route_id: str,
    session: Session,
    organization_id: str,
) -> ApiGatewayRoute:
    route = session.execute(
        select(ApiGatewayRoute).where(
            ApiGatewayRoute.id == route_id,
            ApiGatewayRoute.agent_id == agent_id,
            ApiGatewayRoute.organization_id == organization_id,
        )
    ).scalar_one_or_none()
    if route is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Gateway route not found")
    return route


def _normalize_slug(value: str | None, *, agent_id: str) -> str:
    slug = (value or f"{agent_id}-{secrets.token_hex(4)}").strip().lower()
    slug = re.sub(r"[^a-z0-9-]+", "-", slug).strip("-")
    if not _SLUG_PATTERN.fullmatch(slug):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="slug must use lowercase letters, numbers, and hyphens",
        )
    return slug


def _route_response(route: ApiGatewayRoute) -> AgentGatewayRouteResponse:
    return AgentGatewayRouteResponse.model_validate(route)


def _consume_rate_limit(route: ApiGatewayRoute) -> bool:
    now = time.monotonic()
    cutoff = now - _RATE_WINDOW_SECONDS
    bucket = [stamp for stamp in _rate_buckets.get(route.id, []) if stamp >= cutoff]
    if len(bucket) >= route.rate_limit:
        _rate_buckets[route.id] = bucket
        return False
    bucket.append(now)
    _rate_buckets[route.id] = bucket
    return True


def reset_gateway_rate_limiter() -> None:
    _rate_buckets.clear()


def _create_gateway_plan_run(
    *,
    route: ApiGatewayRoute,
    agent: Agent,
    request_payload: GatewayInvokeRequest,
    source_host: str | None,
    session: Session,
) -> Task:
    now = utc_now()
    goal = _run_goal(request_payload)
    run = Task(
        organization_id=route.organization_id,
        agent_id=agent.id,
        created_by=f"api_gateway:{route.id}",
        title=request_payload.title or f"API Gateway {route.slug}",
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
            "mode": "api_gateway",
            "route_id": route.id,
            "slug": route.slug,
        },
        actor_type="api_gateway",
        actor_id=route.id,
    )
    event_store.append(
        task_id=run.id,
        event_type=EventType.API_GATEWAY_INVOKED,
        payload_json={
            "route_id": route.id,
            "slug": route.slug,
            "agent_id": agent.id,
            "rate_limit": route.rate_limit,
            "source_host": source_host,
            "input_keys": sorted(request_payload.input.keys()),
        },
        actor_type="api_gateway",
        actor_id=route.id,
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
            "mode": "api_gateway",
            "prompt_version": PLANNER_PROMPT_VERSION,
        },
        actor_type="api_gateway",
        actor_id=route.id,
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
            "mode": "api_gateway",
            "prompt_version": PLANNER_PROMPT_VERSION,
            "trace_summary": "API Gateway created a planned Agent Run.",
        },
        actor_type="api_gateway",
        actor_id=route.id,
    )
    run.status = "PLANNED"
    run.updated_at = utc_now()
    session.flush()
    return run


def _run_goal(request_payload: GatewayInvokeRequest) -> str:
    base_goal = (request_payload.goal or "Handle API Gateway invocation").strip()
    if not request_payload.input:
        return base_goal
    preview = json.dumps(
        request_payload.input,
        ensure_ascii=False,
        sort_keys=True,
        default=str,
    )
    if len(preview) > _MAX_INPUT_PREVIEW:
        preview = preview[: _MAX_INPUT_PREVIEW - 3] + "..."
    return f"{base_goal}\n\nGateway input preview:\n{preview}"
