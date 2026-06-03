import importlib.util
import sys
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.bootstrap import first_admin
from app.bootstrap.first_admin import bootstrap_first_admin
from app.core.config import Settings, get_settings, validate_startup_settings
from app.db.models import Organization, OrganizationMember, User
from app.main import app
from app.security.jwt_utils import verify_password

REPO_ROOT = Path(__file__).resolve().parents[3]


def _settings(**overrides: object) -> Settings:
    values = {
        "APP_ENV": "test",
        "AUTH_JWT_SECRET": "test-harness-jwt-secret-32-characters-min",
        "HARNESS_INITIAL_ADMIN_EMAIL": "",
        "HARNESS_INITIAL_ADMIN_PASSWORD": "",
    }
    values.update(overrides)
    return Settings(**values)


def _load_create_admin_script() -> Any:
    path = REPO_ROOT / "scripts/create-admin.py"
    spec = importlib.util.spec_from_file_location("create_admin_script", path)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["create_admin_script"] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_bootstrap_first_admin_creates_owner_and_login_succeeds(db_session: Session) -> None:
    admin = bootstrap_first_admin(
        db_session,
        settings=_settings(
            HARNESS_INITIAL_ADMIN_EMAIL="Admin@Example.com",
            HARNESS_INITIAL_ADMIN_PASSWORD="Strong!Pass1",
        ),
    )

    assert admin is not None
    assert admin.email == "admin@example.com"
    assert verify_password("Strong!Pass1", admin.password_hash)
    org = db_session.execute(select(Organization)).scalar_one()
    membership = db_session.execute(select(OrganizationMember)).scalar_one()
    assert org.owner_user_id == admin.id
    assert membership.user_id == admin.id
    assert membership.role == "owner"

    response = TestClient(app).post(
        "/api/auth/login",
        json={"email": "admin@example.com", "password": "Strong!Pass1"},
    )
    assert response.status_code == 200
    assert response.json()["access_token"]


def test_bootstrap_first_admin_is_idempotent_when_users_exist(db_session: Session) -> None:
    created = bootstrap_first_admin(
        db_session,
        settings=_settings(
            HARNESS_INITIAL_ADMIN_EMAIL="admin@example.com",
            HARNESS_INITIAL_ADMIN_PASSWORD="Strong!Pass1",
        ),
    )
    skipped = bootstrap_first_admin(
        db_session,
        settings=_settings(
            HARNESS_INITIAL_ADMIN_EMAIL="second@example.com",
            HARNESS_INITIAL_ADMIN_PASSWORD="Strong!Pass2",
        ),
    )

    assert created is not None
    assert skipped is None
    assert db_session.query(User).count() == 1


def test_bootstrap_first_admin_handles_concurrent_create_race(
    monkeypatch: pytest.MonkeyPatch,
    db_session: Session,
) -> None:
    original_create_admin_user = first_admin.create_admin_user

    def create_then_raise(*args: Any, **kwargs: Any) -> User:
        original_create_admin_user(*args, **kwargs)
        raise IntegrityError("insert", {}, Exception("duplicate"))

    monkeypatch.setattr(first_admin, "create_admin_user", create_then_raise)

    result = bootstrap_first_admin(
        db_session,
        settings=_settings(
            HARNESS_INITIAL_ADMIN_EMAIL="race@example.com",
            HARNESS_INITIAL_ADMIN_PASSWORD="Strong!Pass1",
        ),
    )

    assert result is None
    assert db_session.query(User).count() == 1


def test_bootstrap_first_admin_warns_when_empty_without_env(
    caplog: pytest.LogCaptureFixture,
    db_session: Session,
) -> None:
    result = bootstrap_first_admin(db_session, settings=_settings())

    assert result is None
    assert "No users exist" in caplog.text
    assert db_session.query(User).count() == 0


def test_auth_secret_validation_rejects_missing_and_placeholder() -> None:
    with pytest.raises(RuntimeError, match="AUTH_JWT_SECRET is required"):
        validate_startup_settings(_settings(AUTH_JWT_SECRET=""))
    with pytest.raises(RuntimeError, match="placeholder"):
        validate_startup_settings(
            _settings(AUTH_JWT_SECRET="replace-with-openssl-rand-hex-32")
        )


def test_lifespan_rejects_placeholder_auth_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("AUTH_JWT_SECRET", "replace-with-openssl-rand-hex-32")
    monkeypatch.setattr("app.main.bootstrap_first_admin", lambda session, settings: None)
    get_settings.cache_clear()
    try:
        with pytest.raises(RuntimeError, match="placeholder"):
            with TestClient(app):
                pass
    finally:
        get_settings.cache_clear()


def test_create_admin_script_noninteractive_creates_owner(
    monkeypatch: pytest.MonkeyPatch,
    db_session: Session,
) -> None:
    script = _load_create_admin_script()

    class SessionFactory:
        def __call__(self) -> Session:
            return db_session

    monkeypatch.setattr("app.cli.create_admin.SessionLocal", SessionFactory())

    exit_code = script.main(
        [
            "--email",
            "script-admin@example.com",
            "--password",
            "Strong!Pass1",
            "--organization-name",
            "Script Workspace",
        ]
    )

    assert exit_code == 0
    user = db_session.execute(
        select(User).where(User.email == "script-admin@example.com")
    ).scalar_one()
    assert verify_password("Strong!Pass1", user.password_hash)
