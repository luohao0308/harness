from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)
ADMIN_HEADERS = {"Authorization": "Bearer dev-admin-token"}
ENGINEER_HEADERS = {"Authorization": "Bearer dev-engineer-token"}


def test_frontend_error_capture_and_admin_listing() -> None:
    created = client.post(
        "/api/frontend-errors",
        headers=ENGINEER_HEADERS,
        json={
            "url": "http://localhost/runs",
            "error_message": "test render failure",
            "stack": "Error: test",
            "browser": "vitest",
            "metadata_json": {"component": "RunHistoryPage"},
        },
    )
    assert created.status_code == 201, created.text
    assert created.json()["error_message"] == "test render failure"

    forbidden = client.get("/api/frontend-errors", headers=ENGINEER_HEADERS)
    assert forbidden.status_code == 403

    listed = client.get("/api/frontend-errors", headers=ADMIN_HEADERS)
    assert listed.status_code == 200, listed.text
    assert listed.json()["items"][0]["metadata_json"]["component"] == "RunHistoryPage"

    summary = client.get("/api/frontend-errors/summary", headers=ADMIN_HEADERS)
    assert summary.status_code == 200
    assert summary.json()["items"][0]["count"] == 1
