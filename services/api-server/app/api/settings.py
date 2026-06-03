from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.agents.model_gateway import (
    DEFAULT_MODEL_SETTINGS as GATEWAY_DEFAULT_MODEL_SETTINGS,
)
from app.agents.model_gateway import (
    ModelHealthChecker,
    normalize_model_settings,
)
from app.api.schemas import (
    CountItem,
    ModelFallbackEventItem,
    ModelFallbackSummaryResponse,
    ModelHealthPage,
    ModelOfficialStatusPage,
    ModelPricingSourceItem,
    ModelPricingSourcePage,
    ModelSettingsResponse,
    PolicySettingsResponse,
)
from app.db.models import AdminAuditEvent, AgentEvent, ModelCall, SystemSetting, Task, utc_now
from app.db.session import get_db_session
from app.events.event_types import EventType
from app.security.auth import AuthenticatedPrincipal, Principal, require_role
from app.security.secrets import (
    SECRET_PURPOSE_MODEL_PROVIDER,
    SECRET_SCOPE_ORG,
    SECRET_SOURCE_ORG,
    SecretEncryptionError,
    resolve_secret,
    upsert_secret,
)
from app.settings.model_pricing_sources import (
    SOURCE_BLOCKING_STATUSES,
    list_model_pricing_sources,
    load_model_pricing_source_document,
)

router = APIRouter(prefix="/settings", tags=["settings"])
DbSession = Annotated[Session, Depends(get_db_session)]

MODEL_SETTINGS_KEY = "settings.models"
POLICY_SETTINGS_KEY = "settings.policies"

MODEL_OFFICIAL_STATUS_SOURCES = [
    {
        "provider": "openai",
        "label": "OpenAI",
        "page_url": "https://status.openai.com/",
        "api_url": "https://status.openai.com/api/v2/status.json",
        "fetch_mode": "statuspage_json",
    },
    {
        "provider": "deepseek",
        "label": "DeepSeek",
        "page_url": "https://status.deepseek.com/",
        "api_url": "https://status.deepseek.com/",
        "fetch_mode": "status_page",
    },
]

DEFAULT_MODEL_SETTINGS = ModelSettingsResponse(**GATEWAY_DEFAULT_MODEL_SETTINGS)

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
    web_research={
        "enabled": False,
        "require_allowlist": True,
        "allow_domains": [],
        "deny_domains": [],
        "max_results": 2,
        "timeout_seconds": 8,
        "max_content_bytes": 1200,
        "max_calls_per_run": 1,
    },
    context_assembly_v2_enabled=True,
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


def _store_model_provider_secrets(
    *,
    session: Session,
    principal: AuthenticatedPrincipal,
    value: dict,
) -> dict:
    sanitized = _strip_model_provider_raw_keys(value)
    providers = sanitized.get("providers")
    if not isinstance(providers, list):
        return sanitized
    original_providers = value.get("providers") if isinstance(value.get("providers"), list) else []
    for index, provider in enumerate(providers):
        if not isinstance(provider, dict):
            continue
        original = original_providers[index] if index < len(original_providers) else provider
        if not isinstance(original, dict):
            continue
        raw_key = str(original.get("api_key") or "").strip()
        if raw_key and raw_key != "replace-me":
            provider_name = str(provider.get("name") or "").strip()
            if not provider_name:
                continue
            try:
                row = upsert_secret(
                    session,
                    organization_id=principal.organization_id,
                    actor_id=principal.user_id,
                    scope=SECRET_SCOPE_ORG,
                    owner_user_id=None,
                    provider=provider_name,
                    purpose=SECRET_PURPOSE_MODEL_PROVIDER,
                    secret_ref=f"secret://models/{provider_name}/api-key",
                    secret_value=raw_key,
                )
            except (SecretEncryptionError, ValueError) as exc:
                raise ValueError(str(exc)) from exc
            provider["api_key_configured"] = True
            provider["api_key_source"] = SECRET_SOURCE_ORG
            provider["api_key_secret_id"] = row.id
    return sanitized


def _model_settings_response_value(
    *,
    session: Session,
    organization_id: str,
    user_id: str,
    value: dict,
) -> dict:
    sanitized = _strip_model_provider_raw_keys(value)
    providers = sanitized.get("providers")
    if not isinstance(providers, list):
        return sanitized
    original_providers = value.get("providers") if isinstance(value.get("providers"), list) else []
    for index, provider in enumerate(providers):
        if not isinstance(provider, dict):
            continue
        original = original_providers[index] if index < len(original_providers) else provider
        if not isinstance(original, dict):
            original = provider
        provider_name = str(provider.get("name") or "").strip()
        if not provider_name:
            continue
        resolved = resolve_secret(
            session,
            organization_id=organization_id,
            user_id=user_id,
            provider=provider_name,
            purpose=SECRET_PURPOSE_MODEL_PROVIDER,
            env_candidates=[
                str(provider.get("api_key_env") or ""),
            ],
        )
        raw_legacy = str(original.get("api_key") or "").strip()
        provider["api_key_configured"] = resolved.found or bool(
            raw_legacy and raw_legacy != "replace-me"
        )
        provider["api_key_source"] = resolved.source if resolved.found else "missing"
        if resolved.secret_id:
            provider["api_key_secret_id"] = resolved.secret_id
    return sanitized


