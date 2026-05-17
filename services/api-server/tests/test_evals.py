from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    AdminAuditEvent,
    Agent,
    AgentEvent,
    EvalCase,
    EvalRun,
    PromptAssemblyManifest,
    SystemSetting,
    Task,
    utc_now,
)
from app.knowledge import ground_query, ingest_knowledge_source, set_web_research_provider
from app.main import app
from tests.conftest import AUTH_HEADERS


def _create_completed_run(client: TestClient) -> str:
    created = client.post(
        "/api/tasks",
        headers=AUTH_HEADERS,
        json={
            "title": "Eval source run",
            "goal": "Create a trace that can be saved as an eval case",
            "model_provider": "openai-compatible",
            "model_name": "default",
            "max_runtime_seconds": 1800,
            "max_subagents": 5,
            "enable_sandbox": True,
            "enable_network": False,
        },
    )
    assert created.status_code == 201
    run_id = created.json()["id"]
    started = client.post(f"/api/tasks/{run_id}/start", headers=AUTH_HEADERS)
    assert started.status_code == 202
    assert started.json()["status"] == "COMPLETED"
    return run_id


def _ensure_agent(session: Session, agent_id: str = "default") -> Agent:
    agent = session.get(Agent, agent_id)
    if agent is not None:
        return agent
    agent = Agent(
        id=agent_id,
        organization_id=None,
        name="Default Agent",
        description="Test agent",
        role="planner",
        status="ACTIVE",
        model_provider="default",
        model_name="default",
        system_prompt="You are a test agent.",
        tools_json=[],
        routing_tags=[],
        max_parallel_assignments=1,
        created_at=utc_now(),
        updated_at=utc_now(),
    )
    session.add(agent)
    session.flush()
    return agent


def _enable_web_research_policy(session: Session) -> None:
    session.add(
        SystemSetting(
            organization_id="dev-org",
            key="settings.policies",
            value_json={
                "risk_levels": [
                    {"name": "low", "requires_sandbox": False, "approval": "auto"},
                    {"name": "medium", "requires_sandbox": True, "approval": "auto"},
                    {"name": "high", "requires_sandbox": True, "approval": "admin"},
                    {"name": "critical", "requires_sandbox": True, "approval": "admin"},
                ],
                "approvals": {"manual_review": True, "deny_on_missing_policy": True},
                "sandbox": {
                    "default_network": False,
                    "default_timeout_seconds": 60,
                    "memory_mb": 1024,
                    "cpus": "1.0",
                    "workspace_quota_mb": 1024,
                    "network_allowlist": [],
                },
                "audit": {"model_calls": True, "tool_calls": True, "policy_actions": True},
                "web_research": {
                    "enabled": True,
                    "require_allowlist": True,
                    "allow_domains": ["example.test"],
                    "deny_domains": [],
                    "max_results": 2,
                    "timeout_seconds": 8,
                    "max_content_bytes": 1200,
                    "max_calls_per_run": 1,
                },
            },
            updated_by="dev-admin",
        )
    )
    session.flush()


def _grounded_completed_run(session: Session) -> str:
    _ensure_agent(session)
    task = Task(
        organization_id="dev-org",
        created_by="dev-engineer",
        title="Grounding Eval source run",
        goal="orion anchor",
        status="COMPLETED",
        model_provider="default",
        model_name="default",
        created_at=utc_now(),
        updated_at=utc_now(),
        completed_at=utc_now(),
    )
    session.add(task)
    session.flush()
    ingest_knowledge_source(
        session,
        organization_id="dev-org",
        agent_id="default",
        name="Grounding Facts",
        description="Grounding facts",
        source_type="text",
        title="Facts",
        content=("orion anchor local fact. " + ("alpha " * 120) + "\n") * 2,
        uri=None,
        mime_type="text/markdown",
        created_by="dev-engineer",
        idempotency_key="grounding-facts",
    )
    ground_query(
        session,
        organization_id="dev-org",
        agent_id="default",
        run_id=task.id,
        query="orion anchor",
    )
    session.flush()
    return task.id


