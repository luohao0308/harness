import json
import time
from base64 import b64encode
from datetime import datetime
from typing import Annotated
from urllib import error, request
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.schemas import (
    CountItem,
    GrafanaDashboardPage,
    GrafanaDashboardResponse,
    ObservabilityLogEntry,
    ObservabilityLogPage,
    ObservabilityServiceHealthResponse,
    ObservabilityServicesHealthResponse,
    ObservabilitySummaryResponse,
    ObservabilityTraceResponse,
    ObservabilityTraceSpan,
    WarmPoolResponse,
)
from app.core.config import Settings, get_settings
from app.db.models import AgentEvent, AgentRun, ModelCall, SandboxInstance, Task, ToolCall
from app.db.session import get_db_session
from app.sandbox.warm_pool import WarmPoolManager
from app.security.auth import Principal

router = APIRouter(prefix="/observability", tags=["observability"])
DbSession = Annotated[Session, Depends(get_db_session)]


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
    )


@router.get(
    "/logs",
    response_model=ObservabilityLogPage,
    summary="查询结构化日志",
    description=(
        "按任务、trace、服务和事件类型查询结构化日志；"
        "Loki 不可用时返回 Event Store 日志视图。"
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
    loki_entries = _query_loki_logs(
        task_id=task_id,
        trace_id=trace_id,
        service=service,
        event_type=event_type,
        limit=limit,
    )
    if loki_entries:
        return ObservabilityLogPage(items=loki_entries, next_cursor=None, source="loki")
    return ObservabilityLogPage(
        items=_event_logs(
            session=session,
            principal=principal,
            task_id=task_id,
            trace_id=trace_id,
            service=service,
            event_type=event_type,
            limit=limit,
        ),
        next_cursor=None,
        source="event_store",
    )


@router.get(
    "/traces/{trace_id}",
    response_model=ObservabilityTraceResponse,
    summary="查询 Trace 链路",
    description="按 trace_id 查询链路；外部 Trace 后端未接入时返回 Event Store 合成 span。",
)
def get_observability_trace(
    trace_id: str,
    session: DbSession,
    principal: Principal,
) -> ObservabilityTraceResponse:
    spans = _event_trace_spans(session=session, principal=principal, trace_id=trace_id)
    return ObservabilityTraceResponse(trace_id=trace_id, spans=spans, source="event_store")


@router.get(
    "/grafana/dashboards",
    response_model=GrafanaDashboardPage,
    summary="查询 Grafana Dashboard",
    description=(
        "返回 Grafana dashboard 列表；"
        "Grafana 不可用时返回已配置的 Harness dashboard 深链。"
    ),
)
def list_grafana_dashboards() -> GrafanaDashboardPage:
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
    description="探测 Prometheus、Grafana、Loki 和 OpenTelemetry Collector 健康状态。",
)
def get_observability_services_health() -> ObservabilityServicesHealthResponse:
    settings = get_settings()
    services = [
        ("prometheus", f"{str(settings.prometheus_base_url).rstrip('/')}/-/ready"),
        ("grafana", f"{str(settings.grafana_base_url).rstrip('/')}/api/health"),
        ("loki", f"{str(settings.loki_base_url).rstrip('/')}/ready"),
        ("otel-collector", f"{str(settings.otel_collector_http_url).rstrip('/')}/"),
    ]
    return ObservabilityServicesHealthResponse(
        services=[_probe_service(name=name, url=url) for name, url in services]
    )


def _count_items(session: Session, statement) -> list[CountItem]:
    rows = session.execute(statement.group_by(statement.selected_columns[0])).all()
    return [CountItem(name=str(name), count=int(count)) for name, count in rows]


def _count_total(session: Session, statement) -> int:
    return int(session.execute(statement).scalar_one() or 0)


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
                duration_ms=0,
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
        f'{key}="{_escape_loki_label_value(value)}"'
        for key, value in labels.items()
        if value
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
        return ObservabilityServiceHealthResponse(
            name=name,
            status="unreachable",
            url=url,
            latency_ms=int((time.monotonic() - started_at) * 1000),
            error_message=str(exc),
        )
    return ObservabilityServiceHealthResponse(
        name=name,
        status=status,
        url=url,
        latency_ms=int((time.monotonic() - started_at) * 1000),
        error_message=None,
    )


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
