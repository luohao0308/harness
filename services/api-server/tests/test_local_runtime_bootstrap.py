from __future__ import annotations

import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session
from starlette.websockets import WebSocketDisconnect

from app.agents.model_gateway import (
    ModelRequest,
    ModelSetupRequiredError,
    OpenAICompatibleModelGateway,
)
from app.bootstrap.local_owner import (
    LOCAL_ORGANIZATION_ID,
    LOCAL_USER_ID,
    bootstrap_local_owner,
)
from app.cache.query_cache import query_cache
from app.core.config import clear_runtime_settings, get_settings, install_runtime_settings
from app.db.models import Organization, OrganizationMember, User
from app.local_runtime.bootstrap import LocalRuntimeBootstrap, read_bootstrap_from_fd
from app.local_runtime.web_bootstrap import WEB_BOOTSTRAP_STORE, WebBootstrapStore
from app.main import app
from app.services.terminal_capability_store import (
    InMemoryTerminalCapabilityStore,
    get_terminal_capability_store,
    reset_terminal_capability_store_for_tests,
    set_terminal_capability_store_for_tests,
)


def _bootstrap(tmp_path: Path, **overrides: object) -> LocalRuntimeBootstrap:
    values: dict[str, object] = {
        "runtime_data_dir": tmp_path,
        "session_signing_secret": "session-signing-secret-at-least-32-characters",
        "vault_encryption_secret": "vault-encryption-secret-at-least-32-characters",
        "desktop_bootstrap_token": "desktop-bootstrap-token-at-least-32-characters",
    }
    values.update(overrides)
    return LocalRuntimeBootstrap(**values)


@pytest.fixture(autouse=True)
def reset_local_runtime_state():
    clear_runtime_settings()
    WEB_BOOTSTRAP_STORE.clear()
    reset_terminal_capability_store_for_tests()
    try:
        yield
    finally:
        clear_runtime_settings()
        WEB_BOOTSTRAP_STORE.clear()
        reset_terminal_capability_store_for_tests()
        get_settings.cache_clear()


@pytest.fixture
def local_settings(tmp_path: Path):
    settings = _bootstrap(tmp_path).to_settings()
    install_runtime_settings(settings)
    return settings


def test_bootstrap_builds_explicit_local_settings_without_model_key(tmp_path: Path) -> None:
    bootstrap = _bootstrap(tmp_path)

    settings = bootstrap.to_settings()

    assert settings.runtime_profile == "local"
    assert settings.database_url == f"sqlite+pysqlite:///{tmp_path / 'harness.sqlite3'}"
    assert settings.auth_jwt_secret == bootstrap.session_signing_secret.get_secret_value()
    assert (
        settings.harness_secret_encryption_key
        == bootstrap.vault_encryption_secret.get_secret_value()
    )
    assert settings.ai_provider_api_key == ""
    assert settings.ai_provider_base_url == "https://ai.112102.xyz/v1"
    assert str(settings.model_gateway_base_url) == "https://ai.112102.xyz/v1"
    assert settings.ai_provider_model == "minimax-m3"
    assert settings.ai_provider_models == (
        "deepseek-v4-flash",
        "gpt-oss-120b",
        "mimo-v2.5",
        "minimax-m3",
        "nvidia-gpt-oss",
    )
    assert "session-signing-secret" not in repr(bootstrap)
    assert "vault-encryption-secret" not in repr(bootstrap)
    assert "session-signing-secret" not in repr(settings)
    assert "vault-encryption-secret" not in repr(settings)


def test_bootstrap_propagates_custom_model_configuration(tmp_path: Path) -> None:
    settings = _bootstrap(
        tmp_path,
        model_base_url="http://127.0.0.1:11434/v1/",
        model_name="vendor/model:preview",
        model_api_key="bootstrap-model-key",
    ).to_settings()

    assert settings.ai_provider_base_url == "http://127.0.0.1:11434/v1"
    assert str(settings.model_gateway_base_url) == "http://127.0.0.1:11434/v1"
    assert settings.ai_provider_model == "vendor/model:preview"
    assert settings.ai_provider_models == ("vendor/model:preview",)
    assert settings.ai_provider_api_key == "bootstrap-model-key"
    assert settings.model_gateway_api_key == "bootstrap-model-key"
    assert "bootstrap-model-key" not in repr(settings)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("model_base_url", "http://models.example.test/v1"),
        ("model_base_url", "https://user:pass@models.example.test/v1"),
        ("model_base_url", "https://models.example.test/v1?key=secret"),
        ("model_name", "invalid model"),
    ],
)
def test_bootstrap_rejects_invalid_model_configuration(
    tmp_path: Path,
    field: str,
    value: str,
) -> None:
    with pytest.raises(ValueError):
        _bootstrap(tmp_path, **{field: value})