def test_eval_dataset_case_from_run_and_eval_run_vertical_slice(db_session: Session) -> None:
    client = TestClient(app)
    run_id = _create_completed_run(client)

    dataset_response = client.post(
        "/api/evals/datasets",
        headers=AUTH_HEADERS,
        json={"name": "Regression Dataset", "description": "Saved agent runs"},
    )
    assert dataset_response.status_code == 201
    dataset = dataset_response.json()
    assert dataset["case_count"] == 0

    case_response = client.post(
        f"/api/evals/datasets/{dataset['id']}/cases/from-run/{run_id}",
        headers=AUTH_HEADERS,
        json={"expected_json": {"status": "COMPLETED"}, "tags_json": ["smoke", "trace"]},
    )
    assert case_response.status_code == 201
    eval_case = case_response.json()
    assert eval_case["source_task_id"] == run_id
    assert eval_case["input_json"]["goal"].startswith("Create a trace")

    listed_cases = client.get(
        f"/api/evals/datasets/{dataset['id']}/cases",
        headers=AUTH_HEADERS,
    )
    assert listed_cases.status_code == 200
    assert [item["id"] for item in listed_cases.json()["items"]] == [eval_case["id"]]

    eval_run_response = client.post(
        f"/api/evals/datasets/{dataset['id']}/runs",
        headers=AUTH_HEADERS,
        json={"agent_id": "default"},
    )
    assert eval_run_response.status_code == 201
    eval_run = eval_run_response.json()
    assert eval_run["status"] == "COMPLETED"
    assert eval_run["metrics_json"]["task_success_rate"] == 1.0
    assert eval_run["metrics_json"]["case_total"] == 1
    assert eval_run["results"][0]["status"] == "PASSED"
    assert eval_run["results"][0]["grader_trace_json"]["grader"] == "deterministic_trace_grader_v1"

    stored_run = db_session.get(EvalRun, eval_run["id"])
    stored_case = db_session.get(EvalCase, eval_case["id"])
    assert stored_run is not None
    assert stored_case is not None

    task_event_types = [
        event.event_type
        for event in db_session.execute(
            select(AgentEvent).where(AgentEvent.task_id == run_id).order_by(AgentEvent.sequence)
        ).scalars()
    ]
    assert "EVAL_CASE_CREATED" in task_event_types
    audit_types = [
        event.event_type for event in db_session.execute(select(AdminAuditEvent)).scalars()
    ]
    assert "EVAL_DATASET_CREATED" in audit_types
    assert "EVAL_RUN_STARTED" in audit_types
    assert "EVAL_RUN_COMPLETED" in audit_types


def test_eval_run_requires_cases() -> None:
    client = TestClient(app)
    dataset = client.post(
        "/api/evals/datasets",
        headers=AUTH_HEADERS,
        json={"name": "Empty Dataset", "description": ""},
    ).json()

    response = client.post(
        f"/api/evals/datasets/{dataset['id']}/runs",
        headers=AUTH_HEADERS,
        json={},
    )

    assert response.status_code == 409


def test_eval_run_grades_grounding_contract_cases(db_session: Session) -> None:
    client = TestClient(app)
    run_id = _grounded_completed_run(db_session)
    prompt_manifest = db_session.scalar(
        select(PromptAssemblyManifest).where(PromptAssemblyManifest.run_id == run_id)
    )
    assert prompt_manifest is not None
    dataset = client.post(
        "/api/evals/datasets",
        headers=AUTH_HEADERS,
        json={"name": "Grounding Dataset", "description": "P1 grounding contract"},
    ).json()

    passing_case = client.post(
        f"/api/evals/datasets/{dataset['id']}/cases/from-run/{run_id}",
        headers=AUTH_HEADERS,
        json={
            "expected_json": {
                "status": "COMPLETED",
                "grounding_contract": {
                    "require_grounded": True,
                    "require_prompt_manifest": True,
                    "prompt_manifest_id": prompt_manifest.id,
                    "require_policy_decisions": ["allowed", "no_omission_applicable"],
                },
            },
            "tags_json": ["grounding", "citation", "prompt-manifest"],
        },
    )
    assert passing_case.status_code == 201
    failing_case = client.post(
        f"/api/evals/datasets/{dataset['id']}/cases/from-run/{run_id}",
        headers=AUTH_HEADERS,
        json={
            "expected_json": {
                "status": "COMPLETED",
                "grounding_contract": {
                    "require_policy_decisions": ["denied"],
                },
            },
            "tags_json": ["grounding", "negative"],
        },
    )
    assert failing_case.status_code == 201

    eval_run_response = client.post(
        f"/api/evals/datasets/{dataset['id']}/runs",
        headers=AUTH_HEADERS,
        json={"agent_id": "default"},
    )

    assert eval_run_response.status_code == 201
    results = eval_run_response.json()["results"]
    statuses = {result["eval_case_id"]: result["status"] for result in results}
    assert statuses[passing_case.json()["id"]] == "PASSED"
    assert statuses[failing_case.json()["id"]] == "FAILED"
    traces = {result["eval_case_id"]: result["grader_trace_json"] for result in results}
    assert traces[passing_case.json()["id"]]["grader"] == "deterministic_grounding_grader_v1"
    assert traces[passing_case.json()["id"]]["inferred_fallback"] is False
    assert traces[passing_case.json()["id"]]["grounding_provider"] == "local_knowledge"
    assert traces[passing_case.json()["id"]]["fixture_grounded"] is False
    assert traces[passing_case.json()["id"]]["verified_grounded"] is True
    assert traces[failing_case.json()["id"]]["grounding_failures"] == ["missing_policy_decisions"]


