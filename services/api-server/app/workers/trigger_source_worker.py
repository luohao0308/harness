from __future__ import annotations

import time
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import Trigger
from app.runtime_jobs.profile import is_local_runtime_profile
from app.runtime_jobs.repository import RuntimeJobRepository
from app.triggers.sources import (
    SourceObservation,
    next_schedule_state,
    scan_files,
    scan_git,
    schedule_due,
    schedule_observation,
)

LOCAL_TRIGGER_TYPES = ("schedule", "file", "git")
DEFAULT_POLL_BUDGET_SECONDS = 0.5
DEFAULT_FILE_TRIGGER_BUDGET_SECONDS = 0.1
DEFAULT_MAX_TRIGGERS_PER_POLL = 8


def local_triggers_enabled() -> bool:
    settings = get_settings()
    return is_local_runtime_profile(settings) and bool(
        getattr(settings, "trigger_automation_enabled", False)
    )


def poll_local_trigger_sources(
    payload: dict[str, Any],
    *,
    session: Session,
    now: float | None = None,
) -> dict[str, Any]:
    """Observe enabled local sources and atomically enqueue new invocations."""
    if not local_triggers_enabled():
        return {"status": "disabled", "observed": 0, "enqueued": 0}

    current = float(time.time() if now is None else now)
    poll_budget = max(
        0.05,
        min(float(payload.get("max_poll_duration_seconds", DEFAULT_POLL_BUDGET_SECONDS)), 5.0),
    )
    max_triggers = max(
        1,
        min(int(payload.get("max_triggers_per_poll", DEFAULT_MAX_TRIGGERS_PER_POLL)), 100),
    )
    deadline = time.monotonic() + poll_budget
    triggers = list(
        session.execute(
            select(Trigger).where(
                Trigger.type.in_(LOCAL_TRIGGER_TYPES),
                Trigger.enabled.is_(True),
                Trigger.deleted_at.is_(None),
            )
        ).scalars()
    )
    triggers.sort(key=_poll_order)
    observed = 0
    enqueued = 0
    processed = 0
    for trigger in triggers:
        if processed >= max_triggers or time.monotonic() >= deadline:
            break
        # Re-check after the query so a locally mutated ORM object fails closed.
        if not trigger.enabled or trigger.deleted_at is not None or not local_triggers_enabled():
            continue
        config = {**(trigger.config_json or {}), "enabled": True}
        if trigger.type == "file":
            remaining = max(0.01, deadline - time.monotonic())
            configured_budget = float(
                config.get("max_duration_seconds", DEFAULT_FILE_TRIGGER_BUDGET_SECONDS)
            )
            config["max_duration_seconds"] = min(
                configured_budget,
                DEFAULT_FILE_TRIGGER_BUDGET_SECONDS,
                remaining,
            )
        previous = trigger.runtime_state_json or {}
        observations, next_state = _observe_trigger(
            trigger_id=trigger.id,
            trigger_type=trigger.type,
            config=config,
            previous=previous,
            now=current,
        )
        trigger.runtime_state_json = {
            **next_state,
            "_poll": {"last_polled_at": current},
        }
        processed += 1
        observed += len(observations)
        for observation in observations:
            invocation, created = _create_invocation(
                trigger=trigger,
                observation=observation,
                config=config,
                session=session,
            )
            if not created:
                continue
            RuntimeJobRepository(session).enqueue(
                kind="trigger_invocation",
                payload={"invocation_id": invocation.id},
                dedupe_key=f"trigger-invocation:{invocation.id}",
                max_attempts=max(1, min(int(config.get("max_attempts", 3)), 10)),
            )
            enqueued += 1
    session.flush()
    return {
        "status": "ok",
        "triggers": len(triggers),
        "processed": processed,
        "deferred": len(triggers) - processed,
        "observed": observed,
        "enqueued": enqueued,
    }


def _poll_order(trigger: Trigger) -> tuple[float, str]:
    state = trigger.runtime_state_json or {}
    poll_state = state.get("_poll") if isinstance(state.get("_poll"), dict) else {}
    return float(poll_state.get("last_polled_at", 0) or 0), trigger.id


def _observe_trigger(
    *,
    trigger_id: str,
    trigger_type: str,
    config: dict[str, Any],
    previous: dict[str, Any],
    now: float,
) -> tuple[list[SourceObservation], dict[str, Any]]:
    if trigger_type == "schedule":
        if previous.get("next_run_at") is None:
            return [], next_schedule_state(config, now=now)
        if not schedule_due(config, previous, now=now):
            return [], previous
        scheduled_at = float(previous["next_run_at"])
        return [
            schedule_observation(
                trigger_id,
                config,
                now=now,
                scheduled_at=scheduled_at,
            )
        ], next_schedule_state(
            config,
            previous,
            now=now,
        )
    if trigger_type == "file":
        return scan_files(config, previous=previous or None)
    if trigger_type == "git":
        return scan_git(config, previous=previous or None)
    return [], previous


def _create_invocation(
    *,
    trigger: Trigger,
    observation: SourceObservation,
    config: dict[str, Any],
    session: Session,
):
    from app.triggers.service import create_trigger_invocation

    return create_trigger_invocation(
        trigger=trigger,
        idempotency_key=observation.dedupe_key,
        source=observation.source_key,
        payload_summary=observation.metadata,
        goal=config.get("goal"),
        title=config.get("title"),
        session=session,
    )
