from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, NoReturn
from uuid import uuid4

from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.agents.executor import Executor
from app.agents.planner import PLANNER_PROMPT_VERSION, DeterministicPlanner
from app.core.config import get_settings
from app.db.models import Agent, ExecutionPlan, Task, Trigger, TriggerInvocation, utc_now
from app.events.event_store import EventStore
from app.events.event_types import EventType

MAX_IDEMPOTENCY_KEY_LENGTH = 255
MAX_SUMMARY_BYTES = 4096
MAX_SUMMARY_KEYS = 100
MAX_SUMMARY_KEY_BYTES = 2048
MAX_WEBHOOK_PREVIEW_BYTES = 1536
MAX_WEBHOOK_PREVIEW_DEPTH = 6
MAX_WEBHOOK_PREVIEW_ITEMS = 100
MAX_WEBHOOK_STRING_BYTES = 512
TRIGGER_INVOCATION_TTL = timedelta(hours=24)
TRIGGER_EXECUTION_LEASE_GRACE = timedelta(seconds=60)
TERMINAL_INVOCATION_STATUSES = {"SUCCEEDED", "FAILED", "DISABLED"}
LOCAL_SOURCE_SUMMARY_FIELDS = {
    "path",
    "change_type",
    "sha256",
    "size",
    "head",
    "branch",
    "scheduled_at",
    "interval_seconds",
    "changed_count",
    "changed_paths",
    "changes_sha256",
    "truncated",
}
WEBHOOK_SENSITIVE_KEY_PATTERN = re.compile(
    r"authorization|cookie|pass(?:word|wd)?|secret|signature|token|api.?key",
    re.IGNORECASE,
)
WEBHOOK_SENSITIVE_VALUE_PATTERNS = (
    re.compile(r"\bBearer\s+[A-Za-z0-9._~+/=-]+", re.IGNORECASE),
    re.compile(
        r"\b(?:authorization|cookie|pass(?:word|wd)?|secret|signature|token|api.?key)"
        r"\s*[:=]\s*[^\s,;]+",
        re.IGNORECASE,
    ),
)


class TriggerInvocationRejected(RuntimeError):
    """Raised when trigger automation is unavailable or the trigger cannot run."""


class TriggerInvocationLeaseBusy(RuntimeError):
    """Raised when another worker still owns the invocation execution lease."""

    def __init__(self, retry_after_seconds: float) -> None:
        super().__init__("Trigger invocation is already running")
        self.retry_after_seconds = max(1.0, retry_after_seconds)


class _TriggerInvocationStopped(RuntimeError):
    """Internal signal used to stop Executor without retrying a terminal safety gate."""


def _enqueue_trigger_invocation_job(
    *,
    trigger: Trigger,
    invocation: TriggerInvocation,
    now: datetime,
    session: Session,
) -> None:
    """Queue execution for the active runtime profile without running the Plan inline."""
    from app.runtime_jobs.repository import RuntimeJobRepository

    repository = RuntimeJobRepository(session)
    if get_settings().runtime_profile == "local":
        repository.enqueue(
            kind="trigger_invocation",
            payload={
                "invocation_id": invocation.id,
                "expires_at": (now + TRIGGER_INVOCATION_TTL).isoformat(),
            },
            dedupe_key=f"trigger-invocation:{invocation.id}",
            max_attempts=max(1, int((trigger.config_json or {}).get("max_attempts", 3))),
        )
        return
    if trigger.type != "webhook":
        raise TriggerInvocationRejected("Trigger source is unavailable in the server runtime")
    from app.workers.trigger_dispatch_worker import TRIGGER_DISPATCH_JOB_KIND

    repository.enqueue(
        kind=TRIGGER_DISPATCH_JOB_KIND,
        payload={"invocation_id": invocation.id},
        dedupe_key=f"trigger-dispatch:{invocation.id}",
        max_attempts=10_000,
    )


