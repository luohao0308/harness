from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)
ADMIN_HEADERS = {"Authorization": "Bearer dev-admin-token"}
ENGINEER_HEADERS = {"Authorization": "Bearer dev-engineer-token"}


def test_demo_load_is_admin_only_and_idempotent() -> None:
    denied = client.post("/api/demo/load", headers=ENGINEER_HEADERS)
    assert denied.status_code == 403

    loaded = client.post("/api/demo/load", headers=ADMIN_HEADERS)
    assert loaded.status_code == 200, loaded.text
    payload = loaded.json()
    assert payload["status"] == "loaded"
    assert len(payload["agent_ids"]) == 3
    assert payload["dataset_id"]
    assert payload["task_id"]
    assert payload["demo_loaded"] is True

    second = client.post("/api/demo/load", headers=ADMIN_HEADERS)
    assert second.status_code == 200, second.text
    assert second.json()["status"] == "already_loaded"


def test_demo_load_syncs_org_demo_state_to_current_onboarding_user() -> None:
    loaded = client.post("/api/demo/load", headers=ADMIN_HEADERS)
    assert loaded.status_code == 200, loaded.text
    demo_task_id = loaded.json()["task_id"]

    engineer_state = client.get("/api/onboarding/state", headers=ENGINEER_HEADERS)
    assert engineer_state.status_code == 200, engineer_state.text
    engineer_payload = engineer_state.json()
    assert engineer_payload["demo_loaded"] is True
    assert engineer_payload["demo_task_id"] == demo_task_id

    reset = client.post(
        "/api/demo/reset",
        headers=ADMIN_HEADERS,
        json={"confirm_token": "reset-demo-data"},
    )
    assert reset.status_code == 200, reset.text

    engineer_state_after_reset = client.get("/api/onboarding/state", headers=ENGINEER_HEADERS)
    assert engineer_state_after_reset.status_code == 200, engineer_state_after_reset.text
    assert engineer_state_after_reset.json()["demo_loaded"] is False
    assert engineer_state_after_reset.json()["demo_task_id"] is None


def test_demo_reset_requires_confirm_token() -> None:
    loaded = client.post("/api/demo/load", headers=ADMIN_HEADERS)
    assert loaded.status_code == 200

    rejected = client.post(
        "/api/demo/reset",
        headers=ADMIN_HEADERS,
        json={"confirm_token": "wrong"},
    )
    assert rejected.status_code == 400

    reset = client.post(
        "/api/demo/reset",
        headers=ADMIN_HEADERS,
        json={"confirm_token": "reset-demo-data"},
    )
    assert reset.status_code == 200, reset.text
    assert reset.json()["status"] == "reset"
    assert reset.json()["demo_loaded"] is False
