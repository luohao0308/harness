from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal, InvalidOperation
from typing import Literal

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.api.schemas import CostRollupBreakdownItem, CostRollupResponse, CostRollupSeriesPoint
from app.db.models import (
    AgentRun,
    ModelCall,
    ModelPricing,
    SubagentOutput,
    SubagentSpecialist,
    Task,
    ToolCall,
    utc_now,
)

CostWindow = Literal["24h", "7d", "30d", "all"]
CostGroupBy = Literal["agent", "provider", "specialist", "adapter"]

_WINDOW_DELTAS = {
    "24h": timedelta(hours=24),
    "7d": timedelta(days=7),
    "30d": timedelta(days=30),
}


@dataclass(frozen=True)
class CostEntry:
    key: str
    label: str
    cost_usd: Decimal
    tokens_in: int
    tokens_out: int
    run_id: str
    timestamp: object


def build_cost_rollup(
    *,
    session: Session,
    organization_id: str,
    window: CostWindow,
    group_by: CostGroupBy,
) -> CostRollupResponse:
    if window not in {"24h", "7d", "30d", "all"}:
        raise ValueError("window must be one of 24h, 7d, 30d, all")
    if group_by not in {"agent", "provider", "specialist", "adapter"}:
        raise ValueError("group_by must be one of agent, provider, specialist, adapter")
    since = _window_since(window)
    model_rows = _model_call_rows(session=session, organization_id=organization_id, since=since)
    pricing_rows = list(
        session.execute(
            select(ModelPricing).where(
                ModelPricing.active.is_(True),
                or_(
                    ModelPricing.organization_id == organization_id,
                    ModelPricing.organization_id.is_(None),
                ),
            )
        ).scalars()
    )
    pricing_index = _pricing_index(pricing_rows)
    entries: list[CostEntry] = []
    model_cost_by_agent_run: dict[str, Decimal] = {}
    for call, task, _agent_run, specialist in model_rows:
        cost = _model_call_cost(
            call=call,
            organization_id=organization_id,
            pricing_index=pricing_index,
        )
        if call.agent_run_id:
            model_cost_by_agent_run[call.agent_run_id] = (
                model_cost_by_agent_run.get(call.agent_run_id, Decimal("0")) + cost
            )
        key, label = _model_group_key(
            group_by=group_by,
            task=task,
            call=call,
            specialist=specialist,
        )
        entries.append(
            CostEntry(
                key=key,
                label=label,
                cost_usd=cost,
                tokens_in=max(0, int(call.prompt_tokens or 0)),
                tokens_out=max(0, int(call.completion_tokens or 0)),
                run_id=task.id,
                timestamp=call.created_at,
            )
        )
    if group_by == "specialist":
        entries.extend(
            _specialist_budget_fallback_entries(
                session=session,
                organization_id=organization_id,
                since=since,
                model_cost_by_agent_run=model_cost_by_agent_run,
            )
        )
    if group_by == "adapter":
        entries.extend(
            _adapter_tool_entries(
                session=session,
                organization_id=organization_id,
                since=since,
            )
        )
    return _rollup_response(window=window, group_by=group_by, entries=entries)


def cost_for_window(
    *,
    session: Session,
    organization_id: str | None,
    since,
    until=None,
) -> Decimal:
    if organization_id is None:
        return Decimal("0")
    statement = (
        select(ModelCall, Task)
        .join(Task, Task.id == ModelCall.task_id)
        .where(Task.organization_id == organization_id)
    )
    if since is not None:
        statement = statement.where(ModelCall.created_at >= since)
    if until is not None:
        statement = statement.where(ModelCall.created_at < until)
    rows = list(session.execute(statement).all())
    pricing_rows = list(
        session.execute(
            select(ModelPricing).where(
                ModelPricing.active.is_(True),
                or_(
                    ModelPricing.organization_id == organization_id,
                    ModelPricing.organization_id.is_(None),
                ),
            )
        ).scalars()
    )
    pricing_index = _pricing_index(pricing_rows)
    return sum(
        (
            _model_call_cost(
                call=call,
                organization_id=organization_id,
                pricing_index=pricing_index,
            )
            for call, _task in rows
        ),
        Decimal("0"),
    )


def _model_call_rows(*, session: Session, organization_id: str, since):
    statement = (
        select(ModelCall, Task, AgentRun, SubagentSpecialist)
        .join(Task, Task.id == ModelCall.task_id)
        .outerjoin(AgentRun, AgentRun.id == ModelCall.agent_run_id)
        .outerjoin(SubagentSpecialist, SubagentSpecialist.id == AgentRun.specialist_id)
        .where(Task.organization_id == organization_id)
        .order_by(ModelCall.created_at.asc(), ModelCall.id.asc())
        .limit(5000)
    )
    if since is not None:
        statement = statement.where(ModelCall.created_at >= since)
    return list(session.execute(statement).all())


