from fastapi.testclient import TestClient

from app.core.config import Settings, get_settings, public_registration_enabled
from app.db.models import AdminAuditEvent, ApiKey, OrganizationMember, User, utc_now
from app.main import app
from app.security.jwt_utils import hash_api_key
from tests.conftest import AUTH_HEADERS

ADMIN_HEADERS = {"Authorization": "Bearer dev-admin-token"}
TINY_PNG = b"\x89PNG\r\n\x1a\navatar-bytes"
MEDIUM_PNG = b"\x89PNG\r\n\x1a\n" + b"x" * (600 * 1024)
OVERSIZED_PNG = b"\x89PNG\r\n\x1a\n" + b"x" * (2 * 1024 * 1024 + 1)
FAKE_API_KEY = "hk_avatar_api_key_test"


def test_auth_config_reports_registration_and_hides_placeholder_oauth() -> None:
    client = TestClient(app)

    response = client.get("/api/auth/config")

    assert response.status_code == 200
    assert response.json() == {
        "public_registration_enabled": True,
        "oauth_providers": [],
    }


def test_public_registration_defaults_to_closed_in_production() -> None:
    settings = Settings(
        _env_file=None,
        APP_ENV="production",
        AUTH_JWT_SECRET="production-test-secret-32-characters-min",
        HARNESS_SECRET_ENCRYPTION_KEY="production-secret-encryption-key-32-min",
    )

    assert public_registration_enabled(settings) is False
    assert public_registration_enabled(
        settings.model_copy(update={"auth_public_registration_enabled": True})
    ) is True


def test_register_rejects_when_public_registration_disabled(monkeypatch) -> None:
    monkeypatch.setenv("AUTH_PUBLIC_REGISTRATION_ENABLED", "false")
    get_settings.cache_clear()
    try:
        response = TestClient(app).post(
            "/api/auth/register",
            json={
                "email": "blocked-register@example.com",
                "password": "correct-password",
                "name": "Blocked Register",
                "organization_name": "Blocked Workspace",
            },
        )
    finally:
        get_settings.cache_clear()

    assert response.status_code == 403
    assert response.json()["detail"] == "Public registration is disabled"


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


def test_upload_avatar_stores_image_in_database_and_returns_me_payload(db_session) -> None:
    client = TestClient(app)
    registered = client.post(
        "/api/auth/register",
        json={
            "email": "avatar-owner@example.com",
            "password": "correct-password",
            "name": "Avatar Owner",
            "organization_name": "Avatar Workspace",
        },
    )
    assert registered.status_code == 201
    headers = {"Authorization": f"Bearer {registered.json()['access_token']}"}

    uploaded = client.post(
        "/api/auth/me/avatar",
        headers=headers,
        files={"file": ("avatar.png", TINY_PNG, "image/png")},
    )

    assert uploaded.status_code == 200
    payload = uploaded.json()
    assert payload["avatar_data_url"].startswith("data:image/png;base64,")
    user = db_session.query(User).filter_by(email="avatar-owner@example.com").one()
    assert user.avatar_mime_type == "image/png"
    assert user.avatar_content == TINY_PNG
    assert user.avatar_sha256
    assert user.avatar_updated_at is not None

    me = client.get("/api/auth/me", headers=headers)
    assert me.status_code == 200
    assert me.json()["avatar_data_url"] == payload["avatar_data_url"]


def test_upload_avatar_accepts_common_phone_avatar_after_frontend_compression(db_session) -> None:
    client = TestClient(app)
    registered = client.post(
        "/api/auth/register",
        json={
            "email": "avatar-medium@example.com",
            "password": "correct-password",
            "name": "Avatar Medium",
            "organization_name": "Avatar Medium Workspace",
        },
    )
    assert registered.status_code == 201
    headers = {"Authorization": f"Bearer {registered.json()['access_token']}"}

    uploaded = client.post(
        "/api/auth/me/avatar",
        headers=headers,
        files={"file": ("avatar.png", MEDIUM_PNG, "image/png")},
    )

    assert uploaded.status_code == 200
    user = db_session.query(User).filter_by(email="avatar-medium@example.com").one()
    assert user.avatar_mime_type == "image/png"
    assert len(user.avatar_content or b"") == len(MEDIUM_PNG)


