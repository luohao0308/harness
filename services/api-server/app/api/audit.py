from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.schemas import AuditEventPage
from app.db.models import AdminAuditEvent
from app.db.session import get_db_session
from app.security.auth import Principal, require_permission_value
from app.security.rbac import Permission

router = APIRouter(prefix="/audit", tags=["audit"])
DbSession = Annotated[Session, Depends(get_db_session)]


@router.get("", response_model=AuditEventPage)
def list_audit_events(
    session: DbSession,
    principal: Principal,
    actor_id: Annotated[str | None, Query()] = None,
    action: Annotated[str | None, Query()] = None,
    resource_type: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> AuditEventPage:
    require_permission_value(principal, Permission.AUDIT_READ)
    statement = select(AdminAuditEvent).where(
        AdminAuditEvent.organization_id == principal.organization_id
    )
    if actor_id:
        statement = statement.where(AdminAuditEvent.actor_id == actor_id)
    if action:
        statement = statement.where(AdminAuditEvent.action == action)
    if resource_type:
        statement = statement.where(AdminAuditEvent.resource_type == resource_type)
    events = list(
        session.execute(statement.order_by(AdminAuditEvent.created_at.desc()).limit(limit)).scalars()
    )
    return AuditEventPage(items=events)


@router.get("/export.csv", response_class=Response)
def export_audit_events_csv(session: DbSession, principal: Principal) -> Response:
    require_permission_value(principal, Permission.AUDIT_READ)
    events = list(
        session.execute(
            select(AdminAuditEvent)
            .where(AdminAuditEvent.organization_id == principal.organization_id)
            .order_by(AdminAuditEvent.created_at.desc())
            .limit(1000)
        ).scalars()
    )
    lines = ["id,actor_id,action,resource_type,resource_id,created_at"]
    for event in events:
        lines.append(
            ",".join(
                [
                    event.id,
                    event.actor_id or "",
                    event.action,
                    event.resource_type,
                    str(event.resource_id).replace(",", " "),
                    event.created_at.isoformat(),
                ]
            )
        )
    return Response(
        "\n".join(lines) + "\n",
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="audit-events.csv"'},
    )
