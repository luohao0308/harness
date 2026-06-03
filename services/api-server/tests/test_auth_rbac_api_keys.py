from fastapi.testclient import TestClient

from app.db.models import AdminAuditEvent, OrganizationMember, User
from app.main import app
from tests.conftest import AUTH_HEADERS

ADMIN_HEADERS = {"Authorization": "Bearer dev-admin-token"}


def test_register_login_refresh_and_me_flow() -> None:
    client = TestClient(app)

    registered = client.post(
        "/api/auth/register",
        json={
            "email": "owner@example.com",
            "password": "correct-password",
            "name": "Owner Example",
            "organization_name": "Owner Workspace",
        },
    )
    assert registered.status_code == 201
    assert registered.json()["access_token"]
    refresh_token = registered.json()["refresh_token"]

    logged_in = client.post(
        "/api/auth/login",
        json={"email": "owner@example.com", "password": "correct-password"},
    )
    assert logged_in.status_code == 200
    headers = {"Authorization": f"Bearer {logged_in.json()['access_token']}"}

    me = client.get("/api/auth/me", headers=headers)
    assert me.status_code == 200
    assert me.json()["role"] == "owner"
    assert me.json()["organizations"][0]["name"] == "Owner Workspace"

    refreshed = client.post("/api/auth/refresh", json={"refresh_token": refresh_token})
    assert refreshed.status_code == 200
    assert refreshed.json()["access_token"]


def test_jwt_requires_current_accepted_membership(db_session) -> None:
    client = TestClient(app)

    registered = client.post(
        "/api/auth/register",
        json={
            "email": "removed-member@example.com",
            "password": "correct-password",
            "name": "Removed Member",
            "organization_name": "Removed Workspace",
        },
    )
    assert registered.status_code == 201
    access_token = registered.json()["access_token"]

    user = db_session.query(User).filter_by(email="removed-member@example.com").one()
    membership = db_session.query(OrganizationMember).filter_by(user_id=user.id).one()
    db_session.delete(membership)
    db_session.commit()

    response = client.get("/api/auth/me", headers={"Authorization": f"Bearer {access_token}"})
    assert response.status_code == 401


def test_viewer_cannot_create_api_key_but_owner_key_can_access_tasks(db_session) -> None:
    client = TestClient(app)
    viewer_login = client.post(
        "/api/auth/register",
        json={
            "email": "viewer@example.com",
            "password": "correct-password",
            "name": "Viewer Example",
            "organization_name": "Viewer Workspace",
        },
    ).json()
    viewer_headers = {"Authorization": f"Bearer {viewer_login['access_token']}"}

    # Owner creates a viewer member, then demotes their own token is not needed; use dev operator.
    forbidden = client.post(
        "/api/api-keys",
        headers={"Authorization": "Bearer dev-operator-token"},
        json={"name": "viewer-key"},
    )
    assert forbidden.status_code == 403

    created = client.post(
        "/api/api-keys",
        headers=viewer_headers,
        json={"name": "owner-key", "scopes": ["run:read", "run:create"]},
    )
    assert created.status_code == 201
    api_key = created.json()["key"]
    assert created.json()["key_prefix"]
    assert client.get("/api/api-keys", headers=viewer_headers).status_code == 200

    task = client.post(
        "/api/tasks",
        headers={"Authorization": f"Bearer {api_key}"},
        json={
            "title": "API key task",
            "goal": "prove api key auth",
            "model_provider": "default",
            "model_name": "default",
        },
    )
    assert task.status_code == 201

    key_id = created.json()["id"]
    assert client.delete(f"/api/api-keys/{key_id}", headers=viewer_headers).status_code == 204
    after_revoke = client.get("/api/tasks", headers={"Authorization": f"Bearer {api_key}"})
    assert after_revoke.status_code == 401


def test_api_key_requires_active_user(db_session) -> None:
    client = TestClient(app)
    registered = client.post(
        "/api/auth/register",
        json={
            "email": "disabled-key-owner@example.com",
            "password": "correct-password",
            "name": "Disabled Key Owner",
            "organization_name": "Disabled Key Workspace",
        },
    )
    assert registered.status_code == 201
    headers = {"Authorization": f"Bearer {registered.json()['access_token']}"}
    created = client.post(
        "/api/api-keys",
        headers=headers,
        json={"name": "disabled-owner-key", "scopes": ["run:read"]},
    )
    assert created.status_code == 201

    user = db_session.query(User).filter_by(email="disabled-key-owner@example.com").one()
    user.status = "disabled"
    db_session.commit()

    response = client.get(
        "/api/tasks",
        headers={"Authorization": f"Bearer {created.json()['key']}"},
    )
    assert response.status_code == 401


def test_user_management_writes_audit_events(db_session) -> None:
    client = TestClient(app)

    created = client.post(
        "/api/users",
        headers=ADMIN_HEADERS,
        json={"email": "member@example.com", "name": "Member", "role": "member"},
    )
    assert created.status_code == 201
    user_id = created.json()["user_id"]

    updated = client.patch(
        f"/api/users/{user_id}/role",
        headers=ADMIN_HEADERS,
        json={"role": "viewer"},
    )
    assert updated.status_code == 200
    assert updated.json()["role"] == "viewer"

    audit = client.get("/api/audit?action=user.role_update", headers=ADMIN_HEADERS)
    assert audit.status_code == 200
    assert audit.json()["items"][0]["resource_id"] == user_id
    assert db_session.query(AdminAuditEvent).filter_by(action="user.role_update").count() == 1


def test_dev_token_compatibility_still_scopes_tasks() -> None:
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
    assert created.status_code == 201
    hidden = client.get(
        f"/api/tasks/{created.json()['id']}",
        headers={"Authorization": "Bearer dev-other-org-token"},
    )
    assert hidden.status_code == 404
