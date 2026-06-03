import json
import time
from base64 import b64encode
from collections.abc import Iterator
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import Annotated, Any
from urllib import error, request
from urllib.parse import urlencode
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from fastapi.responses import StreamingResponse
from sqlalchemy import delete, func, or_, select
from sqlalchemy.orm import Session

from app.agents.planner import PLANNER_PROMPT_VERSION
from app.agents.subagent_manager import SUBAGENT_CONCURRENCY_LIMIT
from app.api.schemas import (
    AlertEventPage,
    AlertEventResponse,
    AlertRuleCreateRequest,
    AlertRulePage,
    AlertRuleResponse,
    AlertRuleUpdateRequest,
    CacheSourceSummary,
    CostRollupResponse,
    CountItem,
    EventSourcingArchitectureResponse,
    GrafanaDashboardPage,
    GrafanaDashboardResponse,
    MultiAgentArchitectureResponse,
    NotificationChannelCreateRequest,
    NotificationChannelPage,
    NotificationChannelResponse,
    NotificationChannelUpdateRequest,
    ObservabilityExportHistoryItem,
    ObservabilityExportHistoryPage,
    ObservabilityExportItem,
    ObservabilityExportPage,
    ObservabilityGroundingQualityItem,
    ObservabilityGroundingQualityResponse,
    ObservabilityLogEntry,
    ObservabilityLogPage,
    ObservabilityQueueResponse,
    ObservabilityServiceHealthResponse,
    ObservabilityServicesHealthResponse,
    ObservabilitySummaryResponse,
    ObservabilityTraceResponse,
    ObservabilityTraceServiceEdge,
    ObservabilityTraceServiceNode,
    ObservabilityTraceSpan,
    PlannerExecutorArchitectureResponse,
    RuntimeArchitectureResponse,
    SubagentArchitectureResponse,
    TokenSavingsLowCostRoute,
    TokenSavingsOmissionReason,
    TokenSavingsPage,
    TokenSavingsRunItem,
    TokenSavingsSummary,
    TraceListItem,
    TraceListResponse,
    WarmPoolArchitectureResponse,
    WarmPoolResponse,
)
from app.cache.query_cache import query_cache
from app.core.config import Settings, get_settings
from app.db.models import (
    Agent,
    AgentAssignment,
    AgentEvent,
    AgentHandoff,
    AgentRun,
    AlertEvent,
    AlertRule,
    ContextAssemblyManifest,
    EvalResult,
    EvalRun,
    ExecutionPlan,
    ModelCall,
    NotificationChannel,
    ObservabilityExportRecord,
    OtelSpan,
    SandboxInstance,
    Task,
    TaskSnapshot,
    ToolCall,
    WorkspaceContextCache,
)
from app.db.session import get_db_session
from app.events.event_store import SNAPSHOT_FREQUENCY_EVENTS
from app.observability.alert_evaluator import evaluate_alert_rules, validate_alert_rule_fields
from app.observability.cost_rollup import build_cost_rollup
from app.observability.notification_dispatcher import (
    redact_channel_config,
    validate_channel_config,
)
from app.sandbox.warm_pool import WarmPoolManager
from app.security.auth import Principal, require_role
from app.security.secrets import SECRET_PURPOSE_NOTIFICATION, SECRET_SCOPE_ORG, upsert_secret
from app.workers.subagent_worker import DEFAULT_SUBAGENT_TIMEOUT_SECONDS

router = APIRouter(prefix="/observability", tags=["observability"])
DEFAULT_CONTEXT_CACHE_SOURCES = ("compression_summary", "rag_retrieval", "long_term_memory")
DbSession = Annotated[Session, Depends(get_db_session)]
_cost_rollup_last_seen: dict[str, float] = {}


@router.get(
    "/cost-rollup",
    response_model=CostRollupResponse,
    summary="查询成本聚合",
    description="按时间窗口和维度聚合模型、专家和工具适配器成本证据。",
)
def get_cost_rollup(
    session: DbSession,
    principal: Principal,
    window: str = "7d",
    group_by: str = "agent",
) -> CostRollupResponse:
    try:
        if window not in {"24h", "7d", "30d", "all"}:
            raise ValueError("window must be one of 24h, 7d, 30d, all")
        if group_by not in {"agent", "provider", "specialist", "adapter"}:
            raise ValueError("group_by must be one of agent, provider, specialist, adapter")
        cache_key = f"cost_rollup:{principal.organization_id}:{window}:{group_by}"
        cached = query_cache.get_with_metrics(cache_key, entity="cost_rollup")
        if cached is not None:
            return CostRollupResponse.model_validate(cached)
        _check_cost_rollup_rate_limit(principal.organization_id)
        response = build_cost_rollup(
            session=session,
            organization_id=principal.organization_id,
            window=window,  # type: ignore[arg-type]
            group_by=group_by,  # type: ignore[arg-type]
        )
        query_cache.set(cache_key, response, ttl_seconds=60)
        return response
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get(
    "/traces",
    response_model=TraceListResponse,
    summary="查询 Trace 列表",
    description="返回本地 OpenTelemetry span 存储中的 Trace 摘要。",
)
def list_observability_traces(
    session: DbSession,
    principal: Principal,
    task_id: str | None = Query(default=None, description="任务 ID"),
    limit: int = Query(default=50, ge=1, le=200, description="返回数量"),
) -> TraceListResponse:
    rows = _local_trace_list(
        session=session,
        principal=principal,
        task_id=task_id,
        limit=limit,
    )
    return TraceListResponse(items=rows, next_cursor=None)


@router.get(
    "/alert-rules",
    response_model=AlertRulePage,
    summary="查询告警规则",
    description="返回当前组织和系统默认告警规则。",
)
def list_alert_rules(session: DbSession, principal: Principal) -> AlertRulePage:
    statement = select(AlertRule).where(
        or_(
            AlertRule.organization_id == principal.organization_id,
            AlertRule.organization_id.is_(None),
        )
    )
    rows = session.execute(statement.order_by(AlertRule.created_at.asc())).scalars()
    by_name: dict[str, AlertRule] = {}
    for row in rows:
        current = by_name.get(row.name)
        if current is None or row.organization_id == principal.organization_id:
            by_name[row.name] = row
    return AlertRulePage(
        items=[AlertRuleResponse.model_validate(row) for row in by_name.values()],
        next_cursor=None,
    )


