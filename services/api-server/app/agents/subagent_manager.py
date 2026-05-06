from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import AgentRun, Task, utc_now
from app.events.event_store import EventStore
from app.events.event_types import EventType
from app.events.replay import EventReplay
from app.observability.metrics import agent_subagent_recovery_total, agent_subagents_queued
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
            self._enqueue(agent_run=agent_run, task_id=task.id, stage="queued")
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

    def recover_for_task(
        self,
        *,
        task: Task,
        stale_after_seconds: int,
        enqueue: bool,
    ) -> tuple[int, list[dict]]:
        replay_state = EventReplay(self.session).replay_state_json(task_id=task.id)
        replay_subagents = replay_state.get("subagents", {})
        now = utc_now()
        agent_runs = list(
            self.session.execute(
                select(AgentRun)
                .where(
                    AgentRun.task_id == task.id,
                    AgentRun.agent_type == "subagent",
                    AgentRun.status.in_(["PENDING", "RUNNING"]),
                )
                .order_by(AgentRun.started_at.asc().nullsfirst(), AgentRun.id.asc())
            ).scalars()
        )
        recovered = []
        for agent_run in agent_runs:
            replay_status = replay_subagents.get(agent_run.id)
            if agent_run.status == "RUNNING" and self._is_timed_out(agent_run=agent_run, now=now):
                recovered.append(
                    self._mark_timeout(
                        agent_run=agent_run,
                        replay_status=replay_status,
                        reason="timeout_at exceeded during recovery",
                    )
                )
                continue
            if agent_run.status == "RUNNING" and self._is_stale(
                agent_run=agent_run,
                now=now,
                stale_after_seconds=stale_after_seconds,
            ):
                recovered.append(
                    self._reset_stale_running(
                        agent_run=agent_run,
                        replay_status=replay_status,
                        stale_after_seconds=stale_after_seconds,
                        enqueue=enqueue,
                    )
                )
                continue
        self.session.flush()
        return int(replay_state.get("last_sequence") or 0), recovered

    def _enqueue(self, *, agent_run: AgentRun, task_id: str, stage: str) -> None:
        from app.workers.subagent_worker import run_subagent

        try:
            run_subagent.send(agent_run.id)
            self.event_store.append(
                task_id=task_id,
                agent_run_id=agent_run.id,
                event_type=EventType.SUBAGENT_PROGRESS,
                payload_json={
                    "agent_run_id": agent_run.id,
                    "stage": stage,
                    "summary": "Subagent queued in Dramatiq",
                },
            )
        except Exception as exc:
            self.event_store.append(
                task_id=task_id,
                agent_run_id=agent_run.id,
                event_type=EventType.SUBAGENT_PROGRESS,
                payload_json={
                    "agent_run_id": agent_run.id,
                    "stage": "queue_deferred",
                    "summary": "Subagent queue unavailable; agent remains pending",
                    "error": str(exc),
                },
            )

    def _mark_timeout(
        self,
        *,
        agent_run: AgentRun,
        replay_status: str | None,
        reason: str,
    ) -> dict:
        previous_status = agent_run.status
        agent_run.status = "TIMEOUT"
        agent_run.completed_at = utc_now()
        agent_subagent_recovery_total.labels(action="marked_timeout").inc()
        self.event_store.append(
            task_id=agent_run.task_id,
            agent_run_id=agent_run.id,
            event_type=EventType.SUBAGENT_TIMEOUT,
            payload_json={"agent_run_id": agent_run.id, "reason": reason},
        )
        return {
            "id": agent_run.id,
            "previous_status": previous_status,
            "status": agent_run.status,
            "action": "marked_timeout",
            "reason": reason,
            "replay_status": replay_status,
        }

    def _reset_stale_running(
        self,
        *,
        agent_run: AgentRun,
        replay_status: str | None,
        stale_after_seconds: int,
        enqueue: bool,
    ) -> dict:
        previous_status = agent_run.status
        recovery_attempts = int(agent_run.context_json.get("recovery_attempts", 0) or 0) + 1
        agent_run.context_json = {**agent_run.context_json, "recovery_attempts": recovery_attempts}
        agent_run.status = "PENDING"
        agent_run.started_at = None
        agent_subagent_recovery_total.labels(action="reset_to_pending").inc()
        reason = f"running longer than {stale_after_seconds}s without terminal event"
        self.event_store.append(
            task_id=agent_run.task_id,
            agent_run_id=agent_run.id,
            event_type=EventType.SUBAGENT_PROGRESS,
            payload_json={
                "agent_run_id": agent_run.id,
                "stage": "worker_recovered",
                "from_status": previous_status,
                "to_status": agent_run.status,
                "recovery_attempts": recovery_attempts,
                "reason": reason,
                "replay_status": replay_status,
            },
        )
        if enqueue:
            self._enqueue(
                agent_run=agent_run,
                task_id=agent_run.task_id,
                stage="recovery_requeued",
            )
        return {
            "id": agent_run.id,
            "previous_status": previous_status,
            "status": agent_run.status,
            "action": "reset_to_pending",
            "reason": reason,
            "replay_status": replay_status,
        }

    def _is_timed_out(self, *, agent_run: AgentRun, now) -> bool:
        if agent_run.timeout_at is None:
            return False
        return agent_run.timeout_at <= _align_datetime(now=now, value=agent_run.timeout_at)

    def _is_stale(self, *, agent_run: AgentRun, now, stale_after_seconds: int) -> bool:
        if agent_run.started_at is None:
            return False
        aligned_now = _align_datetime(now=now, value=agent_run.started_at)
        return (aligned_now - agent_run.started_at).total_seconds() >= stale_after_seconds


def _align_datetime(*, now, value):
    if value.tzinfo is None:
        return now.replace(tzinfo=None)
    return now
