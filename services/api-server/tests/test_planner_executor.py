from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.executor import Executor
from app.agents.model_gateway import ModelRequest, ModelResponse
from app.agents.planner import PLANNER_PROMPT_VERSION, DeterministicPlanner
from app.agents.schemas import PlanStep
from app.db.models import AgentEvent, AgentRun, ExecutionPlan, SubagentOutput, Task, TaskStep
from app.main import app
from tests.conftest import AUTH_HEADERS


def test_planner_uses_model_generated_sync_and_async_steps(db_session: Session) -> None:
    created = (
        TestClient(app)
        .post(
            "/api/tasks",
            headers=AUTH_HEADERS,
            json={
                "title": "LLM Plan",
                "goal": "拆分同步和异步任务",
                "model_provider": "openai-compatible",
                "model_name": "default",
            },
        )
        .json()
    )
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
    assert plan.planner_prompt_version == PLANNER_PROMPT_VERSION
    assert plan.quality_gates["unique_step_keys"] is True
    assert plan.quality_score > 0


def test_planner_repairs_review_plan_with_required_expert_subagent(
    db_session: Session,
) -> None:
    task = Task(
        organization_id="dev-org",
        created_by="dev-engineer",
        title="审查本次会话逻辑",
        goal="审查本次会话逻辑，输出专家证据",
        status="CREATED",
        model_provider="openai-compatible",
        model_name="default",
        max_subagents=5,
        enable_sandbox=False,
        enable_network=False,
    )
    db_session.add(task)
    db_session.flush()

    plan = DeterministicPlanner().create_plan(
        task,
        model_content="""
        {
          "summary": "模型生成了全同步审查计划",
          "steps": [
            {
              "key": "fetch_session_transcript",
              "description": "Fetch the current session transcript",
              "execution_mode": "sync",
              "requires_sandbox": true,
              "can_spawn_subagent": false,
              "tool_hints": ["run_shell"],
              "acceptance_criteria": ["拿到会话文本"],
              "risk_level": "medium",
              "artifact_expectations": ["session.md"]
            },
            {
              "key": "summarize_logic",
              "description": "Summarize the session logic",
              "execution_mode": "sync",
              "requires_sandbox": false,
              "can_spawn_subagent": false,
              "tool_hints": ["read_file"],
              "acceptance_criteria": ["总结逻辑问题"],
              "risk_level": "low",
              "artifact_expectations": ["logic.md"]
            }
          ]
        }
        """,
    )

    expert_steps = [step for step in plan.steps if step.key == "expert_review"]
    assert len(expert_steps) == 1
    expert = expert_steps[0]
    assert expert.execution_mode == "async"
    assert expert.can_spawn_subagent is True
    assert expert.requires_sandbox is False
    assert expert.recommended_specialist_slug == "code-reviewer"
    assert expert.fanout_specialist_slugs == ["code-reviewer", "safety-checker"]
    assert any("自动补充专家审查步骤" in warning for warning in plan.validation_warnings)


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


