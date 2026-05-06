from __future__ import annotations

import os
import signal
import time
from collections.abc import Iterator
from contextlib import contextmanager
from threading import Lock

import dramatiq
from prometheus_client import start_http_server
from sqlalchemy import select, text
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
DEFAULT_RECOVERY_METRICS_PORT = 9102
RECOVERY_ADVISORY_LOCK_KEY = 830_202_605
_sqlite_recovery_lock = Lock()


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
    with _recovery_lease(session) as lease_acquired:
        if not lease_acquired:
            agent_subagent_recovery_sweeps_total.inc()
            agent_subagent_recovery_last_recovered.set(0)
            return {
                "lock_acquired": False,
                "task_count": 0,
                "recovered_count": 0,
                "recovered_by_task": [],
            }
        return _recover_stalled_subagents_after_lease(
            session=session,
            stale_after_seconds=stale_after_seconds,
            enqueue=enqueue,
        )


def _recover_stalled_subagents_after_lease(
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
        "lock_acquired": True,
        "task_count": len(tasks),
        "recovered_count": recovered_total,
        "recovered_by_task": recovered_by_task,
    }


@contextmanager
def _recovery_lease(session: Session) -> Iterator[bool]:
    bind = session.get_bind()
    dialect_name = bind.dialect.name if bind is not None else ""
    if dialect_name == "postgresql":
        acquired = bool(
            session.execute(
                text("SELECT pg_try_advisory_lock(:lock_key)"),
                {"lock_key": RECOVERY_ADVISORY_LOCK_KEY},
            ).scalar()
        )
        try:
            yield acquired
        finally:
            if acquired:
                session.execute(
                    text("SELECT pg_advisory_unlock(:lock_key)"),
                    {"lock_key": RECOVERY_ADVISORY_LOCK_KEY},
                )
        return

    acquired = _sqlite_recovery_lock.acquire(blocking=False)
    try:
        yield acquired
    finally:
        if acquired:
            _sqlite_recovery_lock.release()


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
    metrics_port: int = DEFAULT_RECOVERY_METRICS_PORT,
) -> None:
    running = True

    def stop(_signum, _frame) -> None:
        nonlocal running
        running = False

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)

    if metrics_port > 0:
        start_http_server(metrics_port)

    while running:
        recover_stalled_subagents(
            stale_after_seconds=stale_after_seconds,
            enqueue=enqueue,
        )
        time.sleep(interval_seconds)


def _env_int(name: str, default: int) -> int:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    return int(raw_value)


if __name__ == "__main__":
    run_subagent_recovery_service(
        stale_after_seconds=_env_int(
            "SUBAGENT_RECOVERY_STALE_AFTER_SECONDS",
            DEFAULT_RECOVERY_STALE_AFTER_SECONDS,
        ),
        interval_seconds=_env_int(
            "SUBAGENT_RECOVERY_INTERVAL_SECONDS",
            DEFAULT_RECOVERY_INTERVAL_SECONDS,
        ),
        metrics_port=_env_int(
            "SUBAGENT_RECOVERY_METRICS_PORT",
            DEFAULT_RECOVERY_METRICS_PORT,
        ),
    )
