from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.main import app

client = TestClient(app)


def test_liveness_returns_ok() -> None:
    response = client.get("/api/health/liveness")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_readiness_can_check_llm_only() -> None:
    response = client.get("/api/health/readiness?check=llm")
    assert response.status_code == 200
    payload = response.json()
    assert payload["ready"] is True
    assert payload["llm"]["healthy_provider_count"] >= 1


def test_readiness_reports_redis_failure(monkeypatch) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "redis_url", "redis://127.0.0.1:1/0")
    response = client.get("/api/health/readiness?check=redis")
    assert response.status_code == 503
    payload = response.json()
    assert payload["ready"] is False
    assert payload["redis"]["status"] == "error"
