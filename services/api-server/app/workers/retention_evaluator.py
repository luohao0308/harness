from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.db.models import (
    AgentEvent,
    ArchivedRecord,
    FrontendError,
    ModelCall,
    OtelSpan,
    RetentionPolicy,
    RetentionRun,
    Task,
    ToolCall,
    WorkspaceContextCache,
    utc_now,
)
from app.services.archive_service import archive_and_delete, delete_expired

ENTITY_MODELS: dict[str, type[Any]] = {
    "otel_spans": OtelSpan,
    "agent_events": AgentEvent,
    "frontend_errors": FrontendError,
    "model_calls": ModelCall,
    "tool_calls": ToolCall,
    "workspace_context_caches": WorkspaceContextCache,
}


def evaluate_retention_once(
    session: Session,
    *,
    organization_id: str | None = None,
    now: datetime | None = None,
) -> list[RetentionRun]:
    current_time = now or datetime.now(UTC)
    policies = list(
        session.execute(
            select(RetentionPolicy).where(RetentionPolicy.enabled.is_(True))
        ).scalars()
    )
    runs: list[RetentionRun] = []
    for policy in policies:
        if organization_id is not None and policy.organization_id not in {None, organization_id}:
            continue
        if policy.action == "keep" or policy.retention_days is None:
            continue
        model = ENTITY_MODELS.get(policy.entity_type)
        if model is None:
            continue
        effective_org = (
            organization_id
            if policy.organization_id is None
            else policy.organization_id
        )
        run = RetentionRun(
            policy_id=policy.id,
            organization_id=effective_org,
            entity_type=policy.entity_type,
            action=policy.action,
            started_at=utc_now(),
        )
        session.add(run)
        try:
            archived_count, deleted_count = _apply_policy(
                session=session,
                model=model,
                entity_type=policy.entity_type,
                action=policy.action,
                cutoff=current_time - timedelta(days=policy.retention_days),
                organization_id=effective_org,
            )
            run.archived_count = archived_count
            run.deleted_count = deleted_count
            run.finished_at = utc_now()
        except Exception as exc:
            run.error_message = str(exc)
            run.finished_at = utc_now()
        runs.append(run)
    session.commit()
    return runs


def _apply_policy(
    *,
    session: Session,
    model: type[Any],
    entity_type: str,
    action: str,
    cutoff: datetime,
    organization_id: str | None,
) -> tuple[int, int]:
    if _has_org_column(model):
        if action == "archive":
            return archive_and_delete(
                session,
                model=model,
                entity_type=entity_type,
                cutoff=cutoff,
                organization_id=organization_id,
            )
        return 0, delete_expired(
            session,
            model=model,
            cutoff=cutoff,
            organization_id=organization_id,
        )
    rows = _task_bound_expired_rows(
        session=session,
        model=model,
        cutoff=cutoff,
        organization_id=organization_id,
    )
    archived_count = 0
    if action == "archive":
        for row in rows:
            original_id = str(row.id)
            exists = session.execute(
                select(ArchivedRecord.id).where(
                    ArchivedRecord.organization_id == organization_id,
                    ArchivedRecord.entity_type == entity_type,
                    ArchivedRecord.original_id == original_id,
                )
            ).scalar_one_or_none()
            if exists is None:
                session.add(
                    ArchivedRecord(
                        organization_id=organization_id,
                        entity_type=entity_type,
                        original_id=original_id,
                        payload_json={
                            column.name: _json_value(getattr(row, column.name))
                            for column in row.__table__.columns
                        },
                        archived_at=utc_now(),
                    )
                )
                archived_count += 1
    deleted = session.execute(delete(model).where(model.id.in_([row.id for row in rows])))
    return archived_count, int(deleted.rowcount or 0)


def _task_bound_expired_rows(
    *,
    session: Session,
    model: type[Any],
    cutoff: datetime,
    organization_id: str | None,
) -> list[Any]:
    statement = select(model).join(Task, model.task_id == Task.id).where(
        model.created_at < cutoff
    )
    if organization_id is not None:
        statement = statement.where(Task.organization_id == organization_id)
    return list(session.execute(statement.limit(10_000)).scalars())


def _has_org_column(model: type[Any]) -> bool:
    return hasattr(model, "organization_id")


def _json_value(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    return value
