from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api import observability as observability_api
from app.db.models import (
    AgentRun,
    ModelCall,
    ModelPricing,
    SubagentOutput,
    SubagentSpecialist,
    Task,
    ToolCall,
    utc_now,
)
from app.main import app
from tests.conftest import AUTH_HEADERS


def test_cost_rollup_by_agent_provider_specialist_and_adapter(db_session: Session) -> None:
    observability_api._cost_rollup_last_seen.clear()
    task = Task(
        id="cost-task-1",
        organization_id="dev-org",
        agent_id="default",
        created_by="dev-engineer",
        title="Cost rollup",
        goal="Measure cost",
        status="COMPLETED",
        model_provider="deepseek-flash",
        model_name="deepseek-v4-flash",
        max_runtime_seconds=1800,
        max_subagents=5,
        enable_sandbox=True,
        enable_network=False,
        created_at=utc_now(),
        updated_at=utc_now(),
    )
    specialist = SubagentSpecialist(
        id="specialist-cost-reviewer",
        organization_id="dev-org",
        slug="reviewer",
        display_name="审查专家",
        description="review",
        role="reviewer",
        system_prompt="review",
        capability_slugs_json=[],
        output_schema_json={"type": "object"},
        budget_json={},
        trigger_keywords_json=[],
        visibility="org",
        status="ACTIVE",
        created_at=utc_now(),
        updated_at=utc_now(),
    )
    agent_run = AgentRun(
        id="agent-run-cost-reviewer",
        task_id=task.id,
        agent_type="subagent",
        status="SUCCESS",
        specialist_id=specialist.id,
        context_json={},
    )
    db_session.add_all(
        [
            task,
            specialist,
            agent_run,
            ModelPricing(
                id="price-deepseek-flash",
                organization_id="dev-org",
                provider="deepseek-flash",
                model="deepseek-v4-flash",
                prompt_per_1k_usd="0.00014",
                completion_per_1k_usd="0.00028",
                cache_prompt_per_1k_usd="0.0000028",
                active=True,
            ),
            ModelCall(
                task_id=task.id,
                agent_run_id=agent_run.id,
                model_provider="deepseek-flash",
                model_name="deepseek-v4-flash",
                status="SUCCESS",
                prompt_tokens=1000,
                completion_tokens=500,
                duration_ms=100,
                request_json={},
                response_json={},
                created_at=utc_now(),
            ),
            SubagentOutput(
                agent_run_id=agent_run.id,
                task_id=task.id,
                specialist_id=specialist.id,
                output_json={},
                output_schema_sha256="a" * 64,
                budget_consumed_json={"cost_usd": "0.999", "prompt_tokens": 1},
                budget_exceeded_json=[],
                written_at=utc_now(),
            ),
            ToolCall(
                task_id=task.id,
                agent_run_id=agent_run.id,
                tool_name="brave",
                status="SUCCESS",
                risk_level="low",
                capability_snapshot_json={"adapter": {"slug": "brave"}},
                requires_sandbox=False,
                duration_ms=20,
                input_json={},
                output_json={"cost_usd": "0.005"},
                created_at=utc_now(),
            ),
        ]
    )
    db_session.commit()
    client = TestClient(app)

    by_agent = client.get(
        "/api/observability/cost-rollup?window=7d&group_by=agent",
        headers=AUTH_HEADERS,
    )
    assert by_agent.status_code == 200
    payload = by_agent.json()
    assert payload["total_cost_usd"] == 0.00028
    assert payload["total_tokens"] == 1500
    assert payload["total_runs"] == 1
    assert payload["breakdown"][0]["key"] == "default"
    assert payload["breakdown"][0]["share"] == 1
    assert payload["breakdown"][0]["pricing_status"] == "verified"
    assert payload["breakdown"][0]["pricing_blocking"] is False
    assert payload["pricing_statuses"] == [
        {
            "model": "deepseek-flash/deepseek-v4-flash",
            "status": "verified",
            "blocking": False,
        }
    ]

    observability_api._cost_rollup_last_seen.clear()
    by_provider = client.get(
        "/api/observability/cost-rollup?window=7d&group_by=provider",
        headers=AUTH_HEADERS,
    )
    assert by_provider.status_code == 200
    assert by_provider.json()["breakdown"][0]["key"] == "deepseek-flash/deepseek-v4-flash"

    observability_api._cost_rollup_last_seen.clear()
    by_specialist = client.get(
        "/api/observability/cost-rollup?window=7d&group_by=specialist",
        headers=AUTH_HEADERS,
    )
    assert by_specialist.status_code == 200
    assert by_specialist.json()["breakdown"][0]["key"] == "reviewer"

    observability_api._cost_rollup_last_seen.clear()
    by_adapter = client.get(
        "/api/observability/cost-rollup?window=7d&group_by=adapter",
        headers=AUTH_HEADERS,
    )
    assert by_adapter.status_code == 200
    assert by_adapter.json()["breakdown"][0]["key"] == "brave@local"
    assert by_adapter.json()["breakdown"][0]["cost_usd"] == 0.005


