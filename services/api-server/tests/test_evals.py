from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import AdminAuditEvent, AgentEvent, EvalCase, EvalRun
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
        event.event_type
        for event in db_session.execute(select(AdminAuditEvent)).scalars()
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
