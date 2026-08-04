from __future__ import annotations

import logging
import os
import signal
import time
from collections.abc import Iterator
from concurrent.futures import ProcessPoolExecutor, TimeoutError
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from threading import Lock
from uuid import uuid4

from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings
from app.db.models import Team, TeamAgent, TeamGoal, TeamMailboxMessage, TeamTask, utc_now
from app.db.session import SessionLocal
from app.teams.goal_supervisor import AUTO_SUPERVISED_GOAL_STATUSES, normalize_goal_json
from app.teams.model_runtime import TeamModelRuntime
from app.teams.service import WAKE_TIMEOUT_SECONDS, TeamSessionService

DEFAULT_TEAM_RUNTIME_INTERVAL_SECONDS = 5
DEFAULT_TEAM_RUNTIME_MAX_GOALS = 20
DEFAULT_TEAM_RUNTIME_MAX_WAKES_PER_TICK = 4
DEFAULT_TEAM_RUNTIME_WORKER_POOL_SIZE = 2
DEFAULT_TEAM_RUNTIME_WORKER_TIMEOUT_SECONDS = 300
TEAM_RUNTIME_ADVISORY_LOCK_KEY = 830_202_624
_sqlite_team_runtime_lock = Lock()
WAKE_TIMEOUT_DELTA = timedelta(seconds=WAKE_TIMEOUT_SECONDS)
logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class TeamWakeExecutionRequest:
    organization_id: str
    team_id: str
    slot_id: str
    actor_id: str
    team_goal_id: str
    reason: str
    database_url: str | None = None


class TeamWakeExecutionBackend:
    requires_committed_state = False

    def execute_wakes(self, requests: list[TeamWakeExecutionRequest]) -> list[dict]:
        raise NotImplementedError


class InlineTeamWakeExecutionBackend(TeamWakeExecutionBackend):
    def __init__(self, *, service: TeamSessionService) -> None:
        self.service = service

    def execute_wakes(self, requests: list[TeamWakeExecutionRequest]) -> list[dict]:
        results: list[dict] = []
        for request in requests:
            self.service.wake_agent(team_id=request.team_id, slot_id=request.slot_id)
            results.append(
                {
                    "team_id": request.team_id,
                    "slot_id": request.slot_id,
                    "status": "completed",
                }
            )
        return results


class ProcessPoolTeamWakeExecutionBackend(TeamWakeExecutionBackend):
    requires_committed_state = True

    def __init__(
        self,
        *,
        max_workers: int = DEFAULT_TEAM_RUNTIME_WORKER_POOL_SIZE,
        timeout_seconds: int = DEFAULT_TEAM_RUNTIME_WORKER_TIMEOUT_SECONDS,
    ) -> None:
        self.max_workers = max(1, int(max_workers))
        self.timeout_seconds = max(1, int(timeout_seconds))
        self._executor = ProcessPoolExecutor(max_workers=self.max_workers)

    def execute_wakes(self, requests: list[TeamWakeExecutionRequest]) -> list[dict]:
        if not requests:
            return []
        futures = [
            self._executor.submit(_execute_team_wake_in_child_process, request)
            for request in requests
        ]
        results: list[dict] = []
        for request, future in zip(requests, futures, strict=True):
            try:
                results.append(future.result(timeout=self.timeout_seconds))
            except TimeoutError:
                future.cancel()
                results.append(
                    {
                        "team_id": request.team_id,
                        "slot_id": request.slot_id,
                        "status": "failed",
                        "error": "team runtime worker process timed out",
                    }
                )
            except Exception as exc:
                results.append(
                    {
                        "team_id": request.team_id,
                        "slot_id": request.slot_id,
                        "status": "failed",
                        "error": str(exc)[:200],
                    }
                )
        return results

    def shutdown(self) -> None:
        self._executor.shutdown(wait=True, cancel_futures=True)