def test_bootstrap_can_be_read_from_inherited_fd(tmp_path: Path) -> None:
    read_fd, write_fd = os.pipe()
    payload = {
        "runtime_data_dir": str(tmp_path),
        "session_signing_secret": "session-signing-secret-at-least-32-characters",
        "vault_encryption_secret": "vault-encryption-secret-at-least-32-characters",
        "desktop_bootstrap_token": "desktop-bootstrap-token-at-least-32-characters",
    }
    os.write(write_fd, json.dumps(payload).encode())
    os.close(write_fd)
    try:
        bootstrap = read_bootstrap_from_fd(read_fd)
    finally:
        os.close(read_fd)

    assert bootstrap.runtime_data_dir == tmp_path


def test_local_owner_bootstrap_is_stable_and_idempotent(db_session: Session) -> None:
    first = bootstrap_local_owner(db_session)
    second = bootstrap_local_owner(db_session)

    assert first.id == second.id == LOCAL_USER_ID
    assert db_session.query(User).count() == 1
    assert db_session.query(Organization).count() == 1
    membership = db_session.execute(select(OrganizationMember)).scalar_one()
    assert membership.organization_id == LOCAL_ORGANIZATION_ID
    assert membership.user_id == LOCAL_USER_ID
    assert membership.role == "owner"
    assert first.password_hash == "!local-runtime-password-login-disabled"


def test_local_profile_disables_public_and_saml_login(local_settings) -> None:
    client = TestClient(app, base_url="http://127.0.0.1:8000")

    config = client.get("/api/auth/config")
    login = client.post("/api/auth/login", json={"email": "local@invalid", "password": "unused"})
    register = client.post(
        "/api/auth/register",
        json={
            "email": "new@example.com",
            "password": "Strong!Pass1",
            "name": "New User",
        },
    )
    saml = client.post("/api/saml/login", json={"provider_id": "example"})

    assert config.status_code == 200
    assert config.json()["public_registration_enabled"] is False
    assert login.status_code == 404
    assert register.status_code == 404
    assert saml.status_code == 404


def test_desktop_bootstrap_sets_httponly_cookie_and_returns_no_secret(
    local_settings,
    db_session: Session,
) -> None:
    bootstrap_local_owner(db_session)
    client = TestClient(app, base_url="http://127.0.0.1:8000")

    response = client.post(
        "/api/local-runtime/desktop-session",
        headers={"X-Harness-Desktop-Bootstrap": local_settings.local_desktop_bootstrap_token},
    )

    assert response.status_code == 204
    cookie = response.headers["set-cookie"]
    assert "harness_local_session=" in cookie
    assert "HttpOnly" in cookie
    assert "SameSite=strict" in cookie
    assert local_settings.local_desktop_bootstrap_token not in response.text
    me = client.get("/api/auth/me")
    assert me.status_code == 200
    assert me.json()["user_id"] == LOCAL_USER_ID


def test_missing_local_model_key_is_setup_required_and_never_mock(local_settings) -> None:
    gateway = OpenAICompatibleModelGateway()

    with pytest.raises(ModelSetupRequiredError) as exc_info:
        gateway.complete(
            ModelRequest(
                model_provider="openai-compatible",
                model_name="default",
                messages=[],
            )
        )

    assert exc_info.value.code == "MODEL_SETUP_REQUIRED"


def test_desktop_can_apply_and_delete_process_only_model_key(local_settings) -> None:
    client = TestClient(app, base_url="http://127.0.0.1:8000")
    headers = {"X-Harness-Desktop-Bootstrap": local_settings.local_desktop_bootstrap_token}

    applied = client.put(
        "/api/local-runtime/model-key",
        headers=headers,
        json={"api_key": "canary-key"},
    )
    status_response = client.get("/api/local-runtime/status")

    assert applied.status_code == 200
    assert applied.json() == {"model": "configured"}
    assert status_response.json() == {"runtime": "ready", "model": "configured"}
    assert "canary-key" not in applied.text
    assert "canary-key" not in status_response.text
    assert OpenAICompatibleModelGateway()._uses_local_mock() is False

    deleted = client.delete("/api/local-runtime/model-key", headers=headers)
    assert deleted.json() == {"model": "setup_required"}
    assert get_settings().ai_provider_api_key == ""


