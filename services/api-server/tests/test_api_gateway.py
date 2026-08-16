from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.gateway import reset_gateway_rate_limiter
from app.db.models import AgentEvent, ApiGatewayRoute, Task
from app.events.event_types import EventType
from app.main import app

AUTH_HEADERS = {"Authorization": "Bearer dev-engineer-token"}
ADMIN_AUTH_HEADERS = {"Authorization": "Bearer dev-admin-token"}


def test_api_gateway_route_crud_flow(db_session: Session) -> None:
    client = TestClient(app)

    created = client.post(
        "/api/agents/default/gateway-routes",
        headers=AUTH_HEADERS,
        json={"slug": "release-review", "description": "Release review", "rate_limit": 30},
    )

    assert created.status_code == 201
    body = created.json()
    assert body["api_key"].startswith("hgw_")
    assert body["route"]["slug"] == "release-review"
    assert body["route"]["rate_limit"] == 30
    assert "api_key_hash" not in body["route"]
    route_id = body["route"]["id"]
    assert db_session.execute(select(ApiGatewayRoute)).scalar_one().api_key_hash != body["api_key"]

    listed = client.get("/api/agents/default/gateway-routes", headers=AUTH_HEADERS)
    assert listed.status_code == 200
    assert [item["id"] for item in listed.json()["items"]] == [route_id]
    assert "api_key" not in listed.json()["items"][0]

    updated = client.patch(
        f"/api/agents/default/gateway-routes/{route_id}",
        headers=AUTH_HEADERS,
        json={"enabled": False, "rate_limit": 10, "description": "Updated"},
    )
    assert updated.status_code == 200
    assert updated.json()["enabled"] is False
    assert updated.json()["rate_limit"] == 10

    deleted = client.delete(
        f"/api/agents/default/gateway-routes/{route_id}",
        headers=ADMIN_AUTH_HEADERS,
    )
    assert deleted.status_code == 204
    listed_after_delete = client.get("/api/agents/default/gateway-routes", headers=AUTH_HEADERS)
    assert listed_after_delete.json()["items"] == []


def test_api_gateway_invoke_creates_planned_run_and_event(db_session: Session) -> None:
    reset_gateway_rate_limiter()
    client = TestClient(app)
    created = client.post(
        "/api/agents/default/gateway-routes",
        headers=AUTH_HEADERS,
        json={"slug": "incident-summary", "rate_limit": 5},
    ).json()

    response = client.post(
        "/api/gateway/incident-summary/invoke",
        headers={"X-Harness-Gateway-Key": created["api_key"]},
        json={
            "goal": "Summarize incident",
            "title": "Incident INC-123",
            "input": {"ticket_id": "INC-123", "body": "Database failover"},
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["agent_id"] == "default"
    assert body["route_id"] == created["route"]["id"]
    assert body["slug"] == "incident-summary"
    assert body["status"] == "PLANNED"

    run = db_session.get(Task, body["run_id"])
    assert run is not None
    assert run.status == "PLANNED"
    assert "Gateway input preview" in run.goal

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
        EventType.API_GATEWAY_INVOKED.value,
        EventType.PLAN_REQUESTED.value,
        EventType.PLAN_GENERATED.value,
    ]


def test_api_gateway_invoke_rejects_bad_key_without_run(db_session: Session) -> None:
    reset_gateway_rate_limiter()
    client = TestClient(app)
    client.post(
        "/api/agents/default/gateway-routes",
        headers=AUTH_HEADERS,
        json={"slug": "secure-api"},
    )

    response = client.post(
        "/api/gateway/secure-api/invoke",
        headers={"X-Harness-Gateway-Key": "wrong"},
        json={"goal": "Do not run"},
    )

    assert response.status_code == 401
    assert db_session.execute(select(Task)).scalars().all() == []


def test_api_gateway_invoke_rejects_disabled_route(db_session: Session) -> None:
    reset_gateway_rate_limiter()
    client = TestClient(app)
    created = client.post(
        "/api/agents/default/gateway-routes",
        headers=AUTH_HEADERS,
        json={"slug": "disabled-api"},
    ).json()
    client.patch(
        f"/api/agents/default/gateway-routes/{created['route']['id']}",
        headers=AUTH_HEADERS,
        json={"enabled": False},
    )

    response = client.post(
        "/api/gateway/disabled-api/invoke",
        headers={"X-Harness-Gateway-Key": created["api_key"]},
        json={"goal": "Do not run"},
    )

    assert response.status_code == 404
    assert db_session.execute(select(Task)).scalars().all() == []


def test_api_gateway_invoke_enforces_rate_limit(db_session: Session) -> None:
    reset_gateway_rate_limiter()
    client = TestClient(app)
    created = client.post(
        "/api/agents/default/gateway-routes",
        headers=AUTH_HEADERS,
        json={"slug": "limited-api", "rate_limit": 1},
    ).json()

    first = client.post(
        "/api/gateway/limited-api/invoke",
        headers={"X-Harness-Gateway-Key": created["api_key"]},
        json={"goal": "Run once"},
    )
    second = client.post(
        "/api/gateway/limited-api/invoke",
        headers={"X-Harness-Gateway-Key": created["api_key"]},
        json={"goal": "Run twice"},
    )

    assert first.status_code == 200
    assert second.status_code == 429
    assert len(db_session.execute(select(Task)).scalars().all()) == 1
