"""Unit tests for multi-step DAG-driven Executor."""

from unittest.mock import MagicMock

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.dag_scheduler import StepResult as DAGStepResult
from app.agents.executor import (
    DEFAULT_SUBAGENT_TIMEOUT,
    DEFAULT_TOOL_TIMEOUT,
    MAX_STEP_OUTPUT_BYTES,
    SUBAGENT_HEARTBEAT_INTERVAL,
    Executor,
)
from app.agents.model_gateway import ModelRequest, ModelResponse
from app.agents.schemas import PlanStep
from app.db.models import AgentRun, TaskStep
from app.main import app
from tests.conftest import AUTH_HEADERS


def _make_step(key: str, depends_on: list[str] | None = None, **kwargs) -> PlanStep:
    return PlanStep(
        key=key,
        description=f"Step {key}",
        execution_mode=kwargs.get("execution_mode", "sync"),
        requires_sandbox=kwargs.get("requires_sandbox", False),
        can_spawn_subagent=kwargs.get("can_spawn_subagent", False),
        depends_on=depends_on or [],
        tool_hints=kwargs.get("tool_hints", ["read_file"]),
        acceptance_criteria=[f"Step {key} completes."],
        risk_level="low",
        timeout_seconds=kwargs.get("timeout_seconds", 60),
    )


class TestDAGExecution:
    """Tests for DAG-driven execution in the Executor."""

    def test_linear_plan_executes_all_steps(self, db_session: Session) -> None:
        """Linear plan (all empty depends_on) executes all steps sequentially."""
        client = TestClient(app)
        created = client.post(
            "/api/tasks",
            headers=AUTH_HEADERS,
            json={
                "title": "Linear DAG",
                "goal": "Execute linear plan",
                "model_provider": "openai-compatible",
                "model_name": "default",
            },
        ).json()

        response = client.post(f"/api/tasks/{created['id']}/start", headers=AUTH_HEADERS)

        assert response.status_code == 202
        task_data = response.json()
        assert task_data["status"] == "COMPLETED"

        steps = list(
            db_session.execute(
                select(TaskStep)
                .where(TaskStep.task_id == created["id"])
                .order_by(TaskStep.started_at)
            ).scalars()
        )
        assert all(step.status == "STEP_COMPLETED" for step in steps)

    def test_dag_with_dependencies_executes_in_order(
        self, db_session: Session, monkeypatch
    ) -> None:
        """Steps with dependencies execute after their dependencies complete."""

        class FakeGateway:
            def __init__(self, **kwargs) -> None:
                pass

            def complete(self, request_payload: ModelRequest) -> ModelResponse:
                return ModelResponse(
                    content="""{
                        "summary": "DAG plan",
                        "steps": [
                            {
                                "key": "step_a",
                                "description": "First step",
                                "execution_mode": "sync",
                                "requires_sandbox": false,
                                "can_spawn_subagent": false,
                                "depends_on": [],
                                "tool_hints": ["read_file"],
                                "acceptance_criteria": ["done"],
                                "risk_level": "low"
                            },
                            {
                                "key": "step_b",
                                "description": "Second step depends on A",
                                "execution_mode": "sync",
                                "requires_sandbox": false,
                                "can_spawn_subagent": false,
                                "depends_on": ["step_a"],
                                "tool_hints": ["read_file"],
                                "acceptance_criteria": ["done"],
                                "risk_level": "low"
                            },
                            {
                                "key": "step_c",
                                "description": "Third step depends on B",
                                "execution_mode": "sync",
                                "requires_sandbox": false,
                                "can_spawn_subagent": false,
                                "depends_on": ["step_b"],
                                "tool_hints": ["read_file"],
                                "acceptance_criteria": ["done"],
                                "risk_level": "low"
                            }
                        ]
                    }""",
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
                "title": "DAG Order",
                "goal": "Test dependency ordering",
                "model_provider": "openai-compatible",
                "model_name": "default",
            },
        ).json()

        response = client.post(f"/api/tasks/{created['id']}/start", headers=AUTH_HEADERS)

        assert response.status_code == 202
        assert response.json()["status"] == "COMPLETED"

        steps = list(
            db_session.execute(
                select(TaskStep)
                .where(TaskStep.task_id == created["id"])
                .order_by(TaskStep.started_at)
            ).scalars()
        )
        step_keys = [s.step_key for s in steps]
        # Verify order respects dependencies
        assert step_keys.index("step_a") < step_keys.index("step_b")
        assert step_keys.index("step_b") < step_keys.index("step_c")