def _execute_team_wake_in_child_process(request: TeamWakeExecutionRequest) -> dict:
    database_url = request.database_url or get_settings().database_url
    connect_args = {"check_same_thread": False} if database_url.startswith("sqlite") else {}
    engine = create_engine(database_url, pool_pre_ping=True, connect_args=connect_args)
    LocalSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    try:
        with LocalSession() as session:
            service = TeamSessionService(
                session=session,
                organization_id=request.organization_id,
                actor_id=request.actor_id,
            )
            service.wake_agent(team_id=request.team_id, slot_id=request.slot_id)
            session.commit()
        return {
            "team_id": request.team_id,
            "slot_id": request.slot_id,
            "status": "completed",
            "worker_pid": os.getpid(),
        }
    finally:
        engine.dispose()


def tick_active_team_goals(
    *,
    session: Session | None = None,
    model_runtime: TeamModelRuntime | None = None,
    wake_backend: TeamWakeExecutionBackend | None = None,
    actor_id: str = "team_runtime_worker",
    max_goals: int = DEFAULT_TEAM_RUNTIME_MAX_GOALS,
    max_wakes_per_tick: int = DEFAULT_TEAM_RUNTIME_MAX_WAKES_PER_TICK,
) -> dict:
    if session is not None:
        return _tick_active_team_goals_with_session(
            session=session,
            model_runtime=model_runtime,
            wake_backend=wake_backend,
            actor_id=actor_id,
            max_goals=max_goals,
            max_wakes_per_tick=max_wakes_per_tick,
        )
    with SessionLocal() as local_session:
        result = _tick_active_team_goals_with_session(
            session=local_session,
            model_runtime=model_runtime,
            wake_backend=wake_backend,
            actor_id=actor_id,
            max_goals=max_goals,
            max_wakes_per_tick=max_wakes_per_tick,
        )
        local_session.commit()
        return result


def _tick_active_team_goals_with_session(
    *,
    session: Session,
    model_runtime: TeamModelRuntime | None,
    wake_backend: TeamWakeExecutionBackend | None,
    actor_id: str,
    max_goals: int,
    max_wakes_per_tick: int,
) -> dict:
    batch_id = f"team-runtime-{uuid4()}"
    with _team_runtime_lease(session) as lease_acquired:
        if not lease_acquired:
            return {
                "batch_id": batch_id,
                "lock_acquired": False,
                "scanned_goal_count": 0,
                "woke_agent_count": 0,
                "decisions": [],
                "completed_at": datetime.now(UTC).isoformat(),
            }

        goals = list(
            session.execute(
                select(TeamGoal)
                .where(TeamGoal.status.in_(tuple(AUTO_SUPERVISED_GOAL_STATUSES)))
                .order_by(TeamGoal.updated_at.asc(), TeamGoal.created_at.asc(), TeamGoal.id.asc())
                .limit(max_goals)
            ).scalars()
        )
        decisions: list[dict] = []
        woke_agent_count = 0
        for goal in goals:
            if woke_agent_count >= max_wakes_per_tick:
                break
            normalize_goal_json(goal)
            service = TeamSessionService(
                session=session,
                organization_id=goal.organization_id,
                actor_id=actor_id,
                model_runtime=model_runtime,
            )
            coordinator = TeamRuntimeCoordinator(
                service=service,
                actor_id=actor_id,
                wake_backend=wake_backend or InlineTeamWakeExecutionBackend(service=service),
            )
            remaining_wakes = max(max_wakes_per_tick - woke_agent_count, 0)
            decision = coordinator.tick_goal(goal=goal, max_wakes=remaining_wakes)
            woke_agent_count += int(decision.get("woke_agent_count") or 0)
            decisions.append(decision)

        return {
            "batch_id": batch_id,
            "lock_acquired": True,
            "scanned_goal_count": len(goals),
            "woke_agent_count": woke_agent_count,
            "decisions": decisions,
            "completed_at": datetime.now(UTC).isoformat(),
        }


