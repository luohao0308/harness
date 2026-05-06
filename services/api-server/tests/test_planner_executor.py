from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.model_gateway import ModelRequest, ModelResponse
from app.agents.planner import PLANNER_PROMPT_VERSION, DeterministicPlanner
from app.db.models import AgentRun, ExecutionPlan, Task, TaskStep
from app.main import app
from tests.conftest import AUTH_HEADERS


def test_planner_uses_model_generated_sync_and_async_steps(db_session: Session) -> None:
    created = TestClient(app).post(
        "/api/tasks",
        headers=AUTH_HEADERS,
        json={
            "title": "LLM Plan",
            "goal": "拆分同步和异步任务",
            "model_provider": "openai-compatible",
            "model_name": "default",
        },
    ).json()
    task = db_session.get(Task, created["id"])
    assert task is not None

    plan = DeterministicPlanner().create_plan(
        task,
        model_content="""
        {
          "summary": "模型生成计划",
          "steps": [
            {
              "key": "inspect",
              "description": "同步检查",
              "execution_mode": "sync",
              "requires_sandbox": false,
              "can_spawn_subagent": false,
              "tool_hints": ["list_files", "unknown_tool"],
              "acceptance_criteria": ["完成结构检查"],
              "risk_level": "low",
              "artifact_expectations": ["结构摘要"]
            },
            {
              "key": "parallel_review",
              "description": "异步并发审查",
              "execution_mode": "async",
              "requires_sandbox": false,
              "can_spawn_subagent": true,
              "tool_hints": ["read_file"],
              "acceptance_criteria": ["返回并发审查结论"],
              "risk_level": "medium",
              "artifact_expectations": ["审查摘要"]
            }
          ]
        }
        """,
    )

    assert [step.execution_mode for step in plan.steps] == ["sync", "async"]
    assert plan.steps[1].can_spawn_subagent is True
    assert plan.planner_source == "llm"
    assert plan.planner_attempts == 1
    assert plan.steps[0].tool_hints == ["list_files"]
    assert plan.steps[0].acceptance_criteria == ["完成结构检查"]
    assert plan.steps[0].artifact_expectations == ["结构摘要"]
    assert plan.steps[1].risk_level == "medium"


def test_start_task_repairs_invalid_model_plan(
    db_session: Session,
    monkeypatch,
) -> None:
    class FakeGateway:
        calls = 0

        def __init__(self, **kwargs) -> None:
            pass

        def complete(self, request_payload: ModelRequest) -> ModelResponse:
            FakeGateway.calls += 1
            if FakeGateway.calls == 1:
                content = "not json"
            else:
                content = """
                {
                  "summary": "修复后的计划",
                  "steps": [
                    {
                      "key": "inspect_after_repair",
                      "description": "修复后同步检查",
                      "execution_mode": "sync",
                      "requires_sandbox": false,
                      "can_spawn_subagent": false
                    }
                  ]
                }
                """
            return ModelResponse(
                content=content,
                model_provider=request_payload.model_provider,
                model_name=request_payload.model_name,
                usage={},
                raw_response={"mode": "fake"},
            )

    monkeypatch.setattr("app.agents.executor.AuditedModelGateway", FakeGateway)
    client = TestClient(app)
    created = client.post(
        "/api/tasks",
        headers=AUTH_HEADERS,
        json={
            "title": "Repair",
            "goal": "修复模型计划",
            "model_provider": "openai-compatible",
            "model_name": "default",
        },
    ).json()

    response = client.post(f"/api/tasks/{created['id']}/start", headers=AUTH_HEADERS)

    assert response.status_code == 202
    plan = db_session.execute(
        select(ExecutionPlan).where(ExecutionPlan.task_id == created["id"])
    ).scalar_one()
    assert plan.plan_json["planner_source"] == "llm_repaired"
    assert plan.plan_json["planner_attempts"] == 2
    assert plan.plan_json["steps"][0]["key"] == "inspect_after_repair"
    events = client.get(f"/api/tasks/{created['id']}/events", headers=AUTH_HEADERS).json()["items"]
    assert "PLAN_REJECTED" in [event["event_type"] for event in events]