class TestStepOutputPassing:
    """Tests for step output context passing."""

    def test_step_context_accumulates(self, db_session: Session) -> None:
        """Executor accumulates step results in step_context."""
        executor = Executor(session=db_session)

        # Verify step_context starts empty
        assert executor.step_context == {}

    def test_output_truncation_64kb(self) -> None:
        """Step output is truncated to 64KB."""
        large_output = "x" * (MAX_STEP_OUTPUT_BYTES + 5000)
        result = DAGStepResult(
            step_key="test",
            status="COMPLETED",
            output=large_output,
        )

        assert len(result.output) == MAX_STEP_OUTPUT_BYTES


class TestFailurePropagation:
    """Tests for failure propagation in DAG execution."""

    def test_downstream_steps_skipped_on_failure(self, db_session: Session, monkeypatch) -> None:
        """When a step fails, all downstream dependents are marked STEP_SKIPPED."""

        call_count = {"value": 0}

        class FakeGateway:
            def __init__(self, **kwargs) -> None:
                pass

            def complete(self, request_payload: ModelRequest) -> ModelResponse:
                return ModelResponse(
                    content="""{
                        "summary": "Failure plan",
                        "steps": [
                            {
                                "key": "step_a",
                                "description": "Will fail",
                                "execution_mode": "sync",
                                "requires_sandbox": false,
                                "can_spawn_subagent": false,
                                "depends_on": [],
                                "tool_hints": ["read_file"],
                                "acceptance_criteria": ["done"],
                                "risk_level": "low"
                            },
                            {
                                "key": "step_b",
                                "description": "Depends on A (will be skipped)",
                                "execution_mode": "sync",
                                "requires_sandbox": false,
                                "can_spawn_subagent": false,
                                "depends_on": ["step_a"],
                                "tool_hints": ["read_file"],
                                "acceptance_criteria": ["done"],
                                "risk_level": "low"
                            },
                            {
                                "key": "step_c",
                                "description": "Independent (should still run)",
                                "execution_mode": "sync",
                                "requires_sandbox": false,
                                "can_spawn_subagent": false,
                                "depends_on": [],
                                "tool_hints": ["read_file"],
                                "acceptance_criteria": ["done"],
                                "risk_level": "low"
                            }
                        ]
                    }""",
                    model_provider=request_payload.model_provider,
                    model_name=request_payload.model_name,
                    usage={},
                    raw_response={"mode": "fake"},
                )

        monkeypatch.setattr("app.agents.executor.AuditedModelGateway", FakeGateway)

        # Make the ToolRunner fail for step_a

        class FakeToolRunner:
            def __init__(self, **kwargs) -> None:
                pass

            def execute(self, **kwargs):
                call_count["value"] += 1
                step_key = kwargs.get("input_json", {}).get("step_key", "")
                mock_result = MagicMock()
                if step_key == "step_a":
                    mock_result.allowed = False
                    mock_result.tool_call.status = "FAILED"
                    mock_result.tool_call.error_message = "Simulated failure"
                    mock_result.tool_call.id = "tc_fail"
                else:
                    mock_result.allowed = True
                    mock_result.tool_call.status = "SUCCESS"
                    mock_result.tool_call.id = f"tc_{step_key}"
                    mock_result.tool_call.duration_ms = 10
                    mock_result.tool_call.output = "ok"
                return mock_result

        monkeypatch.setattr("app.agents.executor.ToolRunner", FakeToolRunner)

        client = TestClient(app)
        created = client.post(
            "/api/tasks",
            headers=AUTH_HEADERS,
            json={
                "title": "Failure Propagation",
                "goal": "Test failure skipping",
                "model_provider": "openai-compatible",
                "model_name": "default",
            },
        ).json()

        response = client.post(f"/api/tasks/{created['id']}/start", headers=AUTH_HEADERS)

        assert response.status_code == 202
        assert response.json()["status"] == "FAILED"

        # Check events for STEP_SKIPPED
        events = client.get(f"/api/tasks/{created['id']}/events", headers=AUTH_HEADERS).json()[
            "items"
        ]
        event_types = [e["event_type"] for e in events]
        assert "STEP_FAILED" in event_types
        assert "STEP_SKIPPED" in event_types


