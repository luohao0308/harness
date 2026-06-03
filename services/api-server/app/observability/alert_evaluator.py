from __future__ import annotations

import operator
from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.db.models import AlertEvent, AlertRule, EvalRun, SubagentOutput, Task, ToolCall, utc_now
from app.observability.cost_rollup import cost_for_window

ALLOWED_ALERT_METRICS = {
    "eval_regression_triggered",
    "subagent_budget_exceeded_count",
    "tool_adapter_failure_rate",
    "total_cost_spike_ratio",
}
ALLOWED_COMPARATORS = {">", "<", ">=", "<=", "=="}
ALLOWED_SEVERITIES = {"info", "warning", "critical"}

_COMPARATORS = {
    ">": operator.gt,
    "<": operator.lt,
    ">=": operator.ge,
    "<=": operator.le,
    "==": operator.eq,
}


@dataclass(frozen=True)
class AlertEvaluation:
    rule_id: str
    triggered: bool
    observed_value: float
    event_id: str | None = None


def evaluate_alert_rules(
    *,
    session: Session,
    organization_id: str | None = None,
) -> list[AlertEvaluation]:
    rules = _enabled_rules(session=session, organization_id=organization_id)
    results: list[AlertEvaluation] = []
    for rule in rules:
        if rule.organization_id is None and organization_id is not None:
            metric_rule = _organization_rule(rule=rule, organization_id=organization_id)
        else:
            metric_rule = rule
        observed_value, context = _metric_value(session=session, rule=metric_rule)
        triggered = _compare(observed_value, rule.comparator, rule.threshold)
        event_id = None
        if triggered:
            event = AlertEvent(
                organization_id=metric_rule.organization_id,
                rule_id=rule.id,
                rule_name=rule.name,
                metric=rule.metric,
                comparator=rule.comparator,
                threshold=rule.threshold,
                observed_value=observed_value,
                severity=rule.severity,
                status="active",
                message=(
                    f"{rule.name}: {rule.metric} {observed_value:g} "
                    f"{rule.comparator} {rule.threshold:g}"
                ),
                context_json=context,
                triggered_at=utc_now(),
            )
            session.add(event)
            session.flush()
            event_id = event.id
        results.append(
            AlertEvaluation(
                rule_id=rule.id,
                triggered=triggered,
                observed_value=observed_value,
                event_id=event_id,
            )
        )
    return results


def validate_alert_rule_fields(
    *,
    metric: str | None = None,
    comparator: str | None = None,
    severity: str | None = None,
    threshold: float | None = None,
    window_seconds: int | None = None,
) -> None:
    if metric is not None and metric not in ALLOWED_ALERT_METRICS:
        raise ValueError(f"metric must be one of: {', '.join(sorted(ALLOWED_ALERT_METRICS))}")
    if comparator is not None and comparator not in ALLOWED_COMPARATORS:
        raise ValueError("comparator must be one of >, <, >=, <=, ==")
    if severity is not None and severity not in ALLOWED_SEVERITIES:
        raise ValueError("severity must be one of info, warning, critical")
    if threshold is not None and threshold < 0:
        raise ValueError("threshold must be greater than or equal to 0")
    if window_seconds is not None and not 60 <= window_seconds <= 86_400:
        raise ValueError("window_seconds must be between 60 and 86400")


def _organization_rule(*, rule: AlertRule, organization_id: str) -> AlertRule:
    clone = AlertRule(
        id=rule.id,
        organization_id=organization_id,
        name=rule.name,
        metric=rule.metric,
        comparator=rule.comparator,
        threshold=rule.threshold,
        window_seconds=rule.window_seconds,
        enabled=rule.enabled,
        severity=rule.severity,
        notification_channels_json=rule.notification_channels_json,
        created_at=rule.created_at,
        updated_at=rule.updated_at,
    )
    return clone


