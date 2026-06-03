import logging
from threading import RLock

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.tracing import get_current_trace_id
from app.db.models import AgentEvent, Task, TaskSnapshot, utc_now
from app.events.event_types import EventType

_sequence_locks: dict[str, RLock] = {}
_sequence_locks_guard = RLock()
SNAPSHOT_FREQUENCY_EVENTS = 100
logger = logging.getLogger("agent-harness.events")


def _task_sequence_lock(task_id: str) -> RLock:
    with _sequence_locks_guard:
        lock = _sequence_locks.get(task_id)
        if lock is None:
            lock = RLock()
            _sequence_locks[task_id] = lock
        return lock


class EventStore:
    def __init__(self, session: Session) -> None:
        self.session = session

    def append(
        self,
        *,
        task_id: str,
        event_type: EventType,
        payload_json: dict,
        actor_type: str = "system",
        actor_id: str | None = None,
        agent_run_id: str | None = None,
        trace_id: str | None = None,
    ) -> AgentEvent:
        with _task_sequence_lock(task_id):
            self.session.execute(
                select(Task.id).where(Task.id == task_id).with_for_update()
            ).scalar_one()
            max_sequence = self.session.execute(
                select(func.max(AgentEvent.sequence)).where(AgentEvent.task_id == task_id)
            ).scalar_one()
            event = AgentEvent(
                task_id=task_id,
                agent_run_id=agent_run_id,
                sequence=(max_sequence or 0) + 1,
                event_type=event_type.value,
                payload_json=payload_json,
                actor_type=actor_type,
                actor_id=actor_id,
                trace_id=trace_id or get_current_trace_id(),
            )
            self.session.add(event)
            self.session.flush()
            logger.info(
                event.event_type,
                extra={
                    "service": "api-server",
                    "trace_id": event.trace_id,
                    "task_id": event.task_id,
                    "agent_run_id": event.agent_run_id,
                    "event_type": event.event_type,
                },
            )
            self._maybe_create_snapshot(event)
            return event

    def list_by_task(
        self,
        *,
        task_id: str,
        after_sequence: int | None = None,
        limit: int = 100,
    ) -> list[AgentEvent]:
        statement = select(AgentEvent).where(AgentEvent.task_id == task_id)
        if after_sequence is not None:
            statement = statement.where(AgentEvent.sequence > after_sequence)
        statement = statement.order_by(AgentEvent.sequence.asc()).limit(limit)
        return list(self.session.execute(statement).scalars())

    def _maybe_create_snapshot(self, event: AgentEvent) -> None:
        if event.sequence % SNAPSHOT_FREQUENCY_EVENTS != 0:
            return
        events = list(
            self.session.execute(
                select(AgentEvent)
                .where(AgentEvent.task_id == event.task_id, AgentEvent.sequence <= event.sequence)
                .order_by(AgentEvent.sequence.asc())
            ).scalars()
        )
        state = replay_events_to_state(events=events, initial_state=None)
        self.session.add(
            TaskSnapshot(
                task_id=event.task_id,
                sequence=event.sequence,
                state_json=state,
                created_at=utc_now(),
            )
        )
        self.session.flush()


