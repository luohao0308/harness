from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import ExecutionPlan, TaskStep
from app.main import app


def test_start_task_generates_plan_steps_and_completion_events(db_session: Session) -> None:
    client = TestClient(app)
    created = client.post(
        "/api/tasks",
        json={
            "title": "Demo",
            "goal": "Analyze project",
            "model_provider": "openai-compatible",
            "model_name": "default",
        },
    ).json()

    response = client.post(f"/api/tasks/{created['id']}/start")

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

    events = client.get(f"/api/tasks/{created['id']}/events").json()["items"]
    event_types = [event["event_type"] for event in events]
    assert event_types == [
        "TASK_CREATED",
        "PLAN_REQUESTED",
        "PLAN_GENERATED",
        "STEP_STARTED",
        "STEP_COMPLETED",
        "STEP_STARTED",
        "STEP_COMPLETED",
        "TASK_COMPLETED",
    ]


def test_start_task_rejects_missing_task() -> None:
    client = TestClient(app)

    response = client.post("/api/tasks/missing/start")

    assert response.status_code == 404