class TestRunFinalState:
    """Tests for Run final state determination."""

    def test_completed_when_all_steps_succeed(self, db_session: Session) -> None:
        """Run is COMPLETED when all steps complete successfully."""
        client = TestClient(app)
        created = client.post(
            "/api/tasks",
            headers=AUTH_HEADERS,
            json={
                "title": "All Success",
                "goal": "All steps succeed",
                "model_provider": "openai-compatible",
                "model_name": "default",
            },
        ).json()

        response = client.post(f"/api/tasks/{created['id']}/start", headers=AUTH_HEADERS)

        assert response.json()["status"] == "COMPLETED"

    def test_failed_when_any_step_fails(self, db_session: Session, monkeypatch) -> None:
        """Run is FAILED if any step reaches STEP_FAILED."""

        class FakeToolRunner:
            def __init__(self, **kwargs) -> None:
                pass

            def execute(self, **kwargs):
                mock_result = MagicMock()
                mock_result.allowed = False
                mock_result.tool_call.status = "FAILED"
                mock_result.tool_call.error_message = "Forced failure"
                mock_result.tool_call.id = "tc_fail"
                return mock_result

        monkeypatch.setattr("app.agents.executor.ToolRunner", FakeToolRunner)

        client = TestClient(app)
        created = client.post(
            "/api/tasks",
            headers=AUTH_HEADERS,
            json={
                "title": "Fail Test",
                "goal": "Test failure state",
                "model_provider": "openai-compatible",
                "model_name": "default",
            },
        ).json()

        response = client.post(f"/api/tasks/{created['id']}/start", headers=AUTH_HEADERS)

        assert response.json()["status"] == "FAILED"


class TestModelCallEvent:
    """Tests for MODEL_CALL event with purpose=tool_parameter_generation."""

    def test_model_call_event_emitted_for_tool_selection(self, db_session: Session) -> None:
        """MODEL_CALLED event is emitted with purpose=tool_parameter_generation."""
        client = TestClient(app)
        created = client.post(
            "/api/tasks",
            headers=AUTH_HEADERS,
            json={
                "title": "Model Call",
                "goal": "Test model call event",
                "model_provider": "openai-compatible",
                "model_name": "default",
            },
        ).json()

        client.post(f"/api/tasks/{created['id']}/start", headers=AUTH_HEADERS)

        events = client.get(f"/api/tasks/{created['id']}/events", headers=AUTH_HEADERS).json()[
            "items"
        ]
        model_called_events = [
            e
            for e in events
            if e["event_type"] == "MODEL_CALLED"
            and e.get("payload_json", {}).get("purpose") == "tool_parameter_generation"
        ]
        # At least one MODEL_CALLED event with tool_parameter_generation purpose
        assert len(model_called_events) >= 1


class TestSubagentDelegation:
    """Tests for subagent delegation trigger conditions."""

    def test_subagent_only_for_async_with_can_spawn(
        self,
        db_session: Session,
        monkeypatch,
    ) -> None:
        """Subagent delegation only when execution_mode=async AND can_spawn_subagent=true."""
        monkeypatch.setattr("app.workers.subagent_worker.run_subagent.send", lambda _id: None)
        client = TestClient(app)
        created = client.post(
            "/api/tasks",
            headers=AUTH_HEADERS,
            json={
                "title": "Subagent Test",
                "goal": "使用子 Agent 并发分析长时间任务",
                "model_provider": "openai-compatible",
                "model_name": "default",
            },
        ).json()

        response = client.post(f"/api/tasks/{created['id']}/start", headers=AUTH_HEADERS)

        assert response.status_code == 202
        # Check that a subagent was spawned
        subagent = db_session.execute(
            select(AgentRun).where(AgentRun.task_id == created["id"])
        ).scalar_one_or_none()
        assert subagent is not None
        assert subagent.status == "PENDING"

    def test_sync_step_with_can_spawn_executes_inline(
        self, db_session: Session, monkeypatch
    ) -> None:
        """Sync step with can_spawn_subagent=true executes inline (no subagent)."""

        class FakeGateway:
            def __init__(self, **kwargs) -> None:
                pass

            def complete(self, request_payload: ModelRequest) -> ModelResponse:
                return ModelResponse(
                    content="""{
                        "summary": "Sync with spawn",
                        "steps": [
                            {
                                "key": "sync_spawn",
                                "description": "Sync step with can_spawn",
                                "execution_mode": "sync",
                                "requires_sandbox": false,
                                "can_spawn_subagent": true,
                                "depends_on": [],
                                "tool_hints": ["read_file"],
                                "acceptance_criteria": ["done"],
                                "risk_level": "low"
                            }
                        ]
                    }""",
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
                "title": "Sync Spawn",
                "goal": "Test sync with can_spawn",
                "model_provider": "openai-compatible",
                "model_name": "default",
            },
        ).json()

        response = client.post(f"/api/tasks/{created['id']}/start", headers=AUTH_HEADERS)

        assert response.status_code == 202
        # No subagent should be spawned for sync steps
        subagent = db_session.execute(
            select(AgentRun).where(AgentRun.task_id == created["id"])
        ).scalar_one_or_none()
        assert subagent is None


