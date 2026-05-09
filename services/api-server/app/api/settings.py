from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.agents.model_gateway import ModelHealthChecker, normalize_model_settings
from app.api.schemas import (
    CountItem,
    ModelFallbackEventItem,
    ModelFallbackSummaryResponse,
    ModelHealthPage,
    ModelSettingsResponse,
    PolicySettingsResponse,
)
from app.db.models import AdminAuditEvent, AgentEvent, ModelCall, SystemSetting, Task, utc_now
from app.db.session import get_db_session
from app.events.event_types import EventType
from app.security.auth import AuthenticatedPrincipal, Principal, require_role

router = APIRouter(prefix="/settings", tags=["settings"])
DbSession = Annotated[Session, Depends(get_db_session)]

MODEL_SETTINGS_KEY = "settings.models"
POLICY_SETTINGS_KEY = "settings.policies"

DEFAULT_MODEL_SETTINGS = ModelSettingsResponse(
    default_provider="minimax",
    default_model="MiniMax-M2.7-highspeed",
    providers=[
        {
            "name": "minimax",
            "label": "MiniMax Anthropic Compatible",
            "status": "healthy",
            "api_format": "anthropic",
            "model": "MiniMax-M2.7-highspeed",
            "base_url": "https://api.minimaxi.com/anthropic",
            "api_key": "replace-me",
            "api_key_env": "MINIMAX_API_KEY",
            "model_context_window_tokens": 400000,
            "rate_limit_rpm": 300,
            "rate_limit_tpm": 400000,
            "timeout_seconds": 60,
            "health_timeout_seconds": 5,
            "circuit_breaker": {"failure_threshold": 3, "cooldown_seconds": 60},
        },
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
        value = default_value
    else:
        value = setting.value_json
    if key == MODEL_SETTINGS_KEY:
        return normalize_model_settings(value)
    return value


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
    normalized_payload = ModelSettingsResponse.model_validate(
        normalize_model_settings(payload.model_dump())
    )
    write_setting(
        session=session,
        principal=principal,
        key=MODEL_SETTINGS_KEY,
        value=normalized_payload.model_dump(),
    )
    write_admin_action(
        session=session,
        principal=principal,
        resource_id="models",
        action="settings.models.update",
        payload=normalized_payload.model_dump(),
    )
    session.commit()
    return normalized_payload


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
    "/models/fallbacks",
    response_model=ModelFallbackSummaryResponse,
    summary="查询模型 fallback 观测",
    description="按当前组织聚合模型 fallback 事件、主模型失败次数和最近 fallback 明细。",
)
def get_model_fallbacks(
    session: DbSession,
    principal: Principal,
    limit: int = 20,
) -> ModelFallbackSummaryResponse:
    task_ids = select(Task.id).where(Task.organization_id == principal.organization_id)
    capped_limit = max(1, min(limit, 100))
    fallback_events = list(
        session.execute(
            select(AgentEvent)
            .where(
                AgentEvent.task_id.in_(task_ids),
                AgentEvent.event_type == EventType.MODEL_FALLBACK_USED.value,
            )
            .order_by(AgentEvent.created_at.desc(), AgentEvent.sequence.desc())
        ).scalars()
    )
    provider_counts: dict[str, int] = {}
    for event in fallback_events:
        provider = str(event.payload_json.get("model_provider") or "unknown")
        provider_counts[provider] = provider_counts.get(provider, 0) + 1
    primary_failure_total = int(
        session.execute(
            select(func.count(ModelCall.id)).where(
                ModelCall.task_id.in_(task_ids),
                ModelCall.status == "FAILED",
            )
        ).scalar_one()
        or 0
    )
    return ModelFallbackSummaryResponse(
        organization_id=principal.organization_id,
        fallback_total=len(fallback_events),
        primary_failure_total=primary_failure_total,
        providers=[
            CountItem(name=provider, count=count)
            for provider, count in sorted(provider_counts.items())
        ],
        recent_events=[
            _model_fallback_event_item(event)
            for event in fallback_events[:capped_limit]
        ],
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


def _model_fallback_event_item(event: AgentEvent) -> ModelFallbackEventItem:
    payload = event.payload_json
    return ModelFallbackEventItem(
        event_id=event.id,
        task_id=event.task_id,
        sequence=event.sequence,
        primary_provider=payload.get("primary_model_provider"),
        primary_model=payload.get("primary_model_name"),
        fallback_provider=str(payload.get("model_provider") or "unknown"),
        fallback_model=str(payload.get("model_name") or "unknown"),
        fallback_index=int(payload.get("fallback_index") or 1),
        reason=payload.get("reason"),
        trace_id=event.trace_id,
        created_at=event.created_at,
    )