def test_cost_rollup_surfaces_missing_and_blocking_pricing_status(
    db_session: Session,
) -> None:
    observability_api._cost_rollup_last_seen.clear()
    task = Task(
        id="cost-task-unpriced",
        organization_id="dev-org",
        agent_id="default",
        created_by="dev-engineer",
        title="Cost rollup unpriced",
        goal="Expose pricing status",
        status="COMPLETED",
        model_provider="unknown-provider",
        model_name="unknown-model",
        max_runtime_seconds=1800,
        max_subagents=5,
        enable_sandbox=True,
        enable_network=False,
        created_at=utc_now(),
        updated_at=utc_now(),
    )
    db_session.add_all(
        [
            task,
            ModelCall(
                task_id=task.id,
                model_provider="unknown-provider",
                model_name="unknown-model",
                status="SUCCESS",
                prompt_tokens=1000,
                completion_tokens=500,
                duration_ms=100,
                request_json={},
                response_json={},
                created_at=utc_now(),
            ),
        ]
    )
    db_session.commit()
    client = TestClient(app)

    response = client.get(
        "/api/observability/cost-rollup?window=7d&group_by=provider",
        headers=AUTH_HEADERS,
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["total_cost_usd"] == 0
    assert payload["breakdown"][0]["key"] == "unknown-provider/unknown-model"
    assert payload["breakdown"][0]["pricing_status"] == "missing_pricing"
    assert payload["breakdown"][0]["pricing_blocking"] is True
    assert payload["pricing_statuses"] == [
        {
            "model": "unknown-provider/unknown-model",
            "status": "missing_pricing",
            "blocking": True,
        }
    ]


def test_cost_rollup_allows_custom_model_with_org_pricing(
    db_session: Session,
) -> None:
    observability_api._cost_rollup_last_seen.clear()
    task = Task(
        id="cost-task-custom-priced",
        organization_id="dev-org",
        agent_id="default",
        created_by="dev-engineer",
        title="Custom priced cost rollup",
        goal="Use org model pricing",
        status="COMPLETED",
        model_provider="custom-provider",
        model_name="custom-model",
        max_runtime_seconds=1800,
        max_subagents=5,
        enable_sandbox=True,
        enable_network=False,
        created_at=utc_now(),
        updated_at=utc_now(),
    )
    db_session.add_all(
        [
            task,
            ModelPricing(
                id="price-custom-provider-model",
                organization_id="dev-org",
                provider="custom-provider",
                model="custom-model",
                prompt_per_1k_usd="0.010000",
                completion_per_1k_usd="0.020000",
                currency="USD",
                active=True,
                source="org_override",
            ),
            ModelCall(
                task_id=task.id,
                model_provider="custom-provider",
                model_name="custom-model",
                status="SUCCESS",
                prompt_tokens=1000,
                completion_tokens=500,
                duration_ms=100,
                request_json={},
                response_json={},
                created_at=utc_now(),
            ),
        ]
    )
    db_session.commit()
    client = TestClient(app)

    response = client.get(
        "/api/observability/cost-rollup?window=7d&group_by=provider",
        headers=AUTH_HEADERS,
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["total_cost_usd"] == 0.02
    assert payload["breakdown"][0]["key"] == "custom-provider/custom-model"
    assert payload["breakdown"][0]["pricing_status"] == "verified"
    assert payload["breakdown"][0]["pricing_blocking"] is False
    assert payload["pricing_statuses"] == [
        {
            "model": "custom-provider/custom-model",
            "status": "verified",
            "blocking": False,
        }
    ]


def test_cost_rollup_blocks_builtin_source_model_from_fallback_pricing(
    db_session: Session,
) -> None:
    observability_api._cost_rollup_last_seen.clear()
    task = Task(
        id="cost-task-built-in-fallback",
        organization_id="dev-org",
        agent_id="default",
        created_by="dev-engineer",
        title="Built-in fallback cost rollup",
        goal="Reject fallback pricing for sourced SKUs",
        status="COMPLETED",
        model_provider="openai-compatible",
        model_name="gpt-5.5",
        max_runtime_seconds=1800,
        max_subagents=5,
        enable_sandbox=True,
        enable_network=False,
        created_at=utc_now(),
        updated_at=utc_now(),
    )
    db_session.add_all(
        [
            task,
            ModelPricing(
                id="price-openai-compatible-default-only",
                organization_id=None,
                provider="openai-compatible",
                model="default",
                prompt_per_1k_usd="0.00015",
                completion_per_1k_usd="0.00060",
                currency="USD",
                active=True,
                source="default_seed",
            ),
            ModelCall(
                task_id=task.id,
                model_provider="openai-compatible",
                model_name="gpt-5.5",
                status="SUCCESS",
                prompt_tokens=1000,
                completion_tokens=500,
                duration_ms=100,
                request_json={},
                response_json={},
                created_at=utc_now(),
            ),
        ]
    )
    db_session.commit()
    client = TestClient(app)

    response = client.get(
        "/api/observability/cost-rollup?window=7d&group_by=provider",
        headers=AUTH_HEADERS,
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["total_cost_usd"] == 0
    assert payload["breakdown"][0]["key"] == "openai-compatible/gpt-5.5"
    assert payload["breakdown"][0]["pricing_status"] == "missing_pricing"
    assert payload["breakdown"][0]["pricing_blocking"] is True


def test_cost_rollup_blocks_builtin_source_model_when_exact_price_does_not_match(
    db_session: Session,
) -> None:
    observability_api._cost_rollup_last_seen.clear()
    task = Task(
        id="cost-task-built-in-mismatch",
        organization_id="dev-org",
        agent_id="default",
        created_by="dev-engineer",
        title="Built-in mismatch cost rollup",
        goal="Reject unverified official SKU prices",
        status="COMPLETED",
        model_provider="openai-compatible",
        model_name="gpt-5.5",
        max_runtime_seconds=1800,
        max_subagents=5,
        enable_sandbox=True,
        enable_network=False,
        created_at=utc_now(),
        updated_at=utc_now(),
    )
    db_session.add_all(
        [
            task,
            ModelPricing(
                id="price-openai-compatible-gpt55-wrong",
                organization_id=None,
                provider="openai-compatible",
                model="gpt-5.5",
                prompt_per_1k_usd="0.00015",
                completion_per_1k_usd="0.00060",
                cache_prompt_per_1k_usd="0.00000",
                currency="USD",
                active=True,
                source="manual",
            ),
            ModelCall(
                task_id=task.id,
                model_provider="openai-compatible",
                model_name="gpt-5.5",
                status="SUCCESS",
                prompt_tokens=1000,
                completion_tokens=500,
                duration_ms=100,
                request_json={},
                response_json={},
                created_at=utc_now(),
            ),
        ]
    )
    db_session.commit()
    client = TestClient(app)

    response = client.get(
        "/api/observability/cost-rollup?window=7d&group_by=provider",
        headers=AUTH_HEADERS,
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["total_cost_usd"] == 0
    assert payload["breakdown"][0]["key"] == "openai-compatible/gpt-5.5"
    assert payload["breakdown"][0]["pricing_status"] == "price_unverified"
    assert payload["breakdown"][0]["pricing_blocking"] is True


def test_cost_rollup_rejects_invalid_window_and_rate_limits_cache_misses(
    db_session: Session,
) -> None:
    observability_api._cost_rollup_last_seen.clear()
    client = TestClient(app)

    first = client.get("/api/observability/cost-rollup?window=bad", headers=AUTH_HEADERS)
    assert first.status_code == 400

    observability_api._cost_rollup_last_seen.clear()
    ok = client.get("/api/observability/cost-rollup", headers=AUTH_HEADERS)
    assert ok.status_code == 200
    cached = client.get("/api/observability/cost-rollup", headers=AUTH_HEADERS)
    assert cached.status_code == 200
    assert cached.json() == ok.json()

    limited = client.get(
        "/api/observability/cost-rollup?group_by=provider",
        headers=AUTH_HEADERS,
    )
    assert limited.status_code == 429
