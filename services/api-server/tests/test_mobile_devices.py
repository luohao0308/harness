from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db.models import MobileDevice
from app.main import app

AUTH_HEADERS = {"Authorization": "Bearer dev-engineer-token"}


def test_register_mobile_device_creates_and_redacts_token() -> None:
    client = TestClient(app)

    response = client.post(
        "/api/mobile/devices",
        headers=AUTH_HEADERS,
        json={
            "platform": "ios",
            "push_token": "ExponentPushToken[xxxxxxxxxxxxxxxxxxxxxx]",
            "device_name": "iPhone",
            "app_version": "0.1.0",
            "notifications_enabled": True,
            "preferences_json": {"run_terminal": True},
        },
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["platform"] == "ios"
    assert body["push_token"].startswith("Exponent")
    assert body["push_token"].endswith("xxx]")
    assert body["preferences_json"] == {"run_terminal": True}


def test_register_mobile_device_updates_existing_token(db_session) -> None:
    client = TestClient(app)
    payload = {
        "platform": "android",
        "push_token": "ExponentPushToken[yyyyyyyyyyyyyyyyyyyyyy]",
        "device_name": "Pixel",
        "app_version": "0.1.0-beta.1",
        "notifications_enabled": True,
    }

    first = client.post("/api/mobile/devices", headers=AUTH_HEADERS, json=payload)
    second = client.post(
        "/api/mobile/devices",
        headers=AUTH_HEADERS,
        json={**payload, "device_name": "Pixel Fold", "notifications_enabled": False},
    )

    assert first.status_code == 201
    assert second.status_code == 201
    devices = db_session.execute(select(MobileDevice)).scalars().all()
    assert len(devices) == 1
    assert devices[0].device_name == "Pixel Fold"
    assert devices[0].notifications_enabled is False


def test_list_mobile_devices_is_user_scoped() -> None:
    client = TestClient(app)

    created = client.post(
        "/api/mobile/devices",
        headers=AUTH_HEADERS,
        json={
            "platform": "ios",
            "push_token": "ExponentPushToken[zzzzzzzzzzzzzzzzzzzzzz]",
            "device_name": "iPhone",
        },
    )
    assert created.status_code == 201

    listed = client.get("/api/mobile/devices", headers=AUTH_HEADERS)
    assert listed.status_code == 200
    assert len(listed.json()["items"]) == 1

    other_org = client.get(
        "/api/mobile/devices",
        headers={"Authorization": "Bearer dev-other-org-token"},
    )
    assert other_org.status_code == 200
    assert other_org.json()["items"] == []
