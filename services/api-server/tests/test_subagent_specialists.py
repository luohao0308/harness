import json

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.agents.model_gateway import ModelRequest, ModelResponse
from app.agents.specialists import (
    SubagentDepthExceededError,
    SubagentSpecialistRegistry,
    compute_specialist_stats,
    ensure_system_specialists,
    select_specialist_by_ranking,
)
from app.agents.subagent_manager import SubagentManager
from app.db.models import AgentRun, SubagentOutput, SubagentSpecialist
from app.events.event_store import EventStore
from app.events.event_types import EventType
from app.main import app
from app.workers.subagent_worker import execute_subagent
from tests.conftest import AUTH_HEADERS
from tests.test_subagents import ADMIN_HEADERS, create_task


class TokenModelGateway:
    def complete(self, request: ModelRequest) -> ModelResponse:
        return ModelResponse(
            content=json.dumps({"summary": "large model call", "done": True, "next_tools": []}),
            model_provider=request.model_provider,
            model_name=request.model_name,
            usage={"prompt_tokens": 2, "completion_tokens": 1},
            raw_response={"mode": "budget-test"},
        )


def test_system_specialists_are_listed_and_protected(db_session: Session) -> None:
    client = TestClient(app)

    listed = client.get("/api/subagent-specialists", headers=AUTH_HEADERS)

    assert listed.status_code == 200
    slugs = {item["slug"]: item for item in listed.json()["items"]}
    assert {"code-reviewer", "researcher", "safety-checker", "synthesizer"}.issubset(slugs)
    system_id = slugs["code-reviewer"]["id"]
    assert (
        client.delete(f"/api/subagent-specialists/{system_id}", headers=ADMIN_HEADERS).status_code
        == 403
    )
    blocked_update = client.patch(
        f"/api/subagent-specialists/{system_id}",
        headers=ADMIN_HEADERS,
        json={"system_prompt": "modified"},
    )
    assert blocked_update.status_code == 403


def test_specialist_crud_and_preflight_validation(db_session: Session) -> None:
    client = TestClient(app)
    body = {
        "slug": "incident-reviewer",
        "display_name": "Incident Reviewer",
        "description": "Reviews incident reports",
        "role": "reviewer",
        "system_prompt": "Return structured incident review JSON.",
        "capability_slugs_json": ["read_file"],
        "output_schema_json": {
            "type": "object",
            "required": ["summary"],
            "properties": {"summary": {"type": "string"}},
        },
        "budget_json": {"max_runtime_seconds": 60, "max_tokens": 100, "max_tool_calls": 2},
        "trigger_keywords_json": ["incident"],
    }

    created = client.post("/api/subagent-specialists", headers=ADMIN_HEADERS, json=body)

    assert created.status_code == 201
    specialist = created.json()
    assert specialist["slug"] == "incident-reviewer"
    assert specialist["budget_json"]["max_tokens"] == 100
    passed = client.post(
        f"/api/subagent-specialists/{specialist['id']}/preflight",
        headers=AUTH_HEADERS,
        json={"sample_output": {"summary": "ok"}},
    )
    assert passed.status_code == 200
    assert passed.json()["status"] == "passed"
    failed = client.post(
        f"/api/subagent-specialists/{specialist['id']}/preflight",
        headers=AUTH_HEADERS,
        json={"sample_output": {}},
    )
    assert failed.status_code == 200
    assert failed.json()["status"] == "failed"
    archived = client.delete(f"/api/subagent-specialists/{specialist['id']}", headers=ADMIN_HEADERS)
    assert archived.status_code == 204


def test_spawn_with_specialist_snapshots_contract_and_manual_output(
    db_session: Session,
) -> None:
    client = TestClient(app)
    task = create_task(db_session)
    db_session.commit()

    created = client.post(
        f"/api/tasks/{task.id}/subagents",
        headers=AUTH_HEADERS,
        json={
            "assignment": {"step_key": "review_patch"},
            "specialist_slug": "code-reviewer",
            "enqueue": False,
        },
    )

    assert created.status_code == 201
    body = created.json()
    assert body["specialist"]["slug"] == "code-reviewer"
    assert body["context_json"]["specialist_slug"] == "code-reviewer"
    assert body["context_json"]["output_schema_sha256"]
    subagent_id = body["id"]
    invalid = client.post(
        f"/api/subagents/{subagent_id}/output",
        headers=AUTH_HEADERS,
        json={"output_json": {"summary": "missing issues"}},
    )
    assert invalid.status_code == 422
    valid = client.post(
        f"/api/subagents/{subagent_id}/output",
        headers=AUTH_HEADERS,
        json={"output_json": {"issues": [], "summary": "clean"}},
    )
    assert valid.status_code == 201
    assert valid.json()["output_json"]["summary"] == "clean"
    duplicate = client.post(
        f"/api/subagents/{subagent_id}/output",
        headers=AUTH_HEADERS,
        json={"output_json": {"issues": [], "summary": "second"}},
    )
    assert duplicate.status_code == 409


