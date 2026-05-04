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
