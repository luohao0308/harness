from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.model_gateway import ModelResponse, OpenAICompatibleModelGateway
from app.api.settings import _model_settings_response_value, _store_model_provider_secrets
from app.db.models import AdminAuditEvent, StoredSecret, SystemSetting
from app.main import app
from app.security.auth import AuthenticatedPrincipal
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
    assert admin.json()["default_provider"] == "deepseek-flash"
    assert admin.json()["default_model"] == "deepseek-v4-flash"


def test_default_model_settings_include_deepseek_presets() -> None:
    client = TestClient(app)

    response = client.get("/api/settings/models", headers=ADMIN_HEADERS)

    assert response.status_code == 200
    payload = response.json()
    flash = next(
        provider for provider in payload["providers"] if provider["name"] == "deepseek-flash"
    )
    pro = next(provider for provider in payload["providers"] if provider["name"] == "deepseek-pro")
    assert flash["api_format"] == "openai"
    assert flash["model"] == "deepseek-v4-flash"
    assert flash["base_url"] == "https://api.deepseek.com"
    assert flash["api_key_env"] == "DEEPSEEK_API_KEY"
    assert flash["model_context_window_tokens"] == 1000000
    assert flash["max_output_tokens"] == 384000
    assert pro["model"] == "deepseek-v4-pro"
    assert pro["api_key_env"] == "DEEPSEEK_API_KEY"


def test_model_settings_normalizes_legacy_minimax_to_deepseek(
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
                    },
                    {
                        "name": "deepseek",
                        "api_format": "openai",
                        "model": "deepseek-chat",
                        "base_url": "https://api.deepseek.com/v1",
                        "api_key_env": "DEEPSEEK_API_KEY",
                    },
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
    payload = response.json()
    assert payload["default_provider"] == "deepseek-flash"
    assert payload["default_model"] == "deepseek-v4-flash"
    assert all(provider["name"] != "minimax" for provider in payload["providers"])
    assert all(provider["name"] != "deepseek" for provider in payload["providers"])
    flash = next(
        provider for provider in payload["providers"] if provider["name"] == "deepseek-flash"
    )
    assert flash["model_context_window_tokens"] == 1000000
    assert flash["rate_limit_tpm"] == 1000000
    assert flash["api_key_env"] == "DEEPSEEK_API_KEY"


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
    current["default_model"] = "external-model-compatible"

    updated = client.put("/api/settings/models", headers=ADMIN_HEADERS, json=current)
    reloaded = client.get("/api/settings/models", headers=ADMIN_HEADERS)

    assert updated.status_code == 200
    assert reloaded.json()["default_model"] == "external-model-compatible"
    setting = db_session.execute(select(SystemSetting)).scalar_one()
    assert setting.key == "settings.models"
    assert setting.value_json["default_model"] == "external-model-compatible"


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
    saved = client.put("/api/settings/models", headers=ADMIN_HEADERS, json=current)
    assert saved.status_code == 200

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
    captured = []

    def fake_complete(self, request_payload):
        captured.append(
            {
                "provider": request_payload.model_provider,
                "model": request_payload.model_name,
                "response_format": request_payload.response_format,
            }
        )
        return ModelResponse(
            content="{}",
            model_provider=request_payload.model_provider,
            model_name=request_payload.model_name,
            usage={"prompt_tokens": 1, "completion_tokens": 1},
        )

    monkeypatch.setattr(OpenAICompatibleModelGateway, "complete", fake_complete)

    current = client.get("/api/settings/models", headers=ADMIN_HEADERS).json()
    current["default_provider"] = "deepseek-pro"
    current["default_model"] = "deepseek-v4-pro"
    current["providers"] = [
        {
            "name": "deepseek-pro",
            "status": "degraded",
            "api_format": "openai",
            "model": "deepseek-v4-pro",
            "rate_limit_rpm": 60,
            "rate_limit_tpm": 120000,
            "base_url": "https://api.deepseek.com",
            "api_key": "secret-key",
        }
    ]
    saved = client.put("/api/settings/models", headers=ADMIN_HEADERS, json=current)
    assert saved.status_code == 200
    saved_provider = saved.json()["providers"][0]
    assert saved_provider["api_key"] == ""
    assert saved_provider["api_key_configured"] is True
    assert saved_provider["api_key_source"] == "stored_secret_org"
    assert saved_provider["api_key_secret_id"]

    health = client.get("/api/settings/models/health", headers=ADMIN_HEADERS)

    assert health.status_code == 200
    payload = next(item for item in health.json()["items"] if item["provider"] == "deepseek-pro")
    assert payload["status"] == "healthy"
    assert payload["mode"] == "probe"
    assert {
        "provider": "deepseek-pro",
        "model": "deepseek-v4-pro",
        "response_format": "text",
    } in captured
    setting = db_session.execute(select(SystemSetting)).scalar_one()
    assert setting.value_json["health"]["status"] == "healthy"
    assert setting.value_json["providers"][0]["last_health"]["mode"] == "probe"
    assert setting.value_json["providers"][0]["api_key"] == ""
    secret = db_session.execute(select(StoredSecret)).scalar_one()
    assert secret.provider == "deepseek"
    assert secret.purpose == "model_provider"
    assert secret.scope == "org"
    assert secret.owner_user_id is None
    assert saved_provider["api_key_secret_id"] == secret.id
    assert "secret-key" not in secret.encrypted_value