@router.post(
    "/alert-rules",
    response_model=AlertRuleResponse,
    status_code=201,
    summary="创建告警规则",
    description="创建组织级告警规则；v1 通知通道仅支持 in_app。",
)
def create_alert_rule(
    request_body: AlertRuleCreateRequest,
    session: DbSession,
    principal: Principal,
) -> AlertRuleResponse:
    _validate_alert_payload(request_body)
    rule = AlertRule(
        organization_id=principal.organization_id,
        name=request_body.name,
        metric=request_body.metric,
        comparator=request_body.comparator,
        threshold=request_body.threshold,
        window_seconds=request_body.window_seconds,
        enabled=request_body.enabled,
        severity=request_body.severity,
        notification_channels_json=list(request_body.notification_channels_json),
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    session.add(rule)
    session.commit()
    session.refresh(rule)
    return AlertRuleResponse.model_validate(rule)


@router.patch(
    "/alert-rules/{rule_id}",
    response_model=AlertRuleResponse,
    summary="更新告警规则",
    description="更新当前组织告警规则；系统默认规则可复制为组织规则后禁用或调整。",
)
def update_alert_rule(
    rule_id: str,
    request_body: AlertRuleUpdateRequest,
    session: DbSession,
    principal: Principal,
) -> AlertRuleResponse:
    rule = _editable_alert_rule(session=session, principal=principal, rule_id=rule_id)
    _validate_alert_payload(request_body)
    updates = request_body.model_dump(exclude_unset=True)
    for key, value in updates.items():
        setattr(rule, key, value)
    rule.updated_at = datetime.now(UTC)
    session.commit()
    session.refresh(rule)
    return AlertRuleResponse.model_validate(rule)


@router.delete(
    "/alert-rules/{rule_id}",
    status_code=204,
    summary="删除告警规则",
    description="删除当前组织告警规则。",
)
def delete_alert_rule(rule_id: str, session: DbSession, principal: Principal) -> Response:
    rule = _owned_alert_rule(session=session, principal=principal, rule_id=rule_id)
    session.execute(delete(AlertEvent).where(AlertEvent.rule_id == rule.id))
    session.delete(rule)
    session.commit()
    return Response(status_code=204)


@router.post(
    "/alert-rules/evaluate",
    response_model=AlertEventPage,
    summary="手动评估告警规则",
    description="触发一次当前组织告警规则评估，便于本地验证。",
)
def evaluate_alert_rules_once(session: DbSession, principal: Principal) -> AlertEventPage:
    results = evaluate_alert_rules(session=session, organization_id=principal.organization_id)
    session.commit()
    event_ids = [result.event_id for result in results if result.event_id]
    if not event_ids:
        return AlertEventPage(items=[], next_cursor=None)
    events = session.execute(
        select(AlertEvent).where(AlertEvent.id.in_(event_ids)).order_by(AlertEvent.triggered_at.desc())
    ).scalars()
    return AlertEventPage(
        items=[AlertEventResponse.model_validate(event) for event in events],
        next_cursor=None,
    )


@router.get(
    "/alert-events",
    response_model=AlertEventPage,
    summary="查询告警事件",
    description="返回当前组织告警事件时间线。",
)
def list_alert_events(
    session: DbSession,
    principal: Principal,
    since: Annotated[datetime | None, Query(description="起始时间")] = None,
    limit: Annotated[int, Query(ge=1, le=200, description="返回数量")] = 50,
) -> AlertEventPage:
    statement = select(AlertEvent).where(AlertEvent.organization_id == principal.organization_id)
    if since is not None:
        statement = statement.where(AlertEvent.triggered_at >= since)
    events = session.execute(
        statement.order_by(AlertEvent.triggered_at.desc()).limit(limit)
    ).scalars()
    return AlertEventPage(
        items=[AlertEventResponse.model_validate(event) for event in events],
        next_cursor=None,
    )


@router.get(
    "/notification-channels",
    response_model=NotificationChannelPage,
    summary="查询外部通知通道",
    description="返回当前组织可用于告警派发的 Slack、Email 或 Webhook 通道。",
)
def list_notification_channels(session: DbSession, principal: Principal) -> NotificationChannelPage:
    require_role(principal, {"admin", "operator"})
    rows = session.execute(
        select(NotificationChannel)
        .where(NotificationChannel.organization_id == principal.organization_id)
        .order_by(NotificationChannel.created_at.asc(), NotificationChannel.name.asc())
    ).scalars()
    return NotificationChannelPage(
        items=[_notification_channel_response(row) for row in rows],
        next_cursor=None,
    )


@router.post(
    "/notification-channels",
    response_model=NotificationChannelResponse,
    status_code=201,
    summary="创建外部通知通道",
    description="创建组织级告警通知通道。密钥类字段会保存但不会回显。",
)
def create_notification_channel(
    payload: NotificationChannelCreateRequest,
    session: DbSession,
    principal: Principal,
) -> NotificationChannelResponse:
    require_role(principal, {"admin"})
    _validate_notification_channel_config(
        kind=payload.kind,
        config=payload.config_json,
        verified=payload.verified,
    )
    channel = NotificationChannel(
        organization_id=principal.organization_id,
        name=payload.name,
        kind=payload.kind,
        config_json={},
        verified=payload.verified,
        created_by=principal.user_id,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    session.add(channel)
    session.flush()
    channel.config_json = _store_notification_channel_secrets(
        session=session,
        principal=principal,
        channel=channel,
        config=dict(payload.config_json),
    )
    session.commit()
    session.refresh(channel)
    return _notification_channel_response(channel)


@router.patch(
    "/notification-channels/{channel_id}",
    response_model=NotificationChannelResponse,
    summary="更新外部通知通道",
    description="更新当前组织的告警通知通道。",
)
def update_notification_channel(
    channel_id: str,
    payload: NotificationChannelUpdateRequest,
    session: DbSession,
    principal: Principal,
) -> NotificationChannelResponse:
    require_role(principal, {"admin"})
    channel = _owned_notification_channel(
        session=session,
        principal=principal,
        channel_id=channel_id,
    )
    next_kind = payload.kind if payload.kind is not None else channel.kind
    next_config = payload.config_json if payload.config_json is not None else channel.config_json
    next_verified = payload.verified if payload.verified is not None else channel.verified
    _validate_notification_channel_config(
        kind=next_kind,
        config=next_config,
        verified=next_verified,
    )
    updates = payload.model_dump(exclude_unset=True)
    for key, value in updates.items():
        if key == "config_json":
            continue
        setattr(channel, key, value)
    if payload.config_json is not None:
        channel.config_json = _store_notification_channel_secrets(
            session=session,
            principal=principal,
            channel=channel,
            config=dict(payload.config_json),
        )
    channel.updated_at = datetime.now(UTC)
    session.commit()
    session.refresh(channel)
    return _notification_channel_response(channel)


@router.delete(
    "/notification-channels/{channel_id}",
    status_code=204,
    summary="删除外部通知通道",
    description="删除当前组织的告警通知通道。",
)
def delete_notification_channel(
    channel_id: str,
    session: DbSession,
    principal: Principal,
) -> Response:
    require_role(principal, {"admin"})
    channel = _owned_notification_channel(
        session=session,
        principal=principal,
        channel_id=channel_id,
    )
    session.delete(channel)
    session.commit()
    return Response(status_code=204)


@router.get(
    "/alert-events/stream",
    summary="订阅告警事件",
    description="通过 SSE 推送当前组织新的告警事件。",
)
def stream_alert_events(
    session: DbSession,
    principal: Principal,
    since: Annotated[datetime | None, Query(description="起始时间")] = None,
) -> StreamingResponse:
    bind = session.get_bind()
    session.close()
    from sqlalchemy.orm import sessionmaker

    poll_session_factory = sessionmaker(bind=bind, autoflush=False, autocommit=False)

    def iterator() -> Iterator[str]:
        cursor = since or datetime.now(UTC)
        idle_polls = 0
        while True:
            with poll_session_factory() as poll_session:
                events = list(
                    poll_session.execute(
                        select(AlertEvent)
                        .where(
                            AlertEvent.organization_id == principal.organization_id,
                            AlertEvent.triggered_at > cursor,
                        )
                        .order_by(AlertEvent.triggered_at.asc())
                        .limit(50)
                    ).scalars()
                )
            if events:
                idle_polls = 0
                for event in events:
                    cursor = event.triggered_at
                    payload = AlertEventResponse.model_validate(event).model_dump(mode="json")
                    yield f"id: {event.id}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"
                continue
            yield ": heartbeat\n\n"
            idle_polls += 1
            if idle_polls >= 30:
                break
            time.sleep(1)

    return StreamingResponse(
        iterator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no"},
    )


@router.get(
    "/summary",
    response_model=ObservabilitySummaryResponse,
    summary="查询观测聚合摘要",
    description="返回当前组织任务、模型、工具、沙箱、事件和 WarmPool 的聚合状态。",
)
def get_observability_summary(
    session: DbSession,
    principal: Principal,
) -> ObservabilitySummaryResponse:
    task_ids = select(Task.id).where(Task.organization_id == principal.organization_id)
    warm_pool = WarmPoolResponse.model_validate(WarmPoolManager().status(session=session).__dict__)
    return ObservabilitySummaryResponse(
        tasks_by_status=_count_items(
            session,
            select(Task.status, func.count(Task.id)).where(
                Task.organization_id == principal.organization_id
            ),
        ),
        subagents_by_status=_count_items(
            session,
            select(AgentRun.status, func.count(AgentRun.id)).where(AgentRun.task_id.in_(task_ids)),
        ),
        agent_assignments_by_status=_count_items(
            session,
            select(AgentAssignment.status, func.count(AgentAssignment.id)).where(
                AgentAssignment.run_id.in_(task_ids)
            ),
        ),
        model_calls_by_status=_count_items(
            session,
            select(ModelCall.status, func.count(ModelCall.id)).where(
                ModelCall.task_id.in_(task_ids)
            ),
        ),
        tool_calls_by_status=_count_items(
            session,
            select(ToolCall.status, func.count(ToolCall.id)).where(ToolCall.task_id.in_(task_ids)),
        ),
        sandboxes_by_status=_count_items(
            session,
            select(SandboxInstance.status, func.count(SandboxInstance.id)).where(
                SandboxInstance.task_id.in_(task_ids)
            ),
        ),
        subagent_queue=_subagent_queue_summary(
            session=session,
            organization_id=principal.organization_id,
        ),
        assignment_queue=_assignment_queue_summary(
            session=session,
            organization_id=principal.organization_id,
        ),
        warm_pool=warm_pool,
        event_total=_count_total(
            session,
            select(func.count(AgentEvent.id)).where(AgentEvent.task_id.in_(task_ids)),
        ),
        task_total=_count_total(
            session,
            select(func.count(Task.id)).where(Task.organization_id == principal.organization_id),
        ),
        failed_task_total=_count_total(
            session,
            select(func.count(Task.id)).where(
                Task.organization_id == principal.organization_id,
                Task.status == "FAILED",
            ),
        ),
        model_call_total=_count_total(
            session,
            select(func.count(ModelCall.id)).where(ModelCall.task_id.in_(task_ids)),
        ),
        tool_call_total=_count_total(
            session,
            select(func.count(ToolCall.id)).where(ToolCall.task_id.in_(task_ids)),
        ),
        sandbox_total=_count_total(
            session,
            select(func.count(SandboxInstance.id)).where(SandboxInstance.task_id.in_(task_ids)),
        ),
        token_optimization=_token_optimization_summary(session=session, task_ids=task_ids),
    )


@router.get(
    "/token-savings",
    response_model=TokenSavingsPage,
    summary="查询 Token 节省页面数据",
    description="返回当前组织的 Token Optimizer 汇总和最近运行证据。",
)
def get_token_savings(
    session: DbSession,
    principal: Principal,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> TokenSavingsPage:
    task_ids = select(Task.id).where(Task.organization_id == principal.organization_id)
    runs = _token_savings_runs(session=session, task_ids=task_ids, limit=limit)
    summary = _token_savings_summary(
        session=session,
        task_ids=task_ids,
        organization_id=principal.organization_id,
    )
    return TokenSavingsPage(
        generated_at=datetime.now(UTC),
        summary=summary,
        runs=runs,
        next_cursor=None,
    )


def _token_optimization_summary(session: Session, task_ids: object) -> dict:
    model_rows = list(
        session.execute(select(ModelCall).where(ModelCall.task_id.in_(task_ids))).scalars()
    )
    manifests = list(
        session.execute(
            select(ContextAssemblyManifest).where(ContextAssemblyManifest.run_id.in_(task_ids))
        ).scalars()
    )
    prompt_tokens = sum(row.prompt_tokens for row in model_rows)
    completion_tokens = sum(row.completion_tokens for row in model_rows)
    saved_tokens = 0
    cache_hits = 0
    cache_misses = 0
    cache_stale = 0
    cache_sources: dict[str, dict] = {}
    pruning_manifest_count = 0
    optimizer_version_ids: set[str] = set()
    optimizer_decision_count = 0
    for manifest in manifests:
        token_budget = (
            manifest.token_budget_json if isinstance(manifest.token_budget_json, dict) else {}
        )
        optimized = token_budget.get("optimized_vs_baseline", {})
        if isinstance(optimized, dict):
            saved_tokens += int(optimized.get("estimated_saved_tokens") or 0)
        if token_budget.get("pruning_applied"):
            pruning_manifest_count += 1
        context_cache = _context_cache_from_budget(token_budget)
        cache_hits += _int_value(context_cache.get("hit_count"))
        cache_misses += _int_value(context_cache.get("miss_count"))
        cache_stale += _int_value(context_cache.get("stale_count"))
        _merge_cache_sources(cache_sources, context_cache.get("sources"))
        for version_id in token_budget.get("optimizer_capability_version_ids", []):
            if version_id:
                optimizer_version_ids.add(str(version_id))
        decisions = token_budget.get("optimizer_decisions", [])
        if isinstance(decisions, list):
            optimizer_decision_count += len(decisions)
    low_cost_routes = [
        row
        for row in model_rows
        if isinstance(row.request_json, dict)
        and (
            row.request_json.get("low_cost_route") is True
            or row.request_json.get("low_cost_routing_reason")
        )
    ]
    return {
        "actual_prompt_tokens": prompt_tokens,
        "actual_completion_tokens": completion_tokens,
        "actual_total_tokens": prompt_tokens + completion_tokens,
        "estimated_saved_tokens": saved_tokens,
        "context_manifest_count": len(manifests),
        "pruning_manifest_count": pruning_manifest_count,
        "retrieval_cache_hit_count": cache_hits,
        "retrieval_cache_miss_count": cache_misses,
        "retrieval_cache_stale_count": cache_stale,
        "cache_sources": _cache_source_summary_models(cache_sources),
        "low_cost_route_count": len(low_cost_routes),
        "optimizer_capability_version_ids": sorted(optimizer_version_ids),
        "optimizer_decision_count": optimizer_decision_count,
    }


def _token_savings_summary(
    session: Session,
    task_ids: object,
    organization_id: str | None,
) -> TokenSavingsSummary:
    model_rows = list(
        session.execute(select(ModelCall).where(ModelCall.task_id.in_(task_ids))).scalars()
    )
    manifests = list(
        session.execute(
            select(ContextAssemblyManifest).where(ContextAssemblyManifest.run_id.in_(task_ids))
        ).scalars()
    )
    prompt_tokens = sum(int(row.prompt_tokens or 0) for row in model_rows)
    completion_tokens = sum(int(row.completion_tokens or 0) for row in model_rows)
    saved_tokens = 0
    candidate_tokens = 0
    included_tokens = 0
    omitted_tokens = 0
    cache_hits = 0
    cache_misses = 0
    cache_stale = 0
    cache_sources: dict[str, dict] = {}
    pruning_manifest_count = 0
    optimizer_version_ids: set[str] = set()
    optimizer_labels: set[str] = set()
    optimizer_decision_count = 0
    for manifest in manifests:
        token_budget = _dict_or_empty(manifest.token_budget_json)
        token_counts = _token_budget_counts(token_budget)
        saved_tokens += token_counts["saved"]
        candidate_tokens += token_counts["candidate"]
        included_tokens += token_counts["included"]
        omitted_tokens += token_counts["omitted"]
        if token_budget.get("pruning_applied"):
            pruning_manifest_count += 1
        context_cache = _context_cache_from_budget(token_budget)
        cache_hits += _int_value(context_cache.get("hit_count"))
        cache_misses += _int_value(context_cache.get("miss_count"))
        cache_stale += _int_value(context_cache.get("stale_count"))
        _merge_cache_sources(cache_sources, context_cache.get("sources"))
        for version_id in _string_list(token_budget.get("optimizer_capability_version_ids")):
            optimizer_version_ids.add(version_id)
        optimizer_labels.update(_optimizer_labels(token_budget))
        decisions = token_budget.get("optimizer_decisions", [])
        if isinstance(decisions, list):
            optimizer_decision_count += len(decisions)
    persisted_cache = _workspace_context_cache_sources(
        session=session,
        organization_id=organization_id,
    )
    cache_hits += _int_value(persisted_cache.get("hit_count"))
    cache_misses += _int_value(persisted_cache.get("miss_count"))
    cache_stale += _int_value(persisted_cache.get("stale_count"))
    _merge_cache_sources(cache_sources, persisted_cache.get("sources"))
    low_cost_routes = [
        row
        for row in model_rows
        if isinstance(row.request_json, dict)
        and (
            row.request_json.get("low_cost_route") is True
            or row.request_json.get("low_cost_routing_reason")
        )
    ]
    savings_percent = round((saved_tokens / candidate_tokens) * 100, 2) if candidate_tokens else 0
    return TokenSavingsSummary(
        actual_prompt_tokens=prompt_tokens,
        actual_completion_tokens=completion_tokens,
        actual_total_tokens=prompt_tokens + completion_tokens,
        estimated_candidate_tokens=candidate_tokens,
        estimated_included_tokens=included_tokens,
        estimated_omitted_tokens=omitted_tokens,
        estimated_saved_tokens=saved_tokens,
        estimated_savings_percent=savings_percent,
        context_manifest_count=len(manifests),
        pruning_manifest_count=pruning_manifest_count,
        retrieval_cache_hit_count=cache_hits,
        retrieval_cache_miss_count=cache_misses,
        retrieval_cache_stale_count=cache_stale,
        cache_sources=_cache_source_summary_models(cache_sources),
        low_cost_route_count=len(low_cost_routes),
        optimizer_capability_version_ids=sorted(optimizer_version_ids),
        optimizer_labels=sorted(optimizer_labels),
        optimizer_decision_count=optimizer_decision_count,
    )


def _token_savings_runs(
    *,
    session: Session,
    task_ids: object,
    limit: int,
) -> list[TokenSavingsRunItem]:
    rows = list(
        session.execute(
            select(Task, ContextAssemblyManifest)
            .join(ContextAssemblyManifest, ContextAssemblyManifest.run_id == Task.id)
            .where(Task.id.in_(task_ids))
            .order_by(ContextAssemblyManifest.created_at.desc(), ContextAssemblyManifest.id.desc())
            .limit(limit)
        ).all()
    )
    if not rows:
        return []
    run_ids = [task.id for task, _manifest in rows]
    model_calls_by_run: dict[str, list[ModelCall]] = {run_id: [] for run_id in run_ids}
    model_calls = list(
        session.execute(select(ModelCall).where(ModelCall.task_id.in_(run_ids))).scalars()
    )
    for call in model_calls:
        model_calls_by_run.setdefault(call.task_id, []).append(call)

    items: list[TokenSavingsRunItem] = []
    for task, manifest in rows:
        token_budget = _dict_or_empty(manifest.token_budget_json)
        token_counts = _token_budget_counts(token_budget)
        context_cache = _context_cache_from_budget(token_budget)
        run_model_calls = model_calls_by_run.get(task.id, [])
        prompt_tokens = sum(int(call.prompt_tokens or 0) for call in run_model_calls)
        completion_tokens = sum(int(call.completion_tokens or 0) for call in run_model_calls)
        version_ids = _string_list(token_budget.get("optimizer_capability_version_ids"))
        labels = _optimizer_labels(token_budget)
        decisions = token_budget.get("optimizer_decisions", [])
        items.append(
            TokenSavingsRunItem(
                run_id=task.id,
                agent_id=task.agent_id,
                title=task.title,
                status=task.status,
                created_at=task.created_at,
                updated_at=task.updated_at,
                context_manifest_id=manifest.id,
                estimated_candidate_tokens=token_counts["candidate"],
                estimated_included_tokens=token_counts["included"],
                estimated_omitted_tokens=token_counts["omitted"],
                estimated_saved_tokens=token_counts["saved"],
                estimated_savings_percent=token_counts["percent"],
                actual_prompt_tokens=prompt_tokens,
                actual_completion_tokens=completion_tokens,
                actual_total_tokens=prompt_tokens + completion_tokens,
                included_count=len(manifest.included_refs_json or []),
                omitted_count=len(manifest.omitted_refs_json or []),
                pruning_applied=bool(token_budget.get("pruning_applied")),
                retrieval_cache_hit_count=_int_value(context_cache.get("hit_count")),
                retrieval_cache_miss_count=_int_value(context_cache.get("miss_count")),
                retrieval_cache_stale_count=_int_value(context_cache.get("stale_count")),
                cache_sources=_cache_source_summary_models_from_context(context_cache),
                low_cost_routes=_low_cost_routes_for_calls(run_model_calls),
                optimizer_capability_version_ids=version_ids,
                optimizer_labels=labels,
                optimizer_policy_hash=token_budget.get("optimizer_policy_hash"),
                optimizer_decision_count=len(decisions) if isinstance(decisions, list) else 0,
                omission_reasons=_omission_reasons(manifest.omitted_refs_json),
            )
        )
    return items


def _token_budget_counts(token_budget: dict) -> dict[str, int | float]:
    optimized = _dict_or_empty(token_budget.get("optimized_vs_baseline"))
    saved = _int_value(optimized.get("estimated_saved_tokens"))
    omitted = _int_value(token_budget.get("estimated_omitted_tokens")) or saved
    included = _int_value(token_budget.get("estimated_included_tokens")) or _int_value(
        optimized.get("optimized_estimated_tokens")
    )
    candidate = _int_value(token_budget.get("estimated_candidate_tokens")) or _int_value(
        optimized.get("baseline_estimated_tokens")
    )
    if not candidate and included + omitted:
        candidate = included + omitted
    if not included and candidate:
        included = max(candidate - omitted, 0)
    percent = _float_value(optimized.get("estimated_savings_percent"))
    if not percent and candidate:
        percent = round((saved / candidate) * 100, 2)
    return {
        "candidate": candidate,
        "included": included,
        "omitted": omitted,
        "saved": saved,
        "percent": percent,
    }


def _dict_or_empty(value: object) -> dict:
    return value if isinstance(value, dict) else {}


def _context_cache_from_budget(token_budget: dict) -> dict:
    context_cache = _dict_or_empty(token_budget.get("context_cache"))
    if context_cache:
        return context_cache
    retrieval_cache = _dict_or_empty(token_budget.get("retrieval_cache"))
    if not retrieval_cache:
        return {}
    return {
        "hit_count": _int_value(retrieval_cache.get("hit_count")),
        "miss_count": _int_value(retrieval_cache.get("miss_count")),
        "stale_count": _int_value(retrieval_cache.get("stale_count")),
        "status_counts": _dict_or_empty(retrieval_cache.get("status_counts")),
        "sources": [
            {
                "cache_source": "legacy_retrieval_cache",
                "label": "上下文缓存",
                "hit_count": _int_value(retrieval_cache.get("hit_count")),
                "miss_count": _int_value(retrieval_cache.get("miss_count")),
                "stale_count": _int_value(retrieval_cache.get("stale_count")),
                "estimated_saved_tokens": 0,
                "reason": None,
            }
        ],
    }


def _merge_cache_sources(target: dict[str, dict], sources: object) -> None:
    if not isinstance(sources, list):
        return
    for source in sources:
        if not isinstance(source, dict):
            continue
        key = str(source.get("cache_source") or "unknown")
        row = target.setdefault(
            key,
            {
                "cache_source": key,
                "label": str(source.get("label") or _cache_source_label(key)),
                "hit_count": 0,
                "miss_count": 0,
                "stale_count": 0,
                "estimated_saved_tokens": 0,
                "reason": None,
            },
        )
        row["hit_count"] += _int_value(source.get("hit_count"))
        row["miss_count"] += _int_value(source.get("miss_count"))
        row["stale_count"] += _int_value(source.get("stale_count"))
        row["estimated_saved_tokens"] += _int_value(source.get("estimated_saved_tokens"))
        if source.get("reason"):
            row["reason"] = str(source["reason"])


def _workspace_context_cache_sources(
    *,
    session: Session,
    organization_id: str | None,
) -> dict[str, Any]:
    rows = list(
        session.execute(
            select(WorkspaceContextCache).where(
                WorkspaceContextCache.organization_id == organization_id,
                WorkspaceContextCache.status == "active",
            )
        ).scalars()
    )
    sources = []
    for row in rows:
        metadata = row.metadata_json if isinstance(row.metadata_json, dict) else {}
        sources.append(
            {
                "cache_source": row.cache_source,
                "label": _cache_source_label(row.cache_source),
                "hit_count": row.hit_count,
                "miss_count": row.miss_count,
                "stale_count": row.stale_count,
                "estimated_saved_tokens": row.estimated_saved_tokens,
                "reason": metadata.get("reason"),
            }
        )
    return {
        "hit_count": sum(row.hit_count for row in rows),
        "miss_count": sum(row.miss_count for row in rows),
        "stale_count": sum(row.stale_count for row in rows),
        "sources": sources,
    }


def _cache_source_summary_models_from_context(context_cache: dict) -> list[CacheSourceSummary]:
    rows: dict[str, dict] = {}
    _merge_cache_sources(rows, context_cache.get("sources"))
    return _cache_source_summary_models(rows)


def _cache_source_summary_models(rows: dict[str, dict]) -> list[CacheSourceSummary]:
    for source in DEFAULT_CONTEXT_CACHE_SOURCES:
        rows.setdefault(
            source,
            {
                "cache_source": source,
                "label": _cache_source_label(source),
                "hit_count": 0,
                "miss_count": 0,
                "stale_count": 0,
                "estimated_saved_tokens": 0,
                "reason": None,
            },
        )
    out = []
    ordered_keys = [
        *DEFAULT_CONTEXT_CACHE_SOURCES,
        *sorted(key for key in rows if key not in DEFAULT_CONTEXT_CACHE_SOURCES),
    ]
    for key in ordered_keys:
        row = rows[key]
        hit_count = _int_value(row.get("hit_count"))
        miss_count = _int_value(row.get("miss_count"))
        stale_count = _int_value(row.get("stale_count"))
        total = hit_count + miss_count + stale_count
        hit_rate = round((hit_count / total) * 100, 2) if total else 0
        out.append(
            CacheSourceSummary(
                cache_source=key,
                label=str(row.get("label") or _cache_source_label(key)),
                hit_count=hit_count,
                miss_count=miss_count,
                stale_count=stale_count,
                estimated_saved_tokens=_int_value(row.get("estimated_saved_tokens")),
                hit_rate=hit_rate,
                reason=str(row["reason"]) if row.get("reason") else None,
            )
        )
    return out


def _cache_source_label(source: str) -> str:
    return {
        "compression_summary": "摘要缓存",
        "rag_retrieval": "RAG 检索",
        "long_term_memory": "长期记忆",
        "legacy_retrieval_cache": "上下文缓存",
    }.get(source, source)


def _int_value(value: object) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _float_value(value: object) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if item]


def _optimizer_labels(token_budget: dict) -> list[str]:
    labels: set[str] = set()
    decisions = token_budget.get("optimizer_decisions", [])
    if isinstance(decisions, list):
        for decision in decisions:
            if not isinstance(decision, dict):
                continue
            package_name = str(decision.get("package_name") or "")
            for preset_id, label in _optimizer_preset_labels().items():
                if f"builtin-token-optimizer-{preset_id}" == package_name:
                    labels.add(label)
    version_ids = _string_list(token_budget.get("optimizer_capability_version_ids"))
    if version_ids and not labels:
        labels.add("自定义优化器")
    return sorted(labels)


def _optimizer_preset_labels() -> dict[str, str]:
    return {
        "conservative": "保守省 Token",
        "balanced": "均衡",
        "aggressive": "强力省 Token",
    }


def _low_cost_routes_for_calls(model_calls: list[ModelCall]) -> list[TokenSavingsLowCostRoute]:
    routes: list[TokenSavingsLowCostRoute] = []
    for call in model_calls:
        reason = _low_cost_route_reason(call)
        if reason is None:
            continue
        routes.append(
            TokenSavingsLowCostRoute(
                model_call_id=call.id,
                model_name=call.model_name,
                reason=reason,
            )
        )
    return routes


def _low_cost_route_reason(call: ModelCall) -> str | None:
    for payload in (call.request_json, call.response_json):
        if not isinstance(payload, dict):
            continue
        reason = payload.get("low_cost_routing_reason") or payload.get("model_routing_reason")
        if reason:
            return str(reason)
        if payload.get("low_cost_route") is True:
            return "low_cost_route"
    return None


def _omission_reasons(omitted_refs: object) -> list[TokenSavingsOmissionReason]:
    counts: dict[str, int] = {}
    if not isinstance(omitted_refs, list):
        return []
    for ref in omitted_refs:
        if not isinstance(ref, dict):
            continue
        reason = str(ref.get("omission_reason") or "token_budget")
        counts[reason] = counts.get(reason, 0) + 1
    return [
        TokenSavingsOmissionReason(reason=reason, count=count)
        for reason, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    ]


@router.get(
    "/grounding-quality",
    response_model=ObservabilityGroundingQualityResponse,
    summary="查询 Grounding Quality 投影",
    description="只投影 Eval 已计算的 grounding trace/metrics，不重新扫描原始 evidence。",
)
def get_grounding_quality(
    session: DbSession,
    principal: Principal,
    dataset_id: Annotated[str | None, Query()] = None,
    eval_run_id: Annotated[str | None, Query()] = None,
    agent_id: Annotated[str | None, Query()] = None,
    failure_type: Annotated[str | None, Query()] = None,
    grounding_passed: Annotated[bool | None, Query()] = None,
    forbidden_evidence_leaked: Annotated[bool | None, Query()] = None,
    fallback_mismatch: Annotated[bool | None, Query()] = None,
    unsupported_marker_present: Annotated[bool | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> ObservabilityGroundingQualityResponse:
    filters = [EvalRun.organization_id == principal.organization_id]
    if dataset_id:
        filters.append(EvalRun.dataset_id.startswith(dataset_id.strip()))
    if eval_run_id:
        filters.append(EvalRun.id.startswith(eval_run_id.strip()))
    if agent_id:
        filters.append(EvalRun.agent_id == agent_id)

    rows = list(
        session.execute(
            select(EvalRun, EvalResult)
            .join(EvalResult, EvalResult.eval_run_id == EvalRun.id)
            .where(*filters)
            .order_by(EvalResult.created_at.desc(), EvalResult.id.desc())
        ).all()
    )
    items: list[ObservabilityGroundingQualityItem] = []
    failure_counts: dict[str, int] = {}
    metric_totals = {
        "grounding_pass_rate": 0.0,
        "citation_coverage_rate": 0.0,
        "forbidden_evidence_leak_rate": 0.0,
        "fallback_mismatch_rate": 0.0,
        "unsupported_marker_rate": 0.0,
        "required_evidence_miss_rate": 0.0,
    }
    for eval_run, result in rows:
        trace = _project_grounding_trace(result.grader_trace_json)
        failures = trace["grounding_failures"]
        item_fallback_mismatch = bool(trace["fallback_expected"]) != bool(
            trace["fallback_observed"]
        )
        item_unsupported_marker_present = "unsupported_marker_present" in failures
        if failure_type and not _failure_type_matches(failure_type, failures):
            continue
        if grounding_passed is not None and bool(trace["passed"]) != grounding_passed:
            continue
        if (
            forbidden_evidence_leaked is not None
            and bool(trace["forbidden_evidence_leaked"]) != forbidden_evidence_leaked
        ):
            continue
        if fallback_mismatch is not None and item_fallback_mismatch != fallback_mismatch:
            continue
        if (
            unsupported_marker_present is not None
            and item_unsupported_marker_present != unsupported_marker_present
        ):
            continue
        if len(items) >= limit:
            break
        for failure in failures:
            failure_counts[failure] = failure_counts.get(failure, 0) + 1
        metric_totals["grounding_pass_rate"] += 1.0 if trace["passed"] else 0.0
        metric_totals["citation_coverage_rate"] += (
            1.0 if "citation_hit_mismatch" not in failures else 0.0
        )
        metric_totals["forbidden_evidence_leak_rate"] += (
            1.0 if trace["forbidden_evidence_leaked"] else 0.0
        )
        metric_totals["fallback_mismatch_rate"] += 1.0 if item_fallback_mismatch else 0.0
        metric_totals["unsupported_marker_rate"] += (
            1.0 if item_unsupported_marker_present else 0.0
        )
        metric_totals["required_evidence_miss_rate"] += (
            1.0 if "missing_required_evidence" in failures else 0.0
        )
        items.append(
            ObservabilityGroundingQualityItem(
                eval_run_id=eval_run.id,
                eval_result_id=result.id,
                eval_case_id=result.eval_case_id,
                task_id=result.task_id,
                dataset_id=eval_run.dataset_id,
                agent_id=eval_run.agent_id,
                status=result.status,
                created_at=result.created_at,
                grounding_passed=bool(trace["passed"]),
                grounding_failures=failures,
                forbidden_evidence_leaked=bool(trace["forbidden_evidence_leaked"]),
                forbidden_leak_sources=trace["forbidden_leak_sources"],
                fallback_expected=bool(trace["fallback_expected"]),
                fallback_observed=bool(trace["fallback_observed"]),
                unsupported_marker_present=item_unsupported_marker_present,
                citation_keys=trace["citation_keys"],
                citation_hit_ids=trace["citation_hit_ids"],
                retrieval_session_id=trace["retrieval_session_id"],
                prompt_manifest_id=trace["prompt_manifest_id"],
            )
        )
    total = len(items) or 1
    metrics = {key: round(value / total, 4) for key, value in metric_totals.items()}
    metrics["grounding_failure_total"] = sum(failure_counts.values())
    metrics["case_total"] = len(items)
    return ObservabilityGroundingQualityResponse(
        items=items,
        metrics=metrics,
        failure_facets=[
            CountItem(name=name, count=count)
            for name, count in sorted(failure_counts.items(), key=lambda item: item[0])
        ],
        total=len(items),
    )


@router.get(
    "/architecture",
    response_model=RuntimeArchitectureResponse,
    summary="查询运行时架构能力",
    description=(
        "返回 Planner/Executor、Event Sourcing、Subagent 编排和 WarmPool 的当前组织能力摘要。"
    ),
)
def get_runtime_architecture(
    session: DbSession,
    principal: Principal,
) -> RuntimeArchitectureResponse:
    task_ids = select(Task.id).where(Task.organization_id == principal.organization_id)
    plan_rows = list(
        session.execute(select(ExecutionPlan.plan_json).where(ExecutionPlan.task_id.in_(task_ids)))
    )
    sync_step_total = 0
    async_step_total = 0
    langgraph_step_total = 0
    for (plan_json,) in plan_rows:
        for raw_step in plan_json.get("steps", []) if isinstance(plan_json, dict) else []:
            if not isinstance(raw_step, dict):
                continue
            if raw_step.get("execution_mode") == "async":
                async_step_total += 1
            elif raw_step.get("execution_mode") == "langgraph_node":
                langgraph_step_total += 1
            else:
                sync_step_total += 1

    event_total = _count_total(
        session,
        select(func.count(AgentEvent.id)).where(AgentEvent.task_id.in_(task_ids)),
    )
    snapshot_total = _count_total(
        session,
        select(func.count(TaskSnapshot.id)).where(TaskSnapshot.task_id.in_(task_ids)),
    )
    last_sequence = int(
        session.execute(
            select(func.coalesce(func.max(AgentEvent.sequence), 0)).where(
                AgentEvent.task_id.in_(task_ids)
            )
        ).scalar_one()
        or 0
    )
    subagent_queue = _subagent_queue_summary(
        session=session,
        organization_id=principal.organization_id,
    )
    assignment_queue = _assignment_queue_summary(
        session=session,
        organization_id=principal.organization_id,
    )
    agent_total = _count_total(
        session,
        select(func.count(Agent.id)).where(
            (Agent.organization_id == principal.organization_id) | (Agent.organization_id.is_(None))
        ),
    )
    assignment_total = _count_total(
        session,
        select(func.count(AgentAssignment.id)).where(AgentAssignment.run_id.in_(task_ids)),
    )
    handoff_total = _count_total(
        session,
        select(func.count(AgentHandoff.id)).where(AgentHandoff.run_id.in_(task_ids)),
    )
    warm_pool = WarmPoolResponse.model_validate(WarmPoolManager().status(session=session).__dict__)
    subagent_status = (
        "saturated" if subagent_queue.active_total >= SUBAGENT_CONCURRENCY_LIMIT else "ready"
    )
    multi_agent_status = "active" if assignment_queue.active_total > 0 else "ready"
    warm_pool_status = "ready" if warm_pool.idle > 0 else "cold"
    return RuntimeArchitectureResponse(
        planner_executor=PlannerExecutorArchitectureResponse(
            enabled=True,
            planner="LLM-driven planner with deterministic fallback",
            executor="Executor",
            react_engine="ReAct Engine",
            planner_prompt_version=PLANNER_PROMPT_VERSION,
            plan_total=len(plan_rows),
            sync_step_total=sync_step_total,
            async_step_total=async_step_total,
            langgraph_step_total=langgraph_step_total,
            status="active",
        ),
        event_sourcing=EventSourcingArchitectureResponse(
            enabled=True,
            event_total=event_total,
            snapshot_total=snapshot_total,
            snapshot_frequency_events=SNAPSHOT_FREQUENCY_EVENTS,
            replay_enabled=True,
            resume_enabled=True,
            audit_log_enabled=True,
            time_travel_debugging_enabled=True,
            last_sequence=last_sequence,
        ),
        multi_agent=MultiAgentArchitectureResponse(
            enabled=True,
            agent_total=agent_total,
            assignment_total=assignment_total,
            handoff_total=handoff_total,
            pending=assignment_queue.pending,
            queued=assignment_queue.queued,
            running=assignment_queue.running,
            success=assignment_queue.success,
            failed=assignment_queue.failed,
            active_total=assignment_queue.active_total,
            state_machine=[
                "PENDING",
                "QUEUED",
                "RUNNING",
                "SUCCESS",
                "FAILED",
            ],
            strategy="router_parallel_fanout_reduce",
            reducer_enabled=True,
            status=multi_agent_status,
        ),
        subagents=SubagentArchitectureResponse(
            enabled=True,
            concurrency_limit=SUBAGENT_CONCURRENCY_LIMIT,
            timeout_seconds=DEFAULT_SUBAGENT_TIMEOUT_SECONDS,
            pending=subagent_queue.pending,
            running=subagent_queue.running,
            success=subagent_queue.success,
            failed=subagent_queue.failed,
            timeout=subagent_queue.timeout,
            cancelled=subagent_queue.cancelled,
            active_total=subagent_queue.active_total,
            state_machine=[
                "PENDING",
                "RUNNING",
                "SUCCESS",
                "FAILED",
                "TIMEOUT",
                "CANCELLED",
            ],
            status=subagent_status,
        ),
        warm_pool=WarmPoolArchitectureResponse(
            enabled=warm_pool.enabled,
            target_startup_ms=50,
            cold_start_min_ms=100,
            cold_start_max_ms=500,
            min_size=warm_pool.min_size,
            max_size=warm_pool.max_size,
            idle=warm_pool.idle,
            busy=warm_pool.busy,
            failed=warm_pool.failed,
            hit_total=warm_pool.hit_total,
            miss_total=warm_pool.miss_total,
            status=warm_pool_status,
        ),
        notes=[
            "Planner 负责结构化任务分解，Executor 负责同步 ReAct 步骤。",
            "多 Agent 编排由 Router 创建具名 Agent assignments，并通过 Reducer 聚合分支输出。",
            "异步长任务通过 Subagent 派生，父 Executor 不等待 worker 完成。",
            "全部关键操作进入事件流，可用于审计、重放和恢复。",
            "WarmPool 命中默认资源策略时复用预热容器，目标启动耗时小于 50ms。",
        ],
    )


@router.get(
    "/logs",
    response_model=ObservabilityLogPage,
    summary="查询结构化日志",
    description=(
        "按任务、trace、服务和事件类型查询结构化日志；Loki 不可用时返回 Event Store 日志视图。"
    ),
)
def list_observability_logs(
    session: DbSession,
    principal: Principal,
    task_id: str | None = Query(default=None, description="任务 ID"),
    trace_id: str | None = Query(default=None, description="Trace ID"),
    service: str | None = Query(default=None, description="服务名"),
    event_type: str | None = Query(default=None, description="事件类型"),
    limit: int = Query(default=100, ge=1, le=500, description="返回数量"),
) -> ObservabilityLogPage:
    return _observability_logs(
        session=session,
        principal=principal,
        task_id=task_id,
        trace_id=trace_id,
        service=service,
        event_type=event_type,
        limit=limit,
    )


@router.get(
    "/exports",
    response_model=ObservabilityExportPage,
    summary="查询观测导出入口",
    description="仅 admin、operator 可访问。返回日志、Trace、Grafana 和服务健康导出入口。",
)
def list_observability_exports(principal: Principal) -> ObservabilityExportPage:
    require_observability_operator(principal)
    return ObservabilityExportPage(
        items=[
            ObservabilityExportItem(
                name="logs_jsonl",
                title="结构化日志 JSONL",
                description="按任务、Trace、服务和事件类型导出结构化日志。",
                method="GET",
                url="/api/observability/exports/logs",
                format="jsonl",
                required_roles=["admin", "operator"],
            ),
            ObservabilityExportItem(
                name="trace_json",
                title="Trace 链路 JSON",
                description="按 trace_id 导出 Tempo 或 Event Store 链路 span。",
                method="GET",
                url="/api/observability/exports/traces/{trace_id}",
                format="json",
                required_roles=["admin", "operator"],
            ),
            ObservabilityExportItem(
                name="grafana_dashboards_json",
                title="Grafana Dashboard JSON",
                description="导出后端代理可见的 Grafana dashboard 列表。",
                method="GET",
                url="/api/observability/exports/grafana/dashboards",
                format="json",
                required_roles=["admin", "operator"],
            ),
            ObservabilityExportItem(
                name="services_health_json",
                title="观测服务健康 JSON",
                description="导出 Prometheus、Grafana、Loki、OTel Collector 和 Tempo 健康状态。",
                method="GET",
                url="/api/observability/exports/services/health",
                format="json",
                required_roles=["admin", "operator"],
            ),
        ]
    )


@router.get(
    "/exports/history",
    response_model=ObservabilityExportHistoryPage,
    summary="查询观测导出历史",
    description="仅 admin、operator 可访问。返回已留存的观测导出文件历史。",
)
def list_observability_export_history(
    session: DbSession,
    principal: Principal,
    export_type: str | None = Query(default=None, description="导出类型"),
    limit: int = Query(default=20, ge=1, le=100, description="返回数量"),
) -> ObservabilityExportHistoryPage:
    require_observability_operator(principal)
    statement = select(ObservabilityExportRecord).where(
        ObservabilityExportRecord.organization_id == principal.organization_id
    )
    if export_type is not None:
        statement = statement.where(ObservabilityExportRecord.export_type == export_type)
    records = session.execute(
        statement.order_by(ObservabilityExportRecord.created_at.desc()).limit(limit)
    ).scalars()
    return ObservabilityExportHistoryPage(
        items=[_export_history_item(record) for record in records],
        next_cursor=None,
    )


@router.get(
    "/exports/history/{export_id}/download",
    response_class=Response,
    summary="下载观测导出历史文件",
    description="仅 admin、operator 可访问。按导出记录 ID 下载已留存文件。",
    responses={
        200: {
            "description": "导出文件",
            "content": {"application/octet-stream": {}},
        }
    },
)
def download_observability_export_history(
    export_id: str,
    session: DbSession,
    principal: Principal,
) -> Response:
    require_observability_operator(principal)
    record = session.get(ObservabilityExportRecord, export_id)
    if record is None or record.organization_id != principal.organization_id:
        raise HTTPException(status_code=404, detail="导出记录不存在")
    path = Path(record.storage_uri)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="导出文件不存在")
    return Response(
        content=path.read_bytes(),
        media_type=record.content_type,
        headers=_export_headers(record=record),
    )


@router.get(
    "/exports/logs",
    response_class=Response,
    summary="导出结构化日志",
    description=(
        "仅 admin、operator 可访问。按任务、trace、服务和事件类型导出 JSONL；"
        "Loki 不可用时导出 Event Store 日志视图。"
    ),
    responses={
        200: {
            "description": "JSONL 导出文件",
            "content": {"application/x-ndjson": {}},
        }
    },
)
def export_observability_logs(
    session: DbSession,
    principal: Principal,
    task_id: str | None = Query(default=None, description="任务 ID"),
    trace_id: str | None = Query(default=None, description="Trace ID"),
    service: str | None = Query(default=None, description="服务名"),
    event_type: str | None = Query(default=None, description="事件类型"),
    limit: int = Query(default=100, ge=1, le=500, description="返回数量"),
) -> Response:
    require_observability_operator(principal)
    page = _observability_logs(
        session=session,
        principal=principal,
        task_id=task_id,
        trace_id=trace_id,
        service=service,
        event_type=event_type,
        limit=limit,
    )
    lines = [
        json.dumps(item.model_dump(mode="json"), ensure_ascii=False, sort_keys=True)
        for item in page.items
    ]
    body = "\n".join(lines) + ("\n" if lines else "")
    record = _persist_export(
        session=session,
        principal=principal,
        export_type="logs_jsonl",
        filename="observability-logs.jsonl",
        content_type="application/x-ndjson",
        export_format="jsonl",
        source=page.source,
        row_count=len(page.items),
        filter_json={
            "task_id": task_id,
            "trace_id": trace_id,
            "service": service,
            "event_type": event_type,
            "limit": limit,
        },
        body=body.encode("utf-8"),
    )
    return Response(
        content=body,
        media_type="application/x-ndjson",
        headers=_export_headers(record=record),
    )


@router.get(
    "/exports/traces/{trace_id}",
    response_model=ObservabilityTraceResponse,
    summary="导出 Trace 链路",
    description="仅 admin、operator 可访问。按 trace_id 导出 Trace 链路 JSON。",
)
def export_observability_trace(
    trace_id: str,
    session: DbSession,
    principal: Principal,
    response: Response,
    service: str | None = Query(default=None, description="服务名"),
    span_name: str | None = Query(default=None, description="Span 名称"),
    attribute_key: str | None = Query(default=None, description="Span 属性键"),
    attribute_value: str | None = Query(default=None, description="Span 属性值"),
) -> ObservabilityTraceResponse:
    require_observability_operator(principal)
    payload = _observability_trace(
        trace_id=trace_id,
        session=session,
        principal=principal,
        service=service,
        span_name=span_name,
        attribute_key=attribute_key,
        attribute_value=attribute_value,
    )
    filename = f"observability-trace-{_safe_filename(trace_id)}.json"
    record = _persist_export(
        session=session,
        principal=principal,
        export_type="trace_json",
        filename=filename,
        content_type="application/json",
        export_format="json",
        source=payload.source,
        row_count=len(payload.spans),
        filter_json={
            "trace_id": trace_id,
            "service": service,
            "span_name": span_name,
            "attribute_key": attribute_key,
            "attribute_value": attribute_value,
        },
        body=payload.model_dump_json().encode("utf-8"),
    )
    for key, value in _export_headers(record=record).items():
        response.headers[key] = value
    return payload


@router.get(
    "/exports/grafana/dashboards",
    response_model=GrafanaDashboardPage,
    summary="导出 Grafana Dashboard",
    description="仅 admin、operator 可访问。导出后端代理可见的 Grafana dashboard 列表。",
)
def export_grafana_dashboards(
    session: DbSession,
    principal: Principal,
    response: Response,
) -> GrafanaDashboardPage:
    page = list_grafana_dashboards(principal)
    record = _persist_export(
        session=session,
        principal=principal,
        export_type="grafana_dashboards_json",
        filename="grafana-dashboards.json",
        content_type="application/json",
        export_format="json",
        source="grafana" if any(item.source == "grafana" for item in page.items) else "configured",
        row_count=len(page.items),
        filter_json={},
        body=page.model_dump_json().encode("utf-8"),
    )
    for key, value in _export_headers(record=record).items():
        response.headers[key] = value
    return page


@router.get(
    "/exports/services/health",
    response_model=ObservabilityServicesHealthResponse,
    summary="导出观测服务健康",
    description="仅 admin、operator 可访问。导出观测服务健康 JSON。",
)
def export_observability_services_health(
    session: DbSession,
    principal: Principal,
    response: Response,
) -> ObservabilityServicesHealthResponse:
    payload = get_observability_services_health(principal)
    record = _persist_export(
        session=session,
        principal=principal,
        export_type="services_health_json",
        filename="observability-health.json",
        content_type="application/json",
        export_format="json",
        source="probe",
        row_count=len(payload.services),
        filter_json={},
        body=payload.model_dump_json().encode("utf-8"),
    )
    for key, value in _export_headers(record=record).items():
        response.headers[key] = value
    return payload


def _observability_logs(
    *,
    session: Session,
    principal: Principal,
    task_id: str | None,
    trace_id: str | None,
    service: str | None,
    event_type: str | None,
    limit: int,
) -> ObservabilityLogPage:
    loki_entries = _query_loki_logs(
        task_id=task_id,
        trace_id=trace_id,
        service=service,
        event_type=event_type,
        limit=limit,
    )
    if loki_entries:
        return ObservabilityLogPage(
            items=loki_entries,
            next_cursor=None,
            source="loki",
            facets=_log_facets(loki_entries),
        )
    event_entries = _event_logs(
        session=session,
        principal=principal,
        task_id=task_id,
        trace_id=trace_id,
        service=service,
        event_type=event_type,
        limit=limit,
    )
    return ObservabilityLogPage(
        items=event_entries,
        next_cursor=None,
        source="event_store",
        facets=_log_facets(event_entries),
    )


@router.get(
    "/traces/{trace_id}",
    response_model=ObservabilityTraceResponse,
    summary="查询 Trace 链路",
    description=(
        "按 trace_id 查询链路；优先返回 Tempo 真实 span，Tempo 不可用时返回 Event Store 合成 span。"
    ),
)
def get_observability_trace(
    trace_id: str,
    session: DbSession,
    principal: Principal,
    service: str | None = Query(default=None, description="服务名"),
    span_name: str | None = Query(default=None, description="Span 名称"),
    attribute_key: str | None = Query(default=None, description="Span 属性键"),
    attribute_value: str | None = Query(default=None, description="Span 属性值"),
) -> ObservabilityTraceResponse:
    return _observability_trace(
        trace_id=trace_id,
        session=session,
        principal=principal,
        service=service,
        span_name=span_name,
        attribute_key=attribute_key,
        attribute_value=attribute_value,
    )


def _observability_trace(
    *,
    trace_id: str,
    session: Session,
    principal: Principal,
    service: str | None,
    span_name: str | None,
    attribute_key: str | None,
    attribute_value: str | None,
) -> ObservabilityTraceResponse:
    tempo_spans = _query_tempo_trace(trace_id=trace_id)
    if tempo_spans:
        filtered_spans = _filter_spans(
            tempo_spans,
            service=service,
            span_name=span_name,
            attribute_key=attribute_key,
            attribute_value=attribute_value,
        )
        return ObservabilityTraceResponse(
            trace_id=trace_id,
            spans=filtered_spans,
            source="tempo",
            service_nodes=_trace_service_nodes(filtered_spans),
            service_edges=_trace_service_edges(filtered_spans),
        )
    local_spans = _local_trace_spans(session=session, principal=principal, trace_id=trace_id)
    if local_spans:
        filtered_spans = _filter_spans(
            local_spans,
            service=service,
            span_name=span_name,
            attribute_key=attribute_key,
            attribute_value=attribute_value,
        )
        return ObservabilityTraceResponse(
            trace_id=trace_id,
            spans=filtered_spans,
            source="local_otel",
            service_nodes=_trace_service_nodes(filtered_spans),
            service_edges=_trace_service_edges(filtered_spans),
        )
    spans = _event_trace_spans(session=session, principal=principal, trace_id=trace_id)
    filtered_spans = _filter_spans(
        spans,
        service=service,
        span_name=span_name,
        attribute_key=attribute_key,
        attribute_value=attribute_value,
    )
    return ObservabilityTraceResponse(
        trace_id=trace_id,
        spans=filtered_spans,
        source="event_store",
        service_nodes=_trace_service_nodes(filtered_spans),
        service_edges=_trace_service_edges(filtered_spans),
    )


@router.get(
    "/grafana/dashboards",
    response_model=GrafanaDashboardPage,
    summary="查询 Grafana Dashboard",
    description=(
        "仅 admin、operator 可访问。返回 Grafana dashboard 列表；"
        "Grafana 不可用时返回已配置的 Harness dashboard 深链。"
    ),
)
def list_grafana_dashboards(principal: Principal) -> GrafanaDashboardPage:
    require_observability_operator(principal)
    dashboards = _query_grafana_dashboards()
    if dashboards:
        return GrafanaDashboardPage(items=dashboards, next_cursor=None)
    base_url = str(get_settings().grafana_base_url).rstrip("/")
    return GrafanaDashboardPage(
        items=[
            GrafanaDashboardResponse(
                uid="agent-harness",
                title="Harness Agent Runtime",
                url=f"{base_url}/dashboards",
                tags=["harness", "agent", "runtime"],
                source="configured",
            )
        ],
        next_cursor=None,
    )


@router.get(
    "/services/health",
    response_model=ObservabilityServicesHealthResponse,
    summary="查询观测服务健康",
    description=(
        "仅 admin、operator 可访问。"
        "探测 Prometheus、Grafana、Loki、OpenTelemetry Collector 和 Tempo 健康状态。"
    ),
)
def get_observability_services_health(
    principal: Principal,
) -> ObservabilityServicesHealthResponse:
    require_observability_operator(principal)
    settings = get_settings()
    services = [
        ("prometheus", f"{str(settings.prometheus_base_url).rstrip('/')}/-/ready"),
        ("grafana", f"{str(settings.grafana_base_url).rstrip('/')}/api/health"),
        ("loki", f"{str(settings.loki_base_url).rstrip('/')}/ready"),
        ("otel-collector", f"{str(settings.otel_collector_http_url).rstrip('/')}/"),
        ("tempo", f"{str(settings.tempo_base_url).rstrip('/')}/ready"),
    ]
    return ObservabilityServicesHealthResponse(
        services=[_probe_service(name=name, url=url) for name, url in services]
    )


def require_observability_operator(principal: Principal) -> None:
    require_role(principal, {"admin", "operator"})


def _check_cost_rollup_rate_limit(organization_id: str) -> None:
    now = time.monotonic()
    last_seen = _cost_rollup_last_seen.get(organization_id)
    if last_seen is not None and now - last_seen < 10:
        raise HTTPException(status_code=429, detail="成本聚合刷新过于频繁，请稍后重试")
    _cost_rollup_last_seen[organization_id] = now


def _validate_alert_payload(
    payload: AlertRuleCreateRequest | AlertRuleUpdateRequest,
) -> None:
    try:
        validate_alert_rule_fields(
            metric=getattr(payload, "metric", None),
            comparator=getattr(payload, "comparator", None),
            severity=getattr(payload, "severity", None),
            threshold=getattr(payload, "threshold", None),
            window_seconds=getattr(payload, "window_seconds", None),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    channels = getattr(payload, "notification_channels_json", None)
    if channels is not None:
        invalid = [
            channel
            for channel in channels
            if not (
                channel == "in_app"
                or channel.startswith("slack:")
                or channel.startswith("email:")
                or channel.startswith("webhook:")
            )
        ]
        if invalid:
            raise HTTPException(
                status_code=400,
                detail=(
                    "notification channels must be in_app, slack:<name>, "
                    "email:<address>, or webhook:<name>"
                ),
            )


def _owned_alert_rule(*, session: Session, principal: Principal, rule_id: str) -> AlertRule:
    rule = session.get(AlertRule, rule_id)
    if rule is None or rule.organization_id != principal.organization_id:
        raise HTTPException(status_code=404, detail="告警规则不存在")
    return rule


def _editable_alert_rule(*, session: Session, principal: Principal, rule_id: str) -> AlertRule:
    rule = session.get(AlertRule, rule_id)
    if rule is None:
        raise HTTPException(status_code=404, detail="告警规则不存在")
    if rule.organization_id == principal.organization_id:
        return rule
    if rule.organization_id is not None:
        raise HTTPException(status_code=404, detail="告警规则不存在")
    clone = AlertRule(
        organization_id=principal.organization_id,
        name=rule.name,
        metric=rule.metric,
        comparator=rule.comparator,
        threshold=rule.threshold,
        window_seconds=rule.window_seconds,
        enabled=rule.enabled,
        severity=rule.severity,
        notification_channels_json=list(rule.notification_channels_json or ["in_app"]),
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    session.add(clone)
    session.flush()
    return clone


def _owned_notification_channel(
    *,
    session: Session,
    principal: Principal,
    channel_id: str,
) -> NotificationChannel:
    channel = session.get(NotificationChannel, channel_id)
    if channel is None or channel.organization_id != principal.organization_id:
        raise HTTPException(status_code=404, detail="通知通道不存在")
    return channel


def _notification_channel_response(channel: NotificationChannel) -> NotificationChannelResponse:
    return NotificationChannelResponse(
        id=channel.id,
        organization_id=channel.organization_id,
        name=channel.name,
        kind=channel.kind,
        config_json=redact_channel_config(channel.config_json),
        verified=channel.verified,
        created_by=channel.created_by,
        created_at=channel.created_at,
        updated_at=channel.updated_at,
    )


def _validate_notification_channel_config(
    *,
    kind: str,
    config: dict | None,
    verified: bool,
) -> None:
    try:
        validate_channel_config(kind=kind, config=config, verified=verified)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _store_notification_channel_secrets(
    *,
    session: Session,
    principal: Principal,
    channel: NotificationChannel,
    config: dict,
) -> dict:
    sanitized = dict(config)
    for field in ("webhook_url", "url", "smtp_password", "password", "token", "secret"):
        raw_value = str(sanitized.get(field) or "").strip()
        if not raw_value:
            continue
        secret_ref = f"secret://notification/{channel.id}/{field}"
        upsert_secret(
            session,
            organization_id=principal.organization_id,
            actor_id=principal.user_id,
            scope=SECRET_SCOPE_ORG,
            owner_user_id=None,
            provider=f"notification.{channel.id}.{field}",
            purpose=SECRET_PURPOSE_NOTIFICATION,
            secret_ref=secret_ref,
            secret_value=raw_value,
        )
        sanitized.pop(field, None)
        sanitized[f"{field}_secret_ref"] = secret_ref
    return sanitized


def _count_items(session: Session, statement) -> list[CountItem]:
    rows = session.execute(statement.group_by(statement.selected_columns[0])).all()
    return [CountItem(name=str(name), count=int(count)) for name, count in rows]


def _count_total(session: Session, statement) -> int:
    return int(session.execute(statement).scalar_one() or 0)


def _subagent_queue_summary(
    *,
    session: Session,
    organization_id: str,
) -> ObservabilityQueueResponse:
    task_ids = select(Task.id).where(Task.organization_id == organization_id)
    rows = session.execute(
        select(AgentRun.status, func.count(AgentRun.id))
        .where(AgentRun.task_id.in_(task_ids), AgentRun.agent_type == "subagent")
        .group_by(AgentRun.status)
    ).all()
    counts = {str(status).upper(): int(count) for status, count in rows}
    active_tasks = session.execute(
        select(func.coalesce(func.sum(Task.max_subagents), 0)).where(
            Task.organization_id == organization_id,
            Task.status.in_(["PLANNING", "RUNNING", "WAITING_SUBAGENTS"]),
        )
    ).scalar_one()
    capacity = int(active_tasks or 0)
    pending = counts.get("PENDING", 0)
    running = counts.get("RUNNING", 0)
    active_total = pending + running
    available_slots = max(capacity - active_total, 0)
    utilization_percent = int((active_total / capacity) * 100) if capacity > 0 else 0
    return ObservabilityQueueResponse(
        pending=pending,
        queued=0,
        running=running,
        success=counts.get("SUCCESS", 0),
        failed=counts.get("FAILED", 0),
        timeout=counts.get("TIMEOUT", 0),
        cancelled=counts.get("CANCELLED", 0),
        active_total=active_total,
        capacity=capacity,
        available_slots=available_slots,
        utilization_percent=min(utilization_percent, 100),
    )


def _assignment_queue_summary(
    *,
    session: Session,
    organization_id: str,
) -> ObservabilityQueueResponse:
    task_ids = select(Task.id).where(Task.organization_id == organization_id)
    rows = session.execute(
        select(AgentAssignment.status, func.count(AgentAssignment.id))
        .where(AgentAssignment.run_id.in_(task_ids))
        .group_by(AgentAssignment.status)
    ).all()
    counts = {str(status).upper(): int(count) for status, count in rows}
    queued = counts.get("QUEUED", 0)
    running = counts.get("RUNNING", 0)
    active_total = queued + running
    capacity = max(active_total, 5)
    available_slots = max(capacity - active_total, 0)
    utilization_percent = int((active_total / capacity) * 100) if capacity > 0 else 0
    return ObservabilityQueueResponse(
        pending=counts.get("PENDING", 0),
        queued=queued,
        running=running,
        success=counts.get("SUCCESS", 0),
        failed=counts.get("FAILED", 0),
        timeout=0,
        cancelled=0,
        active_total=active_total,
        capacity=capacity,
        available_slots=available_slots,
        utilization_percent=min(utilization_percent, 100),
    )


def _event_logs(
    *,
    session: Session,
    principal: Principal,
    task_id: str | None,
    trace_id: str | None,
    service: str | None,
    event_type: str | None,
    limit: int,
) -> list[ObservabilityLogEntry]:
    task_ids = select(Task.id).where(Task.organization_id == principal.organization_id)
    statement = select(AgentEvent).where(AgentEvent.task_id.in_(task_ids))
    if task_id is not None:
        statement = statement.where(AgentEvent.task_id == task_id)
    if trace_id is not None:
        statement = statement.where(AgentEvent.trace_id == trace_id)
    if event_type is not None:
        statement = statement.where(AgentEvent.event_type == event_type)
    events = session.execute(
        statement.order_by(AgentEvent.created_at.desc(), AgentEvent.sequence.desc()).limit(limit)
    ).scalars()
    entries = []
    for event in events:
        if service not in {None, "api-server"}:
            continue
        entries.append(
            ObservabilityLogEntry(
                timestamp=event.created_at,
                level="INFO" if not event.event_type.endswith("FAILED") else "ERROR",
                service="api-server",
                message=event.event_type,
                trace_id=event.trace_id,
                task_id=event.task_id,
                agent_run_id=event.agent_run_id,
                event_type=event.event_type,
                payload_json=event.payload_json,
                source="event_store",
            )
        )
    return entries


def _event_trace_spans(
    *,
    session: Session,
    principal: Principal,
    trace_id: str,
) -> list[ObservabilityTraceSpan]:
    task_ids = select(Task.id).where(Task.organization_id == principal.organization_id)
    events = session.execute(
        select(AgentEvent)
        .where(AgentEvent.task_id.in_(task_ids), AgentEvent.trace_id == trace_id)
        .order_by(AgentEvent.created_at.asc(), AgentEvent.sequence.asc())
    ).scalars()
    spans = []
    previous_span_id = None
    for event in events:
        span_id = f"event-{event.sequence}"
        spans.append(
            ObservabilityTraceSpan(
                trace_id=trace_id,
                span_id=span_id,
                parent_span_id=previous_span_id,
                name=event.event_type,
                service="api-server",
                start_time=event.created_at,
                end_time=event.created_at,
                duration_ms=0,
                kind="internal",
                status="ERROR" if event.event_type.endswith("FAILED") else "OK",
                task_id=event.task_id,
                agent_run_id=event.agent_run_id,
                attributes={
                    "task_id": event.task_id,
                    "agent_run_id": event.agent_run_id,
                    "sequence": event.sequence,
                    "payload": event.payload_json,
                },
                source="event_store",
            )
        )
        previous_span_id = span_id
    return spans


def _local_trace_spans(
    *,
    session: Session,
    principal: Principal,
    trace_id: str,
) -> list[ObservabilityTraceSpan]:
    task_ids = select(Task.id).where(Task.organization_id == principal.organization_id)
    spans = session.execute(
        select(OtelSpan)
        .where(
            OtelSpan.trace_id == trace_id,
            or_(
                OtelSpan.organization_id == principal.organization_id,
                OtelSpan.task_id.in_(task_ids),
            ),
        )
        .order_by(OtelSpan.start_time.asc(), OtelSpan.id.asc())
        .limit(2000)
    ).scalars()
    return [_otel_span_response(span) for span in spans]


def _otel_span_response(span: OtelSpan) -> ObservabilityTraceSpan:
    attributes = span.attributes_json if isinstance(span.attributes_json, dict) else {}
    return ObservabilityTraceSpan(
        trace_id=span.trace_id,
        span_id=span.span_id,
        parent_span_id=span.parent_span_id,
        name=span.name,
        service=str(attributes.get("service.name") or "api-server"),
        start_time=span.start_time,
        end_time=span.end_time,
        duration_ms=span.duration_ms,
        kind=span.kind,
        status=span.status,
        task_id=span.task_id,
        agent_run_id=span.agent_run_id,
        attributes=attributes,
        source="local_otel",
    )


def _local_trace_list(
    *,
    session: Session,
    principal: Principal,
    task_id: str | None,
    limit: int,
) -> list[TraceListItem]:
    task_ids = select(Task.id).where(Task.organization_id == principal.organization_id)
    statement = select(OtelSpan).where(
        or_(
            OtelSpan.organization_id == principal.organization_id,
            OtelSpan.task_id.in_(task_ids),
        )
    )
    if task_id:
        statement = statement.where(OtelSpan.task_id == task_id)
    rows = list(
        session.execute(
            statement.order_by(OtelSpan.start_time.desc(), OtelSpan.id.desc()).limit(5000)
        ).scalars()
    )
    grouped: dict[str, list[OtelSpan]] = {}
    for row in rows:
        grouped.setdefault(row.trace_id, []).append(row)
    items: list[TraceListItem] = []
    for trace_id, spans in grouped.items():
        ordered = sorted(spans, key=lambda span: (span.start_time, span.id))
        root = next((span for span in ordered if not span.parent_span_id), ordered[0])
        start = min(span.start_time for span in ordered)
        end = max(span.end_time for span in ordered)
        task = next((span.task_id for span in ordered if span.task_id), None)
        items.append(
            TraceListItem(
                trace_id=trace_id,
                task_id=task,
                root_name=root.name,
                start_time=start,
                duration_ms=max(0, int((end - start).total_seconds() * 1000)),
                span_count=len(ordered),
                status="ERROR" if any(span.status == "ERROR" for span in ordered) else "OK",
                source="local_otel",
            )
        )
    items.sort(key=lambda item: item.start_time, reverse=True)
    return items[:limit]


def _filter_spans(
    spans: list[ObservabilityTraceSpan],
    *,
    service: str | None,
    span_name: str | None,
    attribute_key: str | None,
    attribute_value: str | None,
) -> list[ObservabilityTraceSpan]:
    filtered = spans
    if service:
        filtered = [span for span in filtered if span.service == service]
    if span_name:
        needle = span_name.lower()
        filtered = [span for span in filtered if needle in span.name.lower()]
    if attribute_key:
        filtered = [
            span
            for span in filtered
            if _span_attribute_matches(
                span=span,
                attribute_key=attribute_key,
                attribute_value=attribute_value,
            )
        ]
    return filtered


def _span_attribute_matches(
    *,
    span: ObservabilityTraceSpan,
    attribute_key: str,
    attribute_value: str | None,
) -> bool:
    if attribute_key not in span.attributes:
        return False
    if attribute_value is None or attribute_value == "":
        return True
    return str(span.attributes.get(attribute_key)) == attribute_value


def _trace_service_nodes(
    spans: list[ObservabilityTraceSpan],
) -> list[ObservabilityTraceServiceNode]:
    totals: dict[str, dict[str, int]] = {}
    for span in spans:
        bucket = totals.setdefault(
            span.service,
            {"span_count": 0, "error_count": 0, "total_duration_ms": 0},
        )
        bucket["span_count"] += 1
        bucket["total_duration_ms"] += span.duration_ms
        status_code = str(
            span.attributes.get("http.response.status_code")
            or span.attributes.get("http.status_code")
            or ""
        )
        if status_code.startswith("5") or span.status == "ERROR" or "ERROR" in span.name.upper():
            bucket["error_count"] += 1
    return [
        ObservabilityTraceServiceNode(service=service, **values)
        for service, values in sorted(totals.items())
    ]


def _trace_service_edges(
    spans: list[ObservabilityTraceSpan],
) -> list[ObservabilityTraceServiceEdge]:
    spans_by_id = {span.span_id: span for span in spans if span.span_id}
    totals: dict[tuple[str, str], dict[str, int]] = {}
    for span in spans:
        if not span.parent_span_id:
            continue
        parent = spans_by_id.get(span.parent_span_id)
        if parent is None:
            continue
        key = (parent.service, span.service)
        bucket = totals.setdefault(key, {"span_count": 0, "total_duration_ms": 0})
        bucket["span_count"] += 1
        bucket["total_duration_ms"] += span.duration_ms
    return [
        ObservabilityTraceServiceEdge(source=source, target=target, **values)
        for (source, target), values in sorted(totals.items())
    ]


def _log_facets(entries: list[ObservabilityLogEntry]) -> dict[str, list[CountItem]]:
    return {
        "service": _facet_counts(entry.service for entry in entries),
        "event_type": _facet_counts(entry.event_type or "unknown" for entry in entries),
        "level": _facet_counts(entry.level for entry in entries),
        "source": _facet_counts(entry.source for entry in entries),
    }


def _facet_counts(values) -> list[CountItem]:
    counts: dict[str, int] = {}
    for raw_value in values:
        value = str(raw_value or "unknown")
        counts[value] = counts.get(value, 0) + 1
    return [
        CountItem(name=name, count=count)
        for name, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    ]


def _query_tempo_trace(*, trace_id: str) -> list[ObservabilityTraceSpan]:
    settings = get_settings()
    base_url = str(settings.tempo_base_url).rstrip("/")
    tempo_trace_ids = [trace_id]
    search_query = urlencode({"q": f'{{.harness.trace_id="{trace_id}"}}', "limit": "5"})
    try:
        search_payload = _get_json(f"{base_url}/api/search?{search_query}", timeout=0.35)
    except Exception:
        search_payload = {}
    for trace in search_payload.get("traces", []) if isinstance(search_payload, dict) else []:
        candidate = trace.get("traceID") or trace.get("traceId")
        if isinstance(candidate, str) and candidate not in tempo_trace_ids:
            tempo_trace_ids.append(candidate)
    for tempo_trace_id in tempo_trace_ids:
        try:
            payload = _get_json(f"{base_url}/api/traces/{tempo_trace_id}", timeout=0.35)
        except Exception:
            continue
        spans = _tempo_trace_spans(payload=payload, requested_trace_id=trace_id)
        if spans:
            return spans
    return []


def _tempo_trace_spans(
    *,
    payload: dict | list,
    requested_trace_id: str,
) -> list[ObservabilityTraceSpan]:
    if not isinstance(payload, dict):
        return []
    batches = payload.get("batches")
    if not isinstance(batches, list):
        batches = payload.get("resourceSpans")
    if not isinstance(batches, list):
        return []
    spans: list[ObservabilityTraceSpan] = []
    for batch in batches:
        resource_attrs = _tempo_attributes(batch.get("resource", {}).get("attributes", []))
        service_name = str(
            resource_attrs.get("service.name") or resource_attrs.get("service_name") or "unknown"
        )
        scope_spans = batch.get("scopeSpans") or batch.get("instrumentationLibrarySpans") or []
        for scope_span in scope_spans:
            for raw_span in scope_span.get("spans", []):
                attrs = {
                    **resource_attrs,
                    **_tempo_attributes(raw_span.get("attributes", [])),
                }
                span_trace_id = str(raw_span.get("traceId") or requested_trace_id)
                spans.append(
                    ObservabilityTraceSpan(
                        trace_id=str(attrs.get("harness.trace_id") or requested_trace_id),
                        span_id=str(raw_span.get("spanId") or raw_span.get("span_id") or ""),
                        parent_span_id=(
                            raw_span.get("parentSpanId") or raw_span.get("parent_span_id")
                        ),
                        name=str(raw_span.get("name") or "span"),
                        service=service_name,
                        start_time=_parse_tempo_time(raw_span.get("startTimeUnixNano")),
                        end_time=None,
                        duration_ms=_tempo_duration_ms(raw_span),
                        kind=str(raw_span.get("kind") or "internal").lower(),
                        status=_tempo_span_status(raw_span),
                        task_id=str(attrs.get("task_id") or attrs.get("harness.task_id") or "")
                        or None,
                        agent_run_id=str(
                            attrs.get("agent_run_id") or attrs.get("harness.agent_run_id") or ""
                        )
                        or None,
                        attributes={**attrs, "otel_trace_id": span_trace_id},
                        source="tempo",
                    )
                )
    return sorted(spans, key=lambda span: span.start_time)


def _tempo_attributes(raw_attributes: object) -> dict:
    if not isinstance(raw_attributes, list):
        return {}
    attributes = {}
    for item in raw_attributes:
        if not isinstance(item, dict):
            continue
        key = item.get("key")
        value = item.get("value")
        if not isinstance(key, str):
            continue
        attributes[key] = _tempo_attribute_value(value)
    return attributes


def _tempo_attribute_value(value: object) -> object:
    if not isinstance(value, dict):
        return value
    for key in ("stringValue", "intValue", "doubleValue", "boolValue"):
        if key in value:
            return value[key]
    if "arrayValue" in value:
        return value["arrayValue"]
    if "kvlistValue" in value:
        return value["kvlistValue"]
    return value


def _tempo_span_status(raw_span: dict) -> str:
    status = raw_span.get("status") if isinstance(raw_span, dict) else None
    if isinstance(status, dict):
        code = str(status.get("code") or status.get("statusCode") or "")
        if code in {"2", "STATUS_CODE_ERROR", "ERROR"}:
            return "ERROR"
    return "OK"


def _parse_tempo_time(value: object) -> datetime:
    try:
        return datetime.fromtimestamp(int(str(value)) / 1_000_000_000, tz=UTC)
    except (TypeError, ValueError):
        return datetime.now(UTC)


def _tempo_duration_ms(raw_span: dict) -> int:
    try:
        started_at = int(str(raw_span.get("startTimeUnixNano")))
        ended_at = int(str(raw_span.get("endTimeUnixNano")))
    except (TypeError, ValueError):
        return 0
    return max(0, int((ended_at - started_at) / 1_000_000))


def _query_loki_logs(
    *,
    task_id: str | None,
    trace_id: str | None,
    service: str | None,
    event_type: str | None,
    limit: int,
) -> list[ObservabilityLogEntry]:
    base_url = str(get_settings().loki_base_url).rstrip("/")
    selector = _loki_label_selector(
        service=service,
        task_id=task_id,
        trace_id=trace_id,
        event_type=event_type,
    )
    query_params = urlencode({"query": selector, "limit": str(limit)})
    try:
        payload = _get_json(f"{base_url}/loki/api/v1/query_range?{query_params}", timeout=0.35)
    except Exception:
        return []
    entries = []
    for stream in payload.get("data", {}).get("result", []):
        for _, raw_line in stream.get("values", []):
            try:
                line = json.loads(raw_line)
            except json.JSONDecodeError:
                continue
            if task_id is not None and line.get("task_id") != task_id:
                continue
            if trace_id is not None and line.get("trace_id") != trace_id:
                continue
            if event_type is not None and line.get("event_type") != event_type:
                continue
            entries.append(
                ObservabilityLogEntry(
                    timestamp=_parse_datetime(line.get("timestamp") or line.get("created_at")),
                    level=str(line.get("level") or "INFO"),
                    service=str(line.get("service") or service or "api-server"),
                    message=str(line.get("message") or ""),
                    trace_id=line.get("trace_id"),
                    task_id=line.get("task_id"),
                    agent_run_id=line.get("agent_run_id"),
                    event_type=line.get("event_type"),
                    payload_json=line,
                    source="loki",
                )
            )
    return entries


def _loki_label_selector(
    *,
    service: str | None,
    task_id: str | None,
    trace_id: str | None,
    event_type: str | None,
) -> str:
    labels = {
        "service": service or "api-server",
        "task_id": task_id,
        "trace_id": trace_id,
        "event_type": event_type,
    }
    selector_parts = [
        f'{key}="{_escape_loki_label_value(value)}"' for key, value in labels.items() if value
    ]
    return "{" + ",".join(selector_parts) + "}"


def _escape_loki_label_value(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _query_grafana_dashboards() -> list[GrafanaDashboardResponse]:
    settings = get_settings()
    base_url = str(settings.grafana_base_url).rstrip("/")
    try:
        payload = _get_json(
            f"{base_url}/api/search?type=dash-db",
            timeout=0.35,
            headers=_grafana_auth_headers(settings),
        )
    except Exception:
        return []
    dashboards = []
    if not isinstance(payload, list):
        return dashboards
    for item in payload:
        uid = str(item.get("uid") or item.get("uri") or "dashboard")
        dashboards.append(
            GrafanaDashboardResponse(
                uid=uid,
                title=str(item.get("title") or uid),
                url=f"{base_url}{item.get('url') or '/dashboards'}",
                tags=[str(tag) for tag in item.get("tags", [])],
                source="grafana",
            )
        )
    return dashboards


def _grafana_auth_headers(settings: Settings) -> dict[str, str]:
    token = b64encode(f"{settings.grafana_username}:{settings.grafana_password}".encode()).decode(
        "ascii"
    )
    return {"Authorization": f"Basic {token}"}


def _probe_service(*, name: str, url: str) -> ObservabilityServiceHealthResponse:
    started_at = time.monotonic()
    try:
        http_request = request.Request(url, method="GET")
        with request.urlopen(http_request, timeout=0.35) as response:
            status = "healthy" if 200 <= response.status < 500 else "unhealthy"
    except (OSError, error.HTTPError) as exc:
        alert_status, alert_severity = _service_alert(status="unreachable")
        return ObservabilityServiceHealthResponse(
            name=name,
            status="unreachable",
            url=url,
            latency_ms=int((time.monotonic() - started_at) * 1000),
            error_message=str(exc),
            alert_status=alert_status,
            alert_severity=alert_severity,
            runbook_url="/docs/runbooks/troubleshooting#observability",
        )
    alert_status, alert_severity = _service_alert(status=status)
    return ObservabilityServiceHealthResponse(
        name=name,
        status=status,
        url=url,
        latency_ms=int((time.monotonic() - started_at) * 1000),
        error_message=None,
        alert_status=alert_status,
        alert_severity=alert_severity,
        runbook_url="/docs/runbooks/troubleshooting#observability",
    )


def _service_alert(*, status: str) -> tuple[str, str]:
    if status == "healthy":
        return "ok", "none"
    if status == "unhealthy":
        return "firing", "warning"
    return "firing", "critical"


def _get_json(url: str, *, timeout: float, headers: dict[str, str] | None = None) -> dict | list:
    http_request = request.Request(url, headers=headers or {}, method="GET")
    with request.urlopen(http_request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _parse_datetime(value: object) -> datetime:
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            pass
    return datetime.now().astimezone()


def _persist_export(
    *,
    session: Session,
    principal: Principal,
    export_type: str,
    filename: str,
    content_type: str,
    export_format: str,
    source: str,
    row_count: int,
    filter_json: dict,
    body: bytes,
) -> ObservabilityExportRecord:
    export_id = str(uuid4())
    safe_filename = _safe_filename(filename)
    storage_path = (
        Path(get_settings().observability_export_dir)
        / _safe_filename(principal.organization_id)
        / f"{export_id}-{safe_filename}"
    )
    storage_path.parent.mkdir(parents=True, exist_ok=True)
    storage_path.write_bytes(body)
    record = ObservabilityExportRecord(
        id=export_id,
        organization_id=principal.organization_id,
        actor_id=principal.user_id,
        export_type=export_type,
        filename=safe_filename,
        content_type=content_type,
        format=export_format,
        source=source,
        row_count=row_count,
        filter_json={key: value for key, value in filter_json.items() if value is not None},
        storage_driver="local_file",
        storage_uri=str(storage_path),
        size_bytes=len(body),
        sha256=sha256(body).hexdigest(),
    )
    session.add(record)
    session.commit()
    session.refresh(record)
    return record


def _export_headers(*, record: ObservabilityExportRecord) -> dict[str, str]:
    return {
        "Content-Disposition": f'attachment; filename="{record.filename}"',
        "X-Harness-Export-Id": record.id,
        "X-Harness-Export-Count": str(record.row_count),
        "X-Harness-Export-Source": record.source,
        "X-Harness-Export-Sha256": record.sha256,
    }


def _export_history_item(record: ObservabilityExportRecord) -> ObservabilityExportHistoryItem:
    return ObservabilityExportHistoryItem(
        id=record.id,
        export_type=record.export_type,
        filename=record.filename,
        content_type=record.content_type,
        format=record.format,
        source=record.source,
        row_count=record.row_count,
        filter_json=record.filter_json,
        storage_driver=record.storage_driver,
        size_bytes=record.size_bytes,
        sha256=record.sha256,
        download_url=f"/api/observability/exports/history/{record.id}/download",
        created_at=record.created_at,
    )


def _safe_filename(value: str) -> str:
    safe = "".join(ch if ch.isalnum() or ch in {"-", "_", "."} else "_" for ch in value)
    return safe.strip("._") or "export"


def _project_grounding_trace(trace: dict | None) -> dict:
    raw = trace if isinstance(trace, dict) else {}
    forbidden_leak_sources = _string_list(raw.get("forbidden_leak_sources"))
    forbidden_evidence_leaked = bool(raw.get("forbidden_evidence_leaked")) or bool(
        forbidden_leak_sources
    )
    failures = _string_list(raw.get("grounding_failures"))
    if forbidden_evidence_leaked and "forbidden_evidence_leaked" not in failures:
        failures.append("forbidden_evidence_leaked")
    return {
        "passed": bool(raw.get("passed", True)) and not forbidden_evidence_leaked,
        "grounding_failures": failures,
        "forbidden_evidence_leaked": forbidden_evidence_leaked,
        "forbidden_leak_sources": forbidden_leak_sources,
        "fallback_expected": bool(raw.get("fallback_expected") or False),
        "fallback_observed": bool(raw.get("fallback_observed") or False),
        "citation_keys": _string_list(raw.get("citation_keys")),
        "citation_hit_ids": _string_list(raw.get("citation_hit_ids")),
        "retrieval_session_id": _nullable_string(raw.get("retrieval_session_id")),
        "prompt_manifest_id": _nullable_string(raw.get("prompt_manifest_id")),
    }


def _failure_type_matches(query: str, failures: list[str]) -> bool:
    needle = _clean_string(query).lower()
    if not needle:
        return True
    return any(needle in failure.lower() for failure in failures)


def _string_list(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        return [item for item in (_clean_string(item) for item in value) if item]
    item = _clean_string(value)
    return [item] if item else []


def _nullable_string(value: object) -> str | None:
    item = _clean_string(value or "")
    return item or None


def _clean_string(value: object) -> str:
    return str(value).replace("\r\n", "\n").replace("\r", "\n").strip()
