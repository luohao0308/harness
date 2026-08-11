import os
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.agents.plan_steps import sync_subagent_plan_step
from app.agents.specialists import (
    MAX_SPECIALIST_DEPTH,
    SpecialistValidationError,
    SubagentDepthExceededError,
    budget_consumed_for_run,
    normalize_budget,
    output_schema_sha256,
)
from app.agents.subagent_timing import DEFAULT_SUBAGENT_TIMEOUT_SECONDS, timeout_at_from_now
from app.db.models import AgentRun, SubagentOutput, SubagentSpecialist, Task, utc_now
from app.events.event_store import EventStore
from app.events.event_types import EventType
from app.events.replay import EventReplay
from app.observability.metrics import agent_subagent_recovery_total, agent_subagents_queued
from app.observability.tracing import traced_operation

SUBAGENT_CONCURRENCY_LIMIT = 5
MAX_FANOUT_PER_STEP = 5
MAX_DYNAMIC_FANOUT = 10
MAX_DYNAMIC_FANOUT_EXTENDS_PER_BATCH = 3
MAX_DYNAMIC_FANOUT_EXTENDS_PER_SUBAGENT = 1


class SubagentLimitExceededError(RuntimeError):
    pass


class FanoutCapacityExceededError(RuntimeError):
    pass


class FanoutExtendForbiddenError(RuntimeError):
    pass


