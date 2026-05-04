from fastapi.testclient import TestClient

from app.main import app
from tests.conftest import AUTH_HEADERS


def test_invalid_token_is_rejected() -> None:
    client = TestClient(app)

    response = client.get("/api/tasks", headers={"Authorization": "Bearer wrong"})

    assert response.status_code == 401


def test_localhost_and_loopback_console_origins_are_allowed() -> None:
    client = TestClient(app)

    for origin in ["http://localhost:5173", "http://127.0.0.1:5173"]:
        response = client.options(
            "/api/tasks",
            headers={
                "Origin": origin,
                "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Headers": "authorization",
            },
        )

        assert response.status_code == 200
        assert response.headers["access-control-allow-origin"] == origin


def test_tasks_are_scoped_to_principal_organization() -> None:
    client = TestClient(app)
    created = client.post(
        "/api/tasks",
        headers=AUTH_HEADERS,
        json={
            "title": "Scoped task",
            "goal": "Verify tenant boundary",
            "model_provider": "openai-compatible",
            "model_name": "default",
        },
    )
    task_id = created.json()["id"]

    hidden = client.get(
        f"/api/tasks/{task_id}",
        headers={"Authorization": "Bearer dev-other-org-token"},
    )
    other_list = client.get(
        "/api/tasks",
        headers={"Authorization": "Bearer dev-other-org-token"},
    )

    assert hidden.status_code == 404
    assert other_list.status_code == 200
    assert other_list.json()["items"] == []