def test_model_config_requires_desktop_bootstrap(local_settings) -> None:
    client = TestClient(app, base_url="http://127.0.0.1:8000")

    response = client.put(
        "/api/local-runtime/model-config",
        json={"base_url": "https://models.example.test/v1", "model": "example-model"},
    )

    assert response.status_code == 401


@pytest.mark.parametrize(
    ("payload", "code"),
    [
        ({"base_url": "http://models.example.test/v1"}, "INVALID_MODEL_BASE_URL"),
        ({"base_url": "https://user:pass@models.example.test/v1"}, "INVALID_MODEL_BASE_URL"),
        ({"model": "invalid model"}, "INVALID_MODEL_ID"),
    ],
)
def test_model_config_rejects_invalid_values_atomically(
    local_settings,
    payload: dict[str, str],
    code: str,
) -> None:
    client = TestClient(app, base_url="http://127.0.0.1:8000")
    headers = {"X-Harness-Desktop-Bootstrap": local_settings.local_desktop_bootstrap_token}
    original = get_settings()
    request_payload = {
        "base_url": "https://models.example.test/v1",
        "model": "example-model",
        **payload,
    }

    response = client.put(
        "/api/local-runtime/model-config",
        headers=headers,
        json=request_payload,
    )

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == code
    assert get_settings() is original


def test_model_config_atomically_updates_url_model_and_optional_key(local_settings) -> None:
    client = TestClient(app, base_url="http://127.0.0.1:8000")
    headers = {"X-Harness-Desktop-Bootstrap": local_settings.local_desktop_bootstrap_token}

    response = client.put(
        "/api/local-runtime/model-config",
        headers=headers,
        json={
            "base_url": "http://localhost:11434/v1/",
            "model": "local/model:latest",
            "api_key": "model-config-canary-key",
        },
    )
    settings = get_settings()

    assert response.status_code == 200
    assert response.json() == {
        "state": "configured",
        "base_url": "http://localhost:11434/v1",
        "model": "local/model:latest",
    }
    assert settings.ai_provider_base_url == "http://localhost:11434/v1"
    assert str(settings.model_gateway_base_url) == "http://localhost:11434/v1"
    assert settings.ai_provider_model == "local/model:latest"
    assert settings.ai_provider_models == ("local/model:latest",)
    assert settings.ai_provider_api_key == "model-config-canary-key"
    assert settings.model_gateway_api_key == "model-config-canary-key"
    assert "model-config-canary-key" not in response.text
    assert "model-config-canary-key" not in repr(settings)


def _install_discovery_transport(monkeypatch, handler):
    real_client = httpx.Client
    client_options: dict[str, object] = {}

    def client_factory(*args, **kwargs):
        client_options.update(kwargs)
        return real_client(*args, transport=httpx.MockTransport(handler), **kwargs)

    monkeypatch.setattr("app.local_runtime.api.httpx.Client", client_factory)
    return client_options


def test_model_discovery_requires_desktop_bootstrap(local_settings) -> None:
    client = TestClient(app, base_url="http://127.0.0.1:8000")

    response = client.post(
        "/api/local-runtime/model-discovery",
        json={"base_url": "https://models.example.test/v1", "api_key": "key"},
    )

    assert response.status_code == 401


def test_model_discovery_rejects_invalid_url_and_missing_key(local_settings) -> None:
    client = TestClient(app, base_url="http://127.0.0.1:8000")
    headers = {"X-Harness-Desktop-Bootstrap": local_settings.local_desktop_bootstrap_token}

    invalid_url = client.post(
        "/api/local-runtime/model-discovery",
        headers=headers,
        json={"base_url": "http://models.example.test/v1", "api_key": "secret-key"},
    )
    missing_key = client.post(
        "/api/local-runtime/model-discovery",
        headers=headers,
        json={"base_url": "https://models.example.test/v1"},
    )

    assert invalid_url.status_code == 422
    assert invalid_url.json()["detail"]["code"] == "INVALID_MODEL_BASE_URL"
    assert missing_key.status_code == 400
    assert missing_key.json()["detail"]["code"] == "MODEL_API_KEY_REQUIRED"


