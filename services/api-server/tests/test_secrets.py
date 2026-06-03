import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.secrets import ENV_IMPORT_SPECS
from app.db.models import StoredSecret
from app.main import app
from app.security.secrets import SECRET_PURPOSE_MODEL_PROVIDER, disable_secret, resolve_secret
from tests.conftest import AUTH_HEADERS

ADMIN_HEADERS = {"Authorization": "Bearer dev-admin-token"}
OPERATOR_HEADERS = {"Authorization": "Bearer dev-operator-token"}


def test_secret_api_encrypts_and_resolves_user_before_org(db_session: Session) -> None:
    client = TestClient(app)

    org_saved = client.put(
        "/api/secrets",
        headers=ADMIN_HEADERS,
        json={
            "scope": "org",
            "provider": "deepseek-pro",
            "purpose": "model_provider",
            "secret_value": "org-secret-value",
        },
    )
    user_saved = client.put(
        "/api/secrets",
        headers=AUTH_HEADERS,
        json={
            "scope": "user",
            "provider": "deepseek-pro",
            "purpose": "model_provider",
            "secret_value": "user-secret-value",
        },
    )

    assert org_saved.status_code == 200
    assert user_saved.status_code == 200
    assert "org-secret-value" not in org_saved.text
    assert "user-secret-value" not in user_saved.text
    rows = list(db_session.execute(select(StoredSecret)).scalars())
    assert len(rows) == 2
    assert all("secret-value" not in row.encrypted_value for row in rows)

    engineer_resolution = resolve_secret(
        db_session,
        organization_id="dev-org",
        user_id="dev-engineer",
        provider="deepseek-pro",
        purpose=SECRET_PURPOSE_MODEL_PROVIDER,
    )
    admin_resolution = resolve_secret(
        db_session,
        organization_id="dev-org",
        user_id="dev-admin",
        provider="deepseek-pro",
        purpose=SECRET_PURPOSE_MODEL_PROVIDER,
    )

    assert engineer_resolution.value == "user-secret-value"
    assert engineer_resolution.source == "stored_secret_user"
    assert admin_resolution.value == "org-secret-value"
    assert admin_resolution.source == "stored_secret_org"


def test_engineer_cannot_manage_org_secret(db_session: Session) -> None:
    client = TestClient(app)
    created = client.put(
        "/api/secrets",
        headers=ADMIN_HEADERS,
        json={
            "scope": "org",
            "provider": "tavily",
            "purpose": "web_research",
            "secret_value": "tavily-secret",
        },
    )
    assert created.status_code == 200

    blocked_create = client.put(
        "/api/secrets",
        headers=AUTH_HEADERS,
        json={
            "scope": "org",
            "provider": "dify",
            "purpose": "knowledge_connector",
            "secret_value": "dify-secret",
        },
    )
    blocked_delete = client.delete(f"/api/secrets/{created.json()['id']}", headers=AUTH_HEADERS)

    assert blocked_create.status_code == 403
    assert blocked_delete.status_code == 404
    row = db_session.get(StoredSecret, created.json()["id"])
    assert row is not None
    assert row.status == "active"


def test_disable_secret_helper_rejects_other_user_secret(db_session: Session) -> None:
    client = TestClient(app)
    created = client.put(
        "/api/secrets",
        headers=ADMIN_HEADERS,
        json={
            "scope": "user",
            "provider": "dify",
            "purpose": "knowledge_connector",
            "secret_value": "admin-user-secret",
        },
    )
    assert created.status_code == 200

    denied = disable_secret(
        db_session,
        organization_id="dev-org",
        actor_id="dev-engineer",
        secret_id=created.json()["id"],
        allow_org=False,
    )

    assert denied is None
    row = db_session.get(StoredSecret, created.json()["id"])
    assert row is not None
    assert row.status == "active"


def test_secret_list_filters_user_scope_and_delete_disables_resolution(
    db_session: Session,
) -> None:
    client = TestClient(app)
    org_saved = client.put(
        "/api/secrets",
        headers=ADMIN_HEADERS,
        json={
            "scope": "org",
            "provider": "tavily",
            "purpose": "web_research",
            "secret_value": "org-tavily-secret",
        },
    )
    engineer_saved = client.put(
        "/api/secrets",
        headers=AUTH_HEADERS,
        json={
            "scope": "user",
            "provider": "tavily",
            "purpose": "web_research",
            "secret_value": "engineer-tavily-secret",
        },
    )
    admin_user_saved = client.put(
        "/api/secrets",
        headers=ADMIN_HEADERS,
        json={
            "scope": "user",
            "provider": "tavily-admin",
            "purpose": "web_research",
            "secret_value": "admin-private-secret",
        },
    )

    assert org_saved.status_code == 200
    assert engineer_saved.status_code == 200
    assert admin_user_saved.status_code == 200

    engineer_list = client.get("/api/secrets", headers=AUTH_HEADERS)
    assert engineer_list.status_code == 200
    engineer_items = engineer_list.json()["items"]
    engineer_ids = {item["id"] for item in engineer_items}
    assert org_saved.json()["id"] in engineer_ids
    assert engineer_saved.json()["id"] in engineer_ids
    assert admin_user_saved.json()["id"] not in engineer_ids
    assert "org-tavily-secret" not in engineer_list.text
    assert "engineer-tavily-secret" not in engineer_list.text
    assert "admin-private-secret" not in engineer_list.text

    operator_list = client.get("/api/secrets", headers=OPERATOR_HEADERS)
    assert operator_list.status_code == 200
    assert {item["id"] for item in operator_list.json()["items"]} == {org_saved.json()["id"]}

    deleted = client.delete(f"/api/secrets/{engineer_saved.json()['id']}", headers=AUTH_HEADERS)
    assert deleted.status_code == 204
    row = db_session.get(StoredSecret, engineer_saved.json()["id"])
    assert row is not None
    assert row.status == "disabled"

    resolution = resolve_secret(
        db_session,
        organization_id="dev-org",
        user_id="dev-engineer",
        provider="tavily",
        purpose="web_research",
    )
    assert resolution.value == "org-tavily-secret"
    assert resolution.source == "stored_secret_org"
    assert engineer_saved.json()["id"] not in {
        item["id"] for item in client.get("/api/secrets", headers=AUTH_HEADERS).json()["items"]
    }


def test_import_env_admin_only_imports_business_keys(
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = TestClient(app)
    for env_name, _, _ in ENV_IMPORT_SPECS:
        monkeypatch.delenv(env_name, raising=False)
    monkeypatch.setenv("TAVILY_API_KEY", "tavily-env-secret")

    blocked = client.post("/api/secrets/import-env", headers=AUTH_HEADERS)
    imported = client.post("/api/secrets/import-env", headers=ADMIN_HEADERS)

    assert blocked.status_code == 403
    assert imported.status_code == 200
    payload = imported.json()
    assert len(payload["imported"]) == 1
    item = payload["imported"][0]
    assert item["provider"] == "tavily"
    assert item["purpose"] == "web_research"
    assert item["scope"] == "org"
    assert item["source"] == "stored_secret_org"
    assert "tavily-env-secret" not in imported.text
    row = db_session.get(StoredSecret, item["id"])
    assert row is not None
    assert "tavily-env-secret" not in row.encrypted_value
