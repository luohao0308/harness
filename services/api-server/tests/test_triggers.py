from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import AgentEvent, Task, Trigger
from app.events.event_types import EventType
from app.main import app

AUTH_HEADERS = {"Authorization": "Bearer dev-engineer-token"}
ADMIN_AUTH_HEADERS = {"Authorization": "Bearer dev-admin-token"}


def test_trigger_crud_flow(db_session: Session) -> None:
    client = TestClient(app)

    created = client.post(
        "/api/agents/default/triggers",
        headers=AUTH_HEADERS,
        json={"endpoint_path": "release-check", "enabled": True},
    )

    assert created.status_code == 201
    body = created.json()
    assert body["secret"].startswith("htrg_")
    assert body["trigger"]["endpoint_path"] == "release-check"
    assert body["trigger"]["enabled"] is True
    assert "secret_hash" not in body["trigger"]

    trigger_id = body["trigger"]["id"]
    assert db_session.execute(select(Trigger)).scalar_one().secret_hash != body["secret"]

    listed = client.get("/api/agents/default/triggers", headers=AUTH_HEADERS)
    assert listed.status_code == 200
    assert [item["id"] for item in listed.json()["items"]] == [trigger_id]
    assert "secret" not in listed.json()["items"][0]

    updated = client.patch(
        f"/api/agents/default/triggers/{trigger_id}",
        headers=AUTH_HEADERS,
        json={"enabled": False},
    )
    assert updated.status_code == 200
    assert updated.json()["enabled"] is False

    deleted = client.delete(
        f"/api/agents/default/triggers/{trigger_id}",
        headers=ADMIN_AUTH_HEADERS,
    )
    assert deleted.status_code == 204
    assert client.get("/api/agents/default/triggers", headers=AUTH_HEADERS).json()["items"] == []


def test_webhook_trigger_creates_planned_run_and_event(db_session: Session) -> None:
    client = TestClient(app)
    created = client.post(
        "/api/agents/default/triggers",
        headers=AUTH_HEADERS,
        json={"endpoint_path": "ci-run"},
    ).json()

    response = client.post(
        "/api/webhook/trigger/ci-run",
        headers={"X-Harness-Trigger-Secret": created["secret"]},
        json={"goal": "Review release", "title": "CI release", "payload": {"sha": "abc123"}},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["agent_id"] == "default"
    assert body["trigger_id"] == created["trigger"]["id"]
    assert body["status"] == "PLANNED"

    run = db_session.get(Task, body["run_id"])
    assert run is not None
    assert run.agent_id == "default"
    assert run.status == "PLANNED"
    assert "Webhook payload preview" in run.goal

    event_types = [
        row.event_type
        for row in db_session.execute(
            select(AgentEvent)
            .where(AgentEvent.task_id == body["run_id"])
            .order_by(AgentEvent.sequence)
        ).scalars()
    ]
    assert event_types == [
        EventType.TASK_CREATED.value,
        EventType.TRIGGER_INVOKED.value,
        EventType.PLAN_REQUESTED.value,
        EventType.PLAN_GENERATED.value,
    ]


def test_webhook_trigger_rejects_bad_secret_without_run(db_session: Session) -> None:
    client = TestClient(app)
    client.post(
        "/api/agents/default/triggers",
        headers=AUTH_HEADERS,
        json={"endpoint_path": "secure-hook"},
    )

    response = client.post(
        "/api/webhook/trigger/secure-hook",
        headers={"X-Harness-Trigger-Secret": "wrong"},
        json={"goal": "Do not run"},
    )

    assert response.status_code == 401
    assert db_session.execute(select(Task)).scalars().all() == []


def test_webhook_trigger_rejects_disabled_trigger(db_session: Session) -> None:
    client = TestClient(app)
    created = client.post(
        "/api/agents/default/triggers",
        headers=AUTH_HEADERS,
        json={"endpoint_path": "disabled-hook"},
    ).json()
    client.patch(
        f"/api/agents/default/triggers/{created['trigger']['id']}",
        headers=AUTH_HEADERS,
        json={"enabled": False},
    )

    response = client.post(
        "/api/webhook/trigger/disabled-hook",
        headers={"X-Harness-Trigger-Secret": created["secret"]},
        json={"goal": "Do not run"},
    )

    assert response.status_code == 404
    assert db_session.execute(select(Task)).scalars().all() == []
