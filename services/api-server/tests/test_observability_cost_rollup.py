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
                prompt_per_1k_usd="0.002",
                completion_per_1k_usd="0.004",
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
    assert payload["total_cost_usd"] == 0.004
    assert payload["total_tokens"] == 1500
    assert payload["total_runs"] == 1
    assert payload["breakdown"][0]["key"] == "default"
    assert payload["breakdown"][0]["share"] == 1

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


def test_cost_rollup_rejects_invalid_window_and_rate_limits(db_session: Session) -> None:
    observability_api._cost_rollup_last_seen.clear()
    client = TestClient(app)

    first = client.get("/api/observability/cost-rollup?window=bad", headers=AUTH_HEADERS)
    assert first.status_code == 400

    observability_api._cost_rollup_last_seen.clear()
    ok = client.get("/api/observability/cost-rollup", headers=AUTH_HEADERS)
    assert ok.status_code == 200
    limited = client.get("/api/observability/cost-rollup", headers=AUTH_HEADERS)
    assert limited.status_code == 429