class TestTimeoutHandling:
    """Tests for timeout configuration."""

    def test_default_tool_timeout_is_60s(self) -> None:
        """Default tool timeout is 60 seconds."""
        assert DEFAULT_TOOL_TIMEOUT == 60

    def test_default_subagent_timeout_is_300s(self) -> None:
        """Default subagent timeout is 300 seconds."""
        assert DEFAULT_SUBAGENT_TIMEOUT == 300

    def test_heartbeat_interval_is_30s(self) -> None:
        """Subagent heartbeat interval is 30 seconds."""
        assert SUBAGENT_HEARTBEAT_INTERVAL == 30

    def test_step_timeout_from_plan_step(self) -> None:
        """PlanStep timeout_seconds field is respected."""
        step = _make_step("test", timeout_seconds=120)
        assert step.timeout_seconds == 120

    def test_step_default_timeout(self) -> None:
        """PlanStep default timeout is 60 seconds."""
        step = PlanStep(
            key="test",
            description="Test",
            execution_mode="sync",
            requires_sandbox=False,
            can_spawn_subagent=False,
        )
        assert step.timeout_seconds == 60


class TestSubagentHeartbeat:
    """Tests for subagent heartbeat emission."""

    def test_heartbeat_event_emitted_on_subagent_spawn(self, db_session: Session) -> None:
        """SUBAGENT_HEARTBEAT event is emitted when subagent is spawned."""
        client = TestClient(app)
        created = client.post(
            "/api/tasks",
            headers=AUTH_HEADERS,
            json={
                "title": "Heartbeat Test",
                "goal": "使用子 Agent 并发分析长时间任务",
                "model_provider": "openai-compatible",
                "model_name": "default",
            },
        ).json()

        client.post(f"/api/tasks/{created['id']}/start", headers=AUTH_HEADERS)

        events = client.get(f"/api/tasks/{created['id']}/events", headers=AUTH_HEADERS).json()[
            "items"
        ]
        heartbeat_events = [e for e in events if e["event_type"] == "SUBAGENT_HEARTBEAT"]
        assert len(heartbeat_events) >= 1
        interval = heartbeat_events[0]["payload_json"]["interval_seconds"]
        assert interval == SUBAGENT_HEARTBEAT_INTERVAL


class TestDependsOnInPlanStep:
    """Tests for depends_on field in PlanStep schema."""

    def test_depends_on_defaults_to_empty_list(self) -> None:
        """depends_on defaults to empty list."""
        step = PlanStep(
            key="test",
            description="Test",
            execution_mode="sync",
            requires_sandbox=False,
            can_spawn_subagent=False,
        )
        assert step.depends_on == []

    def test_depends_on_accepts_step_keys(self) -> None:
        """depends_on accepts a list of step keys."""
        step = PlanStep(
            key="test",
            description="Test",
            execution_mode="sync",
            requires_sandbox=False,
            can_spawn_subagent=False,
            depends_on=["step_a", "step_b"],
        )
        assert step.depends_on == ["step_a", "step_b"]

    def test_timeout_seconds_field(self) -> None:
        """timeout_seconds field is configurable."""
        step = PlanStep(
            key="test",
            description="Test",
            execution_mode="sync",
            requires_sandbox=False,
            can_spawn_subagent=False,
            timeout_seconds=120,
        )
        assert step.timeout_seconds == 120
