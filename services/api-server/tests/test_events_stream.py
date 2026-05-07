from fastapi.testclient import TestClient

from app.main import app
from tests.conftest import AUTH_HEADERS


def create_started_task(client: TestClient) -> str:
    created = client.post(
        "/api/tasks",
        headers=AUTH_HEADERS,
        json={
            "title": "Stream task",
            "goal": "Verify event stream",
            "model_provider": "openai-compatible",
            "model_name": "default",
        },
    ).json()
    client.post(f"/api/tasks/{created['id']}/start", headers=AUTH_HEADERS)
    return created["id"]


def test_sse_stream_uses_default_message_events_and_after_sequence() -> None:
    client = TestClient(app)
    task_id = create_started_task(client)

    response = client.get(
        f"/api/tasks/{task_id}/events/stream?after_sequence=1&once=true",
        headers=AUTH_HEADERS,
    )

    assert response.status_code == 200
    assert "event:" not in response.text
    assert "PLAN_REQUESTED" in response.text
    assert "TASK_CREATED" not in response.text


def test_sse_stream_accepts_last_event_id_header() -> None:
    client = TestClient(app)
    task_id = create_started_task(client)

    response = client.get(
        f"/api/tasks/{task_id}/events/stream?once=true",
        headers={**AUTH_HEADERS, "Last-Event-ID": "1"},
    )

    assert response.status_code == 200
    assert "PLAN_REQUESTED" in response.text
    assert "TASK_CREATED" not in response.text


def test_sse_after_sequence_overrides_last_event_id_for_reconnect() -> None:
    client = TestClient(app)
    task_id = create_started_task(client)

    response = client.get(
        f"/api/tasks/{task_id}/events/stream?after_sequence=2&once=true",
        headers={**AUTH_HEADERS, "Last-Event-ID": "1"},
    )

    assert response.status_code == 200
    assert "PLAN_GENERATED" in response.text
    assert "PLAN_REQUESTED" not in response.text


def test_sse_invalid_last_event_id_falls_back_to_full_stream() -> None:
    client = TestClient(app)
    task_id = create_started_task(client)

    response = client.get(
        f"/api/tasks/{task_id}/events/stream?once=true",
        headers={**AUTH_HEADERS, "Last-Event-ID": "not-a-sequence"},
    )

    assert response.status_code == 200
    assert "TASK_CREATED" in response.text


def test_sse_stream_emits_heartbeat_when_no_new_events() -> None:
    client = TestClient(app)
    task_id = create_started_task(client)
    events = client.get(f"/api/tasks/{task_id}/events", headers=AUTH_HEADERS).json()["items"]
    last_sequence = events[-1]["sequence"]

    response = client.get(
        f"/api/tasks/{task_id}/events/stream?after_sequence={last_sequence}&once=true",
        headers=AUTH_HEADERS,
    )

    assert response.status_code == 200
    assert ": heartbeat" in response.text
