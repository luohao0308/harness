from fastapi.testclient import TestClient

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