def test_avatar_upload_rejects_dev_token_and_invalid_image() -> None:
    client = TestClient(app)

    dev_response = client.post(
        "/api/auth/me/avatar",
        headers=AUTH_HEADERS,
        files={"file": ("avatar.png", TINY_PNG, "image/png")},
    )
    assert dev_response.status_code == 403

    registered = client.post(
        "/api/auth/register",
        json={
            "email": "bad-avatar@example.com",
            "password": "correct-password",
            "name": "Bad Avatar",
            "organization_name": "Bad Avatar Workspace",
        },
    )
    headers = {"Authorization": f"Bearer {registered.json()['access_token']}"}
    invalid = client.post(
        "/api/auth/me/avatar",
        headers=headers,
        files={"file": ("avatar.txt", b"not an image", "text/plain")},
    )
    assert invalid.status_code == 415


def test_avatar_upload_rejects_dev_token_even_when_legacy_dev_user_exists(db_session) -> None:
    client = TestClient(app)
    legacy_dev_user = User(
        id="dev-engineer",
        email="legacy-dev-engineer@example.com",
        name="Legacy Dev Engineer",
        password_hash="legacy",
        email_verified=True,
        status="active",
        created_at=utc_now(),
        updated_at=utc_now(),
    )
    db_session.add(legacy_dev_user)
    db_session.commit()

    response = client.post(
        "/api/auth/me/avatar",
        headers=AUTH_HEADERS,
        files={"file": ("avatar.png", TINY_PNG, "image/png")},
    )

    assert response.status_code == 403
    db_session.refresh(legacy_dev_user)
    assert legacy_dev_user.avatar_content is None


def test_avatar_upload_rejects_api_key_principal(db_session) -> None:
    client = TestClient(app)
    registered = client.post(
        "/api/auth/register",
        json={
            "email": "api-key-avatar@example.com",
            "password": "correct-password",
            "name": "API Key Avatar",
            "organization_name": "API Key Avatar Workspace",
        },
    )
    assert registered.status_code == 201
    user = db_session.query(User).filter_by(email="api-key-avatar@example.com").one()
    membership = db_session.query(OrganizationMember).filter_by(user_id=user.id).one()
    db_session.add(
        ApiKey(
            id="avatar-api-key",
            organization_id=membership.organization_id,
            user_id=user.id,
            name="avatar-api-key",
            key_hash=hash_api_key(FAKE_API_KEY),
            key_prefix="avatar",
            scope_json=["run:read"],
            created_at=utc_now(),
        )
    )
    db_session.commit()

    response = client.post(
        "/api/auth/me/avatar",
        headers={"Authorization": f"Bearer {FAKE_API_KEY}"},
        files={"file": ("avatar.png", TINY_PNG, "image/png")},
    )

    assert response.status_code == 403
    db_session.refresh(user)
    assert user.avatar_content is None


def test_avatar_upload_rejects_oversized_and_mismatched_image(db_session) -> None:
    client = TestClient(app)
    registered = client.post(
        "/api/auth/register",
        json={
            "email": "avatar-boundary@example.com",
            "password": "correct-password",
            "name": "Avatar Boundary",
            "organization_name": "Avatar Boundary Workspace",
        },
    )
    assert registered.status_code == 201
    headers = {"Authorization": f"Bearer {registered.json()['access_token']}"}

    oversized = client.post(
        "/api/auth/me/avatar",
        headers=headers,
        files={"file": ("avatar.png", OVERSIZED_PNG, "image/png")},
    )
    assert oversized.status_code == 413

    mismatch = client.post(
        "/api/auth/me/avatar",
        headers=headers,
        files={"file": ("avatar.png", b"GIF89a-not-a-png", "image/png")},
    )
    assert mismatch.status_code == 400

    user = db_session.query(User).filter_by(email="avatar-boundary@example.com").one()
    assert user.avatar_content is None


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
