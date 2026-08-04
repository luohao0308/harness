import pytest

from app.agents.model_gateway import MODEL_SETTINGS_KEY, ModelGatewayError, ModelMessage
from app.db.models import SystemSetting, utc_now
from app.teams.model_runtime import GatewayTeamModelRuntime


def test_team_runtime_selects_custom_provider_row_by_model(db_session) -> None:
    db_session.add(
        SystemSetting(
            organization_id="dev-org",
            key=MODEL_SETTINGS_KEY,
            value_json={
                "default_provider": "custom-compatible",
                "default_model": "custom-fast",
                "providers": [
                    {
                        "name": "custom-compatible",
                        "model": "custom-fast",
                        "rate_limit_rpm": 10,
                    },
                    {
                        "name": "custom-compatible",
                        "model": "custom-pro",
                        "rate_limit_rpm": 20,
                    },
                ],
            },
            updated_by="dev-admin",
            updated_at=utc_now(),
        )
    )
    db_session.flush()

    provider_name, model_name, provider = GatewayTeamModelRuntime(db_session)._resolved_provider(
        organization_id="dev-org",
        model_provider="custom-compatible",
        model_name="custom-pro",
    )

    assert (provider_name, model_name) == ("custom-compatible", "custom-pro")
    assert provider["rate_limit_rpm"] == 20


@pytest.mark.parametrize("method", ["complete", "stream"])
def test_team_runtime_rejects_unlisted_platform_model(db_session, method: str) -> None:
    runtime = GatewayTeamModelRuntime(db_session)
    call = getattr(runtime, method)

    with pytest.raises(ModelGatewayError, match="not allowed"):
        result = call(
            organization_id="dev-org",
            model_provider="chybenzun-openai-compatible",
            model_name="unlisted-model",
            messages=[ModelMessage(role="user", content="hello")],
        )
        if method == "stream":
            list(result)
