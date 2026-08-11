from fastapi.testclient import TestClient

from app.main import app, build_cors_origin_regex, build_cors_origins


def test_build_cors_origins_allows_dev_console_ports() -> None:
    origins = build_cors_origins()

    assert "http://127.0.0.1:5177" in origins
    assert "http://localhost:5177" in origins
    assert "http://127.0.0.1:15174" in origins
    assert "http://localhost:15174" in origins
    assert "http://0.0.0.0:15174" in origins
    assert "http://[::1]:15174" in origins
    assert "harness-app://renderer" in origins
    assert build_cors_origin_regex() is not None


def test_cors_preflight_allows_dev_console_ports() -> None:
    client = TestClient(app)

    for origin in [
        "harness-app://renderer",
        "http://127.0.0.1:5177",
        "http://127.0.0.1:15174",
        "http://0.0.0.0:15174",
        "http://192.168.1.23:15174",
    ]:
        response = client.options(
            "/api/tasks",
            headers={
                "Origin": origin,
                "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Headers": "authorization",
            },
        )

        assert response.status_code == 200
        assert response.headers["access-control-allow-origin"] == origin