def test_deepseek_model_settings_store_one_secret_for_multiple_models(
    db_session: Session,
) -> None:
    principal = AuthenticatedPrincipal(
        user_id="dev-admin",
        organization_id="dev-org",
        roles=["admin", "engineer"],
        role="owner",
    )
    value = {
        "default_provider": "deepseek-flash",
        "default_model": "deepseek-v4-flash",
        "providers": [
            {
                "name": "deepseek-flash",
                "label": "DeepSeek Flash",
                "model": "deepseek-v4-flash",
                "api_format": "openai",
                "base_url": "https://api.deepseek.com",
                "api_key_env": "DEEPSEEK_API_KEY",
                "api_key": "secret-key",
            },
            {
                "name": "deepseek-pro",
                "label": "DeepSeek Pro",
                "model": "deepseek-v4-pro",
                "api_format": "openai",
                "base_url": "https://api.deepseek.com",
                "api_key_env": "DEEPSEEK_API_KEY",
                "api_key": "",
            },
        ],
        "rate_limits": {"rpm": 600, "tpm": 120000},
        "health": {"status": "healthy", "updated_at": None},
        "circuit_breaker": {"failure_threshold": 3, "cooldown_seconds": 60},
    }

    stored = _store_model_provider_secrets(
        session=db_session,
        principal=principal,
        value=value,
    )
    reloaded = _model_settings_response_value(
        session=db_session,
        organization_id=principal.organization_id,
        user_id=principal.user_id,
        value=stored,
    )

    secrets = list(db_session.execute(select(StoredSecret)).scalars())
    assert [secret.provider for secret in secrets] == ["deepseek"]
    providers = {provider["name"]: provider for provider in reloaded["providers"]}
    assert providers["deepseek-flash"]["api_key_configured"] is True
    assert providers["deepseek-pro"]["api_key_configured"] is True
    assert providers["deepseek-flash"]["api_key_secret_id"] == secrets[0].id
    assert providers["deepseek-pro"]["api_key_secret_id"] == secrets[0].id
    assert providers["deepseek-flash"]["api_key"] == ""
    assert providers["deepseek-pro"]["api_key"] == ""


def test_model_settings_store_explicit_secret_provider_for_multiple_models(
    db_session: Session,
) -> None:
    principal = AuthenticatedPrincipal(
        user_id="dev-admin",
        organization_id="dev-org",
        roles=["admin", "engineer"],
        role="owner",
    )
    value = {
        "default_provider": "openai-compatible",
        "default_model": "gpt-5.5",
        "providers": [
            {
                "name": "openai-compatible",
                "label": "OpenAI GPT-5.5",
                "model": "gpt-5.5",
                "secret_provider": "openai",
                "api_format": "openai",
                "base_url": "https://api.openai.com/v1",
                "api_key_env": "OPENAI_API_KEY",
                "api_key": "secret-openai-key",
            },
            {
                "name": "openai-gpt-5-3-codex-spark",
                "label": "OpenAI GPT-5.3 Codex Spark",
                "model": "gpt-5.3-codex-spark",
                "secret_provider": "openai",
                "api_format": "openai",
                "base_url": "https://api.openai.com/v1",
                "api_key_env": "OPENAI_API_KEY",
                "api_key": "",
            },
        ],
        "rate_limits": {"rpm": 600, "tpm": 120000},
        "health": {"status": "healthy", "updated_at": None},
        "circuit_breaker": {"failure_threshold": 3, "cooldown_seconds": 60},
    }

    stored = _store_model_provider_secrets(
        session=db_session,
        principal=principal,
        value=value,
    )
    reloaded = _model_settings_response_value(
        session=db_session,
        organization_id=principal.organization_id,
        user_id=principal.user_id,
        value=stored,
    )

    secrets = list(db_session.execute(select(StoredSecret)).scalars())
    assert [secret.provider for secret in secrets] == ["openai"]
    providers = {provider["name"]: provider for provider in reloaded["providers"]}
    assert providers["openai-compatible"]["api_key_configured"] is True
    assert providers["openai-gpt-5-3-codex-spark"]["api_key_configured"] is True
    assert providers["openai-compatible"]["api_key_secret_id"] == secrets[0].id
    assert providers["openai-gpt-5-3-codex-spark"]["api_key_secret_id"] == secrets[0].id
    assert providers["openai-compatible"]["api_key"] == ""
    assert providers["openai-gpt-5-3-codex-spark"]["api_key"] == ""


def test_model_official_status_endpoint_returns_external_reference(monkeypatch) -> None:
    from app.api import settings as settings_api

    def fake_fetch_model_official_statuses():
        return [
            {
                "provider": "openai",
                "label": "OpenAI",
                "status": "operational",
                "indicator": "none",
                "description": "All Systems Operational",
                "page_url": "https://status.openai.com/",
                "api_url": "https://status.openai.com/api/v2/status.json",
                "checked_at": settings_api.utc_now(),
                "updated_at": "2026-04-27T15:52:49Z",
                "error_message": None,
            },
            {
                "provider": "deepseek",
                "label": "DeepSeek",
                "status": "unknown",
                "indicator": "unknown",
                "description": "官方状态暂不可查",
                "page_url": "https://status.deepseek.com/",
                "api_url": "https://status.deepseek.com/",
                "checked_at": settings_api.utc_now(),
                "updated_at": None,
                "error_message": "connection reset",
            },
        ]

    monkeypatch.setattr(
        settings_api,
        "_fetch_model_official_statuses",
        fake_fetch_model_official_statuses,
    )
    client = TestClient(app)

    response = client.get("/api/settings/models/official-status", headers=ADMIN_HEADERS)

    assert response.status_code == 200
    payload = response.json()
    assert [item["provider"] for item in payload["items"]] == ["openai", "deepseek"]
    assert payload["items"][0]["status"] == "operational"
    assert payload["items"][0]["page_url"] == "https://status.openai.com/"
    assert payload["items"][1]["status"] == "unknown"
    assert payload["items"][1]["description"] == "官方状态暂不可查"