def create_trigger_invocation(
    *,
    trigger: Trigger | str | None = None,
    trigger_id: str | None = None,
    idempotency_key: str | None,
    source: str,
    payload_summary: dict,
    session: Session,
    goal: str | None = None,
    title: str | None = None,
) -> tuple[TriggerInvocation, bool]:
    """Create one persisted receipt and its planned Run, or return an idempotent replay."""
    if not get_settings().trigger_automation_enabled:
        raise TriggerInvocationRejected("Trigger automation is disabled")
    trigger_row = _resolve_trigger(trigger=trigger, trigger_id=trigger_id, session=session)
    if not trigger_row.enabled or trigger_row.deleted_at is not None:
        raise TriggerInvocationRejected("Trigger is disabled")

    normalized_key = _normalize_idempotency_key(idempotency_key)
    if normalized_key is not None:
        existing = _find_invocation(
            trigger_id=trigger_row.id,
            idempotency_key=normalized_key,
            session=session,
        )
        if existing is not None:
            return existing, False

    now = utc_now()
    invocation = TriggerInvocation(
        trigger_id=trigger_row.id,
        organization_id=trigger_row.organization_id,
        idempotency_key=normalized_key,
        config_summary_json=_summarize_config(trigger_row),
        payload_summary_json=_summarize_payload(
            payload_summary,
            trigger_type=trigger_row.type,
        ),
        workspace_root=_trigger_workspace_root(trigger_row),
        status="RECEIVED",
        attempt=1,
        created_at=now,
        updated_at=now,
    )
    try:
        with session.begin_nested():
            session.add(invocation)
            session.flush()
    except IntegrityError:
        if normalized_key is None:
            raise
        existing = _find_invocation(
            trigger_id=trigger_row.id,
            idempotency_key=normalized_key,
            session=session,
        )
        if existing is None:
            raise
        return existing, False

    agent = _trigger_agent(trigger_row, session=session)
    run = _create_planned_run(
        trigger=trigger_row,
        invocation=invocation,
        agent=agent,
        source=source,
        goal=goal,
        title=title,
        session=session,
    )
    invocation.run_id = run.id
    invocation.status = "PLANNED"
    invocation.updated_at = utc_now()
    trigger_row.last_triggered_at = utc_now()
    trigger_row.updated_at = utc_now()
    _enqueue_trigger_invocation_job(
        trigger=trigger_row,
        invocation=invocation,
        now=now,
        session=session,
    )
    session.flush()
    return invocation, True


def execute_trigger_invocation(
    *,
    invocation_id: str,
    session: Session,
    lease_owner: str | None = None,
) -> TriggerInvocation:
    """Execute or resume one persisted invocation under a fenced execution lease."""
    owner = lease_owner or f"trigger-execution:{uuid4()}"
    generation = _acquire_execution_lease(
        invocation_id=invocation_id,
        lease_owner=owner,
        session=session,
    )
    if generation is None:
        invocation = session.get(TriggerInvocation, invocation_id)
        if invocation is None:
            raise ValueError("Trigger invocation not found") from None
        return invocation

    try:
        invocation, _trigger, run = _guard_next_trigger_step(
            invocation_id=invocation_id,
            lease_owner=owner,
            lease_generation=generation,
            session=session,
        )
        try:
            workspace_root = _validated_invocation_workspace(invocation)
        except TriggerInvocationRejected as exc:
            _stop_invocation(
                invocation,
                run=run,
                status="FAILED",
                error=str(exc),
                session=session,
            )

        runtime_checkpoint = session.info.get("runtime_job_step_checkpoint")

        def checkpoint() -> None:
            _assert_execution_lease(
                invocation_id=invocation_id,
                lease_owner=owner,
                lease_generation=generation,
                session=session,
            )
            if runtime_checkpoint is not None:
                runtime_checkpoint()
            else:
                session.commit()

        def guard_step() -> None:
            _guard_next_trigger_step(
                invocation_id=invocation_id,
                lease_owner=owner,
                lease_generation=generation,
                session=session,
            )

        executor = Executor(
            session,
            step_checkpoint=checkpoint,
            step_guard=guard_step,
        )
        executor.workspace_access_enabled = workspace_root is not None
        if workspace_root is not None:
            executor.workspace_root = workspace_root
        executed = (
            executor.execute_existing_plan(run)
            if run.status == "PLANNED"
            else executor.resume_task(run)
        )
    except _TriggerInvocationStopped:
        invocation = session.get(TriggerInvocation, invocation_id)
        if invocation is None:
            raise ValueError("Trigger invocation not found") from None
        return invocation
    except Exception:
        _release_execution_lease_after_error(
            invocation_id=invocation_id,
            lease_owner=owner,
            lease_generation=generation,
            session=session,
        )
        raise

    invocation = session.get(TriggerInvocation, invocation_id)
    if invocation is None:
        raise ValueError("Trigger invocation not found")
    _sync_invocation_from_run(invocation, executed)
    _clear_execution_lease(invocation)
    session.flush()
    return invocation


