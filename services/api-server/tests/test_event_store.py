from concurrent.futures import ThreadPoolExecutor

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.db.models import Base, Task, TaskSnapshot, utc_now
from app.events.event_store import EventStore
from app.events.event_types import EventType
from app.events.replay import EventReplay


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


def test_event_store_assigns_unique_sequences_under_concurrent_writes(tmp_path) -> None:
    engine = create_engine(
        f"sqlite+pysqlite:///{tmp_path / 'events.db'}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    with SessionLocal() as session:
        task = Task(
            title="Concurrent demo",
            goal="Write events concurrently",
            status="RUNNING",
            model_provider="openai-compatible",
            model_name="default",
            max_runtime_seconds=1800,
            max_subagents=5,
            enable_sandbox=True,
            enable_network=False,
            created_at=utc_now(),
            updated_at=utc_now(),
        )
        session.add(task)
        session.commit()
        task_id = task.id

    def append_event(index: int) -> int:
        with SessionLocal() as session:
            event = EventStore(session).append(
                task_id=task_id,
                event_type=EventType.SUBAGENT_PROGRESS,
                payload_json={"index": index},
            )
            sequence = event.sequence
            session.commit()
            return sequence

    with ThreadPoolExecutor(max_workers=5) as executor:
        sequences = list(executor.map(append_event, range(10)))

    assert sorted(sequences) == list(range(1, 11))

    with SessionLocal() as session:
        replay = EventReplay(session).replay_task(task_id=task_id, sequence=5)
        assert replay.sequence == 5
        assert "sequence=5" in replay.state_summary
        events_after_reconnect = EventStore(session).list_by_task(
            task_id=task_id,
            after_sequence=5,
            limit=10,
        )
        assert [event.sequence for event in events_after_reconnect] == [6, 7, 8, 9, 10]


def test_event_store_creates_snapshot_every_100_events(db_session: Session) -> None:
    task = Task(
        title="Snapshot demo",
        goal="Write enough events",
        status="RUNNING",
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

    event_store.append(
        task_id=task.id,
        event_type=EventType.TASK_CREATED,
        payload_json={"title": task.title},
    )
    for index in range(98):
        event_store.append(
            task_id=task.id,
            event_type=EventType.SUBAGENT_PROGRESS,
            payload_json={"index": index},
        )
    event_store.append(
        task_id=task.id,
        event_type=EventType.TASK_COMPLETED,
        payload_json={"task_id": task.id},
    )

    snapshot = db_session.query(TaskSnapshot).filter(TaskSnapshot.task_id == task.id).one()
    assert snapshot.sequence == 100
    assert snapshot.state_json["status"] == "COMPLETED"
    assert snapshot.state_json["last_sequence"] == 100


def test_replay_keeps_cancelled_status_after_cancelled_model_failure(
    db_session: Session,
) -> None:
    task = Task(
        title="Cancelled model replay",
        goal="Keep cancellation terminal",
        status="CANCELLED",
        model_provider="openai-compatible",
        model_name="default",
        max_runtime_seconds=1800,
        max_subagents=0,
        enable_sandbox=False,
        enable_network=False,
        created_at=utc_now(),
        updated_at=utc_now(),
    )
    db_session.add(task)
    db_session.flush()
    store = EventStore(db_session)
    store.append(task_id=task.id, event_type=EventType.TASK_CREATED, payload_json={})
    store.append(task_id=task.id, event_type=EventType.TASK_CANCELLED, payload_json={})
    store.append(
        task_id=task.id,
        event_type=EventType.MODEL_CALL_FAILED,
        payload_json={"model_call_id": "cancelled-call", "cancelled": True},
    )

    replay = EventReplay(db_session).replay_state_json(task_id=task.id)

    assert replay["status"] == "CANCELLED"
    assert replay["failure_point"] is None


def test_replay_projects_paused_status(db_session: Session) -> None:
    task = Task(
        title="Paused replay",
        goal="Keep pause terminal",
        status="PAUSED",
        model_provider="openai-compatible",
        model_name="default",
        max_runtime_seconds=1800,
        max_subagents=0,
        enable_sandbox=False,
        enable_network=False,
        created_at=utc_now(),
        updated_at=utc_now(),
    )
    db_session.add(task)
    db_session.flush()
    store = EventStore(db_session)
    store.append(task_id=task.id, event_type=EventType.TASK_CREATED, payload_json={})
    store.append(task_id=task.id, event_type=EventType.TASK_PAUSED, payload_json={})

    replay = EventReplay(db_session).replay_state_json(task_id=task.id)

    assert replay["status"] == "PAUSED"


def test_replay_tracks_multi_agent_assignments_handoffs_and_reduce(
    db_session: Session,
) -> None:
    task = Task(
        title="Multi-agent replay",
        goal="Replay assignments",
        status="RUNNING",
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

    event_store.append(
        task_id=task.id,
        event_type=EventType.AGENT_ASSIGNMENT_CREATED,
        payload_json={
            "assignment_id": "assignment-researcher",
            "agent_id": "researcher",
            "role": "researcher",
        },
    )
    event_store.append(
        task_id=task.id,
        event_type=EventType.AGENT_ASSIGNMENT_QUEUED,
        payload_json={
            "assignment_id": "assignment-researcher",
            "agent_id": "researcher",
        },
    )
    event_store.append(
        task_id=task.id,
        event_type=EventType.AGENT_ASSIGNMENT_STARTED,
        payload_json={
            "assignment_id": "assignment-researcher",
            "agent_id": "researcher",
        },
    )
    event_store.append(
        task_id=task.id,
        event_type=EventType.AGENT_HANDOFF_COMPLETED,
        payload_json={
            "handoff_id": "handoff-review",
            "from_assignment_id": "assignment-researcher",
            "to_assignment_id": "assignment-reviewer",
            "handoff_type": "reduce_input",
        },
    )
    event_store.append(
        task_id=task.id,
        event_type=EventType.AGENT_ASSIGNMENT_COMPLETED,
        payload_json={
            "assignment_id": "assignment-researcher",
            "agent_id": "researcher",
        },
    )
    event_store.append(
        task_id=task.id,
        event_type=EventType.AGENT_REDUCE_COMPLETED,
        payload_json={
            "reducer_assignment_id": "assignment-reviewer",
            "assignment_count": 2,
            "summary": "researcher and reviewer completed",
        },
    )

    replay_state = EventReplay(db_session).replay_state_json(task_id=task.id)

    assert replay_state["agent_assignments"]["assignment-researcher"] == {
        "status": "SUCCESS",
        "agent_id": "researcher",
        "role": "researcher",
        "sequence": 5,
    }
    assert replay_state["agent_handoffs"]["handoff-review"]["status"] == "COMPLETED"
    assert (
        replay_state["agent_handoffs"]["handoff-review"]["from_assignment_id"]
        == "assignment-researcher"
    )
    assert replay_state["agent_reduce"]["status"] == "COMPLETED"
    assert replay_state["agent_reduce"]["assignment_count"] == 2
