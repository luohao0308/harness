import json
import zipfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

from fastapi.testclient import TestClient

from app.db.models import (
    ApiKey,
    ArchivedRecord,
    ModelCall,
    Organization,
    OrganizationMember,
    RetentionPolicy,
    Task,
    User,
    utc_now,
)
from app.main import app
from app.security.jwt_utils import hash_api_key

ADMIN_HEADERS = {"Authorization": "Bearer dev-admin-token"}


def test_retention_run_deletes_and_archives_expired_records(db_session) -> None:
    client = TestClient(app)
    old = datetime.now(UTC) - timedelta(days=120)
    task = Task(
        id="retention-task",
        organization_id="dev-org",
        created_by="dev-admin",
        title="Old task",
        goal="retention",
        status="COMPLETED",
        model_provider="default",
        model_name="default",
        created_at=old,
        updated_at=old,
    )
    model_call = ModelCall(
        id="old-model-call",
        task_id=task.id,
        model_provider="default",
        model_name="default",
        status="SUCCESS",
        request_json={},
        response_json={},
        created_at=old,
    )
    db_session.add_all(
        [
            task,
            model_call,
            RetentionPolicy(
                id="test-model-call-archive",
                organization_id="dev-org",
                entity_type="model_calls",
                action="archive",
                retention_days=90,
                delete_after_days=365,
                enabled=True,
                created_at=utc_now(),
                updated_at=utc_now(),
            ),
        ]
    )
    db_session.commit()

    response = client.post("/api/retention/run", headers=ADMIN_HEADERS)

    assert response.status_code == 202
    assert db_session.get(ModelCall, "old-model-call") is None
    archived = db_session.query(ArchivedRecord).filter_by(original_id="old-model-call").one()
    assert archived.entity_type == "model_calls"
    assert archived.organization_id == "dev-org"


def test_org_export_and_delete_dry_run_confirm(db_session) -> None:
    client = TestClient(app)
    org = Organization(
        id="delete-org",
        name="Delete Workspace",
        slug="delete-workspace",
        owner_user_id="delete-owner",
        plan="free",
        created_at=utc_now(),
    )
    user = User(
        id="delete-owner",
        email="delete-owner@example.com",
        name="Delete Owner",
        password_hash="pbkdf2_sha256$260000$dev-seed-salt$09b9f7c7137bdbfdf08c43ff1e58f4f4cf147352b2c88c53b8e5cd8523545525",
        email_verified=True,
        status="active",
        created_at=utc_now(),
        updated_at=utc_now(),
    )
    member = OrganizationMember(
        organization_id=org.id,
        user_id=user.id,
        role="owner",
        accepted_at=utc_now(),
    )
    task = Task(
        id="delete-org-task",
        organization_id=org.id,
        created_by=user.id,
        title="Delete me",
        goal="delete org",
        status="CREATED",
        model_provider="default",
        model_name="default",
        created_at=utc_now(),
        updated_at=utc_now(),
    )
    db_session.add_all([org, user, member, task])
    db_session.commit()

    login = client.post(
        "/api/auth/login",
        json={"email": user.email, "password": "dev-password", "organization_id": org.id},
    )
    assert login.status_code == 200
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    api_key = client.post(
        "/api/api-keys",
        headers=headers,
        json={"name": "export verifier", "scopes": ["run:read"]},
    )
    assert api_key.status_code == 201
    api_key_hash = hash_api_key(api_key.json()["key"])

    export = client.post(f"/api/organizations/{org.id}/export", headers=headers)
    assert export.status_code == 202
    assert export.json()["status"] == "completed"
    assert export.json()["file_sha256"]
    export_file = Path(export.json()["file_path"])
    with zipfile.ZipFile(export_file) as archive:
        users = json.loads(archive.read("users.json"))
        api_keys = json.loads(archive.read("api_keys.json"))
    assert users[0]["password_hash"] == "[redacted]"
    assert api_keys[0]["key_hash"] == "[redacted]"
    export_payload = json.dumps({"users": users, "api_keys": api_keys})
    assert user.password_hash not in export_payload
    assert api_key_hash not in export_payload
    assert db_session.get(ApiKey, api_key.json()["id"]) is not None

    preview = client.delete(f"/api/organizations/{org.id}/dry-run", headers=headers)
    assert preview.status_code == 200
    assert preview.json()["counts"]["tasks"] == 1

    deleted = client.request(
        "DELETE",
        f"/api/organizations/{org.id}",
        headers=headers,
        json={"confirmation_name": org.name},
    )
    assert deleted.status_code == 200
    assert deleted.json()["deleted_counts_json"]["tasks"] == 1
    assert db_session.get(Organization, org.id) is None