def test_worker_writes_structured_output_for_specialist(db_session: Session) -> None:
    ensure_system_specialists(db_session)
    task = create_task(db_session)
    specialist = db_session.query(SubagentSpecialist).filter_by(
        slug="synthesizer",
        visibility="system",
    ).one()
    agent_run = SubagentManager(db_session).spawn(
        task=task,
        assignment={"step_key": "summarize"},
        specialist=specialist,
    )
    db_session.commit()

    status = execute_subagent(agent_run.id, session=db_session)

    assert status == "SUCCESS"
    output = db_session.query(SubagentOutput).filter_by(agent_run_id=agent_run.id).one()
    assert output.output_json["summary"].startswith("Subagent completed summarize")
    refreshed = db_session.get(AgentRun, agent_run.id)
    assert refreshed is not None
    assert refreshed.context_json["result"]["summary"].startswith("Subagent completed summarize")


def test_worker_marks_budget_exceeded_after_model_call(db_session: Session) -> None:
    ensure_system_specialists(db_session)
    task = create_task(db_session)
    specialist = (
        db_session.query(SubagentSpecialist).filter_by(slug="researcher", visibility="system").one()
    )
    specialist.budget_json = {"max_runtime_seconds": 900, "max_tokens": 1, "max_tool_calls": 10}
    agent_run = SubagentManager(db_session).spawn(
        task=task,
        assignment={"step_key": "research"},
        specialist=specialist,
    )
    db_session.commit()

    status = execute_subagent(agent_run.id, session=db_session, model_gateway=TokenModelGateway())

    assert status == "BUDGET_EXCEEDED"
    refreshed = db_session.get(AgentRun, agent_run.id)
    assert refreshed is not None
    assert refreshed.context_json["budget_exceeded"] == ["max_tokens"]
    events = EventStore(db_session).list_by_task(task_id=task.id)
    assert events[-1].event_type == "SUBAGENT_FAILED"
    assert events[-1].payload_json["failure_reason"] == "budget_exceeded"


def test_worker_denies_tool_outside_specialist_whitelist(
    db_session: Session,
    tmp_path,
) -> None:
    ensure_system_specialists(db_session)
    task = create_task(db_session)
    specialist = db_session.query(SubagentSpecialist).filter_by(
        slug="safety-checker",
        visibility="system",
    ).one()
    agent_run = SubagentManager(db_session).spawn(
        task=task,
        assignment={
            "step_key": "restricted",
            "tools": [{"tool_name": "run_shell", "input_json": {"command": "echo nope"}}],
        },
        specialist=specialist,
    )
    db_session.commit()

    status = execute_subagent(agent_run.id, session=db_session, workspace_root=tmp_path)

    assert status == "SUCCESS"
    refreshed = db_session.get(AgentRun, agent_run.id)
    assert refreshed is not None
    tool_result = refreshed.context_json["result"]["tool_results"][0]
    assert tool_result["status"] == "DENIED"
    assert "whitelist" in tool_result["error_message"]


