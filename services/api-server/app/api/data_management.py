from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.schemas import (
    DataExportPage,
    DataExportResponse,
    OrganizationDeleteRequest,
    OrganizationDeletionPreviewResponse,
    OrganizationDeletionResponse,
)
from app.db.models import AdminAuditEvent, DataExport, Organization, utc_now
from app.db.session import get_db_session
from app.events.event_types import EventType
from app.security.auth import Principal, require_permission_value
from app.security.rbac import Permission
from app.workers.data_export_worker import create_org_export
from app.workers.org_deletion_worker import delete_organization, preview_org_deletion

router = APIRouter(prefix="/organizations", tags=["data-management"])
DbSession = Annotated[Session, Depends(get_db_session)]


@router.post(
    "/{org_id}/export",
    response_model=DataExportResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def export_organization(org_id: str, session: DbSession, principal: Principal) -> DataExport:
    _ensure_current_org(org_id, principal)
    require_permission_value(principal, Permission.DATA_EXPORT)
    export = create_org_export(
        session,
        organization_id=principal.organization_id,
        requested_by=principal.user_id,
    )
    _audit(
        session,
        principal,
        action="organization.export",
        resource_id=org_id,
        payload={"export_id": export.id, "status": export.status},
    )
    session.commit()
    return export


@router.get("/{org_id}/exports", response_model=DataExportPage)
def list_organization_exports(
    org_id: str,
    session: DbSession,
    principal: Principal,
) -> DataExportPage:
    _ensure_current_org(org_id, principal)
    require_permission_value(principal, Permission.DATA_EXPORT)
    exports = list(
        session.execute(
            select(DataExport)
            .where(DataExport.organization_id == principal.organization_id)
            .order_by(DataExport.requested_at.desc())
            .limit(100)
        ).scalars()
    )
    return DataExportPage(items=exports)


@router.delete("/{org_id}/dry-run", response_model=OrganizationDeletionPreviewResponse)
def preview_delete_organization(
    org_id: str,
    session: DbSession,
    principal: Principal,
) -> OrganizationDeletionPreviewResponse:
    _ensure_current_org(org_id, principal)
    require_permission_value(principal, Permission.DATA_DELETE)
    org = _org(session, org_id)
    return OrganizationDeletionPreviewResponse(
        organization_id=org.id,
        organization_name=org.name,
        confirmation_name=org.name,
        counts=preview_org_deletion(session, organization_id=org.id),
    )


@router.delete("/{org_id}", response_model=OrganizationDeletionResponse)
def confirm_delete_organization(
    org_id: str,
    payload: OrganizationDeleteRequest,
    session: DbSession,
    principal: Principal,
) -> OrganizationDeletionResponse:
    _ensure_current_org(org_id, principal)
    require_permission_value(principal, Permission.DATA_DELETE)
    log = delete_organization(
        session,
        organization_id=org_id,
        deleted_by=principal.user_id,
        confirmation_name=payload.confirmation_name,
    )
    return OrganizationDeletionResponse(
        organization_id=log.organization_id,
        status=log.status,
        deleted_counts_json=log.deleted_counts_json,
    )


def _org(session: Session, org_id: str) -> Organization:
    org = session.get(Organization, org_id)
    if org is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found")
    return org


def _ensure_current_org(org_id: str, principal: Principal) -> None:
    if org_id != principal.organization_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found")


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
            resource_type="organization",
            resource_id=resource_id,
            action=action,
            payload_json=payload,
            created_at=utc_now(),
        )
    )
