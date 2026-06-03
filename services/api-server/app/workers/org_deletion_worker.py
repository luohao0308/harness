from __future__ import annotations

from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.db.models import (
    AdminAuditEvent,
    Agent,
    AgentEvent,
    ApiKey,
    ArchivedRecord,
    DataExport,
    FrontendError,
    ModelCall,
    Organization,
    OrganizationDeletionLog,
    OrganizationMember,
    RetentionPolicy,
    RetentionRun,
    Task,
    ToolCall,
    UserOnboardingState,
    WorkspaceContextCache,
    utc_now,
)

ORG_MODELS: list[tuple[str, type[Any]]] = [
    ("api_keys", ApiKey),
    ("archived_records", ArchivedRecord),
    ("data_exports", DataExport),
    ("frontend_errors", FrontendError),
    ("retention_policies", RetentionPolicy),
    ("retention_runs", RetentionRun),
    ("user_onboarding_state", UserOnboardingState),
    ("workspace_context_caches", WorkspaceContextCache),
    ("agents", Agent),
    ("admin_audit_events", AdminAuditEvent),
    ("organization_members", OrganizationMember),
]
TASK_CHILD_MODELS: list[tuple[str, type[Any]]] = [
    ("agent_events", AgentEvent),
    ("model_calls", ModelCall),
    ("tool_calls", ToolCall),
]


def preview_org_deletion(session: Session, *, organization_id: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    task_ids = _task_ids(session, organization_id)
    for name, model in TASK_CHILD_MODELS:
        counts[name] = _count_task_child(session, model=model, task_ids=task_ids)
    counts["tasks"] = _count_org_model(session, model=Task, organization_id=organization_id)
    for name, model in ORG_MODELS:
        counts[name] = _count_org_model(session, model=model, organization_id=organization_id)
    counts["organizations"] = _count_org_row(session, organization_id)
    return counts


def delete_organization(
    session: Session,
    *,
    organization_id: str,
    deleted_by: str,
    confirmation_name: str,
) -> OrganizationDeletionLog:
    org = session.get(Organization, organization_id)
    if org is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found")
    if confirmation_name != org.name:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Confirmation name mismatch",
        )
    counts = preview_org_deletion(session, organization_id=organization_id)
    task_ids = _task_ids(session, organization_id)
    for _name, model in TASK_CHILD_MODELS:
        if task_ids:
            session.execute(delete(model).where(model.task_id.in_(task_ids)))
    session.execute(delete(Task).where(Task.organization_id == organization_id))
    for _name, model in ORG_MODELS:
        session.execute(delete(model).where(model.organization_id == organization_id))
    session.execute(delete(Organization).where(Organization.id == organization_id))
    log = OrganizationDeletionLog(
        organization_id=organization_id,
        deleted_by=deleted_by,
        deleted_at=utc_now(),
        deleted_counts_json=counts,
        status="completed",
    )
    session.add(log)
    session.commit()
    session.refresh(log)
    return log


def _task_ids(session: Session, organization_id: str) -> list[str]:
    return list(
        session.execute(select(Task.id).where(Task.organization_id == organization_id)).scalars()
    )


def _count_task_child(session: Session, *, model: type[Any], task_ids: list[str]) -> int:
    if not task_ids:
        return 0
    return int(
        session.execute(
            select(func.count()).select_from(model).where(model.task_id.in_(task_ids))
        ).scalar_one()
    )


def _count_org_model(session: Session, *, model: type[Any], organization_id: str) -> int:
    return int(
        session.execute(
            select(func.count()).select_from(model).where(model.organization_id == organization_id)
        ).scalar_one()
    )


def _count_org_row(session: Session, organization_id: str) -> int:
    return int(
        session.execute(
            select(func.count()).select_from(Organization).where(Organization.id == organization_id)
        ).scalar_one()
    )
