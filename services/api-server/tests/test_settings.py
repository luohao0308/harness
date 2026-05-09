from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.model_gateway import AnthropicCompatibleModelGateway, ModelResponse
from app.db.models import AdminAuditEvent, SystemSetting
from app.main import app
from tests.conftest import AUTH_HEADERS

ADMIN_HEADERS = {"Authorization": "Bearer dev-admin-token"}


def test_settings_read_allowed_for_engineer_and_write_requires_admin() -> None:
    client = TestClient(app)

    engineer = client.get("/api/settings/models", headers=AUTH_HEADERS)
    admin = client.get("/api/settings/models", headers=ADMIN_HEADERS)
    blocked_update = client.put(
        "/api/settings/models",
        headers=AUTH_HEADERS,
        json=admin.json(),
    )

    assert engineer.status_code == 200
    assert admin.status_code == 200
    assert blocked_update.status_code == 403
    assert admin.json()["default_provider"] == "minimax"
    assert admin.json()["default_model"] == "MiniMax-M2.7-highspeed"


def test_default_model_settings_include_minimax_preset() -> None:
    client = TestClient(app)

    response = client.get("/api/settings/models", headers=ADMIN_HEADERS)

    assert response.status_code == 200
    payload = response.json()
    minimax = next(provider for provider in payload["providers"] if provider["name"] == "minimax")
    assert minimax["api_format"] == "anthropic"
    assert minimax["model"] == "MiniMax-M2.7-highspeed"
    assert minimax["base_url"] == "https://api.minimaxi.com/anthropic"
    assert minimax["api_key_env"] == "MINIMAX_API_KEY"
    assert minimax["model_context_window_tokens"] == 400000


def test_model_settings_normalizes_legacy_minimax_preset(
    db_session: Session,
) -> None:
    db_session.add(
        SystemSetting(
            organization_id="dev-org",
            key="settings.models",
            value_json={
                "default_provider": "minimax",
                "default_model": "MiniMax-M2.7-highspeed",
                "providers": [
                    {
                        "name": "minimax",
                        "api_format": "anthropic",
                        "model": "MiniMax-M2.7-highspeed",
                        "base_url": "https://api.minimaxi.com/anthropic",
                        "api_key": "secret-key",
                        "api_key_env": "MINIMAX_API_KEY",
                        "model_context_window_tokens": 204800,
                        "rate_limit_rpm": 60,
                        "rate_limit_tpm": 204800,
                    }
                ],
                "rate_limits": {"rpm": 60, "tpm": 204800},
                "health": {"status": "healthy", "updated_at": None},
            },
            updated_by="dev-admin",
        )
    )
    db_session.flush()
    client = TestClient(app)

    response = client.get("/api/settings/models", headers=ADMIN_HEADERS)

    assert response.status_code == 200
    minimax = next(
        provider for provider in response.json()["providers"] if provider["name"] == "minimax"
    )
    assert minimax["model_context_window_tokens"] == 400000
    assert minimax["rate_limit_tpm"] == 400000
    assert minimax["api_key"] == "secret-key"


def test_policy_settings_round_trip_for_admin(db_session: Session) -> None:
    client = TestClient(app)

    policies = client.get("/api/settings/policies", headers=ADMIN_HEADERS)
    assert policies.status_code == 200

    updated = client.put(
        "/api/settings/policies",
        headers=ADMIN_HEADERS,
        json=policies.json(),
    )
    assert updated.status_code == 200
    assert updated.json()["audit"]["tool_calls"] is True
    assert updated.json()["sandbox"]["memory_mb"] == 1024
    assert updated.json()["sandbox"]["cpus"] == "1.0"
    assert updated.json()["sandbox"]["workspace_quota_mb"] == 1024
    assert updated.json()["sandbox"]["network_allowlist"] == []

    audit_event = db_session.execute(select(AdminAuditEvent)).scalar_one()
    assert audit_event.event_type == "ADMIN_ACTION"
    assert audit_event.resource_id == "policies"
    assert audit_event.action == "settings.policies.update"


def test_model_settings_persist_per_organization(db_session: Session) -> None:
    client = TestClient(app)

    current = client.get("/api/settings/models", headers=ADMIN_HEADERS).json()
    current["default_model"] = "local Agent CLI-code-compatible"

    updated = client.put("/api/settings/models", headers=ADMIN_HEADERS, json=current)
    reloaded = client.get("/api/settings/models", headers=ADMIN_HEADERS)

    assert updated.status_code == 200
    assert reloaded.json()["default_model"] == "local Agent CLI-code-compatible"
    setting = db_session.execute(select(SystemSetting)).scalar_one()
    assert setting.key == "settings.models"
    assert setting.value_json["default_model"] == "local Agent CLI-code-compatible"


def test_model_settings_health_endpoint_uses_current_settings() -> None:
    client = TestClient(app)

    current = client.get("/api/settings/models", headers=ADMIN_HEADERS).json()
    current["providers"] = [
        {
            "name": "openai-compatible",
            "status": "degraded",
            "rate_limit_rpm": 60,
            "model": "configured-model",
        }
    ]
    client.put("/api/settings/models", headers=ADMIN_HEADERS, json=current)

    health = client.get("/api/settings/models/health", headers=ADMIN_HEADERS)

    assert health.status_code == 200
    payload = next(
        item for item in health.json()["items"] if item["provider"] == "openai-compatible"
    )
    assert payload["provider"] == "openai-compatible"
    assert payload["model"] == "configured-model"
    assert payload["status"] == "healthy"
    assert payload["mode"] == "mock"
    assert payload["circuit_status"] == "closed"


def test_model_settings_health_endpoint_probes_real_provider(
    monkeypatch,
    db_session: Session,
) -> None:
    client = TestClient(app)
    captured = {}

    def fake_complete(self, request_payload):
        captured["provider"] = request_payload.model_provider
        captured["model"] = request_payload.model_name
        return ModelResponse(
            content="{}",
            model_provider=request_payload.model_provider,
            model_name=request_payload.model_name,
            usage={"prompt_tokens": 1, "completion_tokens": 1},
        )

    monkeypatch.setattr(AnthropicCompatibleModelGateway, "complete", fake_complete)

    current = client.get("/api/settings/models", headers=ADMIN_HEADERS).json()
    current["default_provider"] = "minimax"
    current["default_model"] = "MiniMax-M2.7-highspeed"
    current["providers"] = [
        {
            "name": "minimax",
            "status": "degraded",
            "api_format": "anthropic",
            "model": "MiniMax-M2.7-highspeed",
            "rate_limit_rpm": 60,
            "rate_limit_tpm": 120000,
            "base_url": "https://api.minimaxi.com/anthropic",
            "api_key": "secret-key",
        }
    ]
    client.put("/api/settings/models", headers=ADMIN_HEADERS, json=current)

    health = client.get("/api/settings/models/health", headers=ADMIN_HEADERS)

    assert health.status_code == 200
    payload = health.json()["items"][0]
    assert payload["status"] == "healthy"
    assert payload["mode"] == "probe"
    assert captured == {"provider": "minimax", "model": "MiniMax-M2.7-highspeed"}
    setting = db_session.execute(select(SystemSetting)).scalar_one()
    assert setting.value_json["health"]["status"] == "healthy"
    assert setting.value_json["providers"][0]["last_health"]["mode"] == "probe"