def test_eval_run_rejects_fake_web_fallback_unless_fixture_opted_in(
    db_session: Session,
) -> None:
    client = TestClient(app)
    _ensure_agent(db_session)
    task = Task(
        organization_id="dev-org",
        created_by="dev-engineer",
        title="Fake web grounding Eval source run",
        goal="uncovered web claim",
        status="COMPLETED",
        model_provider="default",
        model_name="default",
        created_at=utc_now(),
        updated_at=utc_now(),
        completed_at=utc_now(),
    )
    db_session.add(task)
    db_session.flush()
    _enable_web_research_policy(db_session)
    set_web_research_provider(
        db_session,
        organization_id="dev-org",
        provider="fake",
        updated_by="dev-engineer",
    )
    grounding = ground_query(
        db_session,
        organization_id="dev-org",
        agent_id="default",
        run_id=task.id,
        query="uncovered web claim",
    )
    assert grounding.prompt_manifest is not None
    assert grounding.web_sources
    dataset = client.post(
        "/api/evals/datasets",
        headers=AUTH_HEADERS,
        json={"name": "Fake Web Dataset", "description": "P1 fake web fallback"},
    ).json()
    default_case = client.post(
        f"/api/evals/datasets/{dataset['id']}/cases/from-run/{task.id}",
        headers=AUTH_HEADERS,
        json={
            "expected_json": {
                "status": "COMPLETED",
                "grounding_contract": {
                    "require_grounded": True,
                    "require_insufficient": True,
                    "prompt_manifest_id": grounding.prompt_manifest.id,
                },
            },
            "tags_json": ["grounding", "fake-web"],
        },
    )
    assert default_case.status_code == 201
    opt_in_case = client.post(
        f"/api/evals/datasets/{dataset['id']}/cases/from-run/{task.id}",
        headers=AUTH_HEADERS,
        json={
            "expected_json": {
                "status": "COMPLETED",
                "grounding_contract": {
                    "require_grounded": True,
                    "require_insufficient": True,
                    "allow_fixture_grounding": True,
                    "prompt_manifest_id": grounding.prompt_manifest.id,
                },
            },
            "tags_json": ["grounding", "fake-web", "fixture-opt-in"],
        },
    )
    assert opt_in_case.status_code == 201

    eval_run_response = client.post(
        f"/api/evals/datasets/{dataset['id']}/runs",
        headers=AUTH_HEADERS,
        json={"agent_id": "default"},
    )

    assert eval_run_response.status_code == 201
    results = eval_run_response.json()["results"]
    statuses = {result["eval_case_id"]: result["status"] for result in results}
    traces = {result["eval_case_id"]: result["grader_trace_json"] for result in results}
    assert statuses[default_case.json()["id"]] == "FAILED"
    assert statuses[opt_in_case.json()["id"]] == "PASSED"
    assert traces[default_case.json()["id"]]["grounding_failures"] == [
        "missing_grounded_hits_or_citations"
    ]
    assert traces[opt_in_case.json()["id"]]["inferred_fallback"] is False
    assert traces[opt_in_case.json()["id"]]["grounding_provider"] == "fake_web_fixture"
    assert traces[opt_in_case.json()["id"]]["fixture_grounded"] is True
    assert traces[opt_in_case.json()["id"]]["verified_grounded"] is False