class TeamRuntimeCoordinator:
    def __init__(
        self,
        *,
        service: TeamSessionService,
        actor_id: str,
        wake_backend: TeamWakeExecutionBackend,
    ) -> None:
        self.service = service
        self.actor_id = actor_id
        self.wake_backend = wake_backend

    def tick_goal(self, *, goal: TeamGoal, max_wakes: int) -> dict:
        team = self.service.get_team(goal.team_id)
        normalize_goal_json(goal)
        started_at = utc_now()
        self.service.append_event(
            team_id=team.id,
            event_type="TEAM_RUNTIME_TICK",
            payload={
                "team_goal_id": goal.id,
                "status": "started",
                "started_at": started_at.isoformat(),
            },
            actor_type="system",
            actor_id=self.actor_id,
        )
        actions: list[dict] = []
        if team.status != "ACTIVE":
            actions.append({"type": "skip", "reason": "team_not_active"})
        elif max_wakes <= 0:
            actions.append({"type": "skip", "reason": "wake_budget_exhausted"})
        else:
            actions = self._decide_actions(team=team, goal=goal, max_wakes=max_wakes)

        woke_agent_count = self._execute_wake_actions(team=team, goal=goal, actions=actions)

        goal.progress_json = self.service.goal_supervisor.reconcile_progress(goal=goal)
        decision = {
            "team_id": team.id,
            "team_goal_id": goal.id,
            "actions": actions,
            "woke_agent_count": woke_agent_count,
            "completed_at": utc_now().isoformat(),
        }
        self.service.append_event(
            team_id=team.id,
            event_type="TEAM_RUNTIME_DECISION",
            payload=decision,
            actor_type="system",
            actor_id=self.actor_id,
        )
        return decision

    def _execute_wake_actions(
        self,
        *,
        team: Team,
        goal: TeamGoal,
        actions: list[dict],
    ) -> int:
        wake_actions = [action for action in actions if action.get("type") == "wake_agent"]
        requests: list[TeamWakeExecutionRequest] = []
        action_by_key: dict[tuple[str, str], dict] = {}
        settings = get_settings()
        for action in wake_actions:
            slot_id = str(action.get("slot_id") or "")
            reason = str(action.get("reason") or "runtime_wake")
            if not slot_id:
                continue
            request = TeamWakeExecutionRequest(
                organization_id=goal.organization_id,
                team_id=team.id,
                slot_id=slot_id,
                actor_id=self.actor_id,
                team_goal_id=goal.id,
                reason=reason,
                database_url=settings.database_url,
            )
            requests.append(request)
            action_by_key[(slot_id, reason)] = action

        if not requests:
            return 0
        if getattr(self.wake_backend, "requires_committed_state", False):
            self.service.session.commit()
        results = self.wake_backend.execute_wakes(requests)
        woke_agent_count = 0
        for request, result in zip(requests, results, strict=False):
            action = action_by_key.get((request.slot_id, request.reason))
            if action is None:
                continue
            action["status"] = str(result.get("status") or "failed")
            if not isinstance(self.wake_backend, InlineTeamWakeExecutionBackend):
                action["backend"] = self.wake_backend.__class__.__name__
            for key in ("worker_pid", "error"):
                if key in result:
                    action[key] = result[key]
            if action["status"] in {"completed", "queued"}:
                woke_agent_count += 1
                continue
            self.service.append_event(
                team_id=team.id,
                event_type="TEAM_RUNTIME_WAKE_FAILED",
                payload={
                    "team_goal_id": goal.id,
                    "slot_id": request.slot_id,
                    "error": str(action.get("error") or "team runtime wake failed")[:200],
                },
                actor_type="system",
                actor_id=self.actor_id,
            )
        return woke_agent_count

    def _decide_actions(self, *, team: Team, goal: TeamGoal, max_wakes: int) -> list[dict]:
        stale_action = self._stale_wake_action(team=team, goal=goal)
        if stale_action is not None:
            return [stale_action]

        wake_slots: list[tuple[str, str]] = []
        unread_slot = self._first_unread_recipient(team=team)
        if unread_slot:
            wake_slots.append((unread_slot, "unread_mailbox"))

        assigned_slot = self._first_open_task_owner(team=team)
        if assigned_slot and assigned_slot not in {slot for slot, _reason in wake_slots}:
            wake_slots.append((assigned_slot, "open_assigned_task"))

        if not wake_slots:
            bootstrapped = self._ensure_goal_bootstrap_message(team=team, goal=goal)
            if bootstrapped:
                wake_slots.append((team.leader_slot_id, "goal_bootstrap"))

        if not wake_slots:
            return [{"type": "wait", "reason": "no_runnable_agent"}]

        return [
            {"type": "wake_agent", "slot_id": slot_id, "reason": reason}
            for slot_id, reason in wake_slots[:max_wakes]
        ]

    def _stale_wake_action(self, *, team: Team, goal: TeamGoal) -> dict | None:
        for agent in self.service._agents(team.id):
            wake_state = (agent.metadata_json or {}).get("wake")
            if not isinstance(wake_state, dict) or wake_state.get("in_progress") is not True:
                continue
            started_at = self._parse_iso_datetime(wake_state.get("started_at"))
            if started_at is None or utc_now() - started_at < WAKE_TIMEOUT_DELTA:
                continue
            self.service.report_agent_inactivity_timeout(
                team_id=team.id,
                slot_id=agent.slot_id,
                timeout_seconds=WAKE_TIMEOUT_SECONDS,
            )
            return {
                "type": "timeout_agent",
                "slot_id": agent.slot_id,
                "team_goal_id": goal.id,
                "reason": "wake_timeout",
                "status": "completed",
            }
        return None

    def _first_unread_recipient(self, *, team: Team) -> str | None:
        agents = {agent.slot_id: agent for agent in self.service._agents(team.id)}
        messages = list(
            self.service.session.execute(
                select(TeamMailboxMessage)
                .where(
                    TeamMailboxMessage.team_id == team.id,
                    TeamMailboxMessage.read.is_(False),
                )
                .order_by(TeamMailboxMessage.created_at.asc(), TeamMailboxMessage.id.asc())
            ).scalars()
        )
        for message in messages:
            agent = agents.get(message.to_agent_slot_id)
            if self._is_wakeable(agent):
                return message.to_agent_slot_id
        return None

    def _first_open_task_owner(self, *, team: Team) -> str | None:
        agents = {agent.slot_id: agent for agent in self.service._agents(team.id)}
        tasks = list(
            self.service.session.execute(
                select(TeamTask)
                .where(
                    TeamTask.team_id == team.id,
                    TeamTask.owner_slot_id.is_not(None),
                    TeamTask.status.in_(("pending", "in_progress")),
                )
                .order_by(TeamTask.updated_at.asc(), TeamTask.created_at.asc(), TeamTask.id.asc())
            ).scalars()
        )
        for task in tasks:
            if not task.owner_slot_id:
                continue
            agent = agents.get(task.owner_slot_id)
            if self._is_wakeable(agent):
                return task.owner_slot_id
        return None

    def _ensure_goal_bootstrap_message(self, *, team: Team, goal: TeamGoal) -> bool:
        state = dict(goal.supervisor_state_json or {})
        if state.get("runtime_bootstrapped_at"):
            return False
        leader = self.service.get_agent(team.id, team.leader_slot_id)
        if not self._is_wakeable(leader):
            return False
        content = self._goal_bootstrap_content(goal)
        self.service.write_message(
            team_id=team.id,
            target=leader.slot_id,
            content=content,
            from_agent_slot_id="team_runtime_worker",
            message_type="system",
            mode="goal",
            wake_recipient=False,
        )
        state["runtime_bootstrapped_at"] = utc_now().isoformat()
        goal.supervisor_state_json = state
        goal.updated_at = utc_now()
        return True

    @staticmethod
    def _goal_bootstrap_content(goal: TeamGoal) -> str:
        non_goals = ", ".join(str(item) for item in goal.non_goals_json) or "none"
        criteria = ", ".join(str(item) for item in goal.acceptance_criteria_json) or "none"
        return (
            "Autonomous team goal is active. "
            f"Objective: {goal.objective}. "
            f"Acceptance criteria: {criteria}. "
            f"Non-goals: {non_goals}. "
            "Plan the work, create tasks, assign teammates, and keep reporting progress "
            "through team tools."
        )

    @staticmethod
    def _is_wakeable(agent: TeamAgent | None) -> bool:
        if agent is None:
            return False
        if agent.status in {"completed", "failed"}:
            return False
        wake_state = (agent.metadata_json or {}).get("wake")
        return not isinstance(wake_state, dict) or wake_state.get("in_progress") is not True

    @staticmethod
    def _parse_iso_datetime(value: object) -> datetime | None:
        if not isinstance(value, str) or not value.strip():
            return None
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=UTC)
        return parsed


