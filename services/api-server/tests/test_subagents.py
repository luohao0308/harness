import json
from datetime import timedelta
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.agents.model_gateway import ModelRequest, ModelResponse
from app.agents.specialists import ensure_system_specialists
from app.agents.subagent_manager import (
    MAX_FANOUT_PER_STEP,
    SUBAGENT_CONCURRENCY_LIMIT,
    FanoutCapacityExceededError,
    SubagentManager,
)
from app.db.models import Agent, AgentRun, SubagentRecoveryBatch, SubagentSpecialist, Task, utc_now
from app.events.event_store import EventStore
from app.main import app
from app.tools.capabilities import CapabilityRegistry
from app.workers.subagent_recovery_worker import _sqlite_recovery_lock, recover_stalled_subagents
from app.workers.subagent_worker import (
    DEFAULT_REACT_CONTEXT_RECENT_RESULTS,
    DEFAULT_SUBAGENT_TIMEOUT_SECONDS,
    execute_subagent,
)
from tests.conftest import AUTH_HEADERS

ADMIN_HEADERS = {"Authorization": "Bearer dev-admin-token"}


class SequencedModelGateway:
    def __init__(self, contents: list[dict]) -> None:
        self.contents = contents
        self.requests: list[ModelRequest] = []

    def complete(self, request: ModelRequest) -> ModelResponse:
        self.requests.append(request)
        content = self.contents[min(len(self.requests) - 1, len(self.contents) - 1)]
        return ModelResponse(
            content=json.dumps(content, ensure_ascii=False),
            model_provider=request.model_provider,
            model_name=request.model_name,
            usage={"prompt_tokens": 0, "completion_tokens": 0},
            raw_response={"mode": "test"},
        )


