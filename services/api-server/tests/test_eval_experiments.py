from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import EvalExperiment, EvalExperimentArm, EvalRun
from app.main import app
from tests.conftest import AUTH_HEADERS


def _create_completed_task_run(client: TestClient) -> str:
    created = client.post(
        "/api/tasks",
        headers=AUTH_HEADERS,
        json={
            "title": "Eval source run",
            "goal": "Create a trace for experiment eval",
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


def _create_dataset(client: TestClient, name: str) -> dict:
    response = client.post(
        "/api/evals/datasets",
        headers=AUTH_HEADERS,
        json={"name": name, "description": "Contrast experiment dataset"},
    )
    assert response.status_code == 201
    return response.json()


def _save_case(client: TestClient, dataset_id: str, task_run_id: str) -> dict:
    response = client.post(
        f"/api/evals/datasets/{dataset_id}/cases/from-run/{task_run_id}",
        headers=AUTH_HEADERS,
        json={"expected_json": {"status": "COMPLETED"}, "tags_json": ["experiment"]},
    )
    assert response.status_code == 201
    return response.json()


def _run_eval(client: TestClient, dataset_id: str) -> dict:
    response = client.post(
        f"/api/evals/datasets/{dataset_id}/runs",
        headers=AUTH_HEADERS,
        json={"agent_id": "default"},
    )
    assert response.status_code == 201
    return response.json()


def _dataset_with_case(client: TestClient, name: str) -> tuple[dict, str]:
    task_run_id = _create_completed_task_run(client)
    dataset = _create_dataset(client, name)
    _save_case(client, dataset["id"], task_run_id)
    return dataset, task_run_id


def test_eval_experiment_links_existing_eval_runs_and_preserves_regression_delta(
    db_session: Session,
) -> None:
    client = TestClient(app)
    dataset, _task_run_id = _dataset_with_case(client, "LangGraph Native Contrast")
    baseline = _run_eval(client, dataset["id"])
    candidate = _run_eval(client, dataset["id"])
    client.patch(
        f"/api/evals/datasets/{dataset['id']}/baseline",
        headers=AUTH_HEADERS,
        json={"eval_run_id": baseline["id"]},
    )

    response = client.post(
        f"/api/evals/datasets/{dataset['id']}/experiments",
        headers=AUTH_HEADERS,
        json={
            "name": "LangGraph vs native",
            "description": "Projection over normal EvalRun rows",
            "metadata_json": {"capability_hash": "sha256:test"},
            "arms": [
                {
                    "name": "native",
                    "arm_type": "baseline",
                    "eval_run_id": baseline["id"],
                    "capability_hashes_json": {"content_sha256_values": ["native"]},
                },
                {
                    "name": "langgraph",
                    "arm_type": "candidate",
                    "eval_run_id": candidate["id"],
                    "capability_hashes_json": {"content_sha256_values": ["langgraph"]},
                },
            ],
        },
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["dataset_id"] == dataset["id"]
    assert payload["eval_run_ids"] == [baseline["id"], candidate["id"]]
    assert payload["metadata_json"]["regression_delta_replaced"] is False
    assert [arm["name"] for arm in payload["arms"]] == ["native", "langgraph"]
    assert payload["arms"][0]["metrics_json"]["case_total"] == 1
    assert payload["arms"][1]["capability_hashes_json"]["content_sha256_values"] == [
        "langgraph"
    ]

    listed = client.get("/api/evals/experiments", headers=AUTH_HEADERS)
    assert listed.status_code == 200
    assert payload["id"] in {item["id"] for item in listed.json()["items"]}

    detail = client.get(f"/api/evals/experiments/{payload['id']}", headers=AUTH_HEADERS)
    assert detail.status_code == 200
    assert detail.json()["eval_run_ids"] == [baseline["id"], candidate["id"]]

    delta = client.get(
        f"/api/evals/runs/{candidate['id']}/regression",
        headers=AUTH_HEADERS,
    )
    assert delta.status_code == 200
    assert delta.json()["baseline_run_id"] == baseline["id"]
    assert delta.json()["current_run_id"] == candidate["id"]

    experiment = db_session.get(EvalExperiment, payload["id"])
    arms = db_session.execute(
        select(EvalExperimentArm).where(EvalExperimentArm.experiment_id == payload["id"])
    ).scalars().all()
    assert experiment is not None
    assert len(arms) == 2


def test_eval_experiment_rejects_missing_and_mismatched_eval_runs() -> None:
    client = TestClient(app)
    dataset_a, _task_run_id_a = _dataset_with_case(client, "Experiment Dataset A")
    dataset_b, _task_run_id_b = _dataset_with_case(client, "Experiment Dataset B")
    run_b = _run_eval(client, dataset_b["id"])

    missing = client.post(
        f"/api/evals/datasets/{dataset_a['id']}/experiments",
        headers=AUTH_HEADERS,
        json={
            "name": "Missing run",
            "arms": [{"name": "missing", "eval_run_id": "missing-eval-run"}],
        },
    )
    assert missing.status_code == 404

    mismatched = client.post(
        f"/api/evals/datasets/{dataset_a['id']}/experiments",
        headers=AUTH_HEADERS,
        json={
            "name": "Mismatched run",
            "arms": [{"name": "wrong-dataset", "eval_run_id": run_b["id"]}],
        },
    )
    assert mismatched.status_code == 409


def test_eval_experiment_rejects_invalid_arm_shape() -> None:
    client = TestClient(app)
    dataset, _task_run_id = _dataset_with_case(client, "Experiment Arm Validation")
    eval_run = _run_eval(client, dataset["id"])

    empty_arms = client.post(
        f"/api/evals/datasets/{dataset['id']}/experiments",
        headers=AUTH_HEADERS,
        json={"name": "No arms", "arms": []},
    )
    assert empty_arms.status_code == 422

    invalid_type = client.post(
        f"/api/evals/datasets/{dataset['id']}/experiments",
        headers=AUTH_HEADERS,
        json={
            "name": "Invalid arm type",
            "arms": [
                {
                    "name": "native",
                    "arm_type": "freeform",
                    "eval_run_id": eval_run["id"],
                }
            ],
        },
    )
    assert invalid_type.status_code == 422

    invalid_status = client.post(
        f"/api/evals/datasets/{dataset['id']}/experiments",
        headers=AUTH_HEADERS,
        json={
            "name": "Invalid status",
            "arms": [
                {
                    "name": "native",
                    "status": "SOMEDAY",
                    "eval_run_id": eval_run["id"],
                }
            ],
        },
    )
    assert invalid_status.status_code == 422

    duplicate_names = client.post(
        f"/api/evals/datasets/{dataset['id']}/experiments",
        headers=AUTH_HEADERS,
        json={
            "name": "Duplicate arms",
            "arms": [
                {"name": "native", "eval_run_id": eval_run["id"]},
                {"name": " native ", "eval_run_id": eval_run["id"]},
            ],
        },
    )
    assert duplicate_names.status_code == 422


def test_eval_experiment_arm_failure_is_isolated_to_arm() -> None:
    client = TestClient(app)
    dataset, _task_run_id = _dataset_with_case(client, "Arm Failure Isolation")
    baseline = _run_eval(client, dataset["id"])
    candidate = _run_eval(client, dataset["id"])

    response = client.post(
        f"/api/evals/datasets/{dataset['id']}/experiments",
        headers=AUTH_HEADERS,
        json={
            "name": "Failure isolation",
            "arms": [
                {"name": "native", "arm_type": "baseline", "eval_run_id": baseline["id"]},
                {
                    "name": "langgraph",
                    "arm_type": "candidate",
                    "eval_run_id": candidate["id"],
                    "error_message": "workflow failed",
                },
            ],
        },
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["status"] == "COMPLETED"
    failed_arm = next(arm for arm in payload["arms"] if arm["name"] == "langgraph")
    native_arm = next(arm for arm in payload["arms"] if arm["name"] == "native")
    assert failed_arm["status"] == "FAILED"
    assert failed_arm["error_message"] == "workflow failed"
    assert native_arm["status"] == "COMPLETED"


def test_eval_experiment_arm_status_defaults_to_linked_eval_run_status(
    db_session: Session,
) -> None:
    client = TestClient(app)
    dataset, _task_run_id = _dataset_with_case(client, "Arm Status Follows EvalRun")
    baseline = _run_eval(client, dataset["id"])
    candidate = _run_eval(client, dataset["id"])
    failed_run = db_session.get(EvalRun, candidate["id"])
    assert failed_run is not None
    failed_run.status = "FAILED"
    failed_run.metrics_json = {"case_total": 1, "passed_total": 0}
    db_session.flush()

    response = client.post(
        f"/api/evals/datasets/{dataset['id']}/experiments",
        headers=AUTH_HEADERS,
        json={
            "name": "Failed EvalRun projection",
            "arms": [
                {"name": "native", "arm_type": "baseline", "eval_run_id": baseline["id"]},
                {"name": "langgraph", "arm_type": "candidate", "eval_run_id": candidate["id"]},
            ],
        },
    )

    assert response.status_code == 201
    langgraph_arm = next(arm for arm in response.json()["arms"] if arm["name"] == "langgraph")
    assert langgraph_arm["status"] == "FAILED"