@contextmanager
def _team_runtime_lease(session: Session) -> Iterator[bool]:
    bind = session.get_bind()
    dialect_name = bind.dialect.name if bind is not None else ""
    if dialect_name == "postgresql":
        acquired = bool(
            session.execute(
                text("SELECT pg_try_advisory_lock(:lock_key)"),
                {"lock_key": TEAM_RUNTIME_ADVISORY_LOCK_KEY},
            ).scalar()
        )
        try:
            yield acquired
        finally:
            if acquired:
                session.execute(
                    text("SELECT pg_advisory_unlock(:lock_key)"),
                    {"lock_key": TEAM_RUNTIME_ADVISORY_LOCK_KEY},
                )
        return

    acquired = _sqlite_team_runtime_lock.acquire(blocking=False)
    try:
        yield acquired
    finally:
        if acquired:
            _sqlite_team_runtime_lock.release()


def run_team_runtime_service(
    *,
    interval_seconds: int = DEFAULT_TEAM_RUNTIME_INTERVAL_SECONDS,
    max_goals: int = DEFAULT_TEAM_RUNTIME_MAX_GOALS,
    max_wakes_per_tick: int = DEFAULT_TEAM_RUNTIME_MAX_WAKES_PER_TICK,
    execution_backend: TeamWakeExecutionBackend | None = None,
) -> None:
    running = True

    def stop(_signum, _frame) -> None:
        nonlocal running
        running = False

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)

    try:
        while running:
            try:
                tick_active_team_goals(
                    wake_backend=execution_backend,
                    max_goals=max_goals,
                    max_wakes_per_tick=max_wakes_per_tick,
                )
            except Exception:
                logger.exception(
                    "Team runtime tick failed",
                    extra={"event_type": "TEAM_RUNTIME_SERVICE_ERROR"},
                )
            time.sleep(interval_seconds)
    finally:
        if isinstance(execution_backend, ProcessPoolTeamWakeExecutionBackend):
            execution_backend.shutdown()


