from __future__ import annotations

import hmac
import re
import secrets
import subprocess
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.agents.registry import ensure_default_agents
from app.api.schemas import (
    AgentTriggerCreateRequest,
    AgentTriggerCreateResponse,
    AgentTriggerPage,
    AgentTriggerResponse,
    AgentTriggerUpdateRequest,
    TriggerInvocationPage,
    TriggerInvocationResponse,
    WebhookTriggerRequest,
    WebhookTriggerResponse,
)
from app.core.config import get_settings
from app.db.models import Agent, Task, Trigger, TriggerInvocation, utc_now
from app.db.session import get_db_session
from app.local_runtime.workspace_authorization import WORKSPACE_AUTHORIZATION_STORE
from app.security.auth import Principal, require_permission_value
from app.security.jwt_utils import hash_api_key
from app.security.rbac import Permission
from app.triggers.service import TriggerInvocationRejected, create_trigger_invocation

router = APIRouter(tags=["triggers"])
DbSession = Annotated[Session, Depends(get_db_session)]

_ENDPOINT_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{2,127}$")


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
                Trigger.deleted_at.is_(None),
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
    if payload.type in {"schedule", "file", "git"} and get_settings().runtime_profile != "local":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"{payload.type} triggers are only available in the local runtime profile",
        )
    config_json = _validated_runtime_config(payload, principal=principal)
    endpoint_path = (
        _normalize_endpoint_path(payload.endpoint_path, agent_id=agent_id)
        if payload.type == "webhook"
        else None
    )
    secret = f"htrg_{secrets.token_urlsafe(32)}" if payload.type == "webhook" else None
    now = utc_now()
    trigger = Trigger(
        organization_id=principal.organization_id,
        agent_id=agent_id,
        type=payload.type,
        name=payload.name or endpoint_path or payload.type,
        config_json=config_json,
        runtime_state_json={},
        endpoint_path=endpoint_path,
        secret_hash=hash_api_key(secret) if secret is not None else None,
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
    if payload.name is not None:
        trigger.name = payload.name
    if payload.config_json is not None:
        validated = AgentTriggerCreateRequest(
            type=trigger.type,
            name=trigger.name,
            config_json=payload.config_json,
            endpoint_path=trigger.endpoint_path,
            enabled=trigger.enabled,
        )
        if (
            trigger.type in {"schedule", "file", "git"}
            and get_settings().runtime_profile != "local"
        ):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"{trigger.type} triggers are only available in the local runtime profile",
            )
        trigger.config_json = _validated_runtime_config(validated, principal=principal)
        trigger.runtime_state_json = {}
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
    trigger.deleted_at = utc_now()
    trigger.enabled = False
    trigger.updated_at = utc_now()
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
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> WebhookTriggerResponse:
    if not get_settings().trigger_automation_enabled:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Trigger automation is disabled",
        )
    trigger = session.execute(
        select(Trigger).where(Trigger.endpoint_path == endpoint_path)
    ).scalar_one_or_none()
    if (
        trigger is None
        or trigger.deleted_at is not None
        or not trigger.enabled
        or trigger.type != "webhook"
    ):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Trigger not found")
    supplied_secret = (x_harness_trigger_secret or "").strip()
    if not supplied_secret or not hmac.compare_digest(
        hash_api_key(supplied_secret),
        trigger.secret_hash or "",
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid trigger secret",
        )
    try:
        invocation, _created = create_trigger_invocation(
            trigger=trigger,
            idempotency_key=idempotency_key,
            source="webhook",
            payload_summary={
                "payload": request_payload.payload,
                "source_host": request.client.host if request.client else None,
            },
            goal=request_payload.goal,
            title=request_payload.title,
            session=session,
        )
    except TriggerInvocationRejected as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    run = session.get(Task, invocation.run_id) if invocation.run_id else None
    if run is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Trigger invocation has no Run",
        )
    session.commit()
    return WebhookTriggerResponse(
        run_id=run.id,
        agent_id=trigger.agent_id,
        status=run.status,
        trigger_id=trigger.id,
        invocation_id=invocation.id,
    )


@router.get(
    "/agents/{agent_id}/triggers/{trigger_id}/invocations",
    response_model=TriggerInvocationPage,
)
def list_trigger_invocations(
    agent_id: str,
    trigger_id: str,
    session: DbSession,
    principal: Principal,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> TriggerInvocationPage:
    require_permission_value(principal, Permission.AGENT_READ)
    _owned_agent(agent_id=agent_id, session=session, principal=principal)
    _owned_trigger(
        agent_id=agent_id,
        trigger_id=trigger_id,
        session=session,
        organization_id=principal.organization_id,
        include_deleted=True,
    )
    items = list(
        session.execute(
            select(TriggerInvocation)
            .where(
                TriggerInvocation.trigger_id == trigger_id,
                TriggerInvocation.organization_id == principal.organization_id,
            )
            .order_by(TriggerInvocation.created_at.desc(), TriggerInvocation.id.desc())
            .limit(limit)
        ).scalars()
    )
    return TriggerInvocationPage(
        items=[_invocation_response(item, session=session) for item in items]
    )


@router.get(
    "/agents/{agent_id}/triggers/{trigger_id}/invocations/{invocation_id}",
    response_model=TriggerInvocationResponse,
)
def get_trigger_invocation(
    agent_id: str,
    trigger_id: str,
    invocation_id: str,
    session: DbSession,
    principal: Principal,
) -> TriggerInvocationResponse:
    require_permission_value(principal, Permission.AGENT_READ)
    _owned_agent(agent_id=agent_id, session=session, principal=principal)
    _owned_trigger(
        agent_id=agent_id,
        trigger_id=trigger_id,
        session=session,
        organization_id=principal.organization_id,
        include_deleted=True,
    )
    invocation = session.execute(
        select(TriggerInvocation).where(
            TriggerInvocation.id == invocation_id,
            TriggerInvocation.trigger_id == trigger_id,
            TriggerInvocation.organization_id == principal.organization_id,
        )
    ).scalar_one_or_none()
    if invocation is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Trigger invocation not found",
        )
    return _invocation_response(invocation, session=session)


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
    include_deleted: bool = False,
) -> Trigger:
    filters = [
        Trigger.id == trigger_id,
        Trigger.agent_id == agent_id,
        Trigger.organization_id == organization_id,
    ]
    if not include_deleted:
        filters.append(Trigger.deleted_at.is_(None))
    trigger = session.execute(select(Trigger).where(*filters)).scalar_one_or_none()
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