def _pricing_index(rows: list[ModelPricing]) -> dict[tuple[str | None, str, str], ModelPricing]:
    return {
        (row.organization_id, row.provider, row.model): row
        for row in rows
    }


def _model_call_cost(
    *,
    call: ModelCall,
    organization_id: str | None,
    pricing_index: dict[tuple[str | None, str, str], ModelPricing],
) -> Decimal:
    provider = (call.model_provider or "default").strip() or "default"
    model = (call.model_name or "default").strip() or "default"
    pricing = _lookup_pricing(
        pricing_index=pricing_index,
        organization_id=organization_id,
        provider=provider,
        model=model,
    )
    if pricing is None:
        return Decimal("0")
    try:
        prompt_per_1k = Decimal(pricing.prompt_per_1k_usd or "0")
        completion_per_1k = Decimal(pricing.completion_per_1k_usd or "0")
    except (InvalidOperation, ValueError):
        return Decimal("0")
    return (
        Decimal(max(0, int(call.prompt_tokens or 0))) / Decimal(1000) * prompt_per_1k
        + Decimal(max(0, int(call.completion_tokens or 0))) / Decimal(1000) * completion_per_1k
    )


def _lookup_pricing(
    *,
    pricing_index: dict[tuple[str | None, str, str], ModelPricing],
    organization_id: str | None,
    provider: str,
    model: str,
) -> ModelPricing | None:
    candidates: list[tuple[str | None, str, str]] = []
    if organization_id:
        candidates.extend(
            [
                (organization_id, provider, model),
                (organization_id, provider, "default"),
            ]
        )
    candidates.extend(
        [
            (None, provider, model),
            (None, provider, "default"),
            (None, "default", "default"),
        ]
    )
    for key in candidates:
        row = pricing_index.get(key)
        if row is not None:
            return row
    return None


def _model_group_key(
    *,
    group_by: CostGroupBy,
    task: Task,
    call: ModelCall,
    specialist: SubagentSpecialist | None,
) -> tuple[str, str]:
    if group_by == "agent":
        key = task.agent_id or "unassigned"
        return key, key
    if group_by == "provider":
        key = f"{call.model_provider}/{call.model_name}"
        return key, key
    if group_by == "specialist":
        key = specialist.slug if specialist is not None else "primary-agent"
        label = specialist.display_name if specialist is not None else "主智能体"
        return key, label
    return "no-adapter", "未关联工具适配器"


def _specialist_budget_fallback_entries(
    *,
    session: Session,
    organization_id: str,
    since,
    model_cost_by_agent_run: dict[str, Decimal],
) -> list[CostEntry]:
    statement = (
        select(SubagentOutput, AgentRun, SubagentSpecialist)
        .join(Task, Task.id == SubagentOutput.task_id)
        .join(AgentRun, AgentRun.id == SubagentOutput.agent_run_id)
        .outerjoin(SubagentSpecialist, SubagentSpecialist.id == SubagentOutput.specialist_id)
        .where(Task.organization_id == organization_id)
        .order_by(SubagentOutput.written_at.asc(), SubagentOutput.id.asc())
        .limit(5000)
    )
    if since is not None:
        statement = statement.where(SubagentOutput.written_at >= since)
    entries: list[CostEntry] = []
    for output, agent_run, specialist in session.execute(statement).all():
        if model_cost_by_agent_run.get(agent_run.id, Decimal("0")) > Decimal("0"):
            continue
        budget = (
            output.budget_consumed_json
            if isinstance(output.budget_consumed_json, dict)
            else {}
        )
        cost = _decimal_value(budget.get("cost_usd"))
        key = specialist.slug if specialist is not None else "unknown-specialist"
        label = specialist.display_name if specialist is not None else key
        entries.append(
            CostEntry(
                key=key,
                label=label,
                cost_usd=cost,
                tokens_in=max(0, int(budget.get("prompt_tokens") or 0)),
                tokens_out=max(0, int(budget.get("completion_tokens") or 0)),
                run_id=output.task_id,
                timestamp=output.written_at,
            )
        )
    return entries


def _adapter_tool_entries(*, session: Session, organization_id: str, since) -> list[CostEntry]:
    statement = (
        select(ToolCall)
        .join(Task, Task.id == ToolCall.task_id)
        .where(Task.organization_id == organization_id)
        .order_by(ToolCall.created_at.asc(), ToolCall.id.asc())
        .limit(5000)
    )
    if since is not None:
        statement = statement.where(ToolCall.created_at >= since)
    entries: list[CostEntry] = []
    for call in session.execute(statement).scalars():
        key, label = _adapter_key(call)
        cost = _tool_cost(call)
        entries.append(
            CostEntry(
                key=key,
                label=label,
                cost_usd=cost,
                tokens_in=0,
                tokens_out=0,
                run_id=call.task_id,
                timestamp=call.created_at,
            )
        )
    return entries


