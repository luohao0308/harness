from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import AdminAuditEvent
from app.main import app
from tests.conftest import AUTH_HEADERS

ADMIN_HEADERS = {"Authorization": "Bearer dev-admin-token"}


def test_settings_read_allowed_for_engineer_and_write_requires_admin() -> None:
    client = TestClient(app)

    engineer = client.get("/api/settings/models", headers=AUTH_HEADERS)
    admin = client.get("/api/settings/models", headers=ADMIN_HEADERS)
    blocked_update = client.put(
        "/api/settings/models",
        headers=AUTH_HEADERS,
        json=admin.json(),
    )

    assert engineer.status_code == 200
    assert admin.status_code == 200
    assert blocked_update.status_code == 403
    assert admin.json()["default_provider"] == "openai-compatible"


def test_policy_settings_round_trip_for_admin(db_session: Session) -> None:
    client = TestClient(app)

    policies = client.get("/api/settings/policies", headers=ADMIN_HEADERS)
    assert policies.status_code == 200

    updated = client.put(
        "/api/settings/policies",
        headers=ADMIN_HEADERS,
        json=policies.json(),
    )
    assert updated.status_code == 200
    assert updated.json()["audit"]["tool_calls"] is True

    audit_event = db_session.execute(select(AdminAuditEvent)).scalar_one()
    assert audit_event.event_type == "ADMIN_ACTION"
    assert audit_event.resource_id == "policies"
    assert audit_event.action == "settings.policies.update"
