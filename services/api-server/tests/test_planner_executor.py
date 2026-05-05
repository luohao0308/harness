from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.planner import DeterministicPlanner
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
              "can_spawn_subagent": false
            },
            {
              "key": "parallel_review",
              "description": "异步并发审查",
              "execution_mode": "async",
              "requires_sandbox": false,
              "can_spawn_subagent": true
            }
          ]
        }
        """,
    )

    assert [step.execution_mode for step in plan.steps] == ["sync", "async"]
    assert plan.steps[1].can_spawn_subagent is True


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
