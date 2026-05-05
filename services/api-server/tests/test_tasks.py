from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.db.models import ExecutionPlan, Task, TaskSnapshot, TaskStep, utc_now
from app.events.event_store import EventStore
from app.events.event_types import EventType
from app.main import app
from tests.conftest import AUTH_HEADERS


def test_create_task_writes_task_created_event() -> None:
    client = TestClient(app)

    response = client.post(
        "/api/tasks",
        headers=AUTH_HEADERS,
        json={
            "title": "Demo",
            "goal": "Analyze project",
            "model_provider": "openai-compatible",
            "model_name": "default",
            "max_runtime_seconds": 1800,
            "max_subagents": 5,
            "enable_sandbox": True,
            "enable_network": False,
        },
    )

    assert response.status_code == 201
    task = response.json()
    assert task["status"] == "CREATED"

    events_response = client.get(f"/api/tasks/{task['id']}/events", headers=AUTH_HEADERS)

    assert events_response.status_code == 200
    events = events_response.json()["items"]
    assert [event["sequence"] for event in events] == [1]
    assert events[0]["event_type"] == "TASK_CREATED"


def test_events_stream_endpoint_exists() -> None:
    client = TestClient(app)
    created = client.post(
        "/api/tasks",
        headers=AUTH_HEADERS,
        json={
            "title": "Demo",
            "goal": "Analyze project",
            "model_provider": "openai-compatible",
            "model_name": "default",
        },
    ).json()

    response = client.get(
        f"/api/tasks/{created['id']}/events/stream?once=true",
        headers=AUTH_HEADERS,
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert "TASK_CREATED" in response.text


def test_tasks_require_bearer_token() -> None:
    client = TestClient(app)

    response = client.get("/api/tasks")

    assert response.status_code == 401


def test_task_cancel_resume_result_replay_and_audit_endpoints() -> None:
    client = TestClient(app)
    created = client.post(
        "/api/tasks",
        headers=AUTH_HEADERS,
        json={
            "title": "Runtime completion",
            "goal": "Exercise stage 12 task APIs",
            "model_provider": "openai-compatible",
            "model_name": "default",
        },
    ).json()
    task_id = created["id"]

    cancelled = client.post(f"/api/tasks/{task_id}/cancel", headers=AUTH_HEADERS)
    assert cancelled.status_code == 202
    assert cancelled.json()["status"] == "CANCELLED"

    replay_cancelled = client.post(
        f"/api/tasks/{task_id}/replay",
        headers=AUTH_HEADERS,
        json={},
    )
    assert replay_cancelled.status_code == 200
    assert replay_cancelled.json()["task_id"] == task_id
    assert "CANCELLED" in replay_cancelled.json()["state_summary"]

    resumed = client.post(f"/api/tasks/{task_id}/resume", headers=AUTH_HEADERS)
    assert resumed.status_code == 202
    assert resumed.json()["status"] == "COMPLETED"

    result = client.get(f"/api/tasks/{task_id}/result", headers=AUTH_HEADERS)
    assert result.status_code == 200
    payload = result.json()
    assert payload["task_id"] == task_id
    assert payload["status"] == "COMPLETED"
    assert payload["last_sequence"] >= 1
    assert payload["artifacts"][0]["name"] == "result.md"

    model_calls = client.get(f"/api/tasks/{task_id}/model-calls", headers=AUTH_HEADERS)
    tool_calls = client.get(f"/api/tasks/{task_id}/tool-calls", headers=AUTH_HEADERS)
    assert model_calls.status_code == 200
    assert model_calls.json()["items"][0]["model_provider"] == "openai-compatible"
    assert tool_calls.status_code == 200
    assert tool_calls.json()["items"][0]["tool_name"] == "read_file"


def test_task_plan_steps_and_tool_execute_endpoints() -> None:
    client = TestClient(app)
    created = client.post(
        "/api/tasks",
        headers=AUTH_HEADERS,
        json={
            "title": "Plan and tools",
            "goal": "Inspect project and produce a report",
            "model_provider": "openai-compatible",
            "model_name": "default",
        },
    ).json()
    task_id = created["id"]

    started = client.post(f"/api/tasks/{task_id}/start", headers=AUTH_HEADERS)
    assert started.status_code == 202
    assert started.json()["status"] == "COMPLETED"

    plan = client.get(f"/api/tasks/{task_id}/plan", headers=AUTH_HEADERS)
    assert plan.status_code == 200
    plan_payload = plan.json()
    assert plan_payload["task_id"] == task_id
    assert plan_payload["version"] == 1
    assert plan_payload["steps"][0]["status"] == "STEP_COMPLETED"

    steps = client.get(f"/api/tasks/{task_id}/steps", headers=AUTH_HEADERS)
    assert steps.status_code == 200
    assert steps.json()["items"][0]["step_key"] == plan_payload["steps"][0]["step_key"]

    tool_execution = client.post(
        f"/api/tasks/{task_id}/tools/execute",
        headers=AUTH_HEADERS,
        json={
            "tool_name": "read_file",
            "input_json": {"path": "pyproject.toml"},
        },
    )
    assert tool_execution.status_code == 202
    tool_payload = tool_execution.json()
    assert tool_payload["allowed"] is True
    assert tool_payload["tool_call"]["tool_name"] == "read_file"
    assert "content" in tool_payload["output"]


def test_replay_uses_snapshot_and_events_after_snapshot(db_session: Session) -> None:
    task = Task(
        organization_id="dev-org",
        created_by="dev-engineer",
        title="Replay snapshot",
        goal="Recover from snapshot",
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
    for index in range(99):
        event_store.append(
            task_id=task.id,
            event_type=EventType.SUBAGENT_PROGRESS,
            payload_json={"index": index},
        )
    event_store.append(
        task_id=task.id,
        event_type=EventType.TASK_FAILED,
        payload_json={"summary": "boom"},
    )
    db_session.commit()

    snapshot = db_session.query(TaskSnapshot).filter(TaskSnapshot.task_id == task.id).one()
    assert snapshot.sequence == 100

    client = TestClient(app)
    replay = client.post(
        f"/api/tasks/{task.id}/replay",
        headers=AUTH_HEADERS,
        json={},
    )

    assert replay.status_code == 200
    payload = replay.json()
    assert payload["sequence"] == 101
    assert "FAILED" in payload["state_summary"]
    assert payload["failure_point"]["sequence"] == 101


def test_resume_reuses_plan_and_skips_completed_steps(db_session: Session) -> None:
    task = Task(
        organization_id="dev-org",
        created_by="dev-engineer",
        title="Resume from failed step",
        goal="Continue after failure",
        status="FAILED",
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
    plan = ExecutionPlan(
        task_id=task.id,
        version=1,
        status="GENERATED",
        plan_json={
            "summary": "Continue after failure",
            "steps": [
                {
                    "key": "inspect_project",
                    "description": "Inspect project structure",
                    "execution_mode": "sync",
                    "requires_sandbox": False,
                    "can_spawn_subagent": False,
                    "expected_events": ["STEP_STARTED", "STEP_COMPLETED"],
                },
                {
                    "key": "produce_report",
                    "description": "Produce final report",
                    "execution_mode": "sync",
                    "requires_sandbox": False,
                    "can_spawn_subagent": False,
                    "expected_events": ["STEP_STARTED", "STEP_COMPLETED"],
                },
            ],
        },
        created_at=utc_now(),
    )
    db_session.add(plan)
    db_session.flush()
    event_store = EventStore(db_session)
    event_store.append(
        task_id=task.id,
        event_type=EventType.TASK_CREATED,
        payload_json={"title": task.title},
    )
    event_store.append(
        task_id=task.id,
        event_type=EventType.PLAN_GENERATED,
        payload_json={"plan_id": plan.id, "plan": plan.plan_json},
    )
    event_store.append(
        task_id=task.id,
        event_type=EventType.STEP_STARTED,
        payload_json={"step_key": "inspect_project"},
    )
    event_store.append(
        task_id=task.id,
        event_type=EventType.STEP_COMPLETED,
        payload_json={"step_key": "inspect_project"},
    )
    event_store.append(
        task_id=task.id,
        event_type=EventType.STEP_STARTED,
        payload_json={"step_key": "produce_report"},
    )
    event_store.append(
        task_id=task.id,
        event_type=EventType.STEP_FAILED,
        payload_json={"step_key": "produce_report", "summary": "boom"},
    )
    event_store.append(
        task_id=task.id,
        event_type=EventType.TASK_FAILED,
        payload_json={"failed_step": "produce_report", "summary": "boom"},
    )
    db_session.commit()

    client = TestClient(app)
    resumed = client.post(f"/api/tasks/{task.id}/resume", headers=AUTH_HEADERS)

    assert resumed.status_code == 202
    assert resumed.json()["status"] == "COMPLETED"
    steps = list(
        db_session.query(TaskStep)
        .filter(TaskStep.task_id == task.id)
        .order_by(TaskStep.started_at)
        .all()
    )
    assert [step.step_key for step in steps] == ["produce_report"]
    events = client.get(f"/api/tasks/{task.id}/events", headers=AUTH_HEADERS).json()["items"]
    event_types = [event["event_type"] for event in events]
    assert "STEP_SKIPPED" in event_types
    assert event_types.count("PLAN_GENERATED") == 1
