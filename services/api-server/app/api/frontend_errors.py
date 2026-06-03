from __future__ import annotations

import time
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.schemas import (
    FrontendErrorCreateRequest,
    FrontendErrorPage,
    FrontendErrorResponse,
)
from app.db.models import FrontendError, utc_now
from app.db.session import get_db_session
from app.security.auth import Principal, require_role

router = APIRouter(prefix="/frontend-errors", tags=["frontend-errors"])
DbSession = Annotated[Session, Depends(get_db_session)]
_rate_limit_seen: dict[str, list[float]] = {}


@router.post(
    "",
    response_model=FrontendErrorResponse,
    status_code=201,
    summary="记录前端错误",
    description="前端 ErrorBoundary 和全局 error reporter 使用，按用户 10/min 限流。",
)
def create_frontend_error(
    payload: FrontendErrorCreateRequest,
    session: DbSession,
    principal: Principal,
) -> FrontendError:
    require_role(principal, {"admin", "engineer", "operator"})
    _check_rate_limit(principal.organization_id, principal.user_id)
    row = FrontendError(
        organization_id=principal.organization_id,
        user_id=principal.user_id,
        url=payload.url,
        error_message=payload.error_message,
        stack=payload.stack,
        browser=payload.browser,
        metadata_json=payload.metadata_json,
        created_at=utc_now(),
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    return row


@router.get(
    "",
    response_model=FrontendErrorPage,
    summary="查询前端错误",
    description="Admin only。用于定位最近前端崩溃和 unhandled rejection。",
)
def list_frontend_errors(
    session: DbSession,
    principal: Principal,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
) -> FrontendErrorPage:
    require_role(principal, {"admin"})
    rows = session.execute(
        select(FrontendError)
        .where(FrontendError.organization_id == principal.organization_id)
        .order_by(FrontendError.created_at.desc())
        .limit(limit)
    ).scalars()
    return FrontendErrorPage(
        items=[FrontendErrorResponse.model_validate(row) for row in rows],
        next_cursor=None,
    )


@router.get(
    "/summary",
    summary="查询前端错误聚合",
    description="Admin only。按错误消息聚合最近错误频次。",
)
def summarize_frontend_errors(session: DbSession, principal: Principal) -> dict:
    require_role(principal, {"admin"})
    rows = session.execute(
        select(
            FrontendError.error_message,
            func.count(FrontendError.id),
            func.count(func.distinct(FrontendError.user_id)),
            func.max(FrontendError.created_at),
        )
        .where(FrontendError.organization_id == principal.organization_id)
        .group_by(FrontendError.error_message)
        .order_by(func.count(FrontendError.id).desc())
        .limit(50)
    ).all()
    return {
        "items": [
            {
                "error_message": message,
                "count": int(count),
                "affected_users": int(user_count),
                "last_seen_at": last_seen.isoformat() if last_seen else None,
            }
            for message, count, user_count, last_seen in rows
        ],
    }


def _check_rate_limit(organization_id: str, user_id: str) -> None:
    now = time.monotonic()
    key = f"{organization_id}:{user_id}"
    window = now - 60
    timestamps = [timestamp for timestamp in _rate_limit_seen.get(key, []) if timestamp >= window]
    if len(timestamps) >= 10:
        raise HTTPException(status_code=429, detail="frontend error rate limit exceeded")
    timestamps.append(now)
    _rate_limit_seen[key] = timestamps