def test_model_discovery_uses_hardened_client_and_deduplicates_models(
    local_settings,
    monkeypatch,
) -> None:
    seen_request: httpx.Request | None = None

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal seen_request
        seen_request = request
        return httpx.Response(
            200,
            json={"data": [{"id": "model-a"}, {"id": "model-a"}, {"id": "vendor/model:b"}]},
        )

    client_options = _install_discovery_transport(monkeypatch, handler)
    client = TestClient(app, base_url="http://127.0.0.1:8000")
    headers = {"X-Harness-Desktop-Bootstrap": local_settings.local_desktop_bootstrap_token}

    response = client.post(
        "/api/local-runtime/model-discovery",
        headers=headers,
        json={"base_url": "https://models.example.test/v1/", "api_key": "discovery-key"},
    )

    assert response.status_code == 200
    assert response.json()["models"] == ["model-a", "vendor/model:b"]
    assert isinstance(response.json()["latency_ms"], int)
    assert seen_request is not None
    assert str(seen_request.url) == "https://models.example.test/v1/models"
    assert seen_request.headers["authorization"] == "Bearer discovery-key"
    assert seen_request.headers["user-agent"] == "Harness-Desktop-Model-Discovery/1.0"
    assert client_options == {
        "timeout": 8.0,
        "trust_env": False,
        "follow_redirects": False,
    }
    assert "discovery-key" not in response.text


def test_model_discovery_uses_current_key_when_payload_key_is_blank(
    tmp_path: Path,
    monkeypatch,
) -> None:
    settings = _bootstrap(tmp_path, model_api_key="current-process-key").to_settings()
    install_runtime_settings(settings)

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["authorization"] == "Bearer current-process-key"
        return httpx.Response(200, json={"data": []})

    _install_discovery_transport(monkeypatch, handler)
    client = TestClient(app, base_url="http://127.0.0.1:8000")
    response = client.post(
        "/api/local-runtime/model-discovery",
        headers={"X-Harness-Desktop-Bootstrap": settings.local_desktop_bootstrap_token},
        json={"base_url": "https://models.example.test/v1", "api_key": "  "},
    )

    assert response.status_code == 200


@pytest.mark.parametrize(
    ("status_code", "expected_status", "code"),
    [
        (401, 502, "MODEL_DISCOVERY_AUTH_ERROR"),
        (403, 502, "MODEL_DISCOVERY_AUTH_ERROR"),
        (302, 502, "MODEL_DISCOVERY_UPSTREAM_ERROR"),
        (500, 502, "MODEL_DISCOVERY_UPSTREAM_ERROR"),
    ],
)
def test_model_discovery_maps_upstream_statuses(
    local_settings,
    monkeypatch,
    status_code: int,
    expected_status: int,
    code: str,
) -> None:
    _install_discovery_transport(
        monkeypatch,
        lambda _request: httpx.Response(status_code, text="upstream-secret-body"),
    )
    client = TestClient(app, base_url="http://127.0.0.1:8000")
    response = client.post(
        "/api/local-runtime/model-discovery",
        headers={"X-Harness-Desktop-Bootstrap": local_settings.local_desktop_bootstrap_token},
        json={"base_url": "https://models.example.test/v1", "api_key": "secret-key"},
    )

    assert response.status_code == expected_status
    assert response.json()["detail"]["code"] == code
    assert "secret-key" not in response.text
    assert "upstream-secret-body" not in response.text


