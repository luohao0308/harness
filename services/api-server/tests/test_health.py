from fastapi.testclient import TestClient

from app.main import app


def test_health_returns_ok() -> None:
    client = TestClient(app)

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "api-server"}


def test_openapi_schema_generates() -> None:
    schema = app.openapi()

    assert schema["info"]["title"] == "Forge Harness API"
    assert schema["info"]["summary"] == "Forge Harness API"
    assert "Model + Harness = Agent" in schema["info"]["description"]
    assert "/health" in schema["paths"]
