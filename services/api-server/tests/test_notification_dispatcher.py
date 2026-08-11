from urllib import request as urllib_request

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db.models import AlertEvent, AlertRule, MobileDevice, NotificationChannel, Task, utc_now
from app.main import app
from app.observability.alert_evaluator import evaluate_alert_rules

AUTH_HEADERS = {"Authorization": "Bearer dev-admin-token"}
client = TestClient(app)


def test_notification_channel_crud_redacts_secret() -> None:
    created = client.post(
        "/api/observability/notification-channels",
        headers=AUTH_HEADERS,
        json={
            "name": "ops-webhook",
            "kind": "webhook",
            "verified": True,
            "config_json": {"webhook_url": "https://hooks.example.test/a", "label": "ops"},
        },
    )
    assert created.status_code == 201, created.text
    payload = created.json()
    assert "webhook_url" not in payload["config_json"]
    assert payload["config_json"]["webhook_url_secret_ref"].startswith("secret://notification/")
    assert payload["config_json"]["label"] == "ops"

    listed = client.get("/api/observability/notification-channels", headers=AUTH_HEADERS)
    assert listed.status_code == 200
    assert listed.json()["items"][0]["name"] == "ops-webhook"


def test_verified_notification_channel_rejects_non_http_webhook_url() -> None:
    response = client.post(
        "/api/observability/notification-channels",
        headers=AUTH_HEADERS,
        json={
            "name": "local-file-webhook",
            "kind": "webhook",
            "verified": True,
            "config_json": {"webhook_url": "file:///tmp/harness-alert"},
        },
    )
    assert response.status_code == 400
    assert "HTTP(S)" in response.json()["detail"]


def test_alert_evaluator_dispatches_to_verified_webhook(db_session, monkeypatch) -> None:
    sent_payloads = []

    class FakeResponse:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    def fake_urlopen(http_request, timeout):
        sent_payloads.append((http_request.full_url, http_request.data, timeout))
        return FakeResponse()

    monkeypatch.setattr(urllib_request, "urlopen", fake_urlopen)
    db_session.add(
        NotificationChannel(
            organization_id="dev-org",
            name="ops-webhook",
            kind="webhook",
            config_json={"webhook_url": "https://hooks.example.test/a"},
            verified=True,
            created_at=utc_now(),
            updated_at=utc_now(),
        )
    )
    db_session.add(
        AlertRule(
            organization_id="dev-org",
            name="demo-alert",
            metric="tool_adapter_failure_rate",
            comparator=">=",
            threshold=0.0,
            window_seconds=300,
            enabled=True,
            severity="warning",
            notification_channels_json=["webhook:ops-webhook"],
            created_at=utc_now(),
            updated_at=utc_now(),
        )
    )
    db_session.add(
        Task(
            id="alert-dispatch-task",
            organization_id="dev-org",
            title="Alert dispatch",
            goal="Trigger alert",
            status="COMPLETED",
            model_provider="default",
            model_name="default",
            created_at=utc_now(),
            updated_at=utc_now(),
        )
    )
    db_session.flush()

    result = evaluate_alert_rules(session=db_session, organization_id="dev-org")

    assert result[0].triggered is True
    assert sent_payloads
    event = db_session.execute(select(AlertEvent)).scalar_one()
    assert event.context_json["notification_dispatch"][0]["status"] == "sent"


def test_alert_evaluator_dispatches_to_registered_mobile_device(db_session, monkeypatch) -> None:
    sent_payloads = []

    class FakeResponse:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    def fake_urlopen(http_request, timeout):
        sent_payloads.append((http_request.full_url, http_request.data, timeout))
        return FakeResponse()

    monkeypatch.setattr(urllib_request, "urlopen", fake_urlopen)
    db_session.add(
        MobileDevice(
            user_id="dev-engineer",
            organization_id="dev-org",
            platform="ios",
            push_token="ExponentPushToken[mobile-alert-token]",
            device_name="iPhone",
            notifications_enabled=True,
            preferences_json={"run_terminal": True},
            created_at=utc_now(),
            updated_at=utc_now(),
            last_seen_at=utc_now(),
        )
    )
    db_session.add(
        AlertRule(
            organization_id="dev-org",
            name="mobile-alert",
            metric="tool_adapter_failure_rate",
            comparator=">=",
            threshold=0.0,
            window_seconds=300,
            enabled=True,
            severity="critical",
            notification_channels_json=["mobile:*"],
            created_at=utc_now(),
            updated_at=utc_now(),
        )
    )
    db_session.add(
        Task(
            id="mobile-alert-task",
            organization_id="dev-org",
            title="Mobile alert dispatch",
            goal="Trigger mobile alert",
            status="COMPLETED",
            model_provider="default",
            model_name="default",
            created_at=utc_now(),
            updated_at=utc_now(),
        )
    )
    db_session.flush()

    result = evaluate_alert_rules(session=db_session, organization_id="dev-org")

    assert result[0].triggered is True
    assert sent_payloads
    _, raw_payload, _ = sent_payloads[0]
    payload = raw_payload.decode("utf-8")
    assert "ExponentPushToken[mobile-alert-token]" in payload
    assert "mobile-alert" in payload
    event = db_session.execute(select(AlertEvent)).scalar_one()
    assert event.context_json["notification_dispatch"][0]["kind"] == "mobile"
    assert event.context_json["notification_dispatch"][0]["status"] == "sent"
