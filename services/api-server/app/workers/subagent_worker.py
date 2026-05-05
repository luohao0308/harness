from __future__ import annotations

import time
from datetime import timedelta

import dramatiq
from sqlalchemy.orm import Session

from app.agents.model_gateway import AuditedModelGateway, ModelMessage, ModelRequest
from app.db.models import AgentRun, Task, utc_now
from app.db.session import SessionLocal
from app.events.event_store import EventStore
from app.events.event_types import EventType
from app.observability.metrics import agent_subagents_failed_total, agent_subagents_running
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
    agent_subagents_running.inc()
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
            agent_subagents_running.dec()
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

        event_store.append(
            task_id=agent_run.task_id,
            agent_run_id=agent_run.id,
            event_type=EventType.SUBAGENT_PROGRESS,
            payload_json={
                "agent_run_id": agent_run.id,
                "stage": "executing_assignment",
                "assignment": agent_run.context_json,
            },
        )
        task = session.get(Task, agent_run.task_id)
        summary = _assignment_summary(agent_run.context_json)
        if task is not None:
            response = AuditedModelGateway(
                session=session,
                task_id=agent_run.task_id,
                agent_run_id=agent_run.id,
            ).complete(
                ModelRequest(
                    model_provider=task.model_provider,
                    model_name=task.model_name,
                    messages=[
                        ModelMessage(
                            role="system",
                            content=(
                                "You are a Harness Subagent. Complete the assigned async task "
                                "and return compact JSON with summary and findings."
                            ),
                        ),
                        ModelMessage(
                            role="user",
                            content=jsonish_assignment(agent_run.context_json),
                        ),
                    ],
                )
            )
            if response.content and response.content != "{}":
                summary = response.content[:1000]
        time.sleep(0)
        agent_run.context_json = {
            **agent_run.context_json,
            "result": {
                "summary": summary,
                "completed_at": utc_now().isoformat(),
            },
        }
        agent_run.status = "SUCCESS"
        agent_run.completed_at = utc_now()
        agent_subagents_running.dec()
        event_store.append(
            task_id=agent_run.task_id,
            agent_run_id=agent_run.id,
            event_type=EventType.SUBAGENT_COMPLETED,
            payload_json={"agent_run_id": agent_run.id, "summary": summary},
        )
        session.commit()
        return agent_run.status
    except Exception:
        agent_run.status = "FAILED"
        agent_run.completed_at = utc_now()
        agent_subagents_running.dec()
        agent_subagents_failed_total.inc()
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


def jsonish_assignment(assignment: dict) -> str:
    return "\n".join(f"{key}: {value}" for key, value in assignment.items())


def _assignment_summary(assignment: dict) -> str:
    step_key = assignment.get("step_key") or "subagent_task"
    description = assignment.get("description") or assignment.get("goal") or "异步子任务"
    return f"Subagent completed {step_key}: {description}"
