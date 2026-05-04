from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.tracing import get_current_trace_id
from app.db.models import AgentEvent
from app.events.event_types import EventType


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