def test_model_discovery_maps_timeout(local_settings, monkeypatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out", request=request)

    _install_discovery_transport(monkeypatch, handler)
    client = TestClient(app, base_url="http://127.0.0.1:8000")
    response = client.post(
        "/api/local-runtime/model-discovery",
        headers={"X-Harness-Desktop-Bootstrap": local_settings.local_desktop_bootstrap_token},
        json={"base_url": "https://models.example.test/v1", "api_key": "secret-key"},
    )

    assert response.status_code == 504
    assert response.json()["detail"]["code"] == "MODEL_DISCOVERY_TIMEOUT"


@pytest.mark.parametrize(
    "response_body",
    [
        b"not-json",
        json.dumps({"models": []}).encode(),
        json.dumps({"data": [{"id": "invalid model"}]}).encode(),
    ],
)
def test_model_discovery_rejects_malformed_response(
    local_settings,
    monkeypatch,
    response_body: bytes,
) -> None:
    _install_discovery_transport(
        monkeypatch,
        lambda _request: httpx.Response(200, content=response_body),
    )
    client = TestClient(app, base_url="http://127.0.0.1:8000")
    response = client.post(
        "/api/local-runtime/model-discovery",
        headers={"X-Harness-Desktop-Bootstrap": local_settings.local_desktop_bootstrap_token},
        json={"base_url": "https://models.example.test/v1", "api_key": "secret-key"},
    )

    assert response.status_code == 502
    assert response.json()["detail"]["code"] == "MODEL_DISCOVERY_INVALID_RESPONSE"


def test_model_discovery_rejects_oversized_response(local_settings, monkeypatch) -> None:
    _install_discovery_transport(
        monkeypatch,
        lambda _request: httpx.Response(200, content=b"x" * (1024 * 1024 + 1)),
    )
    client = TestClient(app, base_url="http://127.0.0.1:8000")
    response = client.post(
        "/api/local-runtime/model-discovery",
        headers={"X-Harness-Desktop-Bootstrap": local_settings.local_desktop_bootstrap_token},
        json={"base_url": "https://models.example.test/v1", "api_key": "secret-key"},
    )

    assert response.status_code == 413
    assert response.json()["detail"]["code"] == "MODEL_DISCOVERY_RESPONSE_TOO_LARGE"


def test_local_model_state_returns_metadata_without_secret(local_settings) -> None:
    client = TestClient(app, base_url="http://127.0.0.1:8000")

    setup = client.get("/api/local-runtime/model")
    client.put(
        "/api/local-runtime/model-key",
        headers={"X-Harness-Desktop-Bootstrap": local_settings.local_desktop_bootstrap_token},
        json={"api_key": "state-canary-key"},
    )
    configured = client.get("/api/local-runtime/model")

    assert setup.json() == {
        "state": "setup_required",
        "provider": "chybenzun-openai-compatible",
        "model": "minimax-m3",
        "base_url": "https://ai.112102.xyz/v1",
        "secret_storage": "persistent",
        "message": "A model provider API key is required",
    }
    assert configured.json()["state"] == "configured"
    assert configured.json()["secret_storage"] == "persistent"
    assert "state-canary-key" not in configured.text


def test_session_only_bootstrap_rejects_persistent_secret_writes(
    tmp_path: Path,
    db_session: Session,
) -> None:
    settings = _bootstrap(tmp_path, persistent_secret_storage=False).to_settings()
    install_runtime_settings(settings)
    bootstrap_local_owner(db_session)
    client = TestClient(app, base_url="http://127.0.0.1:8000")
    client.post(
        "/api/local-runtime/desktop-session",
        headers={"X-Harness-Desktop-Bootstrap": settings.local_desktop_bootstrap_token},
    )
    unavailable = client.get("/api/local-runtime/model")
    client.put(
        "/api/local-runtime/model-key",
        headers={"X-Harness-Desktop-Bootstrap": settings.local_desktop_bootstrap_token},
        json={"api_key": "session-only-key"},
    )
    session_only = client.get("/api/local-runtime/model")

    response = client.put(
        "/api/secrets",
        json={
            "scope": "org",
            "provider": "example",
            "purpose": "model_provider",
            "secret_value": "must-not-persist",
        },
    )

    assert unavailable.json()["secret_storage"] == "unavailable"
    assert session_only.json()["secret_storage"] == "session"
    assert "session-only-key" not in session_only.text
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "SECRET_STORAGE_UNAVAILABLE"
    assert "must-not-persist" not in response.text


def test_web_bootstrap_is_single_use_and_sets_browser_cookie(
    local_settings,
    db_session: Session,
) -> None:
    bootstrap_local_owner(db_session)
    desktop = TestClient(app, base_url="http://127.0.0.1:8000")
    bootstrap_headers = {
        "X-Harness-Desktop-Bootstrap": local_settings.local_desktop_bootstrap_token
    }
    issued = desktop.post("/api/local-runtime/web-bootstrap", headers=bootstrap_headers)
    payload = issued.json()
    browser = TestClient(app, base_url="http://127.0.0.1:8000")
    exchange = browser.post(
        "/api/local-runtime/web/bootstrap/exchange",
        headers={"Origin": "http://127.0.0.1:8000"},
        json={"token": payload["token"]},
    )
    reuse = browser.post(
        "/api/local-runtime/web/bootstrap/exchange",
        headers={"Origin": "http://127.0.0.1:8000"},
        json={"token": payload["token"]},
    )

    assert issued.status_code == 200
    assert payload["intended_origin"] == "http://127.0.0.1:8000"
    assert exchange.status_code == 204
    assert "HttpOnly" in exchange.headers["set-cookie"]
    assert "SameSite=strict" in exchange.headers["set-cookie"]
    assert reuse.status_code == 401
    assert browser.get("/api/auth/me").status_code == 200


def test_web_bootstrap_rejects_expired_and_foreign_origin() -> None:
    store = WebBootstrapStore()
    now = datetime.now(UTC)
    token, _ = store.issue(
        user_id=LOCAL_USER_ID,
        organization_id=LOCAL_ORGANIZATION_ID,
        intended_origin="http://127.0.0.1:8000",
        ttl_seconds=1,
        now=now,
    )

    assert store.consume(token, origin="http://evil.invalid", now=now) is None
    assert (
        store.consume(
            token,
            origin="http://127.0.0.1:8000",
            now=now + timedelta(seconds=2),
        )
        is None
    )


def test_local_boundary_rejects_foreign_host_origin_and_websocket(local_settings) -> None:
    client = TestClient(app, base_url="http://127.0.0.1:8000")

    foreign_host = client.get("/health", headers={"Host": "attacker.invalid"})
    foreign_origin = client.get("/health", headers={"Origin": "http://attacker.invalid"})

    assert foreign_host.status_code == 404
    assert foreign_origin.status_code == 404
    with pytest.raises(WebSocketDisconnect) as exc_info:
        with client.websocket_connect(
            "/api/terminal/ws",
            headers={"Origin": "http://attacker.invalid"},
        ):
            pass
    assert exc_info.value.code == 1008


def test_local_readiness_separates_runtime_from_model_setup(
    local_settings,
    db_session: Session,
) -> None:
    client = TestClient(app, base_url="http://127.0.0.1:8000")

    response = client.get("/api/health/readiness")

    assert response.status_code == 200
    assert response.json()["ready"] is True
    assert response.json()["runtime_ready"] is True
    assert response.json()["model"]["state"] == "setup_required"
    assert "redis" not in response.json()


def test_local_terminal_store_never_constructs_redis(local_settings, monkeypatch) -> None:
    def fail_from_url(*_args, **_kwargs):
        raise AssertionError("local terminal store must not construct Redis")

    monkeypatch.setattr(
        "app.services.terminal_capability_store.RedisTerminalCapabilityStore.from_url",
        fail_from_url,
    )
    set_terminal_capability_store_for_tests(object())

    store = get_terminal_capability_store(
        token_ttl_seconds=30,
        max_sessions=2,
        lease_seconds=15,
    )

    assert isinstance(store, InMemoryTerminalCapabilityStore)


def test_local_query_cache_never_constructs_redis(local_settings, monkeypatch) -> None:
    import builtins

    original_import = builtins.__import__

    def reject_redis_import(name, *args, **kwargs):
        if name == "redis" or name.startswith("redis."):
            raise AssertionError("local query cache must not import Redis")
        return original_import(name, *args, **kwargs)

    query_cache.clear_memory()
    query_cache._redis = None
    query_cache._redis_failed = False
    monkeypatch.setattr(builtins, "__import__", reject_redis_import)

    query_cache.set("local:key", {"value": 1}, ttl_seconds=30)

    assert query_cache.get("local:key") == {"value": 1}


def test_local_websocket_requires_origin_but_http_navigation_does_not(local_settings) -> None:
    client = TestClient(app, base_url="http://127.0.0.1:8000")

    assert client.get("/health").status_code == 200
    with pytest.raises(WebSocketDisconnect) as exc_info:
        with client.websocket_connect("/ws/terminal"):
            pass
    assert exc_info.value.code == 1008


def test_local_model_settings_secret_write_uses_typed_storage_error(
    tmp_path: Path,
    db_session: Session,
) -> None:
    settings = _bootstrap(tmp_path, persistent_secret_storage=False).to_settings()
    install_runtime_settings(settings)
    bootstrap_local_owner(db_session)
    client = TestClient(app, base_url="http://127.0.0.1:8000")
    client.post(
        "/api/local-runtime/desktop-session",
        headers={"X-Harness-Desktop-Bootstrap": settings.local_desktop_bootstrap_token},
    )
    current = client.get("/api/settings/models").json()
    current["providers"].append(
        {
            "name": "local-custom",
            "model": "custom-model",
            "base_url": "https://models.example.test/v1",
            "api_format": "openai",
            "api_key": "must-not-persist",
        }
    )

    response = client.put("/api/settings/models", json=current)

    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "SECRET_STORAGE_UNAVAILABLE"
    assert "must-not-persist" not in response.text
