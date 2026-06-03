from __future__ import annotations

import secrets
import time
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import UTC, datetime, timedelta

from opentelemetry import trace
from opentelemetry.trace import SpanKind, Status, StatusCode
from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.core.tracing import get_current_trace_id
from app.db.models import OtelSpan, Task, utc_now

OTEL_SPAN_RETENTION_DAYS = 90
_local_span_stack: ContextVar[tuple[str, ...]] = ContextVar("local_span_stack", default=())


@contextmanager
def traced_operation(
    session: Session,
    name: str,
    *,
    task_id: str | None = None,
    agent_run_id: str | None = None,
    organization_id: str | None = None,
    kind: str = "internal",
    attributes: dict | None = None,
    link_current_parent: bool = True,
    best_effort: bool = False,
) -> Iterator[dict]:
    trace_id = get_current_trace_id() or task_id or secrets.token_hex(16)
    parent_span_id = _current_local_span_id()
    if parent_span_id is None and link_current_parent:
        parent_span_id = _current_span_id()
    started = utc_now()
    started_monotonic = time.monotonic()
    attr = dict(attributes or {})
    if task_id is not None:
        attr.setdefault("task_id", task_id)
    if agent_run_id is not None:
        attr.setdefault("agent_run_id", agent_run_id)
    tracer = trace.get_tracer("api-server")
    span_kind = _span_kind(kind)
    with tracer.start_as_current_span(name, kind=span_kind) as otel_span:
        span_id = _span_id_from_context(otel_span.get_span_context()) or secrets.token_hex(8)
        token = _local_span_stack.set((*_local_span_stack.get(), span_id))
        otel_span.set_attribute("harness.trace_id", trace_id)
        otel_span.set_attribute("harness.span_id", span_id)
        for key, value in attr.items():
            if isinstance(value, (str, int, float, bool)):
                otel_span.set_attribute(key, value)
        status = "OK"
        try:
            try:
                yield attr
            except Exception as exc:
                status = "ERROR"
                otel_span.record_exception(exc)
                otel_span.set_status(Status(StatusCode.ERROR, str(exc)))
                raise
            finally:
                ended = utc_now()
                duration_ms = max(0, int((time.monotonic() - started_monotonic) * 1000))
                for key, value in attr.items():
                    if isinstance(value, (str, int, float, bool)):
                        otel_span.set_attribute(key, value)
                try:
                    persist_span(
                        session=session,
                        trace_id=trace_id,
                        span_id=span_id,
                        parent_span_id=parent_span_id,
                        name=name,
                        kind=kind,
                        start_time=started,
                        end_time=ended,
                        duration_ms=duration_ms,
                        attributes=attr,
                        status=status,
                        task_id=task_id,
                        agent_run_id=agent_run_id,
                        organization_id=organization_id,
                    )
                except Exception:
                    if not best_effort:
                        raise
        finally:
            _local_span_stack.reset(token)


def persist_span(
    *,
    session: Session,
    trace_id: str,
    span_id: str,
    parent_span_id: str | None,
    name: str,
    kind: str,
    start_time: datetime,
    end_time: datetime,
    duration_ms: int,
    attributes: dict,
    status: str,
    task_id: str | None = None,
    agent_run_id: str | None = None,
    organization_id: str | None = None,
) -> OtelSpan | None:
    resolved_org = organization_id or _organization_for_task(session=session, task_id=task_id)
    _prune_old_spans(session)
    row = OtelSpan(
        organization_id=resolved_org,
        trace_id=trace_id,
        span_id=span_id,
        parent_span_id=parent_span_id,
        name=name,
        kind=kind,
        start_time=start_time,
        end_time=end_time,
        duration_ms=duration_ms,
        attributes_json=_safe_attributes(attributes),
        status=status,
        task_id=task_id,
        agent_run_id=agent_run_id,
        created_at=utc_now(),
    )
    session.add(row)
    return row


def _organization_for_task(*, session: Session, task_id: str | None) -> str | None:
    if task_id is None:
        return None
    task = session.get(Task, task_id)
    return task.organization_id if task is not None else None


def _safe_attributes(attributes: dict) -> dict:
    safe = {}
    for key, value in attributes.items():
        if value is None:
            continue
        if isinstance(value, (str, int, float, bool)):
            safe[str(key)] = value
        else:
            safe[str(key)] = str(value)
    return safe


def _current_span_id() -> str | None:
    current = trace.get_current_span()
    context = current.get_span_context() if current is not None else None
    return _span_id_from_context(context)


def _current_local_span_id() -> str | None:
    stack = _local_span_stack.get()
    return stack[-1] if stack else None


def _span_id_from_context(context) -> str | None:
    if context is None or not context.is_valid:
        return None
    return f"{context.span_id:016x}"


def _span_kind(kind: str) -> SpanKind:
    normalized = kind.lower()
    if normalized == "server":
        return SpanKind.SERVER
    if normalized == "client":
        return SpanKind.CLIENT
    if normalized == "producer":
        return SpanKind.PRODUCER
    if normalized == "consumer":
        return SpanKind.CONSUMER
    return SpanKind.INTERNAL


def _prune_old_spans(session: Session) -> None:
    cutoff = datetime.now(UTC) - timedelta(days=OTEL_SPAN_RETENTION_DAYS)
    session.execute(delete(OtelSpan).where(OtelSpan.start_time < cutoff))
