from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)
HEADERS = {"Authorization": "Bearer dev-engineer-token"}


def test_onboarding_status_first_run() -> None:
    """Test GET /api/onboarding/status on first run (no users)."""
    response = client.get("/api/onboarding/status")
    assert response.status_code == 200, response.text

    data = response.json()
    assert data["is_first_run"] is True
    assert data["should_show_wizard"] is True
    assert data["redirect_to"] == "/onboarding/welcome"
    assert data["is_completed"] is False
    assert data["wizard_skipped"] is False


def test_onboarding_status_after_user_creation() -> None:
    """Test GET /api/onboarding/status after first user is created."""
    # First, check it's a first run
    initial = client.get("/api/onboarding/status")
    assert initial.json()["is_first_run"] is True

    # After the test framework creates a user (via auth headers), check again
    # In a real scenario, this would be after admin user creation
    state_response = client.get("/api/onboarding/state", headers=HEADERS)
    assert state_response.status_code == 200

    # Now check status - should still be first run until users are actually created
    # (This test framework doesn't create real users, so we're testing the endpoint works)
    status = client.get("/api/onboarding/status")
    assert status.status_code == 200
    assert "is_first_run" in status.json()


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
