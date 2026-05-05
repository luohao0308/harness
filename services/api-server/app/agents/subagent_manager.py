from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import AgentRun, Task, utc_now
from app.events.event_store import EventStore
from app.events.event_types import EventType
from app.observability.metrics import agent_subagents_queued
from app.workers.subagent_worker import DEFAULT_SUBAGENT_TIMEOUT_SECONDS, timeout_at_from_now

SUBAGENT_CONCURRENCY_LIMIT = 5


class SubagentLimitExceededError(RuntimeError):
    pass


class SubagentManager:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.event_store = EventStore(session)

    def spawn(
        self,
        *,
        task: Task,
        assignment: dict,
        parent_agent_id: str | None = None,
        timeout_seconds: int = DEFAULT_SUBAGENT_TIMEOUT_SECONDS,
        enqueue: bool = False,
    ) -> AgentRun:
        running_or_pending = self.session.execute(
            select(func.count(AgentRun.id)).where(
                AgentRun.task_id == task.id,
                AgentRun.agent_type == "subagent",
                AgentRun.status.in_(["PENDING", "RUNNING"]),
            )
        ).scalar_one()
        if running_or_pending >= SUBAGENT_CONCURRENCY_LIMIT:
            raise SubagentLimitExceededError("Subagent concurrency limit reached")

        agent_run = AgentRun(
            task_id=task.id,
            parent_agent_id=parent_agent_id,
            agent_type="subagent",
            status="PENDING",
            context_json=assignment,
            timeout_at=timeout_at_from_now(timeout_seconds),
        )
        self.session.add(agent_run)
        self.session.flush()
        agent_subagents_queued.inc()
        self.event_store.append(
            task_id=task.id,
            agent_run_id=agent_run.id,
            event_type=EventType.SUBAGENT_SPAWNED,
            payload_json={
                "agent_run_id": agent_run.id,
                "assignment": assignment,
                "timeout_seconds": timeout_seconds,
                "concurrency_limit": SUBAGENT_CONCURRENCY_LIMIT,
            },
        )
        if enqueue:
            from app.workers.subagent_worker import run_subagent

            try:
                run_subagent.send(agent_run.id)
                self.event_store.append(
                    task_id=task.id,
                    agent_run_id=agent_run.id,
                    event_type=EventType.SUBAGENT_PROGRESS,
                    payload_json={
                        "agent_run_id": agent_run.id,
                        "stage": "queued",
                        "summary": "Subagent queued in Dramatiq",
                    },
                )
            except Exception as exc:
                self.event_store.append(
                    task_id=task.id,
                    agent_run_id=agent_run.id,
                    event_type=EventType.SUBAGENT_PROGRESS,
                    payload_json={
                        "agent_run_id": agent_run.id,
                        "stage": "queue_deferred",
                        "summary": "Subagent queue unavailable; agent remains pending",
                        "error": str(exc),
                    },
                )
        return agent_run

    def cancel(self, agent_run: AgentRun) -> AgentRun:
        if agent_run.status in {"SUCCESS", "FAILED", "TIMEOUT", "CANCELLED"}:
            return agent_run
        agent_run.status = "CANCELLED"
        agent_run.completed_at = utc_now()
        self.event_store.append(
            task_id=agent_run.task_id,
            agent_run_id=agent_run.id,
            event_type=EventType.SUBAGENT_CANCELLED,
            payload_json={"agent_run_id": agent_run.id},
        )
        self.session.flush()
        return agent_run