def replay_events_to_state(
    *,
    events: list[AgentEvent],
    initial_state: dict | None,
) -> dict:
    state = {
        "status": "UNKNOWN",
        "completed_steps": [],
        "failed_steps": [],
        "tool_calls": [],
        "model_calls": [],
        "subagents": {},
        "agent_assignments": {},
        "agent_handoffs": {},
        "agent_reduce": {},
        "sandboxes": {},
        "langgraph_events": [],
        "failure_point": None,
        "last_sequence": 0,
    }
    if initial_state is not None:
        state.update(initial_state)
        state["completed_steps"] = list(initial_state.get("completed_steps", []))
        state["failed_steps"] = list(initial_state.get("failed_steps", []))
        state["tool_calls"] = list(initial_state.get("tool_calls", []))
        state["model_calls"] = list(initial_state.get("model_calls", []))
        state["subagents"] = dict(initial_state.get("subagents", {}))
        state["agent_assignments"] = dict(initial_state.get("agent_assignments", {}))
        state["agent_handoffs"] = dict(initial_state.get("agent_handoffs", {}))
        state["agent_reduce"] = dict(initial_state.get("agent_reduce", {}))
        state["sandboxes"] = dict(initial_state.get("sandboxes", {}))
        state["langgraph_events"] = list(initial_state.get("langgraph_events", []))

    for event in events:
        state["last_sequence"] = event.sequence
        payload = event.payload_json
        if event.event_type == EventType.TASK_CREATED.value:
            state["status"] = "CREATED"
        elif event.event_type == EventType.PLAN_REQUESTED.value:
            state["status"] = "PLANNING"
        elif event.event_type == EventType.TASK_RESUMED.value:
            state["status"] = "RUNNING"
            state["failure_point"] = None
        elif event.event_type == EventType.TASK_CANCELLED.value:
            state["status"] = "CANCELLED"
        elif event.event_type == EventType.TASK_COMPLETED.value:
            state["status"] = "COMPLETED"
        elif event.event_type in {
            EventType.TASK_FAILED.value,
            EventType.STEP_FAILED.value,
            EventType.TOOL_FAILED.value,
            EventType.MODEL_CALL_FAILED.value,
            EventType.TOOL_DENIED_BY_POLICY.value,
            EventType.LANGGRAPH_WORKFLOW_FAILED.value,
            EventType.LANGGRAPH_NODE_FAILED.value,
            EventType.LANGGRAPH_TOOL_NODE_DENIED.value,
        }:
            state["status"] = "FAILED"
            state["failure_point"] = {
                "sequence": event.sequence,
                "event_type": event.event_type,
                "payload": payload,
            }

        if event.event_type == EventType.STEP_STARTED.value:
            state["current_step"] = payload.get("step_key")
            if state["status"] not in {"FAILED", "CANCELLED", "COMPLETED"}:
                state["status"] = "RUNNING"
        if event.event_type == EventType.STEP_RETRIED.value:
            step_key = payload.get("step_key")
            state["current_step"] = step_key
            state["status"] = "RUNNING"
            if step_key in state["failed_steps"]:
                state["failed_steps"].remove(step_key)
            state["failure_point"] = None
        if event.event_type == EventType.STEP_COMPLETED.value:
            step_key = payload.get("step_key")
            if step_key is not None and step_key not in state["completed_steps"]:
                state["completed_steps"].append(step_key)
            if step_key in state["failed_steps"]:
                state["failed_steps"].remove(step_key)
            if (
                isinstance(state.get("failure_point"), dict)
                and state["failure_point"].get("payload", {}).get("step_key") == step_key
            ):
                state["failure_point"] = None
            state.pop("current_step", None)
        if event.event_type == EventType.STEP_FAILED.value:
            step_key = payload.get("step_key")
            if step_key is not None and step_key not in state["failed_steps"]:
                state["failed_steps"].append(step_key)
        if event.event_type in {
            EventType.MODEL_CALLED.value,
            EventType.MODEL_RESPONSE_RECEIVED.value,
            EventType.MODEL_CALL_FAILED.value,
            EventType.MODEL_FALLBACK_USED.value,
        }:
            model_call_id = payload.get("model_call_id")
            if model_call_id is not None and model_call_id not in state["model_calls"]:
                state["model_calls"].append(model_call_id)
        if event.event_type in {
            EventType.TOOL_CALLED.value,
            EventType.TOOL_RESULT_RECEIVED.value,
            EventType.TOOL_FAILED.value,
            EventType.TOOL_TIMEOUT.value,
            EventType.TOOL_DENIED_BY_POLICY.value,
        }:
            tool_call_id = payload.get("tool_call_id")
            if tool_call_id is not None and tool_call_id not in state["tool_calls"]:
                state["tool_calls"].append(tool_call_id)
        if event.event_type.startswith("LANGGRAPH_"):
            state["langgraph_events"].append(
                {
                    "sequence": event.sequence,
                    "event_type": event.event_type,
                    "step_key": payload.get("step_key"),
                    "node_key": payload.get("node_key"),
                    "graph_id": payload.get("graph_id"),
                    "status": payload.get("status"),
                    "payload": payload,
                }
            )
        if event.event_type in {
            EventType.SUBAGENT_SPAWNED.value,
            EventType.SUBAGENT_STARTED.value,
            EventType.SUBAGENT_COMPLETED.value,
            EventType.SUBAGENT_FAILED.value,
            EventType.SUBAGENT_TIMEOUT.value,
            EventType.SUBAGENT_CANCELLED.value,
            EventType.SUBAGENT_DEPTH_REJECTED.value,
        }:
            agent_run_id = payload.get("agent_run_id") or payload.get("parent_agent_id")
            if agent_run_id is not None:
                state["subagents"][agent_run_id] = event.event_type.removeprefix("SUBAGENT_")
        if event.event_type in {
            EventType.AGENT_ASSIGNMENT_CREATED.value,
            EventType.AGENT_ASSIGNMENT_QUEUED.value,
            EventType.AGENT_ASSIGNMENT_STARTED.value,
            EventType.AGENT_ASSIGNMENT_COMPLETED.value,
            EventType.AGENT_ASSIGNMENT_FAILED.value,
            EventType.AGENT_PARALLEL_BRANCH_COMPLETED.value,
        }:
            assignment_id = payload.get("assignment_id")
            if assignment_id is not None:
                current_assignment = state["agent_assignments"].get(assignment_id, {})
                state["agent_assignments"][assignment_id] = {
                    **current_assignment,
                    "status": _agent_assignment_replay_status(event.event_type),
                    "agent_id": payload.get("agent_id") or current_assignment.get("agent_id"),
                    "role": payload.get("role") or current_assignment.get("role"),
                    "sequence": event.sequence,
                }
        if event.event_type in {
            EventType.AGENT_HANDOFF_STARTED.value,
            EventType.AGENT_HANDOFF_COMPLETED.value,
        }:
            handoff_id = payload.get("handoff_id")
            if handoff_id is not None:
                current_handoff = state["agent_handoffs"].get(handoff_id, {})
                state["agent_handoffs"][handoff_id] = {
                    **current_handoff,
                    "status": event.event_type.removeprefix("AGENT_HANDOFF_"),
                    "from_assignment_id": payload.get("from_assignment_id")
                    or current_handoff.get("from_assignment_id"),
                    "to_assignment_id": payload.get("to_assignment_id")
                    or current_handoff.get("to_assignment_id"),
                    "handoff_type": payload.get("handoff_type")
                    or current_handoff.get("handoff_type"),
                    "sequence": event.sequence,
                }
        if event.event_type in {
            EventType.AGENT_REDUCE_STARTED.value,
            EventType.AGENT_REDUCE_COMPLETED.value,
        }:
            state["agent_reduce"] = {
                "status": event.event_type.removeprefix("AGENT_REDUCE_"),
                "reducer_assignment_id": payload.get("reducer_assignment_id"),
                "assignment_count": payload.get("assignment_count"),
                "summary": payload.get("summary"),
                "sequence": event.sequence,
            }
        if event.event_type in {
            EventType.SANDBOX_ALLOCATED.value,
            EventType.SANDBOX_RELEASED.value,
            EventType.SANDBOX_DESTROYED.value,
        }:
            sandbox_id = payload.get("sandbox_id")
            if sandbox_id is not None:
                state["sandboxes"][sandbox_id] = event.event_type.removeprefix("SANDBOX_")

    return state


def _agent_assignment_replay_status(event_type: str) -> str:
    status_map = {
        EventType.AGENT_ASSIGNMENT_CREATED.value: "PENDING",
        EventType.AGENT_ASSIGNMENT_QUEUED.value: "QUEUED",
        EventType.AGENT_ASSIGNMENT_STARTED.value: "RUNNING",
        EventType.AGENT_ASSIGNMENT_COMPLETED.value: "SUCCESS",
        EventType.AGENT_ASSIGNMENT_FAILED.value: "FAILED",
        EventType.AGENT_PARALLEL_BRANCH_COMPLETED.value: "SUCCESS",
    }
    return status_map[event_type]
