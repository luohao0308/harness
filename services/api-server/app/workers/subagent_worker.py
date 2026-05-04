from __future__ import annotations

import time
from datetime import timedelta

import dramatiq
from sqlalchemy.orm import Session

from app.db.models import AgentRun, utc_now
from app.db.session import SessionLocal
from app.events.event_store import EventStore
from app.events.event_types import EventType
from app.workers.broker import broker

DEFAULT_SUBAGENT_TIMEOUT_SECONDS = 900


def execute_subagent(
    agent_run_id: str,
    simulate_timeout: bool = False,
    session: Session | None = None,
) -> str:
    if session is not None:
        return _execute_subagent_with_session(
            session=session,
            agent_run_id=agent_run_id,
            simulate_timeout=simulate_timeout,
        )

    with SessionLocal() as session:
        return _execute_subagent_with_session(
            session=session,
            agent_run_id=agent_run_id,
            simulate_timeout=simulate_timeout,
        )


def _execute_subagent_with_session(
    *,
    session: Session,
    agent_run_id: str,
    simulate_timeout: bool,
) -> str:
    agent_run = session.get(AgentRun, agent_run_id)
    if agent_run is None:
        raise ValueError(f"AgentRun not found: {agent_run_id}")

    event_store = EventStore(session)
    agent_run.status = "RUNNING"
    agent_run.started_at = utc_now()
    event_store.append(
        task_id=agent_run.task_id,
        agent_run_id=agent_run.id,
        event_type=EventType.SUBAGENT_STARTED,
        payload_json={"agent_run_id": agent_run.id, "assignment": agent_run.context_json},
    )

    try:
        if simulate_timeout:
            agent_run.status = "TIMEOUT"
            agent_run.completed_at = utc_now()
            event_store.append(
                task_id=agent_run.task_id,
                agent_run_id=agent_run.id,
                event_type=EventType.SUBAGENT_TIMEOUT,
                payload_json={
                    "agent_run_id": agent_run.id,
                    "timeout_seconds": DEFAULT_SUBAGENT_TIMEOUT_SECONDS,
                },
            )
            session.commit()
            return agent_run.status

        time.sleep(0)
        agent_run.status = "SUCCESS"
        agent_run.completed_at = utc_now()
        event_store.append(
            task_id=agent_run.task_id,
            agent_run_id=agent_run.id,
            event_type=EventType.SUBAGENT_COMPLETED,
            payload_json={"agent_run_id": agent_run.id, "summary": "Subagent completed"},
        )
        session.commit()
        return agent_run.status
    except Exception:
        agent_run.status = "FAILED"
        agent_run.completed_at = utc_now()
        event_store.append(
            task_id=agent_run.task_id,
            agent_run_id=agent_run.id,
            event_type=EventType.SUBAGENT_FAILED,
            payload_json={"agent_run_id": agent_run.id},
        )
        session.commit()
        raise


@dramatiq.actor(
    broker=broker,
    max_retries=0,
    time_limit=DEFAULT_SUBAGENT_TIMEOUT_SECONDS * 1000,
    queue_name="subagents",
)
def run_subagent(agent_run_id: str) -> None:
    execute_subagent(agent_run_id)


def timeout_at_from_now(timeout_seconds: int = DEFAULT_SUBAGENT_TIMEOUT_SECONDS):
    return utc_now() + timedelta(seconds=timeout_seconds)