class FanoutNotRunningError(RuntimeError):
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
        specialist: SubagentSpecialist | None = None,
    ) -> AgentRun:
        if parent_agent_id is not None:
            depth = self._compute_depth(parent_agent_id)
            if depth >= MAX_SPECIALIST_DEPTH:
                self.event_store.append(
                    task_id=task.id,
                    agent_run_id=parent_agent_id,
                    event_type=EventType.SUBAGENT_DEPTH_REJECTED,
                    payload_json={
                        "parent_agent_id": parent_agent_id,
                        "depth": depth,
                        "max_depth": MAX_SPECIALIST_DEPTH,
                        "specialist_id": specialist.id if specialist is not None else None,
                        "specialist_slug": specialist.slug if specialist is not None else None,
                    },
                )
                self.session.flush()
                raise SubagentDepthExceededError(
                    f"depth {depth} >= {MAX_SPECIALIST_DEPTH}"
                )
        with traced_operation(
            self.session,
            "subagent_spawn",
            task_id=task.id,
            agent_run_id=parent_agent_id,
            kind="producer" if enqueue else "internal",
            attributes={
                "specialist_id": specialist.id if specialist is not None else None,
                "specialist_slug": specialist.slug if specialist is not None else None,
                "enqueue": enqueue,
            },
        ):
            running_or_pending = self.session.execute(
                select(func.count(AgentRun.id)).where(
                    AgentRun.task_id == task.id,
                    AgentRun.agent_type == "subagent",
                    AgentRun.status.in_(["PENDING", "RUNNING"]),
                )
            ).scalar_one()
            if running_or_pending >= SUBAGENT_CONCURRENCY_LIMIT:
                raise SubagentLimitExceededError("Subagent concurrency limit reached")

            runtime_budget = (
                normalize_budget(specialist.budget_json) if specialist is not None else None
            )
            effective_timeout_seconds = (
                int(runtime_budget.get("max_runtime_seconds") or timeout_seconds)
                if runtime_budget is not None
                else timeout_seconds
            )
            context_json = dict(assignment)
            if specialist is not None:
                context_json = {
                    **context_json,
                    "specialist_id": specialist.id,
                    "specialist_slug": specialist.slug,
                    "specialist_role": specialist.role,
                    "system_prompt_override": specialist.system_prompt,
                    "capability_whitelist": list(specialist.capability_slugs_json or []),
                    "output_schema": specialist.output_schema_json,
                    "output_schema_sha256": output_schema_sha256(specialist.output_schema_json),
                    "budget": runtime_budget,
                }
            agent_run = AgentRun(
                task_id=task.id,
                parent_agent_id=parent_agent_id,
                agent_type="subagent",
                status="PENDING",
                specialist_id=specialist.id if specialist is not None else None,
                context_json=context_json,
                capability_snapshot_json=task.capability_snapshot_json,
                timeout_at=timeout_at_from_now(effective_timeout_seconds),
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
                    "assignment": context_json,
                    "timeout_seconds": effective_timeout_seconds,
                    "concurrency_limit": SUBAGENT_CONCURRENCY_LIMIT,
                    "specialist": _specialist_event_payload(specialist),
                },
            )
            if enqueue:
                self._enqueue(agent_run=agent_run, task_id=task.id, stage="queued")
            return agent_run

    def spawn_fanout(
        self,
        *,
        task: Task,
        assignment: dict,
        specialists: list[SubagentSpecialist],
        aggregation: str = "synthesizer_chain",
        parent_agent_id: str | None = None,
        timeout_seconds: int = DEFAULT_SUBAGENT_TIMEOUT_SECONDS,
        enqueue: bool = False,
    ) -> tuple[str, list[AgentRun]]:
        if len(specialists) < 2:
            raise FanoutCapacityExceededError("fanout requires at least two specialists")
        if len(specialists) > MAX_FANOUT_PER_STEP:
            raise FanoutCapacityExceededError(
                f"fanout size {len(specialists)} exceeds max {MAX_FANOUT_PER_STEP}"
            )
        running_or_pending = self.session.execute(
            select(func.count(AgentRun.id)).where(
                AgentRun.task_id == task.id,
                AgentRun.agent_type == "subagent",
                AgentRun.status.in_(["PENDING", "RUNNING"]),
            )
        ).scalar_one()
        if running_or_pending + len(specialists) > SUBAGENT_CONCURRENCY_LIMIT:
            raise FanoutCapacityExceededError("fanout exceeds subagent concurrency capacity")
        batch_id = f"fanout-{uuid4()}"
        total = len(specialists)
        runs: list[AgentRun] = []
        for index, specialist in enumerate(specialists):
            run = self.spawn(
                task=task,
                assignment={
                    **assignment,
                    "fanout_batch_id": batch_id,
                    "fanout_index": index,
                    "fanout_total": total,
                    "fanout_aggregation": aggregation,
                    "fanout_specialist_slug": specialist.slug,
                },
                parent_agent_id=parent_agent_id,
                timeout_seconds=timeout_seconds,
                enqueue=enqueue,
                specialist=specialist,
            )
            runs.append(run)
        return batch_id, runs

    def extend_fanout(
        self,
        *,
        batch_id: str,
        additional_specialists: list[SubagentSpecialist],
        requested_by_agent_run_id: str,
        reason: str,
        timeout_seconds: int = DEFAULT_SUBAGENT_TIMEOUT_SECONDS,
        enqueue: bool = False,
    ) -> list[AgentRun]:
        requester = self.session.get(AgentRun, requested_by_agent_run_id)
        if requester is None or requester.agent_type != "subagent":
            raise FanoutExtendForbiddenError("requester must be an existing subagent")
        if requester.context_json.get("fanout_batch_id") != batch_id:
            raise FanoutExtendForbiddenError("requester is not in the target fanout batch")
        members = self._fanout_members(batch_id=batch_id, task_id=requester.task_id)
        if not members:
            raise FanoutExtendForbiddenError("fanout batch not found")
        if any(member.task_id != requester.task_id for member in members):
            raise FanoutExtendForbiddenError("fanout batch crosses task boundary")
        if not any(member.status in {"PENDING", "RUNNING"} for member in members):
            raise FanoutNotRunningError("fanout batch is no longer running")
        existing_total = len(members)
        if existing_total + len(additional_specialists) > MAX_DYNAMIC_FANOUT:
            raise FanoutCapacityExceededError("dynamic fanout exceeds max batch size")
        history = self._fanout_extend_history(members)
        if len(history) >= MAX_DYNAMIC_FANOUT_EXTENDS_PER_BATCH:
            raise FanoutCapacityExceededError("fanout batch extend limit reached")
        requester_extends = sum(
            1
            for item in history
            if item.get("requested_by_agent_run_id") == requested_by_agent_run_id
        )
        if requester_extends >= MAX_DYNAMIC_FANOUT_EXTENDS_PER_SUBAGENT:
            raise FanoutCapacityExceededError("requester already extended this fanout batch")
        running_or_pending = self.session.execute(
            select(func.count(AgentRun.id)).where(
                AgentRun.task_id == requester.task_id,
                AgentRun.agent_type == "subagent",
                AgentRun.status.in_(["PENDING", "RUNNING"]),
            )
        ).scalar_one()
        if running_or_pending + len(additional_specialists) > SUBAGENT_CONCURRENCY_LIMIT:
            raise FanoutCapacityExceededError("fanout exceeds subagent concurrency capacity")

        task = self.session.get(Task, requester.task_id)
        if task is None:
            raise FanoutExtendForbiddenError("task not found")
        first = sorted(
            members,
            key=lambda run: int(run.context_json.get("fanout_index") or 0),
        )[0]
        base_assignment = self._fanout_base_assignment(first.context_json)
        extension_event = {
            "extend_index": len(history) + 1,
            "reason": reason,
            "requested_by_agent_run_id": requested_by_agent_run_id,
            "added_specialist_slugs": [specialist.slug for specialist in additional_specialists],
            "created_at": utc_now().isoformat(),
        }
        new_total = existing_total + len(additional_specialists)
        runs: list[AgentRun] = []
        for index, specialist in enumerate(additional_specialists, start=existing_total):
            run = self.spawn(
                task=task,
                assignment={
                    **base_assignment,
                    "fanout_batch_id": batch_id,
                    "fanout_index": index,
                    "fanout_total": new_total,
                    "fanout_specialist_slug": specialist.slug,
                    "dynamic_fanout_origin": batch_id,
                    "dynamic_fanout_requested_by": requested_by_agent_run_id,
                    "dynamic_fanout_reason": reason,
                    "dynamic_fanout_extend_index": len(history) + 1,
                    "fanout_extend_history": [*history, extension_event],
                },
                parent_agent_id=requester.parent_agent_id,
                timeout_seconds=timeout_seconds,
                enqueue=enqueue,
                specialist=specialist,
            )
            runs.append(run)
        for member in members:
            member.context_json = {
                **member.context_json,
                "fanout_total": new_total,
                "fanout_extend_history": [*history, extension_event],
            }
        self.event_store.append(
            task_id=requester.task_id,
            agent_run_id=requested_by_agent_run_id,
            event_type=EventType.FANOUT_EXTENDED,
            payload_json={
                "fanout_batch_id": batch_id,
                "reason": reason,
                "requested_by_agent_run_id": requested_by_agent_run_id,
                "added_agent_run_ids": [run.id for run in runs],
                "added_specialist_slugs": [
                    specialist.slug for specialist in additional_specialists
                ],
                "fanout_total": new_total,
                "extend_count": len(history) + 1,
            },
        )
        self.session.flush()
        return runs

    def finalize_with_output(
        self,
        *,
        agent_run: AgentRun,
        raw_output_dict: dict,
        budget_consumed: dict | None = None,
        budget_exceeded: list[str] | None = None,
    ) -> SubagentOutput:
        with traced_operation(
            self.session,
            "subagent_finalize",
            task_id=agent_run.task_id,
            agent_run_id=agent_run.id,
            kind="consumer",
            attributes={"specialist_id": agent_run.specialist_id},
        ):
            return self._finalize_with_output(
                agent_run=agent_run,
                raw_output_dict=raw_output_dict,
                budget_consumed=budget_consumed,
                budget_exceeded=budget_exceeded,
            )

    def _finalize_with_output(
        self,
        *,
        agent_run: AgentRun,
        raw_output_dict: dict,
        budget_consumed: dict | None = None,
        budget_exceeded: list[str] | None = None,
    ) -> SubagentOutput:
        if agent_run.subagent_output is not None:
            raise ValueError("subagent output is immutable and already exists")
        schema = agent_run.context_json.get("output_schema")
        if not isinstance(schema, dict):
            raise ValueError("subagent output schema snapshot is missing")
        try:
            _validate_output(schema=schema, output=raw_output_dict)
        except SpecialistValidationError as exc:
            agent_run.status = "FAILED"
            agent_run.completed_at = utc_now()
            agent_run.context_json = {
                **agent_run.context_json,
                "failure_reason": "output_schema_violation",
                "failure_detail": str(exc),
            }
            self.event_store.append(
                task_id=agent_run.task_id,
                agent_run_id=agent_run.id,
                event_type=EventType.SUBAGENT_FAILED,
                payload_json={
                    "agent_run_id": agent_run.id,
                    "failure_reason": "output_schema_violation",
                    "error": str(exc),
                },
            )
            sync_subagent_plan_step(session=self.session, agent_run=agent_run, summary=str(exc))
            self.session.flush()
            raise
        output = SubagentOutput(
            agent_run_id=agent_run.id,
            task_id=agent_run.task_id,
            specialist_id=agent_run.specialist_id,
            output_json=raw_output_dict,
            output_schema_sha256=str(
                agent_run.context_json.get("output_schema_sha256")
                or output_schema_sha256(schema)
            ),
            budget_consumed_json=(
                budget_consumed or budget_consumed_for_run(self.session, agent_run)
            ),
            budget_exceeded_json=budget_exceeded or [],
            written_at=utc_now(),
        )
        self.session.add(output)
        agent_run.status = "SUCCESS"
        agent_run.completed_at = utc_now()
        self.event_store.append(
            task_id=agent_run.task_id,
            agent_run_id=agent_run.id,
            event_type=EventType.SUBAGENT_COMPLETED,
            payload_json={
                "agent_run_id": agent_run.id,
                "specialist_id": agent_run.specialist_id,
                "output_id": output.id,
                "budget_consumed": output.budget_consumed_json,
                "budget_exceeded": output.budget_exceeded_json,
            },
        )
        sync_subagent_plan_step(session=self.session, agent_run=agent_run)
        self.session.flush()
        return output

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
        takeover_owner: str | None = None,
    ) -> tuple[int, list[dict], int]:
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
                        takeover_owner=takeover_owner or _default_takeover_owner(),
                    )
                )
                continue
        self.session.flush()
        return int(replay_state.get("last_sequence") or 0), recovered, len(agent_runs)

    def _enqueue(self, *, agent_run: AgentRun, task_id: str, stage: str) -> None:
        from app.runtime_jobs.profile import is_local_runtime_profile

        if is_local_runtime_profile():
            from app.runtime_jobs.repository import RuntimeJobRepository

            RuntimeJobRepository(self.session).enqueue(
                kind="subagent",
                payload={"agent_run_id": agent_run.id},
                dedupe_key=f"subagent:{agent_run.id}",
            )
            self.event_store.append(
                task_id=task_id,
                agent_run_id=agent_run.id,
                event_type=EventType.SUBAGENT_PROGRESS,
                payload_json={
                    "agent_run_id": agent_run.id,
                    "stage": stage,
                    "summary": "Subagent queued in local runtime coordinator",
                },
            )
            return

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

    def _compute_depth(self, parent_agent_id: str | None) -> int:
        depth = 0
        cursor = parent_agent_id
        while cursor and depth <= MAX_SPECIALIST_DEPTH:
            parent = self.session.get(AgentRun, cursor)
            if parent is None:
                break
            depth += 1
            cursor = parent.parent_agent_id
        return depth

    def _fanout_members(self, *, batch_id: str, task_id: str) -> list[AgentRun]:
        runs = list(
            self.session.execute(
                select(AgentRun).where(
                    AgentRun.task_id == task_id,
                    AgentRun.agent_type == "subagent",
                )
            ).scalars()
        )
        return [run for run in runs if run.context_json.get("fanout_batch_id") == batch_id]

    def _fanout_extend_history(self, members: list[AgentRun]) -> list[dict]:
        for member in members:
            history = member.context_json.get("fanout_extend_history")
            if isinstance(history, list):
                return [item for item in history if isinstance(item, dict)]
        return []

    def _fanout_base_assignment(self, context_json: dict) -> dict:
        blocked = {
            "specialist_id",
            "specialist_slug",
            "specialist_role",
            "system_prompt_override",
            "capability_whitelist",
            "output_schema",
            "output_schema_sha256",
            "budget",
        }
        return {key: value for key, value in context_json.items() if key not in blocked}

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
        takeover_owner: str,
    ) -> dict:
        previous_status = agent_run.status
        recovery_attempts = int(agent_run.context_json.get("recovery_attempts", 0) or 0) + 1
        takeover_generation = int(agent_run.context_json.get("takeover_generation", 0) or 0) + 1
        takeover_at = utc_now()
        agent_run.context_json = {
            **agent_run.context_json,
            "recovery_attempts": recovery_attempts,
            "takeover_generation": takeover_generation,
            "last_takeover_at": takeover_at.isoformat(),
            "last_takeover_owner": takeover_owner,
        }
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
                "stage": "worker_takeover",
                "from_status": previous_status,
                "to_status": agent_run.status,
                "recovery_attempts": recovery_attempts,
                "takeover_generation": takeover_generation,
                "takeover_owner": takeover_owner,
                "takeover_at": takeover_at.isoformat(),
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
            "takeover_generation": takeover_generation,
            "takeover_owner": takeover_owner,
            "takeover_at": takeover_at.isoformat(),
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


def _default_takeover_owner() -> str:
    hostname = os.getenv("HOSTNAME") or "local"
    return f"worker:{hostname}:{os.getpid()}"


def _validate_output(*, schema: dict, output: dict) -> None:
    from jsonschema import Draft7Validator, ValidationError

    try:
        Draft7Validator(schema).validate(output)
    except ValidationError as exc:
        path = ".".join(str(item) for item in exc.path)
        suffix = f" at {path}" if path else ""
        raise SpecialistValidationError(f"output_schema_violation{suffix}: {exc.message}") from exc


def _specialist_event_payload(specialist: SubagentSpecialist | None) -> dict | None:
    if specialist is None:
        return None
    return {
        "id": specialist.id,
        "slug": specialist.slug,
        "role": specialist.role,
        "display_name": specialist.display_name,
    }
