from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.db.models import SubagentRecoveryBatch


def recovery_action_counts(recovered: list[dict]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in recovered:
        action = str(item.get("action") or "unknown")
        counts[action] = counts.get(action, 0) + 1
    return counts


def persist_recovery_batch(
    *,
    session: Session,
    organization_id: str | None,
    payload: dict,
) -> SubagentRecoveryBatch:
    completed_at = payload.get("completed_at") or datetime.now(UTC)
    if isinstance(completed_at, str):
        completed_at = datetime.fromisoformat(completed_at)
    batch = SubagentRecoveryBatch(
        batch_id=str(payload["batch_id"]),
        organization_id=organization_id,
        task_id=payload.get("task_id"),
        trigger=str(payload.get("trigger") or "unknown"),
        lock_acquired=bool(payload.get("lock_acquired", True)),
        replay_sequence=int(payload.get("replay_sequence") or 0),
        stale_after_seconds=int(payload.get("stale_after_seconds") or 0),
        enqueue=bool(payload.get("enqueue", False)),
        task_count=int(payload.get("task_count") or (1 if payload.get("task_id") else 0)),
        scanned_count=int(payload.get("scanned_count") or 0),
        recovered_count=int(payload.get("recovered_count") or 0),
        action_counts=dict(payload.get("action_counts") or {}),
        recovered=list(payload.get("recovered") or []),
        recovered_by_task=list(payload.get("recovered_by_task") or []),
        completed_at=completed_at,
    )
    session.add(batch)
    session.flush()
    return batch
