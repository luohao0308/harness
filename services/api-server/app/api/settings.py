
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.schemas import ModelSettingsResponse, PolicySettingsResponse
from app.db.models import AdminAuditEvent, utc_now
from app.db.session import get_db_session
from app.events.event_types import EventType
from app.security.auth import AuthenticatedPrincipal, Principal, require_role

router = APIRouter(prefix="/settings", tags=["settings"])
DbSession = Annotated[Session, Depends(get_db_session)]


def require_admin(principal: Principal) -> None:
    require_role(principal, {"admin"})


def write_admin_action(
    session: Session,
    principal: AuthenticatedPrincipal,
    resource_id: str,
    action: str,
    payload: dict,
) -> None:
    session.add(
        AdminAuditEvent(
            organization_id=principal.organization_id,
            actor_id=principal.user_id,
            event_type=EventType.ADMIN_ACTION,
            resource_type="settings",
            resource_id=resource_id,
            action=action,
            payload_json=payload,
            created_at=utc_now(),
        )
    )


@router.get(
    "/models",
    response_model=ModelSettingsResponse,
    summary="查询模型设置",
    description="返回模型网关、供应商、限流和健康状态。",
)
def get_model_settings(principal: Principal) -> ModelSettingsResponse:
    _ = principal
    return ModelSettingsResponse(
        default_provider="openai-compatible",
        default_model="default",
        providers=[
            {"name": "openai-compatible", "status": "healthy", "rate_limit_rpm": 600},
        ],
        rate_limits={"rpm": 600, "tpm": 120000},
        health={"status": "healthy", "updated_at": None},
    )


@router.put(
    "/models",
    response_model=ModelSettingsResponse,
    summary="更新模型设置",
    description="仅 admin 可更新模型网关设置。",
)
def update_model_settings(
    payload: ModelSettingsResponse,
    session: DbSession,
    principal: Principal,
) -> ModelSettingsResponse:
    require_admin(principal)
    write_admin_action(
        session=session,
        principal=principal,
        resource_id="models",
        action="settings.models.update",
        payload=payload.model_dump(),
    )
    session.commit()
    return payload


@router.get(
    "/policies",
    response_model=PolicySettingsResponse,
    summary="查询策略设置",
    description="返回工具风险、审批规则、沙箱规则和审计要求。",
)
def get_policy_settings(principal: Principal) -> PolicySettingsResponse:
    _ = principal
    return PolicySettingsResponse(
        risk_levels=[
            {"name": "low", "requires_sandbox": False, "approval": "auto"},
            {"name": "medium", "requires_sandbox": True, "approval": "auto"},
            {"name": "high", "requires_sandbox": True, "approval": "admin"},
            {"name": "critical", "requires_sandbox": True, "approval": "admin"},
        ],
        approvals={"manual_review": True, "deny_on_missing_policy": True},
        sandbox={"default_network": False, "default_timeout_seconds": 60},
        audit={"model_calls": True, "tool_calls": True, "policy_actions": True},
    )


@router.put(
    "/policies",
    response_model=PolicySettingsResponse,
    summary="更新策略设置",
    description="仅 admin 可更新策略设置。",
)
def update_policy_settings(
    payload: PolicySettingsResponse,
    session: DbSession,
    principal: Principal,
) -> PolicySettingsResponse:
    require_admin(principal)
    write_admin_action(
        session=session,
        principal=principal,
        resource_id="policies",
        action="settings.policies.update",
        payload=payload.model_dump(),
    )
    session.commit()
    return payload