def _validated_runtime_config(
    payload: AgentTriggerCreateRequest,
    *,
    principal: Principal | None = None,
) -> dict:
    config = dict(payload.config_json)
    if payload.type not in {"file", "git"}:
        return config
    authorization_value = config.pop("workspace_authorization", None)
    if authorization_value is None:
        if principal is not None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Workspace authorization is required",
            )
        return _validated_legacy_runtime_config(payload, config=config)
    if principal is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Workspace authorization principal is required",
        )
    authorization = str(authorization_value)
    settings = get_settings()
    grant = WORKSPACE_AUTHORIZATION_STORE.verify(
        authorization,
        signing_secret=settings.local_desktop_bootstrap_token,
        user_id=principal.user_id,
        organization_id=principal.organization_id,
    )
    if grant is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid workspace authorization",
        )
    try:
        root = grant.root_path.resolve(strict=True)
    except OSError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Authorized workspace is no longer available",
        ) from exc
    if not root.is_dir() or root != grant.root_path:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Authorized workspace is no longer available",
        )
    config["workspace_profile_id"] = grant.profile_id
    if payload.type == "file":
        config["workspace_root"] = str(root)
        config["workspace_root_label"] = grant.label
        if "max_bytes" in config and "max_file_bytes" not in config:
            config["max_file_bytes"] = config.pop("max_bytes")
        return config
    try:
        top_level = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=root,
            shell=False,
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        ).stdout.strip()
        git_root = Path(top_level).resolve(strict=True)
    except (OSError, subprocess.SubprocessError) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="repo_root must be inside a Git worktree",
        ) from exc
    if git_root != root:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Authorized workspace must be the Git top-level directory",
        )
    config["repo_root"] = str(root)
    config["repo_root_label"] = grant.label
    return config


def _validated_legacy_runtime_config(
    payload: AgentTriggerCreateRequest,
    *,
    config: dict,
) -> dict:
    field_name = (
        "workspace_root"
        if payload.type == "file" or "workspace_root" in config
        else "repo_root"
    )
    try:
        root = Path(str(config[field_name])).expanduser().resolve(strict=True)
    except (KeyError, OSError) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"{field_name} must be an existing local directory",
        ) from exc
    if not root.is_dir():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"{field_name} must be an existing local directory",
        )
    config[field_name] = str(root)
    if payload.type == "file":
        if "max_bytes" in config and "max_file_bytes" not in config:
            config["max_file_bytes"] = config.pop("max_bytes")
        return config

    repo_candidate = Path(
        str(config.get("repo_root", ".") if field_name == "workspace_root" else ".")
    ).expanduser()
    try:
        repo_root = (
            repo_candidate if repo_candidate.is_absolute() else root / repo_candidate
        ).resolve(strict=True)
    except OSError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="repo_root must be an existing directory inside workspace_root",
        ) from exc
    if not repo_root.is_dir() or (repo_root != root and root not in repo_root.parents):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="repo_root must be an existing directory inside workspace_root",
        )
    try:
        top_level = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=repo_root,
            shell=False,
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        ).stdout.strip()
        git_root = Path(top_level).resolve(strict=True)
    except (OSError, subprocess.SubprocessError) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="repo_root must be inside a Git worktree",
        ) from exc
    if git_root != root and root not in git_root.parents and git_root not in root.parents:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Git worktree must be within workspace_root",
        )
    config["repo_root"] = str(repo_root)
    return config


def _trigger_response(trigger: Trigger) -> AgentTriggerResponse:
    response = AgentTriggerResponse.model_validate(trigger)
    config = dict(trigger.config_json or {})
    for field_name in ("workspace_root", "repo_root"):
        raw_path = config.pop(field_name, None)
        if raw_path and f"{field_name}_label" not in config:
            config[f"{field_name}_label"] = Path(str(raw_path)).name or "workspace"
    config.pop("workspace_profile_id", None)
    config.pop("workspace_authorization", None)
    return response.model_copy(update={"config_json": config})


def _invocation_response(
    invocation: TriggerInvocation,
    *,
    session: Session,
) -> TriggerInvocationResponse:
    response = TriggerInvocationResponse.model_validate(invocation)
    run = session.get(Task, invocation.run_id) if invocation.run_id else None
    if run is None:
        return response
    status_map = {
        "COMPLETED": "SUCCEEDED",
        "FAILED": "FAILED",
        "CANCELLED": "FAILED",
        "WAITING_APPROVAL": "WAITING_APPROVAL",
    }
    projected = status_map.get(run.status)
    if not projected:
        return response
    update: dict[str, object] = {"status": projected}
    if projected in {"SUCCEEDED", "FAILED"} and response.completed_at is None:
        update["completed_at"] = run.completed_at
    return response.model_copy(update=update)
