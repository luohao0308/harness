import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.model_gateway import ModelGatewayError, ModelResponse
from app.db.models import (
    Agent,
    AgentAssignment,
    AgentEvent,
    ExecutionPlan,
    SandboxInstance,
    SystemSetting,
    Task,
    TaskStep,
    ToolApproval,
    ToolCall,
    utc_now,
)
from app.main import app
from app.sandbox.docker_manager import SandboxCommandResult
from app.workers.agent_assignment_worker import execute_agent_assignment
from tests.conftest import AUTH_HEADERS


def parse_sse_events(body: str) -> list[tuple[str, dict]]:
    events: list[tuple[str, dict]] = []
    for frame in body.strip().split("\n\n"):
        event_line = next((line for line in frame.splitlines() if line.startswith("event:")), None)
        data_line = next((line for line in frame.splitlines() if line.startswith("data:")), None)
        if event_line is None or data_line is None:
            continue
        events.append(
            (
                event_line.removeprefix("event:").strip(),
                json.loads(data_line.removeprefix("data:").strip()),
            )
        )
    return events


class FakeWarmPoolManager:
    def __init__(self, *args, **kwargs) -> None:
        pass

    def acquire(
        self,
        *,
        session: Session,
        task_id: str,
        agent_run_id: str | None = None,
    ) -> SandboxInstance:
        sandbox = SandboxInstance(
            task_id=task_id,
            agent_run_id=agent_run_id,
            container_id=f"fake-{task_id}",
            image="fake-sandbox",
            status="IDLE",
            cpu_limit="1",
            memory_limit_mb=512,
            network_enabled=False,
            warm_pool_reused=True,
        )
        session.add(sandbox)
        session.flush()
        return sandbox

    def release(self, *, session: Session, sandbox: SandboxInstance) -> SandboxInstance:
        sandbox.status = "IDLE"
        session.flush()
        return sandbox


def fake_run_command(
    self,
    *,
    session: Session,
    sandbox: SandboxInstance,
    command: str,
    timeout_seconds: int | None,
    cwd: str = "/workspace",
) -> SandboxCommandResult:
    return SandboxCommandResult(
        stdout=f"{command}\n",
        stderr="",
        exit_code=0,
        duration_ms=1,
    )


def test_agent_workspace_pro_chat_stream_creates_auditable_run(db_session: Session) -> None:
    client = TestClient(app)
    response = client.post(
        "/api/agents/default/runs/chat/stream",
        headers=AUTH_HEADERS,
        json={
            "goal": "Build a Workspace Pro regression plan",
            "messages": [
                {
                    "id": "user-1",
                    "parent_id": None,
                    "children_ids": [],
                    "role": "user",
                    "content": "Build a Workspace Pro regression plan",
                    "state": "done",
                    "metadata": {},
                    "tool_calls": [],
                    "artifacts": [],
                }
            ],
            "active_leaf_id": "user-1",
            "active_branch_id": "branch-1",
            "pinned_node_ids": ["user-1"],
            "context_window_turns": 8,
            "tool_mentions": [{"name": "read_file", "source": "builtin", "payload": {}}],
        },
    )

    assert response.status_code == 200
    body = response.text
    assert "event: think_delta" in body
    assert "event: tool_call_requested" in body
    assert "event: tool_call_result" in body
    assert "event: artifact_created" in body
    assert "event: usage" in body
    assert "event: done" in body
    events = parse_sse_events(body)
    requested = next(payload for event, payload in events if event == "tool_call_requested")
    result = next(payload for event, payload in events if event == "tool_call_result")
    usage = next(payload for event, payload in events if event == "usage")
    done = next(payload for event, payload in events if event == "done")
    assert requested["tool_call_id"] == result["tool_call_id"]
    assert requested["status"] == "running"
    assert result["status"] == "success"
    assert result["output_summary"]
    assert isinstance(result["duration_ms"], int)
    assert done["active_branch_id"] == "branch-1"
    assert done["continue_from_node_id"] is None
    assert usage["cost_usd"] is None
    assert usage["cost_unavailable"] is True
    assert db_session.execute(select(Task)).scalar_one_or_none() is not None


