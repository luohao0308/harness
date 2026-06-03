from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)
HEADERS = {"Authorization": "Bearer dev-engineer-token"}


def test_onboarding_state_lifecycle() -> None:
    initial = client.get("/api/onboarding/state", headers=HEADERS)
    assert initial.status_code == 200, initial.text
    assert initial.json()["current_step"] == 1
    assert initial.json()["completed"] is False

    updated = client.patch(
        "/api/onboarding/state",
        headers=HEADERS,
        json={"current_step": 2, "provider_json": {"provider": "deepseek-flash"}},
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["current_step"] == 2
    assert updated.json()["provider_json"]["provider"] == "deepseek-flash"

    completed = client.post(
        "/api/onboarding/complete",
        headers=HEADERS,
        json={"agent_id": "default", "demo_task_id": None},
    )
    assert completed.status_code == 200, completed.text
    assert completed.json()["completed"] is True
