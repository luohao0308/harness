from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.main import app


def test_dev_admin_token_is_rejected_in_production(monkeypatch) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("AUTH_JWT_SECRET", "production-test-secret-32-characters-min")
    monkeypatch.setenv("HARNESS_SECRET_ENCRYPTION_KEY", "production-secret-encryption-key-32-min")
    get_settings.cache_clear()
    try:
        response = TestClient(app).get(
            "/api/agents",
            headers={"Authorization": "Bearer dev-admin-token"},
        )
    finally:
        get_settings.cache_clear()

    assert response.status_code == 401


def test_dev_admin_token_still_works_in_test_environment(monkeypatch) -> None:
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("AUTH_JWT_SECRET", "test-harness-jwt-secret-32-characters-min")
    get_settings.cache_clear()
    try:
        response = TestClient(app).get(
            "/api/agents",
            headers={"Authorization": "Bearer dev-admin-token"},
        )
    finally:
        get_settings.cache_clear()

    assert response.status_code == 200
