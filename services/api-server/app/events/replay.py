from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import AgentEvent, TaskSnapshot
from app.events.event_store import replay_events_to_state


@dataclass(frozen=True)
class ReplayState:
    task_id: str
    sequence: int
    state_summary: str
    failure_point: dict | None
    diagnosis: str
    requires_manual_review: bool


class EventReplay:
    def __init__(self, session: Session) -> None:
        self.session = session

    def replay_task(self, *, task_id: str, sequence: int | None = None) -> ReplayState:
        state = self.replay_state_json(task_id=task_id, sequence=sequence)
        current_status = state["status"]
        failure_point = state.get("failure_point")
        last_sequence = int(state.get("last_sequence") or 0)

        effective_sequence = sequence or last_sequence
        diagnosis = "未发现失败事件。"
        requires_manual_review = False
        if failure_point is not None:
            diagnosis = "事件流中存在失败点，需要根据失败 payload 和工具审计继续定位。"
            requires_manual_review = True

        return ReplayState(
            task_id=task_id,
            sequence=effective_sequence,
            state_summary=f"任务在 sequence={effective_sequence} 的重放状态为 {current_status}。",
            failure_point=failure_point,
            diagnosis=diagnosis,
            requires_manual_review=requires_manual_review,
        )

    def replay_state_json(self, *, task_id: str, sequence: int | None = None) -> dict:
        snapshot = self._latest_snapshot(task_id=task_id, sequence=sequence)
        statement = select(AgentEvent).where(AgentEvent.task_id == task_id)
        if snapshot is not None:
            statement = statement.where(AgentEvent.sequence > snapshot.sequence)
        if sequence is not None:
            statement = statement.where(AgentEvent.sequence <= sequence)
        events = list(self.session.execute(statement.order_by(AgentEvent.sequence.asc())).scalars())

        state = replay_events_to_state(
            events=events,
            initial_state=snapshot.state_json if snapshot is not None else None,
        )
        if snapshot is not None and not events:
            state["last_sequence"] = snapshot.sequence
        return state

    def _latest_snapshot(self, *, task_id: str, sequence: int | None) -> TaskSnapshot | None:
        statement = select(TaskSnapshot).where(TaskSnapshot.task_id == task_id)
        if sequence is not None:
            statement = statement.where(TaskSnapshot.sequence <= sequence)
        return self.session.execute(
            statement.order_by(TaskSnapshot.sequence.desc()).limit(1)
        ).scalar_one_or_none()