def test_start_task_uses_planner_prompt_version_and_returns_step_metadata(
    db_session: Session,
    monkeypatch,
) -> None:
    captured: dict[str, ModelRequest] = {}

    class FakeGateway:
        def __init__(self, **kwargs) -> None:
            pass

        def complete(self, request_payload: ModelRequest) -> ModelResponse:
            captured["request"] = request_payload
            return ModelResponse(
                content="""
                {
                  "summary": "增强 Planner 计划",
                  "steps": [
                    {
                      "key": "inspect_runtime",
                      "description": "检查运行时",
                      "execution_mode": "sync",
                      "requires_sandbox": false,
                      "can_spawn_subagent": false,
                      "tool_hints": ["list_files"],
                      "acceptance_criteria": ["识别运行时入口"],
                      "risk_level": "low",
                      "artifact_expectations": ["运行时摘要"]
                    }
                  ]
                }
                """,
                model_provider=request_payload.model_provider,
                model_name=request_payload.model_name,
                usage={},
                raw_response={"mode": "fake"},
            )

    monkeypatch.setattr("app.agents.executor.AuditedModelGateway", FakeGateway)
    client = TestClient(app)
    created = client.post(
        "/api/tasks",
        headers=AUTH_HEADERS,
        json={
            "title": "Prompt version",
            "goal": "验证 Planner Prompt 版本",
            "model_provider": "openai-compatible",
            "model_name": "default",
        },
    ).json()

    response = client.post(f"/api/tasks/{created['id']}/start", headers=AUTH_HEADERS)
    plan_response = client.get(f"/api/tasks/{created['id']}/plan", headers=AUTH_HEADERS)

    assert response.status_code == 202
    assert f"Prompt version: {PLANNER_PROMPT_VERSION}" in captured["request"].messages[0].content
    step = plan_response.json()["steps"][0]
    assert step["tool_hints"] == ["list_files"]
    assert step["acceptance_criteria"] == ["识别运行时入口"]
    assert step["risk_level"] == "low"
    assert step["artifact_expectations"] == ["运行时摘要"]
    events = client.get(f"/api/tasks/{created['id']}/events", headers=AUTH_HEADERS).json()["items"]
    plan_events = [event for event in events if event["event_type"] == "PLAN_GENERATED"]
    assert plan_events[0]["payload_json"]["prompt_version"] == PLANNER_PROMPT_VERSION


def test_start_task_generates_plan_steps_and_completion_events(db_session: Session) -> None:
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

    response = client.post(f"/api/tasks/{created['id']}/start", headers=AUTH_HEADERS)

    assert response.status_code == 202
    started = response.json()
    assert started["status"] == "COMPLETED"

    plan = db_session.execute(
        select(ExecutionPlan).where(ExecutionPlan.task_id == created["id"])
    ).scalar_one()
    assert plan.plan_json["steps"][0]["key"] == "inspect_project"

    steps = list(
        db_session.execute(
            select(TaskStep).where(TaskStep.task_id == created["id"]).order_by(TaskStep.step_key)
        ).scalars()
    )
    assert [step.status for step in steps] == ["STEP_COMPLETED", "STEP_COMPLETED"]

    events = client.get(f"/api/tasks/{created['id']}/events", headers=AUTH_HEADERS).json()["items"]
    event_types = [event["event_type"] for event in events]
    assert event_types == [
        "TASK_CREATED",
        "PLAN_REQUESTED",
        "MODEL_CALLED",
        "MODEL_RESPONSE_RECEIVED",
        "PLAN_GENERATED",
        "STEP_STARTED",
        "POLICY_CHECKED",
        "TOOL_CALLED",
        "TOOL_RESULT_RECEIVED",
        "STEP_COMPLETED",
        "STEP_STARTED",
        "POLICY_CHECKED",
        "TOOL_CALLED",
        "TOOL_RESULT_RECEIVED",
        "STEP_COMPLETED",
        "TASK_COMPLETED",
    ]


def test_start_task_rejects_missing_task() -> None:
    client = TestClient(app)

    response = client.post("/api/tasks/missing/start", headers=AUTH_HEADERS)

    assert response.status_code == 404


def test_start_task_spawns_subagent_for_async_plan(db_session: Session) -> None:
    client = TestClient(app)
    created = client.post(
        "/api/tasks",
        headers=AUTH_HEADERS,
        json={
            "title": "Subagent Demo",
            "goal": "使用子 Agent 并发分析长时间任务",
            "model_provider": "openai-compatible",
            "model_name": "default",
        },
    ).json()

    response = client.post(f"/api/tasks/{created['id']}/start", headers=AUTH_HEADERS)

    assert response.status_code == 202
    subagent = db_session.execute(
        select(AgentRun).where(AgentRun.task_id == created["id"])
    ).scalar_one()
    assert subagent.status == "PENDING"

    plan = db_session.execute(
        select(ExecutionPlan).where(ExecutionPlan.task_id == created["id"])
    ).scalar_one()
    async_steps = [step for step in plan.plan_json["steps"] if step["execution_mode"] == "async"]
    assert async_steps[0]["can_spawn_subagent"] is True
