from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.model_gateway import ModelHealthChecker
from app.api.schemas import ModelHealthPage, ModelSettingsResponse, PolicySettingsResponse
from app.db.models import AdminAuditEvent, SystemSetting, utc_now
from app.db.session import get_db_session
from app.events.event_types import EventType
from app.security.auth import AuthenticatedPrincipal, Principal, require_role

router = APIRouter(prefix="/settings", tags=["settings"])
DbSession = Annotated[Session, Depends(get_db_session)]

MODEL_SETTINGS_KEY = "settings.models"
POLICY_SETTINGS_KEY = "settings.policies"

DEFAULT_MODEL_SETTINGS = ModelSettingsResponse(
    default_provider="openai-compatible",
    default_model="default",
    providers=[
        {
            "name": "openai-compatible",
            "status": "healthy",
            "rate_limit_rpm": 600,
            "rate_limit_tpm": 120000,
            "circuit_breaker": {"failure_threshold": 3, "cooldown_seconds": 60},
        },
    ],
    rate_limits={"rpm": 600, "tpm": 120000},
    health={
        "status": "healthy",
        "updated_at": None,
        "mode": "mock",
        "latency_ms": 0,
        "error_message": None,
    },
    circuit_breaker={"failure_threshold": 3, "cooldown_seconds": 60},
)

DEFAULT_POLICY_SETTINGS = PolicySettingsResponse(
    risk_levels=[
        {"name": "low", "requires_sandbox": False, "approval": "auto"},
        {"name": "medium", "requires_sandbox": True, "approval": "auto"},
        {"name": "high", "requires_sandbox": True, "approval": "admin"},
        {"name": "critical", "requires_sandbox": True, "approval": "admin"},
    ],
    approvals={"manual_review": True, "deny_on_missing_policy": True},
    sandbox={
        "default_network": False,
        "default_timeout_seconds": 60,
        "memory_mb": 1024,
        "cpus": "1.0",
        "workspace_quota_mb": 1024,
        "network_allowlist": [],
    },
    audit={"model_calls": True, "tool_calls": True, "policy_actions": True},
)


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


def read_setting(
    session: Session,
    organization_id: str,
    key: str,
    default_value: dict,
) -> dict:
    setting = session.execute(
        select(SystemSetting).where(
            SystemSetting.organization_id == organization_id,
            SystemSetting.key == key,
        )
    ).scalar_one_or_none()
    if setting is None:
        return default_value
    return setting.value_json


def write_setting(
    session: Session,
    principal: AuthenticatedPrincipal,
    key: str,
    value: dict,
) -> None:
    setting = session.execute(
        select(SystemSetting).where(
            SystemSetting.organization_id == principal.organization_id,
            SystemSetting.key == key,
        )
    ).scalar_one_or_none()
    if setting is None:
        setting = SystemSetting(
            organization_id=principal.organization_id,
            key=key,
            value_json=value,
            updated_by=principal.user_id,
            updated_at=utc_now(),
        )
        session.add(setting)
        return
    setting.value_json = value
    setting.updated_by = principal.user_id
    setting.updated_at = utc_now()


@router.get(
    "/models",
    response_model=ModelSettingsResponse,
    summary="查询模型设置",
    description="返回模型网关、供应商、限流和健康状态。",
)
def get_model_settings(session: DbSession, principal: Principal) -> ModelSettingsResponse:
    return ModelSettingsResponse.model_validate(
        read_setting(
            session=session,
            organization_id=principal.organization_id,
            key=MODEL_SETTINGS_KEY,
            default_value=DEFAULT_MODEL_SETTINGS.model_dump(),
        )
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
    write_setting(
        session=session,
        principal=principal,
        key=MODEL_SETTINGS_KEY,
        value=payload.model_dump(),
    )
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
    "/models/health",
    response_model=ModelHealthPage,
    summary="查询模型健康状态",
    description="按当前组织模型设置返回供应商健康状态和探测结果。",
)
def get_model_health(session: DbSession, principal: Principal) -> ModelHealthPage:
    items = ModelHealthChecker(session).check(organization_id=principal.organization_id)
    session.commit()
    return ModelHealthPage(
        items=items
    )


@router.get(
    "/policies",
    response_model=PolicySettingsResponse,
    summary="查询策略设置",
    description="返回工具风险、审批规则、沙箱规则和审计要求。",
)
def get_policy_settings(session: DbSession, principal: Principal) -> PolicySettingsResponse:
    return PolicySettingsResponse.model_validate(
        read_setting(
            session=session,
            organization_id=principal.organization_id,
            key=POLICY_SETTINGS_KEY,
            default_value=DEFAULT_POLICY_SETTINGS.model_dump(),
        )
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
    write_setting(
        session=session,
        principal=principal,
        key=POLICY_SETTINGS_KEY,
        value=payload.model_dump(),
    )
    write_admin_action(
        session=session,
        principal=principal,
        resource_id="policies",
        action="settings.policies.update",
        payload=payload.model_dump(),
    )
    session.commit()
    return payload
