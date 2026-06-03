from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.schemas import DemoLoadResponse, DemoResetRequest
from app.db.session import get_db_session
from app.demo.seed_data import load_demo_data, reset_demo_data
from app.security.auth import Principal, require_role

router = APIRouter(prefix="/demo", tags=["demo"])
DbSession = Annotated[Session, Depends(get_db_session)]


@router.post(
    "/load",
    response_model=DemoLoadResponse,
    summary="加载首轮 Demo 数据",
    description="Admin only。创建 demo Agent、知识源、Eval Dataset、历史 Run 和系统专家投影。",
)
def load_demo(session: DbSession, principal: Principal) -> DemoLoadResponse:
    require_role(principal, {"admin"})
    result = load_demo_data(
        session,
        organization_id=principal.organization_id,
        user_id=principal.user_id,
    )
    session.commit()
    return DemoLoadResponse(**result.__dict__)


@router.post(
    "/reset",
    response_model=DemoLoadResponse,
    summary="重置首轮 Demo 数据",
    description="Admin only。仅清理带 first-run demo marker 的数据。",
)
def reset_demo(
    payload: DemoResetRequest,
    session: DbSession,
    principal: Principal,
) -> DemoLoadResponse:
    require_role(principal, {"admin"})
    if payload.confirm_token != "reset-demo-data":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="confirm_token must be reset-demo-data",
        )
    result = reset_demo_data(
        session,
        organization_id=principal.organization_id,
        user_id=principal.user_id,
    )
    session.commit()
    return DemoLoadResponse(**result.__dict__)