def trigger_invocation_for_run(*, run_id: str, session: Session) -> TriggerInvocation | None:
    return session.execute(
        select(TriggerInvocation)
        .where(TriggerInvocation.run_id == run_id)
        .order_by(TriggerInvocation.created_at.desc(), TriggerInvocation.id.desc())
        .limit(1)
    ).scalar_one_or_none()


def resume_trigger_invocation(*, invocation_id: str, session: Session) -> TriggerInvocation:
    """Reset a user-resumable failed Trigger Run and enqueue its fenced execution."""
    invocation = session.execute(
        select(TriggerInvocation)
        .where(TriggerInvocation.id == invocation_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).scalar_one_or_none()
    if invocation is None:
        session.rollback()
        raise ValueError("Trigger invocation not found")
    trigger = session.get(Trigger, invocation.trigger_id)
    run = session.get(Task, invocation.run_id) if invocation.run_id else None
    if trigger is None or run is None:
        session.rollback()
        raise ValueError("Trigger Run is no longer available")
    if not trigger.enabled or trigger.deleted_at is not None:
        session.rollback()
        raise TriggerInvocationRejected("Trigger is disabled")
    if not get_settings().trigger_automation_enabled:
        session.rollback()
        raise TriggerInvocationRejected("Trigger automation is disabled")
    if invocation.status not in TERMINAL_INVOCATION_STATUSES:
        session.rollback()
        raise TriggerInvocationRejected("Trigger invocation is not resumable")
    invocation.status = "RETRYING"
    invocation.error = None
    invocation.completed_at = None
    invocation.updated_at = utc_now()
    run.status = "PLANNED"
    run.completed_at = None
    run.updated_at = utc_now()
    _enqueue_trigger_invocation_job(
        trigger=trigger,
        invocation=invocation,
        now=utc_now(),
        session=session,
    )
    session.commit()
    session.refresh(invocation)
    return invocation


def sync_trigger_invocation_from_run(
    *,
    run_id: str,
    session: Session,
) -> TriggerInvocation | None:
    """Persist the current Run projection into its Trigger invocation receipt."""
    invocation = session.execute(
        select(TriggerInvocation)
        .where(TriggerInvocation.run_id == run_id)
        .order_by(TriggerInvocation.created_at.desc(), TriggerInvocation.id.desc())
        .limit(1)
    ).scalar_one_or_none()
    if invocation is None:
        return None
    run = session.get(Task, run_id)
    if run is None:
        return invocation
    _sync_invocation_from_run(invocation, run)
    if invocation.status in TERMINAL_INVOCATION_STATUSES:
        _clear_execution_lease(invocation)
    session.flush()
    return invocation


def trigger_workspace_context_for_run(
    *,
    run_id: str,
    session: Session,
) -> tuple[bool, Path | None]:
    invocation = session.execute(
        select(TriggerInvocation)
        .where(TriggerInvocation.run_id == run_id)
        .order_by(TriggerInvocation.created_at.desc(), TriggerInvocation.id.desc())
        .limit(1)
    ).scalar_one_or_none()
    if invocation is None:
        return False, None
    trigger = session.get(Trigger, invocation.trigger_id)
    if (
        trigger is None
        or not trigger.enabled
        or trigger.deleted_at is not None
        or not get_settings().trigger_automation_enabled
    ):
        raise TriggerInvocationRejected("Trigger automation is disabled")
    return True, _validated_invocation_workspace(invocation)


def trigger_workspace_for_run(*, run_id: str, session: Session) -> Path | None:
    _is_trigger_run, workspace_root = trigger_workspace_context_for_run(
        run_id=run_id,
        session=session,
    )
    return workspace_root


def _acquire_execution_lease(
    *,
    invocation_id: str,
    lease_owner: str,
    session: Session,
) -> int | None:
    now = utc_now()
    invocation = session.execute(
        select(TriggerInvocation)
        .where(TriggerInvocation.id == invocation_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).scalar_one_or_none()
    if invocation is None:
        session.rollback()
        raise ValueError("Trigger invocation not found")
    if invocation.status in TERMINAL_INVOCATION_STATUSES:
        session.rollback()
        return None
    if invocation.lease_owner and _lease_deadline(invocation) > now:
        retry_after = (_lease_deadline(invocation) - now).total_seconds()
        session.rollback()
        raise TriggerInvocationLeaseBusy(retry_after)

    invocation.lease_owner = lease_owner
    invocation.lease_generation = max(0, invocation.lease_generation) + 1
    run = session.get(Task, invocation.run_id) if invocation.run_id is not None else None
    invocation.lease_until = now + _execution_lease_duration(run)
    invocation.status = "RUNNING"
    invocation.started_at = invocation.started_at or now
    invocation.updated_at = now
    generation = invocation.lease_generation
    session.commit()
    return generation


def _guard_next_trigger_step(
    *,
    invocation_id: str,
    lease_owner: str,
    lease_generation: int,
    session: Session,
) -> tuple[TriggerInvocation, Trigger, Task]:
    invocation = session.execute(
        select(TriggerInvocation)
        .where(TriggerInvocation.id == invocation_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).scalar_one_or_none()
    if invocation is None:
        session.rollback()
        raise ValueError("Trigger invocation not found")
    if (
        invocation.lease_owner != lease_owner
        or invocation.lease_generation != lease_generation
    ):
        retry_after = max(1.0, (_lease_deadline(invocation) - utc_now()).total_seconds())
        session.rollback()
        raise TriggerInvocationLeaseBusy(retry_after)

    trigger = session.execute(
        select(Trigger)
        .where(Trigger.id == invocation.trigger_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).scalar_one_or_none()
    run = (
        session.execute(
            select(Task)
            .where(Task.id == invocation.run_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        ).scalar_one_or_none()
        if invocation.run_id is not None
        else None
    )
    if trigger is None or not trigger.enabled or trigger.deleted_at is not None:
        _stop_invocation(
            invocation,
            run=run,
            status="DISABLED",
            error="Trigger automation is disabled",
            session=session,
        )
    if not get_settings().trigger_automation_enabled:
        _stop_invocation(
            invocation,
            run=run,
            status="DISABLED",
            error="Trigger automation is disabled",
            session=session,
        )
    if run is None:
        _stop_invocation(
            invocation,
            run=None,
            status="FAILED",
            error="Trigger Run not found",
            session=session,
        )
    if run.status in {"COMPLETED", "FAILED", "CANCELLED", "WAITING_APPROVAL"}:
        _sync_invocation_from_run(invocation, run)
        _clear_execution_lease(invocation)
        session.commit()
        raise _TriggerInvocationStopped

    invocation.lease_until = utc_now() + _execution_lease_duration(run)
    invocation.updated_at = utc_now()
    session.commit()
    return invocation, trigger, run


def _assert_execution_lease(
    *,
    invocation_id: str,
    lease_owner: str,
    lease_generation: int,
    session: Session,
) -> None:
    invocation = session.execute(
        select(TriggerInvocation)
        .where(TriggerInvocation.id == invocation_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).scalar_one_or_none()
    if invocation is None:
        session.rollback()
        raise ValueError("Trigger invocation not found")
    if (
        invocation.lease_owner != lease_owner
        or invocation.lease_generation != lease_generation
    ):
        retry_after = max(1.0, (_lease_deadline(invocation) - utc_now()).total_seconds())
        session.rollback()
        raise TriggerInvocationLeaseBusy(retry_after)


def _stop_invocation(
    invocation: TriggerInvocation,
    *,
    run: Task | None,
    status: str,
    error: str,
    session: Session,
) -> NoReturn:
    now = utc_now()
    if run is not None and run.status not in {"COMPLETED", "FAILED", "CANCELLED"}:
        run.status = "CANCELLED"
        run.updated_at = now
        run.completed_at = now
        EventStore(session).append(
            task_id=run.id,
            event_type=EventType.TASK_CANCELLED,
            payload_json={
                "task_id": run.id,
                "trigger_id": invocation.trigger_id,
                "invocation_id": invocation.id,
                "reason": error,
            },
            actor_type="trigger",
            actor_id=invocation.trigger_id,
        )
    invocation.status = status
    invocation.error = error
    invocation.updated_at = now
    invocation.completed_at = now
    _clear_execution_lease(invocation)
    session.commit()
    raise _TriggerInvocationStopped


def _release_execution_lease_after_error(
    *,
    invocation_id: str,
    lease_owner: str,
    lease_generation: int,
    session: Session,
) -> None:
    session.rollback()
    invocation = session.execute(
        select(TriggerInvocation)
        .where(TriggerInvocation.id == invocation_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).scalar_one_or_none()
    if invocation is not None and (
        invocation.lease_owner == lease_owner
        and invocation.lease_generation == lease_generation
    ):
        _clear_execution_lease(invocation)
        if invocation.status == "RUNNING":
            invocation.status = "RETRYING"
        invocation.updated_at = utc_now()
        session.commit()
        return
    session.rollback()


def _clear_execution_lease(invocation: TriggerInvocation) -> None:
    invocation.lease_owner = None
    invocation.lease_until = None


def _lease_deadline(invocation: TriggerInvocation):
    deadline = invocation.lease_until
    if deadline is None:
        return utc_now() - timedelta(seconds=1)
    if deadline.tzinfo is None:
        return deadline.replace(tzinfo=UTC)
    return deadline


def _execution_lease_duration(run: Task | None) -> timedelta:
    runtime_seconds = max(60, int(run.max_runtime_seconds if run is not None else 1800))
    return timedelta(seconds=runtime_seconds) + TRIGGER_EXECUTION_LEASE_GRACE


def _trigger_workspace_root(trigger: Trigger) -> str | None:
    if trigger.type not in {"file", "git"}:
        return None
    config = trigger.config_json or {}
    raw_root = config.get("workspace_root") if trigger.type == "file" else config.get("repo_root")
    if not raw_root:
        raise TriggerInvocationRejected("Trigger workspace is not configured")
    try:
        root = Path(str(raw_root)).expanduser().resolve(strict=True)
    except OSError as exc:
        raise TriggerInvocationRejected("Trigger workspace is unavailable") from exc
    if not root.is_dir():
        raise TriggerInvocationRejected("Trigger workspace is unavailable")
    return str(root)


def _validated_invocation_workspace(invocation: TriggerInvocation) -> Path | None:
    if invocation.workspace_root is None:
        return None
    if get_settings().runtime_profile != "local":
        raise TriggerInvocationRejected("Local Trigger workspace is unavailable in server profile")
    configured = Path(invocation.workspace_root)
    try:
        resolved = configured.expanduser().resolve(strict=True)
    except OSError as exc:
        raise TriggerInvocationRejected("Trigger workspace is unavailable") from exc
    if not resolved.is_dir() or str(resolved) != invocation.workspace_root:
        raise TriggerInvocationRejected("Trigger workspace identity changed")
    return resolved


def _resolve_trigger(
    *,
    trigger: Trigger | str | None,
    trigger_id: str | None,
    session: Session,
) -> Trigger:
    if isinstance(trigger, Trigger):
        return trigger
    resolved_id = trigger_id or (trigger if isinstance(trigger, str) else None)
    if not resolved_id:
        raise ValueError("trigger or trigger_id is required")
    trigger_row = session.get(Trigger, resolved_id)
    if trigger_row is None:
        raise ValueError("Trigger not found")
    return trigger_row


def _normalize_idempotency_key(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    if not normalized:
        raise ValueError("Idempotency-Key cannot be blank")
    if len(normalized) > MAX_IDEMPOTENCY_KEY_LENGTH:
        raise ValueError(f"Idempotency-Key cannot exceed {MAX_IDEMPOTENCY_KEY_LENGTH} characters")
    return normalized


def _find_invocation(
    *, trigger_id: str, idempotency_key: str, session: Session
) -> TriggerInvocation | None:
    return session.execute(
        select(TriggerInvocation).where(
            TriggerInvocation.trigger_id == trigger_id,
            TriggerInvocation.idempotency_key == idempotency_key,
        )
    ).scalar_one_or_none()


def _trigger_agent(trigger: Trigger, *, session: Session) -> Agent:
    agent = session.execute(
        select(Agent).where(
            Agent.id == trigger.agent_id,
            or_(
                Agent.organization_id == trigger.organization_id,
                Agent.organization_id.is_(None),
            ),
        )
    ).scalar_one_or_none()
    if agent is None:
        raise TriggerInvocationRejected("Trigger Agent not found")
    return agent


def _summarize_payload(payload: dict, *, trigger_type: str) -> dict[str, Any]:
    if trigger_type != "webhook":
        summary: dict[str, Any] = {}
        for key in LOCAL_SOURCE_SUMMARY_FIELDS:
            if key not in payload:
                continue
            value = _bounded_summary_value(payload[key])
            if value is not None:
                summary[key] = value
        return summary
    raw_payload = payload.get("payload") if isinstance(payload.get("payload"), dict) else payload
    encoded = json.dumps(raw_payload, sort_keys=True, default=str).encode("utf-8")
    all_keys = sorted(str(key) for key in raw_payload)
    keys: list[str] = []
    key_bytes = 0
    for key in all_keys[:MAX_SUMMARY_KEYS]:
        encoded_key = key.encode("utf-8")
        if key_bytes + len(encoded_key) > MAX_SUMMARY_KEY_BYTES:
            break
        keys.append(key)
        key_bytes += len(encoded_key)
    preview, preview_truncated, redaction_count = _webhook_payload_preview(raw_payload)
    summary = {
        "keys": keys,
        "key_count": len(all_keys),
        "keys_sha256": hashlib.sha256(
            json.dumps(all_keys, separators=(",", ":")).encode("utf-8")
        ).hexdigest(),
        "size_bytes": len(encoded),
        "preview_json": preview,
        "redaction_count": redaction_count,
        "truncated": (
            len(keys) < len(all_keys)
            or len(encoded) > MAX_SUMMARY_BYTES
            or preview_truncated
        ),
    }
    while (
        keys
        and len(json.dumps(summary, separators=(",", ":")).encode("utf-8"))
        > MAX_SUMMARY_BYTES
    ):
        keys.pop()
        summary["truncated"] = True
    return summary


def _webhook_payload_preview(payload: dict) -> tuple[str, bool, int]:
    state: dict[str, int | bool] = {
        "items": 0,
        "redactions": 0,
        "truncated": False,
    }
    sanitized = _sanitize_webhook_value(payload, depth=0, state=state)
    encoded = json.dumps(
        sanitized,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    if len(encoded) > MAX_WEBHOOK_PREVIEW_BYTES:
        encoded = encoded[:MAX_WEBHOOK_PREVIEW_BYTES]
        preview = encoded.decode("utf-8", errors="ignore") + "..."
        state["truncated"] = True
    else:
        preview = encoded.decode("utf-8")
    return preview, bool(state["truncated"]), int(state["redactions"])


def _sanitize_webhook_value(
    value: Any,
    *,
    depth: int,
    state: dict[str, int | bool],
    sensitive: bool = False,
) -> Any:
    if sensitive:
        state["redactions"] = int(state["redactions"]) + 1
        return "[REDACTED]"
    if depth >= MAX_WEBHOOK_PREVIEW_DEPTH:
        state["truncated"] = True
        return "[TRUNCATED:depth]"
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for raw_key in sorted(value, key=lambda item: str(item)):
            if int(state["items"]) >= MAX_WEBHOOK_PREVIEW_ITEMS:
                state["truncated"] = True
                break
            state["items"] = int(state["items"]) + 1
            key = _truncate_utf8(str(raw_key), 128)
            result[key] = _sanitize_webhook_value(
                value[raw_key],
                depth=depth + 1,
                state=state,
                sensitive=bool(WEBHOOK_SENSITIVE_KEY_PATTERN.search(key)),
            )
        return result
    if isinstance(value, (list, tuple)):
        result: list[Any] = []
        for item in value:
            if int(state["items"]) >= MAX_WEBHOOK_PREVIEW_ITEMS:
                state["truncated"] = True
                break
            state["items"] = int(state["items"]) + 1
            result.append(_sanitize_webhook_value(item, depth=depth + 1, state=state))
        return result
    if isinstance(value, str):
        redacted = value
        for pattern in WEBHOOK_SENSITIVE_VALUE_PATTERNS:
            redacted, count = pattern.subn("[REDACTED]", redacted)
            state["redactions"] = int(state["redactions"]) + count
        truncated = _truncate_utf8(redacted, MAX_WEBHOOK_STRING_BYTES)
        if truncated != redacted:
            state["truncated"] = True
            truncated += "..."
        return truncated
    if value is None or isinstance(value, (bool, int, float)):
        return value
    state["truncated"] = True
    return _truncate_utf8(str(value), MAX_WEBHOOK_STRING_BYTES)


def _truncate_utf8(value: str, max_bytes: int) -> str:
    encoded = value.encode("utf-8")
    if len(encoded) <= max_bytes:
        return value
    return encoded[:max_bytes].decode("utf-8", errors="ignore")


def _bounded_summary_value(value: Any) -> str | int | float | bool | list[str] | None:
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return value[:512]
    if isinstance(value, list):
        return [str(item)[:256] for item in value[:20]]
    return None


def _summarize_config(trigger: Trigger) -> dict[str, Any]:
    config = dict(trigger.config_json or {})
    summary: dict[str, Any] = {"type": trigger.type}
    allowed = {
        "schedule": {"interval_seconds", "max_attempts"},
        "file": {
            "pattern",
            "max_files",
            "max_file_bytes",
            "max_total_bytes",
            "max_duration_seconds",
            "max_attempts",
        },
        "git": {"branch", "max_attempts"},
        "webhook": {"max_attempts"},
    }[trigger.type]
    summary.update({key: config[key] for key in allowed if key in config})
    root = config.get("repo_root") if trigger.type == "git" else config.get("workspace_root")
    if root:
        summary["root_fingerprint"] = hashlib.sha256(str(root).encode()).hexdigest()
    if "goal" in config:
        summary["has_goal"] = True
    if "title" in config:
        summary["has_title"] = True
    return summary


def _create_planned_run(
    *,
    trigger: Trigger,
    invocation: TriggerInvocation,
    agent: Agent,
    source: str,
    goal: str | None,
    title: str | None,
    session: Session,
) -> Task:
    now = utc_now()
    configured_goal = str((trigger.config_json or {}).get("goal") or "").strip()
    configured_title = str((trigger.config_json or {}).get("title") or "").strip()
    run_goal = (goal or configured_goal or f"Handle {trigger.type} trigger invocation").strip()
    if trigger.type == "webhook":
        payload_preview = str(invocation.payload_summary_json.get("preview_json") or "").strip()
        if payload_preview:
            run_goal = f"{run_goal}\n\nWebhook payload (sanitized): {payload_preview}"
    elif invocation.payload_summary_json:
        source_summary = json.dumps(
            invocation.payload_summary_json,
            sort_keys=True,
            ensure_ascii=True,
            separators=(",", ":"),
        )
        run_goal = f"{run_goal}\n\nTrigger source: {source_summary}"
    run = Task(
        organization_id=trigger.organization_id,
        agent_id=agent.id,
        created_by=trigger.created_by,
        title=(
            title or configured_title or f"{trigger.type.title()} trigger {trigger.name}"
        ).strip(),
        goal=run_goal,
        status="CREATED",
        model_provider=agent.model_provider or "default",
        model_name=agent.model_name or "default",
        max_runtime_seconds=1800,
        max_subagents=5,
        enable_sandbox=True,
        enable_network=False,
        created_at=now,
        updated_at=now,
    )
    session.add(run)
    session.flush()
    event_store = EventStore(session)
    event_store.append(
        task_id=run.id,
        event_type=EventType.TASK_CREATED,
        payload_json={
            "task_id": run.id,
            "title": run.title,
            "goal": run.goal,
            "agent_id": agent.id,
            "mode": "trigger",
            "trigger_id": trigger.id,
            "invocation_id": invocation.id,
        },
        actor_type="trigger",
        actor_id=trigger.id,
    )
    event_store.append(
        task_id=run.id,
        event_type=EventType.TRIGGER_INVOKED,
        payload_json={
            "trigger_id": trigger.id,
            "invocation_id": invocation.id,
            "trigger_type": trigger.type,
            "source": source,
            "agent_id": agent.id,
            "config_snapshot": invocation.config_summary_json,
            "payload_summary": invocation.payload_summary_json,
        },
        actor_type="trigger",
        actor_id=trigger.id,
    )
    run.status = "PLANNING"
    run.updated_at = utc_now()
    event_store.append(
        task_id=run.id,
        event_type=EventType.PLAN_REQUESTED,
        payload_json={
            "task_id": run.id,
            "goal": run.goal,
            "agent_id": agent.id,
            "mode": "trigger",
            "trigger_id": trigger.id,
            "invocation_id": invocation.id,
            "prompt_version": PLANNER_PROMPT_VERSION,
        },
        actor_type="trigger",
        actor_id=trigger.id,
    )
    plan = DeterministicPlanner().create_plan(run)
    plan_row = ExecutionPlan(
        task_id=run.id,
        version=1,
        status="GENERATED",
        plan_json=plan.model_dump(),
        created_at=utc_now(),
    )
    session.add(plan_row)
    session.flush()
    event_store.append(
        task_id=run.id,
        event_type=EventType.PLAN_GENERATED,
        payload_json={
            "plan_id": plan_row.id,
            "plan": plan.model_dump(),
            "agent_id": agent.id,
            "mode": "trigger",
            "trigger_id": trigger.id,
            "invocation_id": invocation.id,
            "prompt_version": PLANNER_PROMPT_VERSION,
            "trace_summary": "Trigger invocation created a planned Agent Run.",
        },
        actor_type="trigger",
        actor_id=trigger.id,
    )
    run.status = "PLANNED"
    run.updated_at = utc_now()
    session.flush()
    return run


def _sync_invocation_from_run(invocation: TriggerInvocation, run: Task) -> None:
    status_map = {
        "COMPLETED": "SUCCEEDED",
        "FAILED": "FAILED",
        "CANCELLED": "FAILED",
        "WAITING_APPROVAL": "WAITING_APPROVAL",
        "PLANNED": "PLANNED",
    }
    invocation.status = status_map.get(run.status, "RUNNING")
    invocation.updated_at = utc_now()
    if invocation.status in TERMINAL_INVOCATION_STATUSES:
        invocation.completed_at = utc_now()
    if invocation.status == "FAILED" and not invocation.error:
        invocation.error = f"Run finished with status {run.status}"
