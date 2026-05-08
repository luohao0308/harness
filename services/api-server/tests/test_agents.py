from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.model_gateway import ModelResponse
from app.db.models import Agent, AgentAssignment, AgentEvent, ExecutionPlan, Task, TaskStep
from app.main import app
from app.workers.agent_assignment_worker import execute_agent_assignment
from tests.conftest import AUTH_HEADERS


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