def test_agent_workspace_pro_chat_stream_continue_preserves_run_identity(
    db_session: Session,
) -> None:
    client = TestClient(app)
    created = client.post(
        "/api/agents/default/runs/chat/stream",
        headers=AUTH_HEADERS,
        json={
            "goal": "Create a run for continue",
            "messages": [
                {
                    "id": "user-continue",
                    "parent_id": None,
                    "children_ids": [],
                    "role": "user",
                    "content": "Create a run for continue",
                    "state": "done",
                    "metadata": {},
                    "tool_calls": [],
                    "artifacts": [],
                }
            ],
            "active_leaf_id": "user-continue",
            "active_branch_id": "branch-a",
            "pinned_node_ids": [],
            "context_window_turns": 8,
        },
    )
    assert created.status_code == 200
    run_id = next(
        payload for event, payload in parse_sse_events(created.text) if event == "done"
    )["run_id"]

    continued = client.post(
        "/api/agents/default/runs/chat/stream",
        headers=AUTH_HEADERS,
        json={
            "goal": "Continue the same run",
            "run_id": run_id,
            "active_branch_id": "branch-a",
            "continue_from_node_id": "assistant-paused",
            "partial_assistant_content": "partial",
            "messages": [
                {
                    "id": "assistant-paused",
                    "parent_id": "user-continue",
                    "children_ids": [],
                    "role": "assistant",
                    "content": "partial",
                    "state": "paused",
                    "run_id": run_id,
                    "metadata": {},
                    "tool_calls": [],
                    "artifacts": [],
                }
            ],
            "active_leaf_id": "assistant-paused",
            "pinned_node_ids": [],
            "context_window_turns": 8,
        },
    )

    assert continued.status_code == 200
    done = next(payload for event, payload in parse_sse_events(continued.text) if event == "done")
    assert done["run_id"] == run_id
    assert done["active_branch_id"] == "branch-a"
    assert done["continue_from_node_id"] == "assistant-paused"


def test_agent_workspace_pro_chat_stream_invalid_continue_is_recoverable(
    db_session: Session,
) -> None:
    response = TestClient(app).post(
        "/api/agents/default/runs/chat/stream",
        headers=AUTH_HEADERS,
        json={
            "goal": "Continue missing run",
            "run_id": "missing-run",
            "active_branch_id": "branch-missing",
            "continue_from_node_id": "assistant-paused",
            "messages": [],
            "active_leaf_id": "assistant-paused",
            "pinned_node_ids": [],
            "context_window_turns": 8,
        },
    )

    assert response.status_code == 200
    error = next(payload for event, payload in parse_sse_events(response.text) if event == "error")
    assert error["recoverable"] is True
    assert error["run_id"] == "missing-run"


def test_agent_workspace_pro_chat_stream_side_effect_tool_stays_pending(
    db_session: Session,
) -> None:
    response = TestClient(app).post(
        "/api/agents/default/runs/chat/stream",
        headers=AUTH_HEADERS,
        json={
            "goal": "Do not auto execute shell",
            "messages": [],
            "active_leaf_id": "root",
            "pinned_node_ids": [],
            "context_window_turns": 8,
            "tool_mentions": [
                {"name": "run_shell", "source": "builtin", "payload": {"command": "echo unsafe"}}
            ],
        },
    )

    assert response.status_code == 200
    events = parse_sse_events(response.text)
    requested = next(payload for event, payload in events if event == "tool_call_requested")
    assert requested["status"] == "pending_approval"
    assert not [payload for event, payload in events if event == "tool_call_result"]


@pytest.fixture(autouse=True)
def fake_sandbox_runtime(monkeypatch) -> None:
    monkeypatch.setattr("app.agents.executor.WarmPoolManager", FakeWarmPoolManager)
    monkeypatch.setattr("app.sandbox.docker_manager.DockerManager.run_command", fake_run_command)


def test_list_agents_initializes_named_agent_registry(db_session: Session) -> None:
    response = TestClient(app).get("/api/agents", headers=AUTH_HEADERS)

    assert response.status_code == 200
    payload = response.json()
    agent_ids = [agent["id"] for agent in payload["items"]]
    assert agent_ids == ["coder", "default", "operator", "researcher", "reviewer"]
    researcher = next(agent for agent in payload["items"] if agent["id"] == "researcher")
    assert researcher["role"] == "researcher"
    assert "network_request" in researcher["tools_json"]
    assert "research" in researcher["routing_tags"]


def test_get_agent_returns_named_agent_detail(db_session: Session) -> None:
    response = TestClient(app).get("/api/agents/coder", headers=AUTH_HEADERS)

    assert response.status_code == 200
    payload = response.json()
    assert payload["id"] == "coder"
    assert payload["name"] == "Coder Agent"
    assert payload["model_provider"] == "default"
    assert "run_tests" in payload["tools_json"]