def build_team_wake_execution_backend_from_env() -> TeamWakeExecutionBackend | None:
    backend_name = os.getenv("TEAM_RUNTIME_EXECUTION_BACKEND", "inline").strip().lower()
    if backend_name in {"", "inline"}:
        return None
    if backend_name in {"process_pool", "process-pool", "pool"}:
        return ProcessPoolTeamWakeExecutionBackend(
            max_workers=_env_int(
                "TEAM_RUNTIME_WORKER_POOL_SIZE",
                DEFAULT_TEAM_RUNTIME_WORKER_POOL_SIZE,
            ),
            timeout_seconds=_env_int(
                "TEAM_RUNTIME_WORKER_TIMEOUT_SECONDS",
                DEFAULT_TEAM_RUNTIME_WORKER_TIMEOUT_SECONDS,
            )
        )
    raise ValueError(f"Unsupported TEAM_RUNTIME_EXECUTION_BACKEND: {backend_name}")


def _env_int(name: str, default: int) -> int:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    return int(raw_value)


if __name__ == "__main__":
    run_team_runtime_service(
        interval_seconds=_env_int(
            "TEAM_RUNTIME_INTERVAL_SECONDS",
            DEFAULT_TEAM_RUNTIME_INTERVAL_SECONDS,
        ),
        max_goals=_env_int("TEAM_RUNTIME_MAX_GOALS", DEFAULT_TEAM_RUNTIME_MAX_GOALS),
        max_wakes_per_tick=_env_int(
            "TEAM_RUNTIME_MAX_WAKES_PER_TICK",
            DEFAULT_TEAM_RUNTIME_MAX_WAKES_PER_TICK,
        ),
        execution_backend=build_team_wake_execution_backend_from_env(),
    )
