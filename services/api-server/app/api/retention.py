from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.schemas import (
    RetentionPolicyPage,
    RetentionPolicyResponse,
    RetentionPolicyUpdateRequest,
    RetentionRunPage,
)
from app.db.models import AdminAuditEvent, RetentionPolicy, RetentionRun, utc_now
from app.db.session import get_db_session
from app.events.event_types import EventType
from app.security.auth import Principal, require_permission_value
from app.security.rbac import Permission
from app.workers.retention_evaluator import evaluate_retention_once

router = APIRouter(prefix="/retention", tags=["retention"])
DbSession = Annotated[Session, Depends(get_db_session)]


@router.get("/policies", response_model=RetentionPolicyPage)
def list_retention_policies(session: DbSession, principal: Principal) -> RetentionPolicyPage:
    require_permission_value(principal, Permission.DATA_RETENTION_MANAGE)
    policies = list(
        session.execute(
            select(RetentionPolicy)
            .where(
                RetentionPolicy.organization_id.is_(None)
                | (RetentionPolicy.organization_id == principal.organization_id)
            )
            .order_by(RetentionPolicy.entity_type, RetentionPolicy.organization_id.desc())
        ).scalars()
    )
    return RetentionPolicyPage(items=policies)


@router.patch("/policies/{policy_id}", response_model=RetentionPolicyResponse)
def update_retention_policy(
    policy_id: str,
    payload: RetentionPolicyUpdateRequest,
    session: DbSession,
    principal: Principal,
) -> RetentionPolicy:
    require_permission_value(principal, Permission.DATA_RETENTION_MANAGE)
    policy = session.get(RetentionPolicy, policy_id)
    if policy is None or policy.organization_id not in {None, principal.organization_id}:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Retention policy not found",
        )
    keep_policy_update = (
        policy.action == "keep"
        and (payload.retention_days is not None or payload.delete_after_days is not None)
    )
    if keep_policy_update:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Forever retention policy is immutable",
        )
    if policy.organization_id is None:
        policy = _org_policy_from_system(session, policy, principal.organization_id)
    if payload.retention_days is not None:
        policy.retention_days = payload.retention_days
    if payload.delete_after_days is not None:
        policy.delete_after_days = payload.delete_after_days
    if payload.enabled is not None:
        policy.enabled = payload.enabled
    policy.updated_at = utc_now()
    _audit(
        session,
        principal,
        action="retention.policy.update",
        resource_id=policy.id,
        payload=payload.model_dump(exclude_none=True),
    )
    session.commit()
    session.refresh(policy)
    return policy


@router.post("/run", response_model=RetentionRunPage, status_code=status.HTTP_202_ACCEPTED)
def run_retention(session: DbSession, principal: Principal) -> RetentionRunPage:
    require_permission_value(principal, Permission.DATA_RETENTION_MANAGE)
    runs = evaluate_retention_once(session, organization_id=principal.organization_id)
    return RetentionRunPage(items=runs)


@router.get("/runs", response_model=RetentionRunPage)
def list_retention_runs(session: DbSession, principal: Principal) -> RetentionRunPage:
    require_permission_value(principal, Permission.DATA_RETENTION_MANAGE)
    runs = list(
        session.execute(
            select(RetentionRun)
            .where(RetentionRun.organization_id == principal.organization_id)
            .order_by(RetentionRun.started_at.desc())
            .limit(100)
        ).scalars()
    )
    return RetentionRunPage(items=runs)


def _org_policy_from_system(
    session: Session,
    policy: RetentionPolicy,
    organization_id: str,
) -> RetentionPolicy:
    existing = session.execute(
        select(RetentionPolicy).where(
            RetentionPolicy.organization_id == organization_id,
            RetentionPolicy.entity_type == policy.entity_type,
            RetentionPolicy.action == policy.action,
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing
    clone = RetentionPolicy(
        organization_id=organization_id,
        entity_type=policy.entity_type,
        action=policy.action,
        retention_days=policy.retention_days,
        delete_after_days=policy.delete_after_days,
        enabled=policy.enabled,
        created_at=utc_now(),
        updated_at=utc_now(),
    )
    session.add(clone)
    session.flush()
    return clone


def _audit(
    session: Session,
    principal: Principal,
    *,
    action: str,
    resource_id: str,
    payload: dict,
) -> None:
    session.add(
        AdminAuditEvent(
            organization_id=principal.organization_id,
            actor_id=principal.user_id,
            event_type=EventType.ADMIN_ACTION,
            resource_type="retention_policy",
            resource_id=resource_id,
            action=action,
            payload_json=payload,
            created_at=utc_now(),
        )
    )