def test_plan_api_returns_quality_report_and_step_execution_trace(
    db_session: Session,
    monkeypatch,
) -> None:
    class FakeGateway:
        def __init__(self, **kwargs) -> None:
            pass

        def complete(self, request_payload: ModelRequest) -> ModelResponse:
            return ModelResponse(
                content="""
                {
                  "summary": "执行轨迹计划",
                  "steps": [
                    {
                      "key": "inspect_trace",
                      "description": "检查轨迹",
                      "execution_mode": "sync",
                      "requires_sandbox": false,
                      "can_spawn_subagent": false,
                      "tool_hints": ["list_files"],
                      "acceptance_criteria": ["写入步骤轨迹"],
                      "risk_level": "low",
                      "artifact_expectations": ["轨迹摘要"]
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
            "title": "Trace plan",
            "goal": "验证步骤执行轨迹",
            "model_provider": "openai-compatible",
            "model_name": "default",
        },
    ).json()

    started = client.post(f"/api/tasks/{created['id']}/start", headers=AUTH_HEADERS)
    plan_response = client.get(f"/api/tasks/{created['id']}/plan", headers=AUTH_HEADERS)

    assert started.status_code == 202
    payload = plan_response.json()
    assert payload["planner_prompt_version"] == PLANNER_PROMPT_VERSION
    assert payload["quality_score"] > 0
    assert "has_acceptance_criteria" in payload["quality_gates"]
    step = payload["steps"][0]
    assert step["trace_summary"].startswith("同步步骤 inspect_trace")
    assert step["last_event_sequence"] > 0
    assert [item["event_type"] for item in step["execution_trace"]] == [
        "STEP_STARTED",
        "STEP_COMPLETED",
    ]
    assert step["execution_trace"][1]["payload_json"]["tool_name"] == "mcp_artifact_put"


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
        "MODEL_CALLED",
        "POLICY_CHECKED",
        "TOOL_CALLED",
        "TOOL_RESULT_RECEIVED",
        "STEP_COMPLETED",
        "STEP_STARTED",
        "MODEL_CALLED",
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


def test_start_task_spawns_subagent_for_async_plan(db_session: Session, monkeypatch) -> None:
    monkeypatch.setattr("app.workers.subagent_worker.run_subagent.send", lambda _id: None)
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


def test_start_task_inline_executes_expert_subagent_when_queue_is_deferred(
    db_session: Session,
    monkeypatch,
) -> None:
    class FakeGateway:
        def __init__(self, **kwargs) -> None:
            pass

        def complete(self, request_payload: ModelRequest) -> ModelResponse:
            return ModelResponse(
                content="""
                {
                  "summary": "模型遗漏专家分支",
                  "steps": [
                    {
                      "key": "draft_findings",
                      "description": "Draft review findings",
                      "execution_mode": "sync",
                      "requires_sandbox": false,
                      "can_spawn_subagent": false,
                      "tool_hints": ["write_file"],
                      "acceptance_criteria": ["写入初步审查摘要"],
                      "risk_level": "low",
                      "artifact_expectations": ["findings.md"]
                    }
                  ]
                }
                """,
                model_provider=request_payload.model_provider,
                model_name=request_payload.model_name,
                usage={},
                raw_response={"mode": "fake"},
            )

    def fail_queue(_agent_run_id: str) -> None:
        raise RuntimeError("redis unavailable")

    monkeypatch.setattr("app.agents.executor.AuditedModelGateway", FakeGateway)
    monkeypatch.setattr("app.workers.subagent_worker.run_subagent.send", fail_queue)
    client = TestClient(app)
    created = client.post(
        "/api/tasks",
        headers=AUTH_HEADERS,
        json={
            "title": "审查本次会话逻辑",
            "goal": "审查本次会话逻辑，输出专家证据",
            "model_provider": "openai-compatible",
            "model_name": "default",
            "enable_sandbox": False,
        },
    ).json()

    response = client.post(f"/api/tasks/{created['id']}/start", headers=AUTH_HEADERS)

    assert response.status_code == 202
    task = db_session.get(Task, created["id"])
    assert task is not None
    assert task.status == "COMPLETED"
    subagents = list(
        db_session.execute(
            select(AgentRun).where(AgentRun.task_id == task.id).order_by(AgentRun.id)
        ).scalars()
    )
    assert len(subagents) == 2
    assert {subagent.status for subagent in subagents} == {"SUCCESS"}
    outputs = list(
        db_session.execute(
            select(SubagentOutput).where(SubagentOutput.task_id == task.id)
        ).scalars()
    )
    assert len(outputs) == 2
    event_stages = [
        event.payload_json.get("stage")
        for event in db_session.execute(
            select(AgentEvent).where(AgentEvent.task_id == task.id).order_by(AgentEvent.sequence)
        ).scalars()
        if isinstance(event.payload_json, dict)
    ]
    assert "queue_deferred" in event_stages
    assert "inline_executor_fallback" in event_stages
    workspace = client.get(f"/api/agents/runs/{task.id}/workspace", headers=AUTH_HEADERS)
    assert workspace.status_code == 200
    workspace_subagents = workspace.json()["subagents"]
    assert {item["specialist"]["slug"] for item in workspace_subagents} == {
        "code-reviewer",
        "safety-checker",
    }
    assert all(item["output"]["output_json"] for item in workspace_subagents)


def test_workspace_plan_stream_does_not_force_sandbox(db_session: Session) -> None:
    goal = "只生成计划，不启用 Docker 沙箱"

    response = TestClient(app).post(
        "/api/agents/default/runs/chat/stream",
        headers=AUTH_HEADERS,
        json={
            "mode": "plan",
            "goal": goal,
            "messages": [
                {
                    "id": "user-plan-no-sandbox",
                    "parent_id": None,
                    "children_ids": [],
                    "role": "user",
                    "content": goal,
                    "state": "done",
                    "metadata": {},
                    "tool_calls": [],
                    "artifacts": [],
                }
            ],
            "active_leaf_id": "user-plan-no-sandbox",
            "active_branch_id": "branch-plan-no-sandbox",
            "pinned_node_ids": [],
            "context_window_turns": 8,
        },
    )

    assert response.status_code == 200
    task = db_session.execute(select(Task).where(Task.goal == goal)).scalar_one()
    assert task.enable_sandbox is False
    assert task.enable_network is False


def test_executor_defaults_creative_sync_steps_to_artifact_without_sandbox(
    db_session: Session,
) -> None:
    task = Task(
        organization_id="dev-org",
        created_by="dev-engineer",
        title="500字的小说",
        goal="500字的小说",
        status="CREATED",
        model_provider="openai-compatible",
        model_name="default",
    )
    db_session.add(task)
    db_session.flush()
    step = PlanStep(
        key="generate_outline",
        description="Generate a brief outline for the 500-character story.",
        execution_mode="sync",
        requires_sandbox=False,
        can_spawn_subagent=False,
        artifact_expectations=["File: outline.md with story outline."],
    )

    tool_name, tool_input = Executor(db_session)._default_tool_for_step(task=task, step=step)

    assert tool_name == "mcp_artifact_put"
    assert tool_input["name"] == "outline.md"
    assert tool_input["idempotency_key"] == f"{task.id}:generate_outline:mcp_artifact_put"
    assert "500字的小说" in tool_input["content"]
