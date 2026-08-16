from datetime import timedelta

from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.api.tasks import cancel_task
from app.db.models import (
    AgentRun,
    ExecutionPlan,
    ModelCall,
    Task,
    TaskSnapshot,
    TaskStep,
    ToolCall,
    utc_now,
)
from app.events.event_store import EventStore
from app.events.event_types import EventType
from app.events.replay import EventReplay
from app.main import app
from app.security.auth import AuthenticatedPrincipal
from tests.conftest import AUTH_HEADERS

ENGINEER_PRINCIPAL = AuthenticatedPrincipal(
    user_id="dev-engineer",
    organization_id="dev-org",
    roles=["engineer"],
    role="member",
)


def test_create_task_writes_task_created_event() -> None:
    client = TestClient(app)

    response = client.post(
        "/api/tasks",
        headers=AUTH_HEADERS,
        json={
            "title": "Demo",
            "goal": "Analyze project",
            "model_provider": "openai-compatible",
            "model_name": "default",
            "max_runtime_seconds": 1800,
            "max_subagents": 5,
            "enable_sandbox": True,
            "enable_network": False,
        },
    )

    assert response.status_code == 201
    task = response.json()
    assert task["status"] == "CREATED"

    events_response = client.get(f"/api/tasks/{task['id']}/events", headers=AUTH_HEADERS)

    assert events_response.status_code == 200
    events = events_response.json()["items"]
    assert [event["sequence"] for event in events] == [1]
    assert events[0]["event_type"] == "TASK_CREATED"