def _strip_model_provider_raw_keys(value: dict) -> dict:
    sanitized = dict(value)
    providers = sanitized.get("providers")
    if not isinstance(providers, list):
        return sanitized
    next_providers = []
    for provider in providers:
        if not isinstance(provider, dict):
            next_providers.append(provider)
            continue
        redacted = dict(provider)
        raw_key = str(redacted.get("api_key") or "").strip()
        redacted["api_key"] = ""
        if raw_key and raw_key != "replace-me":
            redacted.setdefault("api_key_configured", True)
            redacted.setdefault("api_key_source", SECRET_SOURCE_ORG)
        next_providers.append(redacted)
    sanitized["providers"] = next_providers
    return sanitized


def _official_status_label(indicator: str) -> str:
    normalized = indicator.strip().lower()
    if normalized == "none":
        return "operational"
    if normalized in {"minor", "degraded"}:
        return "degraded"
    if normalized in {"major", "critical"}:
        return "outage"
    if normalized == "maintenance":
        return "maintenance"
    return "unknown"


def _fetch_model_official_statuses() -> list[dict]:
    checked_at = utc_now()
    items = []
    for source in MODEL_OFFICIAL_STATUS_SOURCES:
        payload: dict = {}
        error_message = None
        indicator = "unknown"
        description = "官方状态暂不可查"
        try:
            with httpx.Client(timeout=3.0, trust_env=False) as client:
                response = client.get(source["api_url"])
                response.raise_for_status()
                if source.get("fetch_mode") == "statuspage_json":
                    payload = response.json()
                else:
                    description = "官方状态页可打开，未提供 JSON 状态 API"
        except (httpx.HTTPError, ValueError) as exc:
            error_message = str(exc)

        status = payload.get("status") if isinstance(payload.get("status"), dict) else {}
        page = payload.get("page") if isinstance(payload.get("page"), dict) else {}
        if status:
            indicator = str(status.get("indicator") or "unknown")
            description = str(status.get("description") or "官方状态暂不可查")
        if error_message:
            indicator = "unknown"
            description = "官方状态暂不可查"
        items.append(
            {
                "provider": source["provider"],
                "label": source["label"],
                "status": _official_status_label(indicator),
                "indicator": indicator,
                "description": description,
                "page_url": str(page.get("url") or source["page_url"]),
                "api_url": source["api_url"],
                "checked_at": checked_at,
                "updated_at": (
                    page.get("updated_at") if isinstance(page.get("updated_at"), str) else None
                ),
                "error_message": error_message,
            }
        )
    return items


@router.get(
    "/models",
    response_model=ModelSettingsResponse,
    summary="查询模型设置",
    description="返回模型网关、供应商、限流和健康状态。",
)
def get_model_settings(session: DbSession, principal: Principal) -> ModelSettingsResponse:
    value = read_setting(
        session=session,
        organization_id=principal.organization_id,
        key=MODEL_SETTINGS_KEY,
        default_value=DEFAULT_MODEL_SETTINGS.model_dump(),
    )
    return ModelSettingsResponse.model_validate(
        _model_settings_response_value(
            session=session,
            organization_id=principal.organization_id,
            user_id=principal.user_id,
            value=value,
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
    try:
        persisted_value = _store_model_provider_secrets(
            session=session,
            principal=principal,
            value=normalized_payload.model_dump(),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    write_setting(
        session=session,
        principal=principal,
        key=MODEL_SETTINGS_KEY,
        value=persisted_value,
    )
    write_admin_action(
        session=session,
        principal=principal,
        resource_id="models",
        action="settings.models.update",
        payload=_strip_model_provider_raw_keys(persisted_value),
    )
    session.commit()
    return ModelSettingsResponse.model_validate(
        _model_settings_response_value(
            session=session,
            organization_id=principal.organization_id,
            user_id=principal.user_id,
            value=persisted_value,
        )
    )


@router.get(
    "/models/health",
    response_model=ModelHealthPage,
    summary="查询模型健康状态",
    description="按当前组织模型设置返回供应商健康状态和探测结果。",
)
def get_model_health(session: DbSession, principal: Principal) -> ModelHealthPage:
    items = ModelHealthChecker(session).check(organization_id=principal.organization_id)
    session.commit()
    return ModelHealthPage(items=items)


@router.get(
    "/models/official-status",
    response_model=ModelOfficialStatusPage,
    summary="查询官方模型服务状态",
    description=(
        "查询已知供应商官方 Statuspage 状态；该结果仅作外部服务参考，不替代 Harness 模型探测。"
    ),
)
def get_model_official_status(principal: Principal) -> ModelOfficialStatusPage:
    _ = principal
    return ModelOfficialStatusPage(items=_fetch_model_official_statuses())


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
            _model_fallback_event_item(event) for event in fallback_events[:capped_limit]
        ],
    )


@router.get(
    "/models/pricing-sources",
    response_model=ModelPricingSourcePage,
    summary="查询内置模型价格官方来源",
    description="返回内置模型价格、官方来源、校验状态和企业成本门禁状态。",
)
def get_model_pricing_sources(principal: Principal) -> ModelPricingSourcePage:
    document = load_model_pricing_source_document()
    rows = list_model_pricing_sources()
    return ModelPricingSourcePage(
        schema_version=document.schema_version,
        retrieved_at=document.retrieved_at,
        parser_version=document.parser_version,
        blocking_statuses=sorted(SOURCE_BLOCKING_STATUSES),
        items=[
            ModelPricingSourceItem(
                **row.model_dump(),
                blocks_usd_rollup=row.blocks_usd_rollup(),
            )
            for row in rows
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