def _adapter_key(call: ToolCall) -> tuple[str, str]:
    snapshot = (
        call.capability_snapshot_json
        if isinstance(call.capability_snapshot_json, dict)
        else {}
    )
    adapter = snapshot.get("adapter") if isinstance(snapshot.get("adapter"), dict) else {}
    config = (
        snapshot.get("runtime_config") if isinstance(snapshot.get("runtime_config"), dict) else {}
    )
    slug = str(adapter.get("slug") or call.tool_name or "unknown-adapter")
    server = str(config.get("server_url") or config.get("endpoint") or "local")
    key = f"{slug}@{server}"
    return key, key


def _tool_cost(call: ToolCall) -> Decimal:
    output = call.output_json if isinstance(call.output_json, dict) else {}
    snapshot = (
        call.capability_snapshot_json
        if isinstance(call.capability_snapshot_json, dict)
        else {}
    )
    for source in (output, snapshot):
        value = source.get("cost_usd")
        if value is not None:
            return _decimal_value(value)
    return Decimal("0")


def _rollup_response(
    *,
    window: CostWindow,
    group_by: CostGroupBy,
    entries: list[CostEntry],
) -> CostRollupResponse:
    totals: dict[str, dict[str, object]] = {}
    series: dict[tuple[str, str], dict[str, object]] = {}
    total_cost = Decimal("0")
    total_tokens = 0
    run_ids: set[str] = set()
    for entry in entries:
        total_cost += entry.cost_usd
        total_tokens += entry.tokens_in + entry.tokens_out
        run_ids.add(entry.run_id)
        bucket = totals.setdefault(
            entry.key,
            {
                "label": entry.label,
                "cost_usd": Decimal("0"),
                "tokens_in": 0,
                "tokens_out": 0,
                "run_ids": set(),
            },
        )
        bucket["cost_usd"] = bucket["cost_usd"] + entry.cost_usd  # type: ignore[operator]
        bucket["tokens_in"] = int(bucket["tokens_in"]) + entry.tokens_in
        bucket["tokens_out"] = int(bucket["tokens_out"]) + entry.tokens_out
        bucket["run_ids"].add(entry.run_id)  # type: ignore[union-attr]
        series_key = (_series_bucket(entry.timestamp, window), entry.key)
        point = series.setdefault(
            series_key,
            {
                "bucket_start": series_key[0],
                "key": entry.key,
                "label": entry.label,
                "cost_usd": Decimal("0"),
                "tokens": 0,
                "run_ids": set(),
            },
        )
        point["cost_usd"] = point["cost_usd"] + entry.cost_usd  # type: ignore[operator]
        point["tokens"] = int(point["tokens"]) + entry.tokens_in + entry.tokens_out
        point["run_ids"].add(entry.run_id)  # type: ignore[union-attr]
    breakdown = [
        CostRollupBreakdownItem(
            key=key,
            label=str(values["label"]),
            cost_usd=_float_cost(values["cost_usd"]),
            tokens_in=int(values["tokens_in"]),
            tokens_out=int(values["tokens_out"]),
            run_count=len(values["run_ids"]),
            share=_share(values["cost_usd"], total_cost),
        )
        for key, values in totals.items()
    ]
    breakdown.sort(key=lambda item: (-item.cost_usd, -item.tokens_in - item.tokens_out, item.key))
    series_points = [
        CostRollupSeriesPoint(
            bucket_start=str(values["bucket_start"]),
            key=str(values["key"]),
            label=str(values["label"]),
            cost_usd=_float_cost(values["cost_usd"]),
            tokens=int(values["tokens"]),
            run_count=len(values["run_ids"]),
        )
        for values in series.values()
    ]
    series_points.sort(key=lambda item: (item.bucket_start, item.key))
    return CostRollupResponse(
        window=window,
        group_by=group_by,
        generated_at=utc_now(),
        total_cost_usd=_float_cost(total_cost),
        total_tokens=total_tokens,
        total_runs=len(run_ids),
        average_run_cost_usd=_float_cost(total_cost / Decimal(len(run_ids))) if run_ids else 0.0,
        breakdown=breakdown[:10],
        series=series_points,
    )


def _series_bucket(timestamp, window: CostWindow) -> str:
    if timestamp is None:
        timestamp = utc_now()
    if window == "24h":
        return timestamp.replace(minute=0, second=0, microsecond=0).isoformat()
    return timestamp.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()


def _window_since(window: CostWindow):
    if window == "all":
        return None
    return utc_now() - _WINDOW_DELTAS[window]


def _decimal_value(value: object) -> Decimal:
    try:
        return Decimal(str(value or "0"))
    except (InvalidOperation, ValueError):
        return Decimal("0")


def _float_cost(value: object) -> float:
    return float(Decimal(str(value or "0")).quantize(Decimal("0.000001")))


def _share(value: object, total: Decimal) -> float:
    if total <= 0:
        return 0.0
    return float((Decimal(str(value or "0")) / total).quantize(Decimal("0.0001")))