def test_events_stream_endpoint_exists() -> None:
    client = TestClient(app)
    created = client.post(
        "/api/tasks",
        headers=AUTH_HEADERS,
        json={
            "title": "Demo",
            "goal": "Analyze project",
            "model_provider": "openai-compatible",
            "model_name": "default",
        },
    ).json()

    response = client.get(
        f"/api/tasks/{created['id']}/events/stream?once=true",
        headers=AUTH_HEADERS,
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert "TASK_CREATED" in response.text


def test_tasks_require_bearer_token() -> None:
    client = TestClient(app)

    response = client.get("/api/tasks")

    assert response.status_code == 401


def test_task_cancel_resume_result_replay_and_audit_endpoints() -> None:
    client = TestClient(app)
    created = client.post(
        "/api/tasks",
        headers=AUTH_HEADERS,
        json={
            "title": "Runtime completion",
            "goal": "Exercise stage 12 task APIs",
            "model_provider": "openai-compatible",
            "model_name": "default",
        },
    ).json()
    task_id = created["id"]

    cancelled = client.post(f"/api/tasks/{task_id}/cancel", headers=AUTH_HEADERS)
    assert cancelled.status_code == 202
    assert cancelled.json()["status"] == "CANCELLED"

    replay_cancelled = client.post(
        f"/api/tasks/{task_id}/replay",
        headers=AUTH_HEADERS,
        json={},
    )
    assert replay_cancelled.status_code == 200
    assert replay_cancelled.json()["task_id"] == task_id
    assert "CANCELLED" in replay_cancelled.json()["state_summary"]

    resumed = client.post(f"/api/tasks/{task_id}/resume", headers=AUTH_HEADERS)
    assert resumed.status_code == 202
    assert resumed.json()["status"] == "COMPLETED"

    result = client.get(f"/api/tasks/{task_id}/result", headers=AUTH_HEADERS)
    assert result.status_code == 200
    payload = result.json()
    assert payload["task_id"] == task_id
    assert payload["status"] == "COMPLETED"
    assert payload["last_sequence"] >= 1
    assert payload["artifacts"][0]["name"] == "result.md"

    model_calls = client.get(f"/api/tasks/{task_id}/model-calls", headers=AUTH_HEADERS)
    tool_calls = client.get(f"/api/tasks/{task_id}/tool-calls", headers=AUTH_HEADERS)
    assert model_calls.status_code == 200
    assert model_calls.json()["items"][0]["model_provider"] == "openai-compatible"
    assert tool_calls.status_code == 200
    tool_call = tool_calls.json()["items"][0]
    assert tool_call["tool_name"] == "mcp_artifact_put"
    assert tool_call["output_kind"] == "json"
    assert tool_call["output_summary"].startswith("JSON 输出字段")
    assert tool_call["timeout_category"] is None


def test_task_cancel_retries_transient_sqlite_lock(
    db_session: Session,
    monkeypatch,
) -> None:
    task = Task(
        organization_id="dev-org",
        created_by="dev-engineer",
        title="Cancel retry",
        goal="Exercise transient SQLite cancellation lock",
        status="RUNNING",
        model_provider="openai-compatible",
        model_name="default",
        max_runtime_seconds=1800,
        max_subagents=0,
        enable_sandbox=False,
        enable_network=False,
        created_at=utc_now(),
        updated_at=utc_now(),
    )
    db_session.add(task)
    db_session.commit()

    original_commit = db_session.commit
    attempts = 0

    def flaky_commit() -> None:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise OperationalError("database is locked", None, None)
        original_commit()

    monkeypatch.setattr(db_session, "commit", flaky_commit)
    cancelled = cancel_task(task.id, db_session, ENGINEER_PRINCIPAL)

    assert attempts == 2
    assert cancelled.status == "CANCELLED"
    assert db_session.get(Task, task.id).status == "CANCELLED"


def test_task_cancel_terminalizes_active_model_calls(
    db_session: Session,
) -> None:
    task = Task(
        organization_id="dev-org",
        created_by="dev-engineer",
        title="Cancel model call",
        goal="Cancel an active model stream",
        status="RUNNING",
        model_provider="openai-compatible",
        model_name="default",
        max_runtime_seconds=1800,
        max_subagents=0,
        enable_sandbox=False,
        enable_network=False,
        created_at=utc_now(),
        updated_at=utc_now(),
    )
    db_session.add(task)
    db_session.flush()
    active = ModelCall(
        task_id=task.id,
        model_provider="openai-compatible",
        model_name="default",
        status="RUNNING",
        prompt_tokens=0,
        completion_tokens=0,
        duration_ms=0,
        request_json={},
        response_json={},
    )
    completed = ModelCall(
        task_id=task.id,
        model_provider="openai-compatible",
        model_name="default",
        status="SUCCESS",
        terminal_status="success",
        prompt_tokens=1,
        completion_tokens=1,
        duration_ms=10,
        request_json={},
        response_json={},
    )
    db_session.add_all([active, completed])
    db_session.commit()

    cancelled = cancel_task(task.id, db_session, ENGINEER_PRINCIPAL)
    db_session.expire_all()
    persisted_active = db_session.get(ModelCall, active.id)
    persisted_completed = db_session.get(ModelCall, completed.id)
    events = EventStore(db_session).list_by_task(task_id=task.id)

    assert cancelled.status == "CANCELLED"
    assert persisted_active is not None
    assert persisted_active.status == "FAILED"
    assert persisted_active.terminal_status == "stream_aborted"
    assert persisted_active.error_message == "stream closed before completion"
    assert persisted_completed is not None
    assert persisted_completed.status == "SUCCESS"
    failed_events = [event for event in events if event.event_type == EventType.MODEL_CALL_FAILED]
    assert len(failed_events) == 1
    assert failed_events[0].payload_json["cancelled"] is True
    assert events[-1].event_type == EventType.TASK_CANCELLED


def test_task_plan_steps_and_tool_execute_endpoints() -> None:
    client = TestClient(app)
    created = client.post(
        "/api/tasks",
        headers=AUTH_HEADERS,
        json={
            "title": "Plan and tools",
            "goal": "Inspect project and produce a report",
            "model_provider": "openai-compatible",
            "model_name": "default",
        },
    ).json()
    task_id = created["id"]

    started = client.post(f"/api/tasks/{task_id}/start", headers=AUTH_HEADERS)
    assert started.status_code == 202
    assert started.json()["status"] == "COMPLETED"

    plan = client.get(f"/api/tasks/{task_id}/plan", headers=AUTH_HEADERS)
    assert plan.status_code == 200
    plan_payload = plan.json()
    assert plan_payload["task_id"] == task_id
    assert plan_payload["version"] == 1
    assert plan_payload["steps"][0]["status"] == "STEP_COMPLETED"

    steps = client.get(f"/api/tasks/{task_id}/steps", headers=AUTH_HEADERS)
    assert steps.status_code == 200
    assert steps.json()["items"][0]["step_key"] == plan_payload["steps"][0]["step_key"]

    tool_execution = client.post(
        f"/api/tasks/{task_id}/tools/execute",
        headers=AUTH_HEADERS,
        json={
            "tool_name": "read_file",
            "input_json": {"path": "pyproject.toml"},
        },
    )
    assert tool_execution.status_code == 202
    tool_payload = tool_execution.json()
    assert tool_payload["allowed"] is True
    assert tool_payload["tool_call"]["tool_name"] == "read_file"
    assert tool_payload["tool_call"]["output_kind"] == "file_content"
    assert tool_payload["tool_call"]["output_summary"].startswith("文件内容")
    assert "content" in tool_payload["output"]


def test_tool_calls_support_filters_and_trace_deep_link(db_session: Session) -> None:
    task = Task(
        organization_id="dev-org",
        created_by="dev-engineer",
        title="Tool audit filters",
        goal="Filter tool calls",
        status="COMPLETED",
        model_provider="openai-compatible",
        model_name="default",
        max_runtime_seconds=1800,
        max_subagents=5,
        enable_sandbox=True,
        enable_network=False,
        created_at=utc_now(),
        updated_at=utc_now(),
    )
    db_session.add(task)
    db_session.flush()
    matching = ToolCall(
        task_id=task.id,
        tool_name="read_file",
        status="SUCCESS",
        risk_level="low",
        requires_sandbox=False,
        input_json={"path": "README.md"},
        output_json={"content": "ok"},
    )
    ignored = ToolCall(
        task_id=task.id,
        tool_name="shell",
        status="DENIED",
        risk_level="high",
        requires_sandbox=True,
        input_json={"command": "rm -rf /"},
        output_json={},
    )
    db_session.add_all([matching, ignored])
    db_session.flush()
    EventStore(db_session).append(
        task_id=task.id,
        event_type=EventType.TOOL_RESULT_RECEIVED,
        payload_json={"tool_call_id": matching.id, "tool_name": matching.tool_name},
        trace_id="trace-tool-filter",
    )
    db_session.commit()

    response = TestClient(app).get(
        f"/api/tasks/{task.id}/tool-calls",
        headers=AUTH_HEADERS,
        params={
            "tool_name": "read",
            "status": "SUCCESS",
            "risk_level": "low",
            "trace_id": "trace-tool-filter",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert [item["id"] for item in payload["items"]] == [matching.id]
    assert payload["items"][0]["trace_id"] == "trace-tool-filter"


def test_audit_detail_endpoints_include_console_acceptance_fields(
    db_session: Session,
) -> None:
    task = Task(
        organization_id="dev-org",
        created_by="dev-engineer",
        title="Audit detail acceptance",
        goal="Validate console audit detail fields",
        status="COMPLETED",
        model_provider="openai-compatible",
        model_name="default",
        max_runtime_seconds=1800,
        max_subagents=5,
        enable_sandbox=True,
        enable_network=False,
        created_at=utc_now(),
        updated_at=utc_now(),
    )
    db_session.add(task)
    db_session.flush()
    model_call = ModelCall(
        task_id=task.id,
        model_provider="openai-compatible",
        model_name="default",
        status="SUCCESS",
        prompt_tokens=3,
        completion_tokens=5,
        duration_ms=11,
        request_json={"estimated_prompt_tokens": 8, "messages": [{"content_length": 20}]},
        response_json={"content_preview": "模型响应摘要"},
    )
    tool_call = ToolCall(
        task_id=task.id,
        tool_name="read_file",
        status="SUCCESS",
        risk_level="low",
        requires_sandbox=False,
        duration_ms=7,
        input_json={"path": "README.md"},
        output_json={"content": "ok", "size_bytes": 2},
    )
    db_session.add_all([model_call, tool_call])
    db_session.flush()
    EventStore(db_session).append(
        task_id=task.id,
        event_type=EventType.MODEL_RESPONSE_RECEIVED,
        payload_json={"model_call_id": model_call.id},
        trace_id="trace-model-detail",
    )
    EventStore(db_session).append(
        task_id=task.id,
        event_type=EventType.TOOL_RESULT_RECEIVED,
        payload_json={"tool_call_id": tool_call.id},
        trace_id="trace-tool-detail",
    )
    db_session.commit()
    client = TestClient(app)

    model_calls = client.get(f"/api/tasks/{task.id}/model-calls", headers=AUTH_HEADERS)
    tool_calls = client.get(f"/api/tasks/{task.id}/tool-calls", headers=AUTH_HEADERS)

    assert model_calls.status_code == 200
    model_payload = model_calls.json()["items"][0]
    assert model_payload["trace_id"] == "trace-model-detail"
    assert model_payload["request_json"]["estimated_prompt_tokens"] == 8
    assert model_payload["response_json"]["content_preview"] == "模型响应摘要"
    assert model_payload["error_message"] is None
    assert tool_calls.status_code == 200
    tool_payload = tool_calls.json()["items"][0]
    assert tool_payload["trace_id"] == "trace-tool-detail"
    assert tool_payload["input_json"] == {"path": "README.md"}
    assert tool_payload["output_json"]["content"] == "ok"
    assert tool_payload["output_kind"] == "file_content"
    assert tool_payload["output_summary"].startswith("文件内容")


def test_task_plan_versions_and_diff_endpoint(db_session: Session) -> None:
    task = Task(
        organization_id="dev-org",
        created_by="dev-engineer",
        title="Plan versions",
        goal="Compare plan versions",
        status="RUNNING",
        model_provider="openai-compatible",
        model_name="default",
        max_runtime_seconds=1800,
        max_subagents=5,
        enable_sandbox=True,
        enable_network=False,
        created_at=utc_now(),
        updated_at=utc_now(),
    )
    db_session.add(task)
    db_session.flush()
    first_plan = ExecutionPlan(
        task_id=task.id,
        version=1,
        status="GENERATED",
        plan_json={
            "summary": "第一版计划",
            "planner_source": "deterministic",
            "planner_attempts": 1,
            "steps": [
                {
                    "key": "inspect",
                    "description": "检查项目",
                    "execution_mode": "sync",
                    "requires_sandbox": False,
                    "can_spawn_subagent": False,
                },
                {
                    "key": "report",
                    "description": "生成报告",
                    "execution_mode": "sync",
                    "requires_sandbox": False,
                    "can_spawn_subagent": False,
                },
            ],
        },
        created_at=utc_now(),
    )
    second_plan = ExecutionPlan(
        task_id=task.id,
        version=2,
        status="GENERATED",
        plan_json={
            "summary": "第二版计划",
            "planner_source": "llm_repaired",
            "planner_attempts": 2,
            "steps": [
                {
                    "key": "inspect",
                    "description": "深入检查项目",
                    "execution_mode": "sync",
                    "requires_sandbox": False,
                    "can_spawn_subagent": False,
                },
                {
                    "key": "subagent_research",
                    "description": "派生子 Agent 调研",
                    "execution_mode": "async",
                    "requires_sandbox": False,
                    "can_spawn_subagent": True,
                },
            ],
        },
        created_at=utc_now(),
    )
    db_session.add_all([first_plan, second_plan])
    db_session.commit()

    client = TestClient(app)
    versions = client.get(f"/api/tasks/{task.id}/plans", headers=AUTH_HEADERS)
    diff = client.get(
        f"/api/tasks/{task.id}/plans/diff?from_version=1&to_version=2",
        headers=AUTH_HEADERS,
    )

    assert versions.status_code == 200
    version_payload = versions.json()
    assert [item["version"] for item in version_payload["items"]] == [2, 1]
    assert version_payload["items"][0]["planner_source"] == "llm_repaired"
    assert diff.status_code == 200
    diff_payload = diff.json()
    assert diff_payload["added"] == 1
    assert diff_payload["removed"] == 1
    assert diff_payload["changed"] == 1
    assert diff_payload["unchanged"] == 0
    changes = {item["step_key"]: item["change_type"] for item in diff_payload["step_diffs"]}
    assert changes == {
        "inspect": "changed",
        "report": "removed",
        "subagent_research": "added",
    }


def test_task_result_aggregates_subagent_outputs(db_session: Session) -> None:
    task = Task(
        organization_id="dev-org",
        created_by="dev-engineer",
        title="Async aggregate",
        goal="Collect async result",
        status="COMPLETED",
        model_provider="openai-compatible",
        model_name="default",
        max_runtime_seconds=1800,
        max_subagents=5,
        enable_sandbox=True,
        enable_network=False,
        created_at=utc_now(),
        updated_at=utc_now(),
        completed_at=utc_now(),
    )
    db_session.add(task)
    db_session.flush()
    subagent = AgentRun(
        task_id=task.id,
        agent_type="subagent",
        status="SUCCESS",
        context_json={
            "step_key": "subagent_research",
            "result": {
                "summary": "异步调研完成",
                "tool_results": [
                    {
                        "tool_call_id": "tool-1",
                        "tool_name": "read_file",
                        "status": "SUCCESS",
                        "allowed": True,
                        "duration_ms": 1,
                        "input_json": {"path": "README.md"},
                        "output": {"content": "ok"},
                        "error_message": None,
                    }
                ],
                "react_trace": [
                    {
                        "round": 1,
                        "executed_tool_count": 1,
                        "next_tool_count": 0,
                        "done": True,
                    }
                ],
            },
        },
        started_at=utc_now(),
        completed_at=utc_now(),
    )
    db_session.add(subagent)
    EventStore(db_session).append(
        task_id=task.id,
        agent_run_id=subagent.id,
        event_type=EventType.SUBAGENT_COMPLETED,
        payload_json={"summary": "异步调研完成"},
    )
    db_session.commit()

    client = TestClient(app)
    result = client.get(f"/api/tasks/{task.id}/result", headers=AUTH_HEADERS)

    assert result.status_code == 200
    payload = result.json()
    subagent_result = payload["subagent_results"][0]
    assert subagent_result["id"] == subagent.id
    assert subagent_result["step_key"] == "subagent_research"
    assert subagent_result["status"] == "SUCCESS"
    assert subagent_result["summary"] == "异步调研完成"
    assert subagent_result["tool_results"][0]["tool_name"] == "read_file"
    assert subagent_result["artifacts"][0]["name"] == "README.md"
    assert subagent_result["artifacts"][0]["preview"] == "ok"
    assert subagent_result["react_trace"][0]["round"] == 1
    assert subagent_result["completed_at"] is not None
    assert payload["artifacts"][1]["name"] == "subagent-results.json"
    assert payload["artifacts"][2]["name"] == "subagent_research/README.md"
    assert "成功 1 个" in payload["summary"]


def test_replay_uses_snapshot_and_events_after_snapshot(db_session: Session) -> None:
    task = Task(
        organization_id="dev-org",
        created_by="dev-engineer",
        title="Replay snapshot",
        goal="Recover from snapshot",
        status="RUNNING",
        model_provider="openai-compatible",
        model_name="default",
        max_runtime_seconds=1800,
        max_subagents=5,
        enable_sandbox=True,
        enable_network=False,
        created_at=utc_now(),
        updated_at=utc_now(),
    )
    db_session.add(task)
    db_session.flush()
    event_store = EventStore(db_session)
    event_store.append(
        task_id=task.id,
        event_type=EventType.TASK_CREATED,
        payload_json={"title": task.title},
    )
    for index in range(99):
        event_store.append(
            task_id=task.id,
            event_type=EventType.SUBAGENT_PROGRESS,
            payload_json={"index": index},
        )
    event_store.append(
        task_id=task.id,
        event_type=EventType.TASK_FAILED,
        payload_json={"summary": "boom"},
    )
    db_session.commit()

    snapshot = db_session.query(TaskSnapshot).filter(TaskSnapshot.task_id == task.id).one()
    assert snapshot.sequence == 100

    client = TestClient(app)
    replay = client.post(
        f"/api/tasks/{task.id}/replay",
        headers=AUTH_HEADERS,
        json={},
    )

    assert replay.status_code == 200
    payload = replay.json()
    assert payload["sequence"] == 101
    assert "FAILED" in payload["state_summary"]
    assert payload["failure_point"]["sequence"] == 101


def _failed_task_with_three_step_plan(db_session: Session) -> tuple[Task, ExecutionPlan]:
    task = Task(
        organization_id="dev-org",
        created_by="dev-engineer",
        title="Step resume from failed step",
        goal="Continue after selected failure",
        status="FAILED",
        model_provider="openai-compatible",
        model_name="default",
        max_runtime_seconds=1800,
        max_subagents=5,
        enable_sandbox=True,
        enable_network=False,
        created_at=utc_now(),
        updated_at=utc_now(),
    )
    db_session.add(task)
    db_session.flush()
    plan = ExecutionPlan(
        task_id=task.id,
        version=1,
        status="GENERATED",
        plan_json={
            "summary": "Continue after selected failure",
            "steps": [
                {
                    "key": "inspect_project",
                    "description": "Inspect project structure",
                    "execution_mode": "sync",
                    "requires_sandbox": False,
                    "can_spawn_subagent": False,
                    "expected_events": ["STEP_STARTED", "STEP_COMPLETED"],
                },
                {
                    "key": "produce_report",
                    "description": "Produce final report",
                    "execution_mode": "sync",
                    "requires_sandbox": False,
                    "can_spawn_subagent": False,
                    "expected_events": ["STEP_STARTED", "STEP_COMPLETED"],
                },
                {
                    "key": "verify_report",
                    "description": "Verify final report",
                    "execution_mode": "sync",
                    "requires_sandbox": False,
                    "can_spawn_subagent": False,
                    "expected_events": ["STEP_STARTED", "STEP_COMPLETED"],
                },
            ],
        },
        created_at=utc_now(),
    )
    db_session.add(plan)
    db_session.flush()
    event_store = EventStore(db_session)
    event_store.append(
        task_id=task.id,
        event_type=EventType.TASK_CREATED,
        payload_json={"title": task.title},
    )
    event_store.append(
        task_id=task.id,
        event_type=EventType.PLAN_GENERATED,
        payload_json={"plan_id": plan.id, "plan": plan.plan_json},
    )
    event_store.append(
        task_id=task.id,
        event_type=EventType.STEP_STARTED,
        payload_json={"step_key": "inspect_project"},
    )
    event_store.append(
        task_id=task.id,
        event_type=EventType.STEP_COMPLETED,
        payload_json={"step_key": "inspect_project"},
    )
    event_store.append(
        task_id=task.id,
        event_type=EventType.STEP_STARTED,
        payload_json={"step_key": "produce_report"},
    )
    event_store.append(
        task_id=task.id,
        event_type=EventType.STEP_FAILED,
        payload_json={"step_key": "produce_report", "summary": "boom"},
    )
    event_store.append(
        task_id=task.id,
        event_type=EventType.TASK_FAILED,
        payload_json={"failed_step": "produce_report", "summary": "boom"},
    )
    db_session.commit()
    return task, plan


def test_resume_reuses_plan_and_skips_completed_steps(db_session: Session) -> None:
    task = Task(
        organization_id="dev-org",
        created_by="dev-engineer",
        title="Resume from failed step",
        goal="Continue after failure",
        status="FAILED",
        model_provider="openai-compatible",
        model_name="default",
        max_runtime_seconds=1800,
        max_subagents=5,
        enable_sandbox=True,
        enable_network=False,
        created_at=utc_now(),
        updated_at=utc_now(),
    )
    db_session.add(task)
    db_session.flush()
    plan = ExecutionPlan(
        task_id=task.id,
        version=1,
        status="GENERATED",
        plan_json={
            "summary": "Continue after failure",
            "steps": [
                {
                    "key": "inspect_project",
                    "description": "Inspect project structure",
                    "execution_mode": "sync",
                    "requires_sandbox": False,
                    "can_spawn_subagent": False,
                    "expected_events": ["STEP_STARTED", "STEP_COMPLETED"],
                },
                {
                    "key": "produce_report",
                    "description": "Produce final report",
                    "execution_mode": "sync",
                    "requires_sandbox": False,
                    "can_spawn_subagent": False,
                    "expected_events": ["STEP_STARTED", "STEP_COMPLETED"],
                },
            ],
        },
        created_at=utc_now(),
    )
    db_session.add(plan)
    db_session.flush()
    event_store = EventStore(db_session)
    event_store.append(
        task_id=task.id,
        event_type=EventType.TASK_CREATED,
        payload_json={"title": task.title},
    )
    event_store.append(
        task_id=task.id,
        event_type=EventType.PLAN_GENERATED,
        payload_json={"plan_id": plan.id, "plan": plan.plan_json},
    )
    event_store.append(
        task_id=task.id,
        event_type=EventType.STEP_STARTED,
        payload_json={"step_key": "inspect_project"},
    )
    event_store.append(
        task_id=task.id,
        event_type=EventType.STEP_COMPLETED,
        payload_json={"step_key": "inspect_project"},
    )
    event_store.append(
        task_id=task.id,
        event_type=EventType.STEP_STARTED,
        payload_json={"step_key": "produce_report"},
    )
    event_store.append(
        task_id=task.id,
        event_type=EventType.STEP_FAILED,
        payload_json={"step_key": "produce_report", "summary": "boom"},
    )
    event_store.append(
        task_id=task.id,
        event_type=EventType.TASK_FAILED,
        payload_json={"failed_step": "produce_report", "summary": "boom"},
    )
    db_session.commit()

    client = TestClient(app)
    resumed = client.post(f"/api/tasks/{task.id}/resume", headers=AUTH_HEADERS)

    assert resumed.status_code == 202
    assert resumed.json()["status"] == "COMPLETED"
    steps = list(
        db_session.query(TaskStep)
        .filter(TaskStep.task_id == task.id)
        .order_by(TaskStep.started_at)
        .all()
    )
    assert [step.step_key for step in steps] == ["produce_report"]
    events = client.get(f"/api/tasks/{task.id}/events", headers=AUTH_HEADERS).json()["items"]
    event_types = [event["event_type"] for event in events]
    assert "STEP_SKIPPED" in event_types
    assert event_types.count("PLAN_GENERATED") == 1


def test_resume_from_selected_step_continues_plan(db_session: Session) -> None:
    task, _plan = _failed_task_with_three_step_plan(db_session)
    client = TestClient(app)

    response = client.post(
        f"/api/tasks/{task.id}/steps/resume",
        headers=AUTH_HEADERS,
        json={"step_keys": ["produce_report"]},
    )

    assert response.status_code == 202
    payload = response.json()
    assert payload["status"] == "COMPLETED"
    assert payload["resume_from_step_key"] == "produce_report"
    assert payload["requested_step_keys"] == ["produce_report"]
    assert payload["resumed_step_keys"] == ["produce_report", "verify_report"]
    assert payload["pending_step_keys"] == []
    steps = list(
        db_session.query(TaskStep)
        .filter(TaskStep.task_id == task.id)
        .order_by(TaskStep.started_at)
        .all()
    )
    assert [step.step_key for step in steps] == ["produce_report", "verify_report"]
    events = client.get(f"/api/tasks/{task.id}/events", headers=AUTH_HEADERS).json()["items"]
    event_types = [event["event_type"] for event in events]
    assert event_types.count("TASK_RESUMED") == 1
    assert event_types.count("STEP_RETRIED") == 2
    assert event_types[-1] == "TASK_COMPLETED"
    replay_state = EventReplay(db_session).replay_state_json(task_id=task.id)
    assert replay_state["status"] == "COMPLETED"
    assert replay_state["failed_steps"] == []
    assert replay_state["failure_point"] is None


def test_resume_from_selected_step_rejects_unknown_step(db_session: Session) -> None:
    task, _plan = _failed_task_with_three_step_plan(db_session)
    client = TestClient(app)

    response = client.post(
        f"/api/tasks/{task.id}/steps/resume",
        headers=AUTH_HEADERS,
        json={"step_keys": ["missing_step"]},
    )

    assert response.status_code == 422
    assert response.json()["detail"]["message"] == "步骤键不存在"
    assert response.json()["detail"]["unknown_step_keys"] == ["missing_step"]


def test_plan_state_uses_latest_step_attempt(db_session: Session) -> None:
    task, plan = _failed_task_with_three_step_plan(db_session)
    failed_at = utc_now()
    completed_at = failed_at + timedelta(seconds=1)
    db_session.add(
        TaskStep(
            task_id=task.id,
            plan_id=plan.id,
            step_key="produce_report",
            description="Produce final report",
            status="STEP_FAILED",
            execution_mode="sync",
            started_at=failed_at,
            completed_at=failed_at,
            error_message="old failure",
        )
    )
    db_session.flush()
    db_session.add(
        TaskStep(
            task_id=task.id,
            plan_id=plan.id,
            step_key="produce_report",
            description="Produce final report",
            status="STEP_COMPLETED",
            execution_mode="sync",
            started_at=completed_at,
            completed_at=completed_at,
        )
    )
    db_session.commit()
    client = TestClient(app)

    response = client.get(f"/api/tasks/{task.id}/plan", headers=AUTH_HEADERS)

    assert response.status_code == 200
    produce_step = next(
        step for step in response.json()["steps"] if step["step_key"] == "produce_report"
    )
    assert produce_step["status"] == "STEP_COMPLETED"
    assert produce_step["error_message"] is None