def test_agent_chat_session_persists_messages(db_session: Session) -> None:
    client = TestClient(app)
    created = client.post(
        "/api/agents/default/sessions",
        headers=AUTH_HEADERS,
        json={"title": "Chat smoke"},
    )
    assert created.status_code == 201
    session_id = created.json()["id"]

    response = client.post(
        f"/api/agents/sessions/{session_id}/messages",
        headers=AUTH_HEADERS,
        json={"content": "你好，先聊一下平台能力"},
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["session"]["id"] == session_id
    assert [message["role"] for message in payload["messages"]] == ["user", "assistant"]
    assert "default 已收到" in payload["messages"][1]["content"]

    listed = client.get(f"/api/agents/sessions/{session_id}/messages", headers=AUTH_HEADERS)
    assert listed.status_code == 200
    assert [message["role"] for message in listed.json()["items"]] == ["user", "assistant"]


def test_agent_plan_mode_creates_plan_without_execution(db_session: Session) -> None:
    response = TestClient(app).post(
        "/api/agents/plan",
        headers=AUTH_HEADERS,
        json={
            "agent_id": "default",
            "goal": "分析项目结构并规划后续实现，不执行工具",
            "model_provider": "openai-compatible",
            "model_name": "default",
            "max_subagents": 5,
            "enable_sandbox": True,
            "enable_network": False,
        },
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["agent_id"] == "default"
    assert payload["task"]["status"] == "PLANNED"
    assert payload["plan"]["steps"]
    assert "未执行任何工具" in payload["message"]

    task = db_session.get(Task, payload["run_id"])
    assert task is not None
    assert task.status == "PLANNED"
    plan = db_session.execute(
        select(ExecutionPlan).where(ExecutionPlan.task_id == task.id)
    ).scalar_one()
    assert plan.status == "GENERATED"
    assert db_session.execute(select(TaskStep).where(TaskStep.task_id == task.id)).all() == []
    event_types = [
        event.event_type
        for event in db_session.execute(
            select(AgentEvent).where(AgentEvent.task_id == task.id).order_by(AgentEvent.sequence)
        ).scalars()
    ]
    assert event_types == [
        "TASK_CREATED",
        "PLAN_REQUESTED",
        "MODEL_CALLED",
        "MODEL_RESPONSE_RECEIVED",
        "PLAN_GENERATED",
    ]


def test_agent_plan_mode_surfaces_model_gateway_failure_without_fallback(
    db_session: Session,
    monkeypatch,
) -> None:
    class BrokenGateway:
        def complete(self, request_payload):
            raise ModelGatewayError("model unavailable")

    monkeypatch.setattr(
        "app.agents.model_gateway.model_gateway_for_provider",
        lambda provider, *, timeout_seconds=30: BrokenGateway(),
    )

    response = TestClient(app).post(
        "/api/agents/plan",
        headers=AUTH_HEADERS,
        json={
            "agent_id": "default",
            "goal": "计划失败时应该显式报错",
            "model_provider": "openai-compatible",
            "model_name": "default",
            "max_subagents": 5,
            "enable_sandbox": True,
            "enable_network": False,
        },
    )

    assert response.status_code == 502
    assert "Plan 模型调用失败" in response.json()["detail"]
    task = db_session.execute(
        select(Task).where(Task.goal == "计划失败时应该显式报错")
    ).scalar_one()
    assert task.status == "FAILED"
    assert (
        db_session.execute(select(ExecutionPlan).where(ExecutionPlan.task_id == task.id))
        .scalar_one_or_none()
        is None
    )
    event_types = [
        event.event_type
        for event in db_session.execute(
            select(AgentEvent).where(AgentEvent.task_id == task.id).order_by(AgentEvent.sequence)
        ).scalars()
    ]
    assert event_types == [
        "TASK_CREATED",
        "PLAN_REQUESTED",
        "MODEL_CALLED",
        "MODEL_CALL_FAILED",
        "TASK_FAILED",
    ]


def test_agent_run_create_surfaces_model_gateway_failure_without_fallback(
    db_session: Session,
    monkeypatch,
) -> None:
    class BrokenGateway:
        def complete(self, request_payload):
            raise ModelGatewayError("model unavailable")

    monkeypatch.setattr(
        "app.agents.model_gateway.model_gateway_for_provider",
        lambda provider, *, timeout_seconds=30: BrokenGateway(),
    )

    response = TestClient(app).post(
        "/api/agents/default/runs",
        headers=AUTH_HEADERS,
        json={
            "goal": "Primary run planning should fail when the model gateway is down",
            "model_provider": "openai-compatible",
            "model_name": "default",
            "max_subagents": 5,
            "enable_sandbox": True,
            "enable_network": False,
        },
    )

    assert response.status_code == 502
    assert "Plan 模型调用失败" in response.json()["detail"]
    task = db_session.execute(
        select(Task).where(
            Task.goal == "Primary run planning should fail when the model gateway is down"
        )
    ).scalar_one()
    assert task.status == "FAILED"
    assert (
        db_session.execute(select(ExecutionPlan).where(ExecutionPlan.task_id == task.id))
        .scalar_one_or_none()
        is None
    )
    event_types = [
        event.event_type
        for event in db_session.execute(
            select(AgentEvent).where(AgentEvent.task_id == task.id).order_by(AgentEvent.sequence)
        ).scalars()
    ]
    assert event_types == [
        "TASK_CREATED",
        "PLAN_REQUESTED",
        "MODEL_CALLED",
        "MODEL_CALL_FAILED",
        "TASK_FAILED",
    ]


def test_agent_run_create_uses_deterministic_plan_when_model_output_is_unparseable(
    db_session: Session,
    monkeypatch,
) -> None:
    class InvalidGateway:
        def complete(self, request_payload):
            return ModelResponse(
                content="not json at all",
                model_provider=request_payload.model_provider,
                model_name=request_payload.model_name,
                usage={"prompt_tokens": 9, "completion_tokens": 4},
                raw_response={"mode": "test-model"},
            )

    monkeypatch.setattr(
        "app.agents.model_gateway.model_gateway_for_provider",
        lambda provider, *, timeout_seconds=30: InvalidGateway(),
    )

    response = TestClient(app).post(
        "/api/agents/default/runs",
        headers=AUTH_HEADERS,
        json={
            "goal": "计划输出不可解析时应该生成可审计计划",
            "model_provider": "openai-compatible",
            "model_name": "default",
            "max_subagents": 5,
            "enable_sandbox": True,
            "enable_network": False,
        },
    )

    assert response.status_code == 201
    run_id = response.json()["run_id"]
    task = db_session.execute(
        select(Task).where(Task.goal == "计划输出不可解析时应该生成可审计计划")
    ).scalar_one()
    assert task.status == "PLANNED"
    plan = (
        db_session.execute(select(ExecutionPlan).where(ExecutionPlan.task_id == task.id))
        .scalars()
        .one()
    )
    assert task.id == run_id
    assert plan.plan_json["planner_source"] == "deterministic"
    assert plan.plan_json["steps"]
    event_types = [
        event.event_type
        for event in db_session.execute(
            select(AgentEvent).where(AgentEvent.task_id == task.id).order_by(AgentEvent.sequence)
        ).scalars()
    ]
    assert event_types == [
        "TASK_CREATED",
        "PLAN_REQUESTED",
        "MODEL_CALLED",
        "MODEL_RESPONSE_RECEIVED",
        "PLAN_REJECTED",
        "MODEL_CALLED",
        "MODEL_RESPONSE_RECEIVED",
        "PLAN_REJECTED",
        "PLAN_GENERATED",
    ]


def test_agent_run_create_records_repair_failure_before_deterministic_plan(
    db_session: Session,
    monkeypatch,
) -> None:
    class RepairFailureGateway:
        calls = 0

        def complete(self, request_payload):
            self.calls += 1
            if self.calls == 1:
                return ModelResponse(
                    content="not json at all",
                    model_provider=request_payload.model_provider,
                    model_name=request_payload.model_name,
                    usage={"prompt_tokens": 9, "completion_tokens": 4},
                    raw_response={"mode": "test-model"},
                )
            raise ModelGatewayError("repair unavailable")

    gateway = RepairFailureGateway()
    monkeypatch.setattr(
        "app.agents.model_gateway.model_gateway_for_provider",
        lambda provider, *, timeout_seconds=30: gateway,
    )

    response = TestClient(app).post(
        "/api/agents/default/runs",
        headers=AUTH_HEADERS,
        json={
            "goal": "Repair failure should still leave auditable planning events",
            "model_provider": "openai-compatible",
            "model_name": "default",
            "max_subagents": 5,
            "enable_sandbox": True,
            "enable_network": False,
        },
    )

    assert response.status_code == 201
    task = db_session.execute(
        select(Task).where(
            Task.goal == "Repair failure should still leave auditable planning events"
        )
    ).scalar_one()
    plan = (
        db_session.execute(select(ExecutionPlan).where(ExecutionPlan.task_id == task.id))
        .scalars()
        .one()
    )
    assert task.status == "PLANNED"
    assert plan.plan_json["planner_source"] == "deterministic"
    events = list(
        db_session.execute(
            select(AgentEvent).where(AgentEvent.task_id == task.id).order_by(AgentEvent.sequence)
        ).scalars()
    )
    assert [event.event_type for event in events] == [
        "TASK_CREATED",
        "PLAN_REQUESTED",
        "MODEL_CALLED",
        "MODEL_RESPONSE_RECEIVED",
        "PLAN_REJECTED",
        "MODEL_CALLED",
        "MODEL_CALL_FAILED",
        "PLAN_REJECTED",
        "PLAN_GENERATED",
    ]
    plan_rejection_reasons = [
        event.payload_json["reason"]
        for event in events
        if event.event_type == "PLAN_REJECTED"
    ]
    assert plan_rejection_reasons == [
        "model_plan_schema_invalid",
        "model_plan_repair_call_failed",
    ]


def test_agent_run_create_entry_and_workspace_projection(db_session: Session) -> None:
    client = TestClient(app)

    created = client.post(
        "/api/agents/default/runs",
        headers=AUTH_HEADERS,
        json={
            "mode": "plan",
            "goal": "通过 Agent Workspace 创建 Run 并查看聚合视图",
            "model_provider": "openai-compatible",
            "model_name": "default",
            "max_subagents": 5,
            "enable_sandbox": True,
            "enable_network": False,
        },
    )

    assert created.status_code == 201
    run_id = created.json()["run_id"]

    listed = client.get("/api/agents/runs", headers=AUTH_HEADERS)
    assert listed.status_code == 200
    assert any(item["id"] == run_id for item in listed.json()["items"])

    workspace = client.get(f"/api/agents/runs/{run_id}/workspace", headers=AUTH_HEADERS)

    assert workspace.status_code == 200
    payload = workspace.json()
    assert payload["run"]["id"] == run_id
    assert payload["plan"]["steps"]
    assert [event["event_type"] for event in payload["events"]] == [
        "TASK_CREATED",
        "PLAN_REQUESTED",
        "MODEL_CALLED",
        "MODEL_RESPONSE_RECEIVED",
        "PLAN_GENERATED",
    ]
    assert payload["tool_calls"] == []
    assert payload["model_calls"][0]["model_provider"] == "openai-compatible"


def test_agent_execute_run_uses_existing_plan_without_replanning(db_session: Session) -> None:
    client = TestClient(app)
    plan_response = client.post(
        "/api/agents/plan",
        headers=AUTH_HEADERS,
        json={
            "agent_id": "default",
            "goal": "分析项目结构并执行现有计划",
            "model_provider": "openai-compatible",
            "model_name": "default",
            "max_subagents": 5,
            "enable_sandbox": True,
            "enable_network": False,
        },
    )
    assert plan_response.status_code == 201
    run_id = plan_response.json()["run_id"]

    execute_response = client.post(f"/api/agents/runs/{run_id}/execute", headers=AUTH_HEADERS)

    assert execute_response.status_code == 202
    assert execute_response.json()["status"] == "COMPLETED"
    plans = list(
        db_session.execute(select(ExecutionPlan).where(ExecutionPlan.task_id == run_id)).scalars()
    )
    assert len(plans) == 1
    assert db_session.execute(select(TaskStep).where(TaskStep.task_id == run_id)).scalars().all()
    event_types = [
        event.event_type
        for event in db_session.execute(
            select(AgentEvent).where(AgentEvent.task_id == run_id).order_by(AgentEvent.sequence)
        ).scalars()
    ]
    assert event_types.count("PLAN_GENERATED") == 1
    assert "TASK_STARTED" in event_types
    assert "STEP_STARTED" in event_types
    assert "STEP_COMPLETED" in event_types
    assert event_types[-1] == "TASK_COMPLETED"


def test_agent_execute_run_rejects_non_planned_status(db_session: Session) -> None:
    task = Task(
        organization_id="dev-org",
        created_by="dev-engineer",
        title="Created run",
        goal="尚未规划",
        status="CREATED",
        model_provider="openai-compatible",
        model_name="default",
        max_runtime_seconds=1800,
        max_subagents=5,
        enable_sandbox=True,
        enable_network=False,
    )
    db_session.add(task)
    db_session.commit()

    response = TestClient(app).post(f"/api/agents/runs/{task.id}/execute", headers=AUTH_HEADERS)

    assert response.status_code == 409


def test_agent_execute_run_waits_for_admin_approval(db_session: Session) -> None:
    db_session.add(
        SystemSetting(
            organization_id="dev-org",
            key="settings.policies",
            value_json={
                "risk_levels": [
                    {
                        "name": "low",
                        "requires_sandbox": False,
                        "approval": "admin",
                        "allowed_roles": ["admin", "engineer"],
                    }
                ],
                "approvals": {"manual_review": True, "deny_on_missing_policy": True},
                "sandbox": {"default_network": False, "default_timeout_seconds": 60},
                "audit": {"model_calls": True, "tool_calls": True, "policy_actions": True},
            },
            updated_by="dev-admin",
            updated_at=utc_now(),
        )
    )
    db_session.commit()
    client = TestClient(app)
    plan_response = client.post(
        "/api/agents/plan",
        headers=AUTH_HEADERS,
        json={
            "agent_id": "default",
            "goal": "规划后执行只读检查，并在策略要求时等待审批",
            "model_provider": "openai-compatible",
            "model_name": "default",
            "max_subagents": 0,
            "enable_sandbox": False,
            "enable_network": False,
        },
    )
    assert plan_response.status_code == 201
    run_id = plan_response.json()["run_id"]

    execute_response = client.post(f"/api/agents/runs/{run_id}/execute", headers=AUTH_HEADERS)

    assert execute_response.status_code == 202
    assert execute_response.json()["status"] == "WAITING_APPROVAL"
    run = db_session.get(Task, run_id)
    assert run is not None
    assert run.status == "WAITING_APPROVAL"
    tool_call = db_session.execute(select(ToolCall).where(ToolCall.task_id == run_id)).scalar_one()
    assert tool_call.status == "PENDING_APPROVAL"
    approval = db_session.execute(
        select(ToolApproval).where(ToolApproval.task_id == run_id)
    ).scalar_one()
    assert approval.status == "PENDING"
    failed_event = db_session.execute(
        select(AgentEvent)
        .where(AgentEvent.task_id == run_id, AgentEvent.event_type == "TASK_FAILED")
        .order_by(AgentEvent.sequence.desc())
    ).scalars().first()
    assert failed_event is not None
    assert failed_event.payload_json["awaiting_approval"] is True


def test_agent_orchestrate_run_creates_named_assignments_and_events(
    db_session: Session,
) -> None:
    client = TestClient(app)
    plan_response = client.post(
        "/api/agents/plan",
        headers=AUTH_HEADERS,
        json={
            "agent_id": "default",
            "goal": "分析项目结构，安排研究与审查 Agent 协作",
            "model_provider": "openai-compatible",
            "model_name": "default",
            "max_subagents": 5,
            "enable_sandbox": True,
            "enable_network": False,
        },
    )
    assert plan_response.status_code == 201
    run_id = plan_response.json()["run_id"]

    response = client.post(f"/api/agents/runs/{run_id}/orchestrate", headers=AUTH_HEADERS)

    assert response.status_code == 201
    payload = response.json()
    assert payload["strategy"] == "deterministic_fallback"
    assert payload["routing_reasoning"]
    assignment_agent_ids = [item["agent_id"] for item in payload["assignments"]]
    assert "default" in assignment_agent_ids
    assert "researcher" in assignment_agent_ids
    assert "reviewer" in assignment_agent_ids
    assert payload["handoffs"]

    assignments = list(
        db_session.execute(
            select(AgentAssignment).where(AgentAssignment.run_id == run_id)
        ).scalars()
    )
    assert len(assignments) == len(payload["assignments"])
    event_types = [
        event.event_type
        for event in db_session.execute(
            select(AgentEvent).where(AgentEvent.task_id == run_id).order_by(AgentEvent.sequence)
        ).scalars()
    ]
    assert "AGENT_SELECTED" in event_types
    assert "AGENT_PARALLEL_FANOUT_STARTED" in event_types
    assert "AGENT_ASSIGNMENT_CREATED" in event_types
    assert "AGENT_HANDOFF_COMPLETED" in event_types
    assert "AGENT_REDUCE_STARTED" in event_types
    selected_event = db_session.execute(
        select(AgentEvent)
        .where(AgentEvent.task_id == run_id, AgentEvent.event_type == "AGENT_SELECTED")
        .order_by(AgentEvent.sequence.desc())
    ).scalars().first()
    assert selected_event is not None
    assert selected_event.payload_json["router_prompt_version"] == "agent-router-v1"

    listed = client.get(f"/api/agents/runs/{run_id}/assignments", headers=AUTH_HEADERS)
    assert listed.status_code == 200
    assert len(listed.json()) == len(payload["assignments"])


def test_agent_orchestrate_uses_llm_router_when_model_returns_valid_decision(
    db_session: Session,
    monkeypatch,
) -> None:
    client = TestClient(app)
    plan_response = client.post(
        "/api/agents/plan",
        headers=AUTH_HEADERS,
        json={
            "agent_id": "default",
            "goal": "需要编码和审查协作",
            "model_provider": "openai-compatible",
            "model_name": "default",
            "max_subagents": 5,
            "enable_sandbox": True,
            "enable_network": False,
        },
    )
    run_id = plan_response.json()["run_id"]

    def fake_complete(self, request_payload, *, fallback_requests=None):
        if "Agent Router" in request_payload.messages[0].content:
            return ModelResponse(
                content=(
                    '{"selected_agent_ids":["default","coder"],'
                    '"strategy":"llm_router","reasoning":"coding work requires coder"}'
                ),
                model_provider=request_payload.model_provider,
                model_name=request_payload.model_name,
            )
        return ModelResponse(
            content="{}",
            model_provider=request_payload.model_provider,
            model_name=request_payload.model_name,
        )

    monkeypatch.setattr("app.agents.orchestrator.AuditedModelGateway.complete", fake_complete)

    response = client.post(f"/api/agents/runs/{run_id}/orchestrate", headers=AUTH_HEADERS)

    assert response.status_code == 201
    payload = response.json()
    assert payload["strategy"] == "llm_router"
    assert payload["routing_reasoning"] == "coding work requires coder"
    assignment_agent_ids = [item["agent_id"] for item in payload["assignments"]]
    assert assignment_agent_ids == ["default", "coder", "reviewer"]


def test_agent_orchestration_execute_runs_assignments_and_reduces(
    db_session: Session,
) -> None:
    client = TestClient(app)
    plan_response = client.post(
        "/api/agents/plan",
        headers=AUTH_HEADERS,
        json={
            "agent_id": "default",
            "goal": "分析项目结构，安排研究与审查 Agent 协作",
            "model_provider": "openai-compatible",
            "model_name": "default",
            "max_subagents": 5,
            "enable_sandbox": True,
            "enable_network": False,
        },
    )
    run_id = plan_response.json()["run_id"]
    client.post(f"/api/agents/runs/{run_id}/orchestrate", headers=AUTH_HEADERS)

    response = client.post(
        f"/api/agents/runs/{run_id}/orchestrate/execute",
        headers=AUTH_HEADERS,
    )

    assert response.status_code == 202
    payload = response.json()
    assert all(item["status"] == "SUCCESS" for item in payload["assignments"])
    reviewer = next(item for item in payload["assignments"] if item["agent_id"] == "reviewer")
    assert "reduced_summary" in reviewer["output_json"]
    assert "tool_call_id" in reviewer["output_json"]

    event_types = [
        event.event_type
        for event in db_session.execute(
            select(AgentEvent).where(AgentEvent.task_id == run_id).order_by(AgentEvent.sequence)
        ).scalars()
    ]
    assert "AGENT_ASSIGNMENT_STARTED" in event_types
    assert "AGENT_ASSIGNMENT_COMPLETED" in event_types
    assert "AGENT_PARALLEL_BRANCH_COMPLETED" in event_types
    assert "AGENT_REDUCE_COMPLETED" in event_types
    assert "TOOL_CALLED" in event_types
    assert "TOOL_RESULT_RECEIVED" in event_types


def test_agent_orchestration_enqueue_marks_assignments_for_worker(
    db_session: Session,
    monkeypatch,
) -> None:
    sent_assignment_ids: list[str] = []

    class FakeActor:
        @staticmethod
        def send(assignment_id: str) -> None:
            sent_assignment_ids.append(assignment_id)

    monkeypatch.setattr("app.workers.agent_assignment_worker.run_agent_assignment", FakeActor)
    client = TestClient(app)
    plan_response = client.post(
        "/api/agents/plan",
        headers=AUTH_HEADERS,
        json={
            "agent_id": "default",
            "goal": "分析项目结构，安排研究与审查 Agent 协作",
            "model_provider": "openai-compatible",
            "model_name": "default",
            "max_subagents": 5,
            "enable_sandbox": True,
            "enable_network": False,
        },
    )
    run_id = plan_response.json()["run_id"]
    client.post(f"/api/agents/runs/{run_id}/orchestrate", headers=AUTH_HEADERS)

    response = client.post(
        f"/api/agents/runs/{run_id}/orchestrate/enqueue",
        headers=AUTH_HEADERS,
    )

    assert response.status_code == 202
    payload = response.json()
    assert all(item["status"] == "QUEUED" for item in payload["assignments"])
    assert sorted(sent_assignment_ids) == sorted(
        item["id"] for item in payload["assignments"]
    )
    event_types = [
        event.event_type
        for event in db_session.execute(
            select(AgentEvent).where(AgentEvent.task_id == run_id).order_by(AgentEvent.sequence)
        ).scalars()
    ]
    assert "AGENT_ASSIGNMENT_QUEUED" in event_types


def test_agent_assignment_worker_executes_one_assignment_and_reduces_when_ready(
    db_session: Session,
) -> None:
    client = TestClient(app)
    plan_response = client.post(
        "/api/agents/plan",
        headers=AUTH_HEADERS,
        json={
            "agent_id": "default",
            "goal": "分析项目结构，安排研究与审查 Agent 协作",
            "model_provider": "openai-compatible",
            "model_name": "default",
            "max_subagents": 5,
            "enable_sandbox": True,
            "enable_network": False,
        },
    )
    run_id = plan_response.json()["run_id"]
    client.post(f"/api/agents/runs/{run_id}/orchestrate", headers=AUTH_HEADERS)
    assignments = list(
        db_session.execute(
            select(AgentAssignment)
            .where(AgentAssignment.run_id == run_id)
            .order_by(AgentAssignment.created_at.asc(), AgentAssignment.id.asc())
        ).scalars()
    )

    for assignment in assignments:
        status = execute_agent_assignment(assignment.id, session=db_session)
        assert status == "SUCCESS"

    reviewer = next(assignment for assignment in assignments if assignment.agent_id == "reviewer")
    assert "reduced_summary" in reviewer.output_json


def test_agent_assignment_respects_agent_tool_allowlist(db_session: Session) -> None:
    client = TestClient(app)
    plan_response = client.post(
        "/api/agents/plan",
        headers=AUTH_HEADERS,
        json={
            "agent_id": "default",
            "goal": "验证 Agent 工具权限边界",
            "model_provider": "openai-compatible",
            "model_name": "default",
            "max_subagents": 5,
            "enable_sandbox": True,
            "enable_network": False,
        },
    )
    run_id = plan_response.json()["run_id"]
    db_session.add(
        Agent(
            id="restricted",
            organization_id=None,
            name="Restricted Agent",
            description="Cannot list files",
            role="researcher",
            status="ACTIVE",
            model_provider="default",
            model_name="default",
            system_prompt="Restricted",
            tools_json=["read_file"],
            routing_tags=[],
        )
    )
    db_session.flush()
    assignment = AgentAssignment(
        run_id=run_id,
        agent_id="restricted",
        role="researcher",
        status="PENDING",
        input_json={},
        output_json={},
    )
    db_session.add(assignment)
    db_session.commit()

    status = execute_agent_assignment(assignment.id, session=db_session)

    assert status == "FAILED"
    assert assignment.output_json["permission_boundary"] == "agent.tools_json"
    assert assignment.output_json["tool_name"] == "list_files"


def test_agent_auto_mode_plans_orchestrates_and_executes_run(db_session: Session) -> None:
    response = TestClient(app).post(
        "/api/agents/auto",
        headers=AUTH_HEADERS,
        json={
            "agent_id": "default",
            "goal": "自动分析项目结构并完成执行",
            "model_provider": "openai-compatible",
            "model_name": "default",
            "max_subagents": 5,
            "enable_sandbox": True,
            "enable_network": False,
        },
    )

    assert response.status_code == 202
    payload = response.json()
    assert payload["task"]["status"] == "COMPLETED"
    assert payload["plan"]["steps"]
    assert all(
        assignment["status"] == "SUCCESS"
        for assignment in payload["orchestration"]["assignments"]
    )
    run_id = payload["run_id"]
    event_types = [
        event.event_type
        for event in db_session.execute(
            select(AgentEvent).where(AgentEvent.task_id == run_id).order_by(AgentEvent.sequence)
        ).scalars()
    ]
    assert "PLAN_GENERATED" in event_types
    assert "AGENT_REDUCE_COMPLETED" in event_types
    assert event_types[-1] == "TASK_COMPLETED"