def create_task(db_session: Session, organization_id: str = "dev-org") -> Task:
    if db_session.get(Agent, "subagent-test-agent") is None:
        db_session.add(
            Agent(
                id="subagent-test-agent",
                organization_id=None,
                name="Subagent Test Agent",
                description="Owns read_file for subagent worker tests",
                role="tester",
                status="ACTIVE",
                model_provider="default",
                model_name="default",
                system_prompt="Run subagent tools through capability attachments.",
                tools_json=["read_file"],
                routing_tags=[],
            )
        )
        db_session.flush()
    task = Task(
        organization_id=organization_id,
        agent_id="subagent-test-agent",
        created_by="dev-engineer",
        title="Demo",
        goal="Analyze project",
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
    CapabilityRegistry(db_session, task.organization_id).backfill_agent_attachments(
        "subagent-test-agent",
        attached_by="test",
    )
    return task


def test_spawn_creates_pending_agent_run_and_event(db_session: Session) -> None:
    task = create_task(db_session)

    agent_run = SubagentManager(db_session).spawn(
        task=task,
        assignment={"step_key": "dependency_review"},
    )

    assert agent_run.status == "PENDING"
    assert agent_run.agent_type == "subagent"
    assert DEFAULT_SUBAGENT_TIMEOUT_SECONDS == 900
    assert SUBAGENT_CONCURRENCY_LIMIT == 5
    events = EventStore(db_session).list_by_task(task_id=task.id)
    assert events[0].event_type == "SUBAGENT_SPAWNED"


def test_worker_success_flow_writes_started_and_completed(db_session: Session) -> None:
    task = create_task(db_session)
    agent_run = SubagentManager(db_session).spawn(task=task, assignment={"step_key": "review"})
    db_session.commit()

    status = execute_subagent(agent_run.id, session=db_session)

    assert status == "SUCCESS"
    refreshed = db_session.get(AgentRun, agent_run.id)
    assert refreshed is not None
    assert refreshed.status == "SUCCESS"
    assert refreshed.context_json["result"]["summary"].startswith("Subagent completed review")
    events = EventStore(db_session).list_by_task(task_id=task.id)
    event_types = [event.event_type for event in events]
    assert event_types[0:3] == ["SUBAGENT_SPAWNED", "SUBAGENT_STARTED", "SUBAGENT_PROGRESS"]
    assert "MODEL_CALLED" in event_types
    assert "MODEL_RESPONSE_RECEIVED" in event_types
    assert event_types[-1] == "SUBAGENT_COMPLETED"


def test_worker_executes_assignment_tools_and_writes_results(
    db_session: Session,
    tmp_path: Path,
) -> None:
    task = create_task(db_session)
    target = tmp_path / "notes.md"
    target.write_text("异步工具结果", encoding="utf-8")
    agent_run = SubagentManager(db_session).spawn(
        task=task,
        assignment={
            "step_key": "tool_review",
            "tools": [{"tool_name": "read_file", "input_json": {"path": "notes.md"}}],
        },
    )
    db_session.commit()

    status = execute_subagent(agent_run.id, session=db_session, workspace_root=tmp_path)

    assert status == "SUCCESS"
    refreshed = db_session.get(AgentRun, agent_run.id)
    assert refreshed is not None
    tool_results = refreshed.context_json["result"]["tool_results"]
    assert tool_results[0]["tool_name"] == "read_file"
    assert tool_results[0]["status"] == "SUCCESS"
    assert tool_results[0]["input_json"]["path"] == "notes.md"
    assert tool_results[0]["output"]["content"] == "异步工具结果"
    assert "工具执行 1 个" in refreshed.context_json["result"]["summary"]
    events = EventStore(db_session).list_by_task(task_id=task.id)
    event_types = [event.event_type for event in events]
    assert "TOOL_CALLED" in event_types
    assert "TOOL_RESULT_RECEIVED" in event_types


def test_worker_denies_assignment_tool_missing_agent_attachment(
    db_session: Session,
    tmp_path: Path,
) -> None:
    task = create_task(db_session)
    agent_run = SubagentManager(db_session).spawn(
        task=task,
        assignment={
            "step_key": "tool_review",
            "tools": [{"tool_name": "list_files", "input_json": {"root": "."}}],
        },
    )
    db_session.commit()

    status = execute_subagent(agent_run.id, session=db_session, workspace_root=tmp_path)

    assert status == "SUCCESS"
    refreshed = db_session.get(AgentRun, agent_run.id)
    assert refreshed is not None
    tool_result = refreshed.context_json["result"]["tool_results"][0]
    assert tool_result["tool_name"] == "list_files"
    assert tool_result["status"] == "DENIED"
    assert tool_result["allowed"] is False
    assert "not attached to capability list_files" in tool_result["error_message"]


def test_worker_runs_multiround_react_tools(
    db_session: Session,
    tmp_path: Path,
) -> None:
    task = create_task(db_session)
    (tmp_path / "notes.md").write_text("第一轮", encoding="utf-8")
    (tmp_path / "extra.md").write_text("第二轮", encoding="utf-8")
    gateway = SequencedModelGateway(
        [
            {
                "summary": "第一轮完成，继续补充文件",
                "done": False,
                "next_tools": [{"tool_name": "read_file", "input_json": {"path": "extra.md"}}],
            },
            {"summary": "多轮 ReAct 子 Agent 完成", "done": True, "next_tools": []},
        ]
    )
    agent_run = SubagentManager(db_session).spawn(
        task=task,
        assignment={
            "step_key": "react_review",
            "max_tool_rounds": 2,
            "tools": [{"tool_name": "read_file", "input_json": {"path": "notes.md"}}],
        },
    )
    db_session.commit()

    status = execute_subagent(
        agent_run.id,
        session=db_session,
        workspace_root=tmp_path,
        model_gateway=gateway,
    )

    assert status == "SUCCESS"
    refreshed = db_session.get(AgentRun, agent_run.id)
    assert refreshed is not None
    result = refreshed.context_json["result"]
    assert result["summary"] == "多轮 ReAct 子 Agent 完成"
    assert [item["output"]["content"] for item in result["tool_results"]] == [
        "第一轮",
        "第二轮",
    ]
    assert result["react_trace"] == [
        {
            "round": 1,
            "executed_tool_count": 1,
            "next_tool_count": 1,
            "done": False,
            "context_retained_tool_result_count": 1,
            "context_omitted_tool_result_count": 0,
        },
        {
            "round": 2,
            "executed_tool_count": 1,
            "next_tool_count": 0,
            "done": True,
            "context_retained_tool_result_count": 2,
            "context_omitted_tool_result_count": 0,
        },
    ]
    assert result["context_summary"]["total_tool_results"] == 2
    assert result["context_summary"]["retained_tool_results"] == 2
    assert result["tool_results"][0]["input_json"]["path"] == "notes.md"
    assert len(gateway.requests) == 2
    first_payload = json.loads(gateway.requests[0].messages[-1].content)
    assert "tool_results" not in first_payload
    first_tool_context = first_payload["tool_context"]["recent_tool_results"][0]
    assert first_tool_context["output_preview"]["content"] == "第一轮"
    events = EventStore(db_session).list_by_task(task_id=task.id)
    react_events = [
        event
        for event in events
        if event.event_type == "SUBAGENT_PROGRESS"
        and event.payload_json.get("stage") == "react_round_completed"
    ]
    assert [event.payload_json["round"] for event in react_events] == [1, 2]


def test_worker_compacts_long_react_context_for_model_requests(
    db_session: Session,
    tmp_path: Path,
) -> None:
    task = create_task(db_session)
    for index in range(1, 6):
        (tmp_path / f"round-{index}.md").write_text(f"第 {index} 轮" * 600, encoding="utf-8")
    gateway = SequencedModelGateway(
        [
            {
                "summary": f"第 {index} 轮完成",
                "done": index == 5,
                "next_tools": []
                if index == 5
                else [{"tool_name": "read_file", "input_json": {"path": f"round-{index + 1}.md"}}],
            }
            for index in range(1, 6)
        ]
    )
    agent_run = SubagentManager(db_session).spawn(
        task=task,
        assignment={
            "step_key": "long_context_review",
            "max_tool_rounds": 5,
            "tools": [{"tool_name": "read_file", "input_json": {"path": "round-1.md"}}],
        },
    )
    db_session.commit()

    status = execute_subagent(
        agent_run.id,
        session=db_session,
        workspace_root=tmp_path,
        model_gateway=gateway,
    )

    assert status == "SUCCESS"
    refreshed = db_session.get(AgentRun, agent_run.id)
    assert refreshed is not None
    result = refreshed.context_json["result"]
    assert len(result["tool_results"]) == 5
    assert result["context_summary"]["total_tool_results"] == 5
    assert (
        result["context_summary"]["retained_tool_results"] == DEFAULT_REACT_CONTEXT_RECENT_RESULTS
    )
    assert result["context_summary"]["omitted_tool_results"] == 2
    assert result["react_trace"][-1]["context_omitted_tool_result_count"] == 2
    last_payload = json.loads(gateway.requests[-1].messages[-1].content)
    assert last_payload["tool_context"]["total_tool_results"] == 5
    assert last_payload["tool_context"]["omitted_tool_results"] == 2
    assert (
        len(last_payload["tool_context"]["recent_tool_results"])
        == DEFAULT_REACT_CONTEXT_RECENT_RESULTS
    )
    preview = last_payload["tool_context"]["recent_tool_results"][-1]["output_preview"]["content"]
    assert preview.endswith("...[truncated]")


def test_worker_timeout_flow_writes_timeout_event(db_session: Session) -> None:
    task = create_task(db_session)
    agent_run = SubagentManager(db_session).spawn(task=task, assignment={"step_key": "slow"})
    db_session.commit()

    status = execute_subagent(agent_run.id, simulate_timeout=True, session=db_session)

    assert status == "TIMEOUT"
    events = EventStore(db_session).list_by_task(task_id=task.id)
    assert events[-1].event_type == "SUBAGENT_TIMEOUT"


def test_subagent_api_list_get_and_cancel(db_session: Session) -> None:
    task = create_task(db_session)
    subagent = SubagentManager(db_session).spawn(
        task=task,
        assignment={"step_key": "dependency_review"},
    )
    db_session.commit()

    client = TestClient(app)

    listed = client.get(f"/api/tasks/{task.id}/subagents", headers=AUTH_HEADERS)
    assert listed.status_code == 200
    assert listed.json()["items"][0]["id"] == subagent.id
    organization_list = client.get("/api/subagents", headers=AUTH_HEADERS)
    assert organization_list.status_code == 200
    organization_item = organization_list.json()["items"][0]
    assert organization_item["id"] == subagent.id
    assert organization_item["task_id"] == task.id
    assert organization_item["task_title"] == task.title
    assert organization_item["task_status"] == task.status
    assert organization_item["step_key"] == "dependency_review"
    filtered = client.get("/api/subagents", headers=AUTH_HEADERS, params={"status": "RUNNING"})
    assert filtered.status_code == 200
    assert filtered.json()["items"] == []

    fetched = client.get(f"/api/subagents/{subagent.id}", headers=AUTH_HEADERS)
    assert fetched.status_code == 200

    cancelled = client.post(f"/api/subagents/{subagent.id}/cancel", headers=AUTH_HEADERS)
    assert cancelled.status_code == 202
    assert cancelled.json()["status"] == "CANCELLED"


def test_subagent_api_create_for_task(db_session: Session) -> None:
    task = create_task(db_session)
    db_session.commit()
    client = TestClient(app)

    created = client.post(
        f"/api/tasks/{task.id}/subagents",
        headers=AUTH_HEADERS,
        json={
            "assignment": {"step_key": "parallel_review", "description": "并发审查"},
            "timeout_seconds": 120,
        },
    )

    assert created.status_code == 201
    payload = created.json()
    assert payload["task_id"] == task.id
    assert payload["status"] == "PENDING"
    assert payload["context_json"]["step_key"] == "parallel_review"


def test_spawn_fanout_creates_shared_batch_metadata_and_api_projection(
    db_session: Session,
) -> None:
    ensure_system_specialists(db_session)
    task = create_task(db_session)
    specialists = [
        db_session.query(SubagentSpecialist).filter_by(slug=slug, visibility="system").one()
        for slug in ["researcher", "code-reviewer", "safety-checker"]
    ]
    batch_id, runs = SubagentManager(db_session).spawn_fanout(
        task=task,
        assignment={"step_key": "parallel_experts", "description": "并行专家审查"},
        specialists=specialists,
        aggregation="concat",
    )
    runs[0].status = "SUCCESS"
    runs[1].status = "FAILED"
    db_session.commit()

    assert batch_id.startswith("fanout-")
    assert [run.context_json["fanout_index"] for run in runs] == [0, 1, 2]
    assert {run.context_json["fanout_batch_id"] for run in runs} == {batch_id}
    assert {run.context_json["fanout_total"] for run in runs} == {3}
    events = EventStore(db_session).list_by_task(task_id=task.id)
    spawned = [event for event in events if event.event_type == "SUBAGENT_SPAWNED"]
    assert len(spawned) == 3
    assert spawned[0].payload_json["assignment"]["fanout_batch_id"] == batch_id

    client = TestClient(app)
    listed = client.get(f"/api/tasks/{task.id}/subagents", headers=AUTH_HEADERS)
    batches = client.get(f"/api/tasks/{task.id}/fanout-batches", headers=AUTH_HEADERS)
    result = client.get(f"/api/tasks/{task.id}/result", headers=AUTH_HEADERS)

    assert listed.status_code == 200
    assert {item["fanout_batch_id"] for item in listed.json()["items"]} == {batch_id}
    assert batches.status_code == 200
    batch = batches.json()["items"][0]
    assert batch["fanout_batch_id"] == batch_id
    assert batch["step_key"] == "parallel_experts"
    assert batch["fanout_total"] == 3
    assert batch["aggregation"] == "concat"
    assert batch["statuses"] == {"SUCCESS": 1, "FAILED": 1, "PENDING": 1}
    assert [member["fanout_index"] for member in batch["members"]] == [0, 1, 2]
    assert result.status_code == 200
    result_members = result.json()["subagent_results"]
    assert {item["fanout_batch_id"] for item in result_members} == {batch_id}
    assert [item["fanout_index"] for item in result_members] == [0, 1, 2]


def test_spawn_fanout_rejects_oversized_and_capacity_excess(
    db_session: Session,
) -> None:
    ensure_system_specialists(db_session)
    task = create_task(db_session)
    researcher = db_session.query(SubagentSpecialist).filter_by(
        slug="researcher",
        visibility="system",
    ).one()
    manager = SubagentManager(db_session)

    too_many = [researcher for _ in range(MAX_FANOUT_PER_STEP + 1)]
    try:
        manager.spawn_fanout(
            task=task,
            assignment={"step_key": "too_many"},
            specialists=too_many,
        )
    except FanoutCapacityExceededError as exc:
        assert "exceeds max" in str(exc)
    else:
        raise AssertionError("expected FanoutCapacityExceededError")

    for index in range(SUBAGENT_CONCURRENCY_LIMIT - 1):
        manager.spawn(task=task, assignment={"step_key": f"existing_{index}"})

    try:
        manager.spawn_fanout(
            task=task,
            assignment={"step_key": "over_capacity"},
            specialists=[researcher, researcher],
        )
    except FanoutCapacityExceededError as exc:
        assert "concurrency capacity" in str(exc)
    else:
        raise AssertionError("expected FanoutCapacityExceededError")


def test_subagent_recovery_resets_stale_running_and_times_out_expired(
    db_session: Session,
) -> None:
    task = create_task(db_session)
    manager = SubagentManager(db_session)
    stale = manager.spawn(
        task=task,
        assignment={"step_key": "stale_worker"},
        timeout_seconds=1800,
    )
    stale.status = "RUNNING"
    stale.started_at = utc_now() - timedelta(seconds=901)
    expired = manager.spawn(
        task=task,
        assignment={"step_key": "expired_worker"},
        timeout_seconds=1,
    )
    expired.status = "RUNNING"
    expired.started_at = utc_now() - timedelta(seconds=60)
    expired.timeout_at = utc_now() - timedelta(seconds=1)
    db_session.commit()

    client = TestClient(app)
    recovered = client.post(
        f"/api/tasks/{task.id}/subagents/recover",
        headers=AUTH_HEADERS,
        json={"stale_after_seconds": 900, "enqueue": False},
    )

    assert recovered.status_code == 202
    payload = recovered.json()
    assert payload["batch_id"].startswith("manual-")
    assert payload["trigger"] == "manual"
    assert payload["stale_after_seconds"] == 900
    assert payload["enqueue"] is False
    assert payload["scanned_count"] == 2
    assert payload["recovered_count"] == 2
    assert payload["action_counts"] == {
        "marked_timeout": 1,
        "reset_to_pending": 1,
    }
    assert payload["completed_at"]
    actions = {item["id"]: item["action"] for item in payload["recovered"]}
    assert actions[stale.id] == "reset_to_pending"
    assert actions[expired.id] == "marked_timeout"
    refreshed_stale = db_session.get(AgentRun, stale.id)
    refreshed_expired = db_session.get(AgentRun, expired.id)
    assert refreshed_stale is not None
    assert refreshed_stale.status == "PENDING"
    assert refreshed_stale.started_at is None
    assert refreshed_stale.context_json["recovery_attempts"] == 1
    assert refreshed_stale.context_json["takeover_generation"] == 1
    assert refreshed_stale.context_json["last_takeover_owner"] == "api:dev-engineer"
    assert refreshed_expired is not None
    assert refreshed_expired.status == "TIMEOUT"
    events = EventStore(db_session).list_by_task(task_id=task.id)
    event_types = [event.event_type for event in events]
    assert "SUBAGENT_PROGRESS" in event_types
    assert event_types[-1] == "SUBAGENT_TIMEOUT"
    takeover_events = [
        event
        for event in events
        if event.event_type == "SUBAGENT_PROGRESS"
        and event.payload_json.get("stage") == "worker_takeover"
    ]
    assert takeover_events[0].payload_json["takeover_generation"] == 1
    assert takeover_events[0].payload_json["takeover_owner"] == "api:dev-engineer"

    history = client.get(
        f"/api/tasks/{task.id}/subagents/recovery-batches",
        headers=AUTH_HEADERS,
    )
    assert history.status_code == 200
    batch = history.json()["items"][0]
    assert batch["batch_id"] == payload["batch_id"]
    assert batch["trigger"] == "manual"
    assert batch["task_id"] == task.id
    assert batch["lock_acquired"] is True
    assert batch["task_count"] == 1
    assert batch["scanned_count"] == 2
    assert batch["recovered_count"] == 2


def test_subagent_bulk_cancel_cancels_selected_owned_runs(db_session: Session) -> None:
    task = create_task(db_session)
    manager = SubagentManager(db_session)
    pending = manager.spawn(task=task, assignment={"step_key": "pending_bulk"})
    running = manager.spawn(task=task, assignment={"step_key": "running_bulk"})
    running.status = "RUNNING"
    completed = manager.spawn(task=task, assignment={"step_key": "done_bulk"})
    completed.status = "SUCCESS"
    db_session.commit()

    response = TestClient(app).post(
        "/api/subagents/bulk",
        headers=AUTH_HEADERS,
        json={
            "action": "cancel",
            "subagent_ids": [pending.id, running.id, completed.id, "missing-subagent"],
        },
    )

    assert response.status_code == 202
    payload = response.json()
    assert payload["requested_count"] == 4
    assert payload["succeeded_count"] == 3
    assert payload["failed_count"] == 1
    items = {item["id"]: item for item in payload["items"]}
    assert items[pending.id]["action"] == "cancelled"
    assert items[running.id]["status"] == "CANCELLED"
    assert items[completed.id]["action"] == "skipped_terminal"
    assert items["missing-subagent"]["success"] is False
    assert db_session.get(AgentRun, pending.id).status == "CANCELLED"
    assert db_session.get(AgentRun, running.id).status == "CANCELLED"
    assert db_session.get(AgentRun, completed.id).status == "SUCCESS"


def test_subagent_recovery_sweep_scans_all_tasks(db_session: Session) -> None:
    first_task = create_task(db_session)
    second_task = create_task(db_session)
    first_stale = SubagentManager(db_session).spawn(
        task=first_task,
        assignment={"step_key": "first_stale"},
        timeout_seconds=1800,
    )
    first_stale.status = "RUNNING"
    first_stale.started_at = utc_now() - timedelta(seconds=901)
    second_expired = SubagentManager(db_session).spawn(
        task=second_task,
        assignment={"step_key": "second_expired"},
        timeout_seconds=1,
    )
    second_expired.status = "RUNNING"
    second_expired.started_at = utc_now() - timedelta(seconds=60)
    second_expired.timeout_at = utc_now() - timedelta(seconds=1)
    db_session.commit()

    result = recover_stalled_subagents(
        stale_after_seconds=900,
        enqueue=False,
        session=db_session,
    )

    assert result["lock_acquired"] is True
    assert result["batch_id"].startswith("auto-")
    assert result["trigger"] == "auto"
    assert result["stale_after_seconds"] == 900
    assert result["enqueue"] is False
    assert result["task_count"] == 2
    assert result["scanned_count"] == 2
    assert result["recovered_count"] == 2
    assert result["action_counts"] == {
        "marked_timeout": 1,
        "reset_to_pending": 1,
    }
    assert result["completed_at"]
    assert result["recovered_by_task"][0]["scanned_count"] == 1
    assert result["recovered_by_task"][0]["recovered_count"] == 1
    batches = list(db_session.query(SubagentRecoveryBatch).order_by(SubagentRecoveryBatch.task_id))
    assert len(batches) == 2
    assert {batch.batch_id for batch in batches} == {result["batch_id"]}
    assert {batch.task_id for batch in batches} == {first_task.id, second_task.id}
    assert {batch.recovered_count for batch in batches} == {1}
    assert db_session.get(AgentRun, first_stale.id).status == "PENDING"
    assert db_session.get(AgentRun, second_expired.id).status == "TIMEOUT"
    summary = TestClient(app).get("/api/subagents/recovery/summary", headers=AUTH_HEADERS)
    assert summary.status_code == 200
    summary_payload = summary.json()
    assert summary_payload["organization_id"] == "dev-org"
    assert summary_payload["batch_total"] == 1
    assert summary_payload["task_total"] == 2
    assert summary_payload["scanned_total"] == 2
    assert summary_payload["recovered_total"] == 2
    assert summary_payload["lock_skipped_total"] == 0
    assert summary_payload["action_counts"] == {
        "marked_timeout": 1,
        "reset_to_pending": 1,
    }
    assert {item["task_id"] for item in summary_payload["tasks"]} == {
        first_task.id,
        second_task.id,
    }
    assert len(summary_payload["recent_batches"]) == 2
    metrics = TestClient(app).get("/metrics").text
    assert 'agent_subagent_recovery_total{action="reset_to_pending"}' in metrics
    assert 'agent_subagent_recovery_total{action="marked_timeout"}' in metrics
    assert "agent_subagent_recovery_sweeps_total" in metrics
    assert "agent_subagent_recovery_last_recovered" in metrics


def test_subagent_recovery_global_summary_and_export_require_admin(db_session: Session) -> None:
    first_task = create_task(db_session)
    second_task = create_task(db_session, organization_id="other-org")
    first_stale = SubagentManager(db_session).spawn(
        task=first_task,
        assignment={"step_key": "first_org_stale"},
        timeout_seconds=1800,
    )
    first_stale.status = "RUNNING"
    first_stale.started_at = utc_now() - timedelta(seconds=901)
    second_expired = SubagentManager(db_session).spawn(
        task=second_task,
        assignment={"step_key": "second_org_expired"},
        timeout_seconds=1,
    )
    second_expired.status = "RUNNING"
    second_expired.started_at = utc_now() - timedelta(seconds=60)
    second_expired.timeout_at = utc_now() - timedelta(seconds=1)
    db_session.commit()
    recover_stalled_subagents(stale_after_seconds=900, enqueue=False, session=db_session)
    client = TestClient(app)

    engineer = client.get("/api/subagents/recovery/global-summary", headers=AUTH_HEADERS)
    summary = client.get("/api/subagents/recovery/global-summary", headers=ADMIN_HEADERS)
    exported = client.get(
        "/api/subagents/recovery/global-summary/export",
        headers=ADMIN_HEADERS,
    )

    assert engineer.status_code == 403
    assert summary.status_code == 200
    payload = summary.json()
    assert payload["organization_count"] == 2
    assert payload["batch_total"] == 1
    assert payload["task_total"] == 2
    assert payload["scanned_total"] == 2
    assert payload["recovered_total"] == 2
    assert payload["action_counts"] == {
        "marked_timeout": 1,
        "reset_to_pending": 1,
    }
    assert {item["organization_id"] for item in payload["organizations"]} == {
        "dev-org",
        "other-org",
    }
    assert all(item["recovered_total"] == 1 for item in payload["organizations"])
    assert exported.status_code == 200
    assert exported.headers["content-type"].startswith("application/json")
    assert exported.headers["x-harness-export-count"] == "1"
    assert "subagent-recovery-global-summary.json" in exported.headers["content-disposition"]
    assert exported.json()["organization_count"] == 2


def test_subagent_recovery_sweep_skips_when_lease_is_held(db_session: Session) -> None:
    task = create_task(db_session)
    stale = SubagentManager(db_session).spawn(
        task=task,
        assignment={"step_key": "locked_recovery"},
        timeout_seconds=1800,
    )
    stale.status = "RUNNING"
    stale.started_at = utc_now() - timedelta(seconds=901)
    db_session.commit()

    assert _sqlite_recovery_lock.acquire(blocking=False) is True
    try:
        result = recover_stalled_subagents(
            stale_after_seconds=900,
            enqueue=False,
            session=db_session,
        )
    finally:
        _sqlite_recovery_lock.release()

    assert result["batch_id"].startswith("auto-")
    assert result["trigger"] == "auto"
    assert result["lock_acquired"] is False
    assert result["stale_after_seconds"] == 900
    assert result["enqueue"] is False
    assert result["task_count"] == 0
    assert result["scanned_count"] == 0
    assert result["recovered_count"] == 0
    assert result["action_counts"] == {}
    assert result["recovered_by_task"] == []
    assert result["completed_at"]
    assert db_session.get(AgentRun, stale.id).status == "RUNNING"
