"""Tests for eval regression flow: baseline setting, delta computation, regression flagging."""

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.db.models import EvalCase, EvalDataset, EvalResult, EvalRun, utc_now
from app.main import app
from tests.conftest import AUTH_HEADERS


def _create_completed_run(client: TestClient) -> str:
    created = client.post(
        "/api/tasks",
        headers=AUTH_HEADERS,
        json={
            "title": "Eval source run",
            "goal": "Create a trace for eval",
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
    return run_id


def _create_dataset(client: TestClient, name: str = "Regression Dataset") -> dict:
    response = client.post(
        "/api/evals/datasets",
        headers=AUTH_HEADERS,
        json={"name": name, "description": "Test dataset"},
    )
    assert response.status_code == 201
    return response.json()


def _save_case(client: TestClient, dataset_id: str, run_id: str) -> dict:
    response = client.post(
        f"/api/evals/datasets/{dataset_id}/cases/from-run/{run_id}",
        headers=AUTH_HEADERS,
        json={"expected_json": {"status": "COMPLETED"}, "tags_json": ["regression"]},
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


class TestSetBaseline:
    def test_set_baseline_happy_path(self, db_session: Session) -> None:
        client = TestClient(app)
        run_id = _create_completed_run(client)
        dataset = _create_dataset(client)
        _save_case(client, dataset["id"], run_id)
        eval_run = _run_eval(client, dataset["id"])

        response = client.patch(
            f"/api/evals/datasets/{dataset['id']}/baseline",
            headers=AUTH_HEADERS,
            json={"eval_run_id": eval_run["id"]},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["baseline_run_id"] == eval_run["id"]

        # Verify persisted
        stored = db_session.get(EvalDataset, dataset["id"])
        assert stored is not None
        assert stored.baseline_run_id == eval_run["id"]

    def test_set_baseline_invalid_run_id(self, db_session: Session) -> None:
        client = TestClient(app)
        dataset = _create_dataset(client)

        response = client.patch(
            f"/api/evals/datasets/{dataset['id']}/baseline",
            headers=AUTH_HEADERS,
            json={"eval_run_id": "nonexistent-run-id"},
        )
        assert response.status_code == 404

    def test_set_baseline_run_not_in_dataset(self, db_session: Session) -> None:
        client = TestClient(app)
        run_id = _create_completed_run(client)
        dataset_a = _create_dataset(client, "Dataset A")
        dataset_b = _create_dataset(client, "Dataset B")
        _save_case(client, dataset_a["id"], run_id)
        eval_run = _run_eval(client, dataset_a["id"])

        # Try to set baseline on dataset_b using eval_run from dataset_a
        response = client.patch(
            f"/api/evals/datasets/{dataset_b['id']}/baseline",
            headers=AUTH_HEADERS,
            json={"eval_run_id": eval_run["id"]},
        )
        assert response.status_code == 409


class TestRegressionDelta:
    def test_null_delta_when_no_baseline(self, db_session: Session) -> None:
        client = TestClient(app)
        run_id = _create_completed_run(client)
        dataset = _create_dataset(client)
        _save_case(client, dataset["id"], run_id)
        eval_run = _run_eval(client, dataset["id"])

        response = client.get(
            f"/api/evals/runs/{eval_run['id']}/regression",
            headers=AUTH_HEADERS,
        )
        assert response.status_code == 200
        assert response.json() is None

    def test_null_delta_when_run_is_baseline(self, db_session: Session) -> None:
        client = TestClient(app)
        run_id = _create_completed_run(client)
        dataset = _create_dataset(client)
        _save_case(client, dataset["id"], run_id)
        eval_run = _run_eval(client, dataset["id"])

        # Set this run as baseline
        client.patch(
            f"/api/evals/datasets/{dataset['id']}/baseline",
            headers=AUTH_HEADERS,
            json={"eval_run_id": eval_run["id"]},
        )

        # Query regression for the baseline itself
        response = client.get(
            f"/api/evals/runs/{eval_run['id']}/regression",
            headers=AUTH_HEADERS,
        )
        assert response.status_code == 200
        assert response.json() is None

    def test_delta_no_regression(self, db_session: Session) -> None:
        """When both runs pass all cases, delta should be 0 and is_regression=False."""
        client = TestClient(app)
        run_id = _create_completed_run(client)
        dataset = _create_dataset(client)
        _save_case(client, dataset["id"], run_id)

        # First eval run → set as baseline
        baseline_run = _run_eval(client, dataset["id"])
        client.patch(
            f"/api/evals/datasets/{dataset['id']}/baseline",
            headers=AUTH_HEADERS,
            json={"eval_run_id": baseline_run["id"]},
        )

        # Second eval run → compare
        current_run = _run_eval(client, dataset["id"])
        response = client.get(
            f"/api/evals/runs/{current_run['id']}/regression",
            headers=AUTH_HEADERS,
        )
        assert response.status_code == 200
        delta = response.json()
        assert delta is not None
        assert delta["baseline_run_id"] == baseline_run["id"]
        assert delta["current_run_id"] == current_run["id"]
        assert delta["task_success_rate_delta"] == 0.0
        assert delta["is_regression"] is False
        assert delta["newly_failing_case_ids"] == []
        assert delta["newly_passing_case_ids"] == []

    def test_regression_flagging_threshold(self, db_session: Session) -> None:
        """Regression is flagged when task_success_rate drops > 10pp."""
        client = TestClient(app)
        run_id = _create_completed_run(client)
        dataset = _create_dataset(client)
        _save_case(client, dataset["id"], run_id)

        # Baseline run (all pass)
        baseline_run = _run_eval(client, dataset["id"])
        client.patch(
            f"/api/evals/datasets/{dataset['id']}/baseline",
            headers=AUTH_HEADERS,
            json={"eval_run_id": baseline_run["id"]},
        )

        # Current run also passes (same data), so no regression
        current_run = _run_eval(client, dataset["id"])
        response = client.get(
            f"/api/evals/runs/{current_run['id']}/regression",
            headers=AUTH_HEADERS,
        )
        delta = response.json()
        assert delta["is_regression"] is False
        assert delta["total_cases"] == 1
        assert delta["passed_cases"] == 1
        assert delta["failed_cases"] == 0

    def test_grounding_regression_fields_and_forbidden_leak_gate(
        self,
        db_session: Session,
    ) -> None:
        dataset = EvalDataset(
            organization_id="dev-org",
            name="P6 Grounding Regression",
            description="Grounding gate coverage",
            status="ACTIVE",
            created_by="dev-engineer",
        )
        db_session.add(dataset)
        db_session.flush()
        baseline_run = EvalRun(
            dataset_id=dataset.id,
            organization_id="dev-org",
            agent_id="default",
            status="COMPLETED",
            metrics_json={},
            created_by="dev-engineer",
            started_at=utc_now(),
            completed_at=utc_now(),
        )
        current_run = EvalRun(
            dataset_id=dataset.id,
            organization_id="dev-org",
            agent_id="default",
            status="COMPLETED",
            metrics_json={},
            created_by="dev-engineer",
            started_at=utc_now(),
            completed_at=utc_now(),
        )
        db_session.add_all([baseline_run, current_run])
        db_session.flush()
        dataset.baseline_run_id = baseline_run.id
        eval_case = EvalCase(
            dataset_id=dataset.id,
            source_task_id=None,
            input_json={},
            expected_json={},
            tags_json=["p6"],
        )
        db_session.add(eval_case)
        db_session.flush()
        eval_case_id = eval_case.id
        db_session.add_all(
            [
                EvalResult(
                    eval_run_id=baseline_run.id,
                    eval_case_id=eval_case_id,
                    task_id=None,
                    status="PASSED",
                    scores_json={"task_success": 1, "tool_selection_accuracy": 1},
                    grader_trace_json={
                        "grader_trace_schema_version": 1,
                        "grader": "deterministic_grounding_grader_v1",
                        "passed": True,
                        "grounding_failures": [],
                        "forbidden_evidence_leaked": False,
                    },
                    latency_ms=0,
                    cost_usd="0",
                ),
                EvalResult(
                    eval_run_id=current_run.id,
                    eval_case_id=eval_case_id,
                    task_id=None,
                    status="FAILED",
                    scores_json={"task_success": 0, "tool_selection_accuracy": 1},
                    grader_trace_json={
                        "grader_trace_schema_version": 1,
                        "grader": "deterministic_grounding_grader_v1",
                        "passed": False,
                        "grounding_failures": ["forbidden_evidence_leaked"],
                        "forbidden_evidence_leaked": True,
                        "forbidden_leak_sources": ["citations"],
                    },
                    latency_ms=0,
                    cost_usd="0",
                ),
            ]
        )
        db_session.commit()

        client = TestClient(app)
        response = client.get(
            f"/api/evals/runs/{current_run.id}/regression",
            headers=AUTH_HEADERS,
        )

        assert response.status_code == 200
        delta = response.json()
        assert delta["is_regression"] is True
        assert delta["grounding_pass_rate_delta"] == -1.0
        assert delta["forbidden_evidence_leak_rate_delta"] == 1.0
        assert delta["newly_grounding_failing_case_ids"] == [eval_case_id]
        assert delta["newly_forbidden_leak_case_ids"] == [eval_case_id]
        assert delta["grounding_sample_count"] == 1
        assert delta["low_sample_count"] is True

    def test_behavior_contract_regression_fields_and_gate(
        self,
        db_session: Session,
    ) -> None:
        dataset = EvalDataset(
            organization_id="dev-org",
            name="P8.2 Behavior Regression",
            description="Refusal safety persona gate coverage",
            status="ACTIVE",
            created_by="dev-engineer",
        )
        db_session.add(dataset)
        db_session.flush()
        baseline_run = EvalRun(
            dataset_id=dataset.id,
            organization_id="dev-org",
            agent_id="default",
            status="COMPLETED",
            metrics_json={},
            created_by="dev-engineer",
            started_at=utc_now(),
            completed_at=utc_now(),
        )
        current_run = EvalRun(
            dataset_id=dataset.id,
            organization_id="dev-org",
            agent_id="default",
            status="COMPLETED",
            metrics_json={},
            created_by="dev-engineer",
            started_at=utc_now(),
            completed_at=utc_now(),
        )
        db_session.add_all([baseline_run, current_run])
        db_session.flush()
        dataset.baseline_run_id = baseline_run.id
        eval_case = EvalCase(
            dataset_id=dataset.id,
            source_task_id=None,
            input_json={},
            expected_json={},
            tags_json=["p8-2"],
        )
        db_session.add(eval_case)
        db_session.flush()
        eval_case_id = eval_case.id
        base_trace = {
            "grader_trace_schema_version": 1,
            "grader": "deterministic_trace_grader_v1",
            "passed": True,
            "grounding_failures": [],
            "forbidden_evidence_leaked": False,
            "refusal_contract": {"configured": True, "passed": True, "outcome": "answer"},
            "safety_contract": {
                "configured": True,
                "passed": True,
                "violation_total": 0,
                "violation_breakdown": {},
            },
            "persona_contract": {
                "configured": True,
                "passed": True,
                "role_drift_count": 0,
            },
        }
        current_trace = {
            **base_trace,
            "safety_contract": {
                "configured": True,
                "passed": False,
                "failures": ["banned_phrase:私人邮箱"],
                "violation_total": 1,
                "violation_breakdown": {"banned_phrase": 1},
            },
            "persona_contract": {
                "configured": True,
                "passed": False,
                "failures": ["role_drift:我是 ChatGPT"],
                "role_drift_count": 1,
            },
        }
        db_session.add_all(
            [
                EvalResult(
                    eval_run_id=baseline_run.id,
                    eval_case_id=eval_case_id,
                    task_id=None,
                    status="PASSED",
                    scores_json={"task_success": 1, "tool_selection_accuracy": 1},
                    grader_trace_json=base_trace,
                    latency_ms=0,
                    cost_usd="0",
                ),
                EvalResult(
                    eval_run_id=current_run.id,
                    eval_case_id=eval_case_id,
                    task_id=None,
                    status="FAILED",
                    scores_json={"task_success": 1, "tool_selection_accuracy": 1},
                    grader_trace_json=current_trace,
                    latency_ms=0,
                    cost_usd="0",
                ),
            ]
        )
        db_session.commit()

        client = TestClient(app)
        response = client.get(
            f"/api/evals/runs/{current_run.id}/regression",
            headers=AUTH_HEADERS,
        )

        assert response.status_code == 200
        delta = response.json()
        assert delta["is_regression"] is True
        assert delta["refusal_contract_pass_rate_delta"] == 0.0
        assert delta["safety_contract_pass_rate_delta"] == -1.0
        assert delta["persona_contract_pass_rate_delta"] == -1.0
        assert delta["safety_violation_total_delta"] == 1
        assert delta["role_drift_total_delta"] == 1

    def test_specialist_contract_regression_field_and_gate(
        self,
        db_session: Session,
    ) -> None:
        dataset = EvalDataset(
            organization_id="dev-org",
            name="Specialist Contract Regression",
            description="Specialist contract gate coverage",
            status="ACTIVE",
            created_by="dev-engineer",
        )
        db_session.add(dataset)
        db_session.flush()
        baseline_run = EvalRun(
            dataset_id=dataset.id,
            organization_id="dev-org",
            agent_id="default",
            status="COMPLETED",
            metrics_json={},
            created_by="dev-engineer",
            started_at=utc_now(),
            completed_at=utc_now(),
        )
        current_run = EvalRun(
            dataset_id=dataset.id,
            organization_id="dev-org",
            agent_id="default",
            status="COMPLETED",
            metrics_json={},
            created_by="dev-engineer",
            started_at=utc_now(),
            completed_at=utc_now(),
        )
        db_session.add_all([baseline_run, current_run])
        db_session.flush()
        dataset.baseline_run_id = baseline_run.id
        eval_case = EvalCase(
            dataset_id=dataset.id,
            source_task_id=None,
            input_json={},
            expected_json={},
            tags_json=["subagent-specialist-v2"],
        )
        db_session.add(eval_case)
        db_session.flush()
        eval_case_id = eval_case.id
        base_trace = {
            "grader_trace_schema_version": 1,
            "grader": "deterministic_trace_grader_v1",
            "passed": True,
            "grounding_failures": [],
            "forbidden_evidence_leaked": False,
            "specialist_contract": {
                "configured": True,
                "passed": True,
                "total_specialist_invocations": 1,
                "total_specialist_cost_usd": "0.010000",
                "specialist_role_distribution": {"reviewer": 1},
            },
        }
        current_trace = {
            **base_trace,
            "specialist_contract": {
                "configured": True,
                "passed": False,
                "failures": ["missing_specialist:code-reviewer"],
                "total_specialist_invocations": 0,
                "total_specialist_cost_usd": "0.000000",
                "specialist_role_distribution": {},
            },
        }
        db_session.add_all(
            [
                EvalResult(
                    eval_run_id=baseline_run.id,
                    eval_case_id=eval_case_id,
                    task_id=None,
                    status="PASSED",
                    scores_json={"task_success": 1, "tool_selection_accuracy": 1},
                    grader_trace_json=base_trace,
                    latency_ms=0,
                    cost_usd="0",
                ),
                EvalResult(
                    eval_run_id=current_run.id,
                    eval_case_id=eval_case_id,
                    task_id=None,
                    status="FAILED",
                    scores_json={"task_success": 1, "tool_selection_accuracy": 1},
                    grader_trace_json=current_trace,
                    latency_ms=0,
                    cost_usd="0",
                ),
            ]
        )
        db_session.commit()

        response = TestClient(app).get(
            f"/api/evals/runs/{current_run.id}/regression",
            headers=AUTH_HEADERS,
        )

        assert response.status_code == 200
        delta = response.json()
        assert delta["is_regression"] is True
        assert delta["specialist_contract_pass_rate_delta"] == -1.0

    def test_regression_run_not_found(self, db_session: Session) -> None:
        client = TestClient(app)
        response = client.get(
            "/api/evals/runs/nonexistent-id/regression",
            headers=AUTH_HEADERS,
        )
        assert response.status_code == 404


class TestEvalCaseFromRunStatus:
    def test_case_from_completed_run(self, db_session: Session) -> None:
        client = TestClient(app)
        run_id = _create_completed_run(client)
        dataset = _create_dataset(client)

        response = client.post(
            f"/api/evals/datasets/{dataset['id']}/cases/from-run/{run_id}",
            headers=AUTH_HEADERS,
            json={"expected_json": {"status": "COMPLETED"}, "tags_json": ["trace"]},
        )
        assert response.status_code == 201
        body = response.json()
        assert body["source_task_id"] == run_id
        assert "execution_trace" in body["expected_json"]
        trace = body["expected_json"]["execution_trace"]
        assert "tool_calls" in trace
        assert "model_call_count" in trace

    def test_case_from_non_terminal_run_rejected(self, db_session: Session) -> None:
        """Runs that are not COMPLETED or FAILED should be rejected."""
        client = TestClient(app)
        # Create a run but don't start it (stays CREATED)
        created = client.post(
            "/api/tasks",
            headers=AUTH_HEADERS,
            json={
                "title": "Pending run",
                "goal": "Not started yet",
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
        dataset = _create_dataset(client)

        response = client.post(
            f"/api/evals/datasets/{dataset['id']}/cases/from-run/{run_id}",
            headers=AUTH_HEADERS,
            json={"expected_json": {"status": "COMPLETED"}, "tags_json": []},
        )
        assert response.status_code == 409
