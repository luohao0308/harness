from __future__ import annotations

import signal
import time

import dramatiq
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.subagent_manager import SubagentManager
from app.db.models import AgentRun, Task
from app.db.session import SessionLocal
from app.observability.metrics import (
    agent_subagent_recovery_last_recovered,
    agent_subagent_recovery_sweeps_total,
)
from app.workers.broker import broker

DEFAULT_RECOVERY_STALE_AFTER_SECONDS = 900
DEFAULT_RECOVERY_INTERVAL_SECONDS = 30
DEFAULT_RECOVERY_ENQUEUE = True


def recover_stalled_subagents(
    *,
    stale_after_seconds: int = DEFAULT_RECOVERY_STALE_AFTER_SECONDS,
    enqueue: bool = DEFAULT_RECOVERY_ENQUEUE,
    session: Session | None = None,
) -> dict:
    if session is not None:
        return _recover_stalled_subagents_with_session(
            session=session,
            stale_after_seconds=stale_after_seconds,
            enqueue=enqueue,
        )

    with SessionLocal() as local_session:
        result = _recover_stalled_subagents_with_session(
            session=local_session,
            stale_after_seconds=stale_after_seconds,
            enqueue=enqueue,
        )
        local_session.commit()
        return result


def _recover_stalled_subagents_with_session(
    *,
    session: Session,
    stale_after_seconds: int,
    enqueue: bool,
) -> dict:
    tasks = list(
        session.execute(
            select(Task)
            .join(AgentRun, AgentRun.task_id == Task.id)
            .where(
                AgentRun.agent_type == "subagent",
                AgentRun.status.in_(["PENDING", "RUNNING"]),
            )
            .distinct()
        ).scalars()
    )
    recovered_by_task = []
    recovered_total = 0
    for task in tasks:
        replay_sequence, recovered = SubagentManager(session).recover_for_task(
            task=task,
            stale_after_seconds=stale_after_seconds,
            enqueue=enqueue,
        )
        if not recovered:
            continue
        recovered_total += len(recovered)
        recovered_by_task.append(
            {
                "task_id": task.id,
                "replay_sequence": replay_sequence,
                "recovered": recovered,
            }
        )
    session.flush()
    agent_subagent_recovery_sweeps_total.inc()
    agent_subagent_recovery_last_recovered.set(recovered_total)
    return {
        "task_count": len(tasks),
        "recovered_count": recovered_total,
        "recovered_by_task": recovered_by_task,
    }


@dramatiq.actor(
    broker=broker,
    max_retries=0,
    queue_name="subagents",
)
def recover_stalled_subagents_actor(
    stale_after_seconds: int = DEFAULT_RECOVERY_STALE_AFTER_SECONDS,
    enqueue: bool = DEFAULT_RECOVERY_ENQUEUE,
) -> None:
    recover_stalled_subagents(
        stale_after_seconds=stale_after_seconds,
        enqueue=enqueue,
    )


def run_subagent_recovery_service(
    *,
    stale_after_seconds: int = DEFAULT_RECOVERY_STALE_AFTER_SECONDS,
    interval_seconds: int = DEFAULT_RECOVERY_INTERVAL_SECONDS,
    enqueue: bool = DEFAULT_RECOVERY_ENQUEUE,
) -> None:
    running = True

    def stop(_signum, _frame) -> None:
        nonlocal running
        running = False

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)

    while running:
        recover_stalled_subagents(
            stale_after_seconds=stale_after_seconds,
            enqueue=enqueue,
        )
        time.sleep(interval_seconds)


if __name__ == "__main__":
    run_subagent_recovery_service()
