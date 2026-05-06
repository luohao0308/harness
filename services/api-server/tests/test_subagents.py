from datetime import timedelta
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.agents.subagent_manager import SUBAGENT_CONCURRENCY_LIMIT, SubagentManager
from app.db.models import AgentRun, Task, utc_now
from app.events.event_store import EventStore
from app.main import app
from app.workers.subagent_recovery_worker import recover_stalled_subagents
from app.workers.subagent_worker import DEFAULT_SUBAGENT_TIMEOUT_SECONDS, execute_subagent
from tests.conftest import AUTH_HEADERS


def create_task(db_session: Session) -> Task:
    task = Task(
        organization_id="dev-org",
        created_by="dev-engineer",
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
    assert refreshed.context_json["result"]["summary"].startswith("Subagent completed review")
    events = EventStore(db_session).list_by_task(task_id=task.id)
    event_types = [event.event_type for event in events]
    assert event_types[0:3] == ["SUBAGENT_SPAWNED", "SUBAGENT_STARTED", "SUBAGENT_PROGRESS"]
    assert "MODEL_CALLED" in event_types
    assert "MODEL_RESPONSE_RECEIVED" in event_types
    assert event_types[-1] == "SUBAGENT_COMPLETED"


def test_worker_executes_assignment_tools_and_writes_results(
    db_session: Session,
    tmp_path: Path,
) -> None:
    task = create_task(db_session)
    target = tmp_path / "notes.md"
    target.write_text("异步工具结果", encoding="utf-8")
    agent_run = SubagentManager(db_session).spawn(
        task=task,
        assignment={
            "step_key": "tool_review",
            "tools": [{"tool_name": "read_file", "input_json": {"path": "notes.md"}}],
        },
    )
    db_session.commit()

    status = execute_subagent(agent_run.id, session=db_session, workspace_root=tmp_path)

    assert status == "SUCCESS"
    refreshed = db_session.get(AgentRun, agent_run.id)
    assert refreshed is not None
    tool_results = refreshed.context_json["result"]["tool_results"]
    assert tool_results[0]["tool_name"] == "read_file"
    assert tool_results[0]["status"] == "SUCCESS"
    assert tool_results[0]["output"]["content"] == "异步工具结果"
    assert "工具执行 1 个" in refreshed.context_json["result"]["summary"]
    events = EventStore(db_session).list_by_task(task_id=task.id)
    event_types = [event.event_type for event in events]
    assert "TOOL_CALLED" in event_types
    assert "TOOL_RESULT_RECEIVED" in event_types


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

    listed = client.get(f"/api/tasks/{task.id}/subagents", headers=AUTH_HEADERS)
    assert listed.status_code == 200
    assert listed.json()["items"][0]["id"] == subagent.id

    fetched = client.get(f"/api/subagents/{subagent.id}", headers=AUTH_HEADERS)
    assert fetched.status_code == 200

    cancelled = client.post(f"/api/subagents/{subagent.id}/cancel", headers=AUTH_HEADERS)
    assert cancelled.status_code == 202
    assert cancelled.json()["status"] == "CANCELLED"


def test_subagent_api_create_for_task(db_session: Session) -> None:
    task = create_task(db_session)
    db_session.commit()
    client = TestClient(app)

    created = client.post(
        f"/api/tasks/{task.id}/subagents",
        headers=AUTH_HEADERS,
        json={
            "assignment": {"step_key": "parallel_review", "description": "并发审查"},
            "timeout_seconds": 120,
        },
    )

    assert created.status_code == 201
    payload = created.json()
    assert payload["task_id"] == task.id
    assert payload["status"] == "PENDING"
    assert payload["context_json"]["step_key"] == "parallel_review"


def test_subagent_recovery_resets_stale_running_and_times_out_expired(
    db_session: Session,
) -> None:
    task = create_task(db_session)
    manager = SubagentManager(db_session)
    stale = manager.spawn(
        task=task,
        assignment={"step_key": "stale_worker"},
        timeout_seconds=1800,
    )
    stale.status = "RUNNING"
    stale.started_at = utc_now() - timedelta(seconds=901)
    expired = manager.spawn(
        task=task,
        assignment={"step_key": "expired_worker"},
        timeout_seconds=1,
    )
    expired.status = "RUNNING"
    expired.started_at = utc_now() - timedelta(seconds=60)
    expired.timeout_at = utc_now() - timedelta(seconds=1)
    db_session.commit()

    client = TestClient(app)
    recovered = client.post(
        f"/api/tasks/{task.id}/subagents/recover",
        headers=AUTH_HEADERS,
        json={"stale_after_seconds": 900, "enqueue": False},
    )

    assert recovered.status_code == 202
    payload = recovered.json()
    actions = {item["id"]: item["action"] for item in payload["recovered"]}
    assert actions[stale.id] == "reset_to_pending"
    assert actions[expired.id] == "marked_timeout"
    refreshed_stale = db_session.get(AgentRun, stale.id)
    refreshed_expired = db_session.get(AgentRun, expired.id)
    assert refreshed_stale is not None
    assert refreshed_stale.status == "PENDING"
    assert refreshed_stale.started_at is None
    assert refreshed_stale.context_json["recovery_attempts"] == 1
    assert refreshed_expired is not None
    assert refreshed_expired.status == "TIMEOUT"
    events = EventStore(db_session).list_by_task(task_id=task.id)
    event_types = [event.event_type for event in events]
    assert "SUBAGENT_PROGRESS" in event_types
    assert event_types[-1] == "SUBAGENT_TIMEOUT"


def test_subagent_recovery_sweep_scans_all_tasks(db_session: Session) -> None:
    first_task = create_task(db_session)
    second_task = create_task(db_session)
    first_stale = SubagentManager(db_session).spawn(
        task=first_task,
        assignment={"step_key": "first_stale"},
        timeout_seconds=1800,
    )
    first_stale.status = "RUNNING"
    first_stale.started_at = utc_now() - timedelta(seconds=901)
    second_expired = SubagentManager(db_session).spawn(
        task=second_task,
        assignment={"step_key": "second_expired"},
        timeout_seconds=1,
    )
    second_expired.status = "RUNNING"
    second_expired.started_at = utc_now() - timedelta(seconds=60)
    second_expired.timeout_at = utc_now() - timedelta(seconds=1)
    db_session.commit()

    result = recover_stalled_subagents(
        stale_after_seconds=900,
        enqueue=False,
        session=db_session,
    )

    assert result["task_count"] == 2
    assert result["recovered_count"] == 2
    assert db_session.get(AgentRun, first_stale.id).status == "PENDING"
    assert db_session.get(AgentRun, second_expired.id).status == "TIMEOUT"
