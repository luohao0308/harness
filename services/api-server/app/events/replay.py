from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import AgentEvent, TaskSnapshot


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
        statement = select(AgentEvent).where(AgentEvent.task_id == task_id)
        if sequence is not None:
            statement = statement.where(AgentEvent.sequence <= sequence)
        events = list(self.session.execute(statement.order_by(AgentEvent.sequence.asc())).scalars())

        snapshot = self._latest_snapshot(task_id=task_id, sequence=sequence)
        current_status = snapshot.state_json.get("status") if snapshot is not None else "UNKNOWN"
        failure_point: dict | None = None
        last_sequence = 0

        for event in events:
            last_sequence = event.sequence
            if event.event_type in {"TASK_CREATED", "TASK_RESUMED"}:
                current_status = "CREATED" if event.event_type == "TASK_CREATED" else "RUNNING"
            if event.event_type == "TASK_CANCELLED":
                current_status = "CANCELLED"
            if event.event_type == "TASK_COMPLETED":
                current_status = "COMPLETED"
            if event.event_type in {"TASK_FAILED", "STEP_FAILED", "TOOL_FAILED"}:
                current_status = "FAILED"
                failure_point = {
                    "sequence": event.sequence,
                    "event_type": event.event_type,
                    "payload": event.payload_json,
                }

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

    def _latest_snapshot(self, *, task_id: str, sequence: int | None) -> TaskSnapshot | None:
        statement = select(TaskSnapshot).where(TaskSnapshot.task_id == task_id)
        if sequence is not None:
            statement = statement.where(TaskSnapshot.sequence <= sequence)
        return self.session.execute(
            statement.order_by(TaskSnapshot.sequence.desc()).limit(1)
        ).scalar_one_or_none()
