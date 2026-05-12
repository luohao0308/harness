from fastapi.testclient import TestClient

from app.main import app, build_cors_origins


def test_build_cors_origins_allows_vite_fallback_dev_port() -> None:
    origins = build_cors_origins()

    assert "http://127.0.0.1:5177" in origins
    assert "http://localhost:5177" in origins


def test_cors_preflight_allows_vite_fallback_dev_port() -> None:
    origin = "http://127.0.0.1:5177"

    response = TestClient(app).options(
        "/api/tasks",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "authorization",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == origin
