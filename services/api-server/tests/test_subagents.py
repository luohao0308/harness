from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.agents.subagent_manager import SUBAGENT_CONCURRENCY_LIMIT, SubagentManager
from app.db.models import AgentRun, Task, utc_now
from app.events.event_store import EventStore
from app.main import app
from app.workers.subagent_worker import DEFAULT_SUBAGENT_TIMEOUT_SECONDS, execute_subagent


def create_task(db_session: Session) -> Task:
    task = Task(
        title="Demo",
        goal="Analyze project",
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
    return task


def test_spawn_creates_pending_agent_run_and_event(db_session: Session) -> None:
    task = create_task(db_session)

    agent_run = SubagentManager(db_session).spawn(
        task=task,
        assignment={"step_key": "dependency_review"},
    )

    assert agent_run.status == "PENDING"
    assert agent_run.agent_type == "subagent"
    assert DEFAULT_SUBAGENT_TIMEOUT_SECONDS == 900
    assert SUBAGENT_CONCURRENCY_LIMIT == 5
    events = EventStore(db_session).list_by_task(task_id=task.id)
    assert events[0].event_type == "SUBAGENT_SPAWNED"


def test_worker_success_flow_writes_started_and_completed(db_session: Session) -> None:
    task = create_task(db_session)
    agent_run = SubagentManager(db_session).spawn(task=task, assignment={"step_key": "review"})
    db_session.commit()

    status = execute_subagent(agent_run.id, session=db_session)

    assert status == "SUCCESS"
    refreshed = db_session.get(AgentRun, agent_run.id)
    assert refreshed is not None
    assert refreshed.status == "SUCCESS"
    events = EventStore(db_session).list_by_task(task_id=task.id)
    assert [event.event_type for event in events] == [
        "SUBAGENT_SPAWNED",
        "SUBAGENT_STARTED",
        "SUBAGENT_COMPLETED",
    ]


def test_worker_timeout_flow_writes_timeout_event(db_session: Session) -> None:
    task = create_task(db_session)
    agent_run = SubagentManager(db_session).spawn(task=task, assignment={"step_key": "slow"})
    db_session.commit()

    status = execute_subagent(agent_run.id, simulate_timeout=True, session=db_session)

    assert status == "TIMEOUT"
    events = EventStore(db_session).list_by_task(task_id=task.id)
    assert events[-1].event_type == "SUBAGENT_TIMEOUT"


def test_subagent_api_list_get_and_cancel(db_session: Session) -> None:
    task = create_task(db_session)
    subagent = SubagentManager(db_session).spawn(
        task=task,
        assignment={"step_key": "dependency_review"},
    )
    db_session.commit()

    client = TestClient(app)

    listed = client.get(f"/api/tasks/{task.id}/subagents")
    assert listed.status_code == 200
    assert listed.json()["items"][0]["id"] == subagent.id

    fetched = client.get(f"/api/subagents/{subagent.id}")
    assert fetched.status_code == 200

    cancelled = client.post(f"/api/subagents/{subagent.id}/cancel")
    assert cancelled.status_code == 202
    assert cancelled.json()["status"] == "CANCELLED"