def test_specialist_stats_endpoint_counts_success_budget_and_failures(
    db_session: Session,
) -> None:
    ensure_system_specialists(db_session)
    task = create_task(db_session)
    specialist = db_session.query(SubagentSpecialist).filter_by(
        slug="code-reviewer",
        visibility="system",
    ).one()
    success = SubagentManager(db_session).spawn(
        task=task,
        assignment={"step_key": "success"},
        specialist=specialist,
    )
    SubagentManager(db_session).finalize_with_output(
        agent_run=success,
        raw_output_dict={"issues": [], "summary": "clean"},
        budget_consumed={"cost_usd": "0.003", "tool_calls": 2, "runtime_seconds": 1.5},
        budget_exceeded=[],
    )
    budget = SubagentManager(db_session).spawn(
        task=task,
        assignment={"step_key": "budget"},
        specialist=specialist,
    )
    SubagentManager(db_session).finalize_with_output(
        agent_run=budget,
        raw_output_dict={"issues": [{"severity": "LOW", "message": "minor"}], "summary": "ok"},
        budget_consumed={"cost_usd": "0.007", "tool_calls": 4, "runtime_seconds": 2},
        budget_exceeded=["max_tokens"],
    )
    failed = SubagentManager(db_session).spawn(
        task=task,
        assignment={"step_key": "failed"},
        specialist=specialist,
    )
    failed.status = "FAILED"
    failed.context_json = {**failed.context_json, "failure_reason": "tool_denied"}
    db_session.commit()

    response = TestClient(app).get(
        f"/api/subagent-specialists/{specialist.id}/stats",
        headers=AUTH_HEADERS,
        params={"window": "30d"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["specialist_id"] == specialist.id
    assert payload["slug"] == "code-reviewer"
    assert payload["total_invocations"] == 3
    assert payload["success_count"] == 2
    assert payload["failed_count"] == 1
    assert payload["budget_exceeded_count"] == 1
    assert payload["success_rate"] == 0.667
    assert payload["avg_cost_usd"] == "0.005000"
    assert payload["total_cost_usd"] == "0.010000"
    assert payload["avg_tool_calls"] == 3.0
    assert payload["recent_failure_reasons"] == [{"reason": "tool_denied", "count": 1}]


def test_depth_guard_rejects_fourth_level_and_stats_count_event(
    db_session: Session,
) -> None:
    ensure_system_specialists(db_session)
    task = create_task(db_session)
    specialist = db_session.query(SubagentSpecialist).filter_by(
        slug="researcher",
        visibility="system",
    ).one()
    manager = SubagentManager(db_session)
    root = manager.spawn(task=task, assignment={"step_key": "root"}, specialist=specialist)
    level_two = manager.spawn(
        task=task,
        parent_agent_id=root.id,
        assignment={"step_key": "level_two"},
        specialist=specialist,
    )
    level_three = manager.spawn(
        task=task,
        parent_agent_id=level_two.id,
        assignment={"step_key": "level_three"},
        specialist=specialist,
    )

    try:
        manager.spawn(
            task=task,
            parent_agent_id=level_three.id,
            assignment={"step_key": "level_four"},
            specialist=specialist,
        )
    except SubagentDepthExceededError as exc:
        assert "depth 3" in str(exc)
    else:
        raise AssertionError("expected SubagentDepthExceededError")

    events = EventStore(db_session).list_by_task(task_id=task.id)
    rejected = [event for event in events if event.event_type == EventType.SUBAGENT_DEPTH_REJECTED]
    assert rejected
    assert rejected[-1].payload_json["specialist_id"] == specialist.id
    stats = compute_specialist_stats(db_session, specialist.id, "all")
    assert stats.total_invocations == 3
    assert stats.depth_rejected_count == 1


def test_ranking_selects_success_rate_after_min_history_and_recency_fallback(
    db_session: Session,
) -> None:
    ensure_system_specialists(db_session)
    first = db_session.query(SubagentSpecialist).filter_by(
        slug="researcher",
        visibility="system",
    ).one()
    second = db_session.query(SubagentSpecialist).filter_by(
        slug="synthesizer",
        visibility="system",
    ).one()

    selected, trace = select_specialist_by_ranking(
        [first, second],
        lambda specialist_id: (
            compute_specialist_stats(db_session, specialist_id, "all")
            if specialist_id in {first.id, second.id}
            else None
        ),
    )

    assert selected.id in {first.id, second.id}
    assert trace["resolved_by"] == "recency_fallback"

    task = create_task(db_session)
    manager = SubagentManager(db_session)
    for index in range(10):
        run = manager.spawn(
            task=task,
            assignment={"step_key": f"first_{index}"},
            specialist=first,
        )
        if index < 6:
            run.status = "SUCCESS"
        else:
            run.status = "FAILED"
    for index in range(10):
        run = manager.spawn(
            task=task,
            assignment={"step_key": f"second_{index}"},
            specialist=second,
        )
        if index < 9:
            run.status = "SUCCESS"
        else:
            run.status = "FAILED"
    db_session.commit()

    selected, trace = select_specialist_by_ranking(
        [first, second],
        lambda specialist_id: compute_specialist_stats(db_session, specialist_id, "all"),
    )

    assert selected.id == second.id
    assert trace["resolved_by"] == "success_rate_ranking"
    assert trace["stats"][second.slug]["success_rate"] == 0.9


def test_keyword_match_trace_uses_ranking_for_multiple_candidates(
    db_session: Session,
) -> None:
    ensure_system_specialists(db_session)
    first = db_session.query(SubagentSpecialist).filter_by(
        slug="researcher",
        visibility="system",
    ).one()
    second = db_session.query(SubagentSpecialist).filter_by(
        slug="synthesizer",
        visibility="system",
    ).one()
    second.trigger_keywords_json = list(second.trigger_keywords_json or []) + ["research"]
    task = create_task(db_session)
    manager = SubagentManager(db_session)
    for index in range(10):
        run = manager.spawn(
            task=task,
            assignment={"step_key": f"researcher_{index}"},
            specialist=first,
        )
        run.status = "SUCCESS" if index < 5 else "FAILED"
    for index in range(10):
        run = manager.spawn(
            task=task,
            assignment={"step_key": f"synthesizer_{index}"},
            specialist=second,
        )
        run.status = "SUCCESS" if index < 9 else "FAILED"
    db_session.commit()

    selected, trace = SubagentSpecialistRegistry(
        db_session, "dev-org"
    ).match_by_keywords_with_trace("research this release")

    assert selected is not None
    assert selected.id == second.id
    assert trace["resolved_by"] == "success_rate_ranking"
