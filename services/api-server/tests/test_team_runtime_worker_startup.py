import pytest

from app.core.config import Settings
from app.workers import team_runtime_worker


def _settings(**overrides: object) -> Settings:
    values = {
        "APP_ENV": "test",
        "AUTH_JWT_SECRET": "test-harness-jwt-secret-32-characters-min",
        "HARNESS_SECRET_ENCRYPTION_KEY": "test-harness-encryption-key-32-min",
    }
    values.update(overrides)
    return Settings(**values)


@pytest.mark.parametrize("api_key", ["", "replace-me"])
def test_team_runtime_service_rejects_invalid_production_provider_key_before_loop(
    monkeypatch: pytest.MonkeyPatch,
    api_key: str,
) -> None:
    monkeypatch.setattr(
        team_runtime_worker,
        "get_settings",
        lambda: _settings(APP_ENV="production", AI_PROVIDER_API_KEY=api_key),
    )
    monkeypatch.setattr(
        team_runtime_worker,
        "tick_active_team_goals",
        lambda **_kwargs: pytest.fail("service loop must not start after invalid settings"),
    )

    with pytest.raises(RuntimeError, match="AI_PROVIDER_API_KEY"):
        team_runtime_worker.run_team_runtime_service()


def test_team_runtime_service_allows_development_without_provider_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        team_runtime_worker,
        "get_settings",
        lambda: _settings(APP_ENV="development", AI_PROVIDER_API_KEY=""),
    )
    monkeypatch.setattr(
        team_runtime_worker,
        "tick_active_team_goals",
        lambda **_kwargs: pytest.fail("service loop must not run after immediate shutdown"),
    )

    def register_and_stop(_signal: int, handler: object) -> None:
        assert callable(handler)
        handler(None, None)

    monkeypatch.setattr(team_runtime_worker.signal, "signal", register_and_stop)

    team_runtime_worker.run_team_runtime_service()
