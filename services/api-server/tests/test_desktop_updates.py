from fastapi.testclient import TestClient

from app.main import app


def test_desktop_update_check_returns_stable_metadata(monkeypatch) -> None:
    monkeypatch.setenv("DESKTOP_UPDATE_STABLE_VERSION", "0.2.0")
    monkeypatch.setenv("DESKTOP_UPDATE_GITHUB_REPO", "luohao0308/harness")
    client = TestClient(app)

    response = client.get(
        "/api/desktop/updates/check",
        params={
            "current_version": "0.1.0",
            "channel": "stable",
            "platform": "darwin",
            "arch": "arm64",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["update_available"] is True
    assert body["channel"] == "stable"
    assert body["latest_version"] == "0.2.0"
    assert body["release_url"].endswith("/releases/tag/v0.2.0")
    assert body["metadata_url"].endswith("/v0.2.0/latest-mac.yml")


def test_desktop_update_check_supports_beta_channel(monkeypatch) -> None:
    monkeypatch.setenv("DESKTOP_UPDATE_STABLE_VERSION", "0.2.0")
    monkeypatch.setenv("DESKTOP_UPDATE_BETA_VERSION", "0.3.0-beta.2")
    client = TestClient(app)

    response = client.get(
        "/api/desktop/updates/check",
        params={
            "current_version": "0.3.0-beta.1",
            "channel": "beta",
            "platform": "win32",
            "arch": "x64",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["update_available"] is True
    assert body["channel"] == "beta"
    assert body["latest_version"] == "0.3.0-beta.2"
    assert body["metadata_url"].endswith("/v0.3.0-beta.2/latest.yml")


def test_desktop_update_check_reports_up_to_date(monkeypatch) -> None:
    monkeypatch.setenv("DESKTOP_UPDATE_STABLE_VERSION", "0.2.0")
    client = TestClient(app)

    response = client.get(
        "/api/desktop/updates/check",
        params={
            "current_version": "0.2.0",
            "channel": "stable",
            "platform": "linux",
            "arch": "x64",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["update_available"] is False
    assert body["metadata_url"].endswith("/v0.2.0/latest-linux.yml")


def test_desktop_update_check_rejects_invalid_version(monkeypatch) -> None:
    monkeypatch.setenv("DESKTOP_UPDATE_STABLE_VERSION", "0.2.0")
    client = TestClient(app)

    response = client.get(
        "/api/desktop/updates/check",
        params={
            "current_version": "not-a-version",
            "channel": "stable",
        },
    )

    assert response.status_code == 400
    assert "version must be semver" in response.json()["detail"]


def test_desktop_feedback_and_metrics_endpoints_record_samples(monkeypatch) -> None:
    client = TestClient(app)

    feedback = client.post(
        "/api/desktop/feedback",
        json={
            "title": "App crash",
            "description": "It crashed on startup.",
            "category": "bug",
            "channel": "beta",
            "app_version": "0.1.0-beta.1",
            "platform": "darwin",
            "logs": ["line 1", "line 2"],
            "screenshot_data_url": "data:image/png;base64,abc",
            "metadata": {"route": "/runs/1"},
        },
    )
    assert feedback.status_code == 200
    feedback_body = feedback.json()
    assert feedback_body["received"] is True
    assert feedback_body["feedback_id"].startswith("desktop-")

    startup = client.post(
        "/api/desktop/metrics",
        json={
            "metric_name": "startup_time_ms",
            "channel": "stable",
            "app_version": "0.1.0",
            "platform": "darwin",
            "value": 2500,
            "metadata": {"source": "main-process"},
        },
    )
    assert startup.status_code == 200

    crash = client.post(
        "/api/desktop/metrics",
        json={
            "metric_name": "crash_event",
            "channel": "stable",
            "app_version": "0.1.0",
            "platform": "darwin",
            "value": 1,
            "metadata": {"scope": "renderer"},
        },
    )
    assert crash.status_code == 200

    success = client.post(
        "/api/desktop/metrics",
        json={
            "metric_name": "sync_success",
            "channel": "stable",
            "app_version": "0.1.0",
            "platform": "darwin",
            "value": 1,
        },
    )
    assert success.status_code == 200

    failure = client.post(
        "/api/desktop/metrics",
        json={
            "metric_name": "sync_failure",
            "channel": "stable",
            "app_version": "0.1.0",
            "platform": "darwin",
            "value": 1,
        },
    )
    assert failure.status_code == 200

    summary = client.get("/api/desktop/metrics/summary")
    assert summary.status_code == 200
    body = summary.json()
    assert body["startup_count"] == 1
    assert body["startup_avg_ms"] == 2500
    assert body["startup_p95_ms"] == 2500
    assert body["crash_events"] == 1
    assert body["sync_successes"] == 1
    assert body["sync_failures"] == 1
    assert body["sync_success_rate"] == 0.5
