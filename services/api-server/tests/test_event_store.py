from sqlalchemy.orm import Session

from app.db.models import Task, utc_now
from app.events.event_store import EventStore
from app.events.event_types import EventType


def test_event_store_assigns_task_local_sequence(db_session: Session) -> None:
    task = Task(
        title="Demo",
        goal="Analyze project",
        status="CREATED",
        model_provider="openai-compatible",
        model_name="default",
        max_runtime_seconds=1800,
        max_subagents=5,
        enable_sandbox=True,
        enable_network=False,
        created_at=utc_now(),
        updated_at=utc_now(),
    )
    db_session.add(task)
    db_session.flush()

    event_store = EventStore(db_session)
    first = event_store.append(
        task_id=task.id,
        event_type=EventType.TASK_CREATED,
        payload_json={"title": task.title},
    )
    second = event_store.append(
        task_id=task.id,
        event_type=EventType.PLAN_REQUESTED,
        payload_json={},
    )

    events = event_store.list_by_task(task_id=task.id)

    assert first.sequence == 1
    assert second.sequence == 2
    assert [event.sequence for event in events] == [1, 2]