def _enabled_rules(*, session: Session, organization_id: str | None) -> list[AlertRule]:
    statement = select(AlertRule).where(AlertRule.enabled.is_(True))
    if organization_id is None:
        statement = statement.where(AlertRule.organization_id.is_(None))
    else:
        statement = statement.where(
            or_(AlertRule.organization_id == organization_id, AlertRule.organization_id.is_(None))
        )
    by_name: dict[str, AlertRule] = {}
    for row in session.execute(statement.order_by(AlertRule.created_at.asc())).scalars():
        current = by_name.get(row.name)
        if current is None or row.organization_id == organization_id:
            by_name[row.name] = row
    return list(by_name.values())


def _metric_value(*, session: Session, rule: AlertRule) -> tuple[float, dict]:
    since = utc_now() - timedelta(seconds=max(60, int(rule.window_seconds or 60)))
    if rule.metric == "eval_regression_triggered":
        return _eval_regression_value(session=session, rule=rule, since=since)
    if rule.metric == "subagent_budget_exceeded_count":
        return _subagent_budget_exceeded_value(session=session, rule=rule, since=since)
    if rule.metric == "tool_adapter_failure_rate":
        return _tool_adapter_failure_rate_value(session=session, rule=rule, since=since)
    if rule.metric == "total_cost_spike_ratio":
        return _cost_spike_ratio_value(session=session, rule=rule, since=since)
    return 0.0, {"reason": "unsupported_metric"}


def _eval_regression_value(*, session: Session, rule: AlertRule, since) -> tuple[float, dict]:
    statement = select(EvalRun).where(EvalRun.created_at >= since)
    if rule.organization_id is not None:
        statement = statement.where(EvalRun.organization_id == rule.organization_id)
    runs = list(session.execute(statement).scalars())
    count = 0
    for run in runs:
        metrics = run.metrics_json if isinstance(run.metrics_json, dict) else {}
        if metrics.get("is_regression") is True or metrics.get("regression_triggered") is True:
            count += 1
    return float(count), {"eval_run_count": len(runs)}


def _subagent_budget_exceeded_value(
    *,
    session: Session,
    rule: AlertRule,
    since,
) -> tuple[float, dict]:
    statement = (
        select(SubagentOutput)
        .join(Task, Task.id == SubagentOutput.task_id)
        .where(SubagentOutput.written_at >= since)
    )
    if rule.organization_id is not None:
        statement = statement.where(Task.organization_id == rule.organization_id)
    outputs = list(session.execute(statement).scalars())
    count = sum(1 for output in outputs if bool(output.budget_exceeded_json))
    return float(count), {"subagent_output_count": len(outputs)}


def _tool_adapter_failure_rate_value(
    *,
    session: Session,
    rule: AlertRule,
    since,
) -> tuple[float, dict]:
    statement = (
        select(ToolCall.status, func.count(ToolCall.id))
        .join(Task, Task.id == ToolCall.task_id)
        .where(ToolCall.created_at >= since)
        .group_by(ToolCall.status)
    )
    if rule.organization_id is not None:
        statement = statement.where(Task.organization_id == rule.organization_id)
    rows = session.execute(statement).all()
    counts = {str(status): int(count) for status, count in rows}
    total = sum(counts.values())
    failed = sum(count for status, count in counts.items() if status in {"FAILED", "TIMEOUT"})
    return (failed / total if total else 0.0), {"tool_call_count": total, "failed_count": failed}


def _cost_spike_ratio_value(*, session: Session, rule: AlertRule, since) -> tuple[float, dict]:
    if rule.organization_id is None:
        return 0.0, {"reason": "global_cost_spike_not_evaluated"}
    now = utc_now()
    window = now - since
    current = cost_for_window(
        session=session,
        organization_id=rule.organization_id,
        since=since,
        until=now,
    )
    baseline_since = since - timedelta(days=7)
    baseline_until = baseline_since + window
    baseline = cost_for_window(
        session=session,
        organization_id=rule.organization_id,
        since=baseline_since,
        until=baseline_until,
    )
    ratio = Decimal("0") if baseline <= 0 else current / baseline
    return float(ratio), {
        "current_cost_usd": str(current),
        "baseline_cost_usd": str(baseline),
        "baseline_window_days_back": 7,
    }


def _compare(observed: float, comparator: str, threshold: float) -> bool:
    compare = _COMPARATORS.get(comparator)
    if compare is None:
        return False
    return bool(compare(observed, threshold))
