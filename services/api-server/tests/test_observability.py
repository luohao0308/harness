import json
import logging

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.logging import JsonFormatter
from app.db.models import AgentRun, ModelCall, SandboxInstance, Task, ToolCall, utc_now
from app.events.event_store import EventStore
from app.events.event_types import EventType
from app.main import app
from tests.conftest import AUTH_HEADERS


def test_metrics_endpoint_exposes_required_metrics() -> None:
    client = TestClient(app)

    response = client.get("/metrics")

    assert response.status_code == 200
    body = response.text
    assert "agent_tasks_total" in body
    assert "agent_subagents_running" in body
    assert "sandbox_containers_total" in body
    assert "warm_pool_hit_total" in body
    assert "model_calls_total" in body


def test_json_formatter_includes_required_fields_and_redacts_sensitive_values() -> None:
    record = logging.LogRecord(
        name="agent-harness",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="task event",
        args=(),
        exc_info=None,
    )
    record.trace_id = "trace-test"
    record.task_id = "task-test"
    record.agent_run_id = "agent-test"
    record.event_type = "TASK_CREATED"
    record.secret_value = "plain-secret"

    payload = json.loads(JsonFormatter().format(record))

    assert payload["level"] == "INFO"
    assert payload["service"] == "api-server"
    assert payload["message"] == "task event"
    assert payload["trace_id"] == "trace-test"
    assert payload["task_id"] == "task-test"
    assert payload["agent_run_id"] == "agent-test"
    assert payload["event_type"] == "TASK_CREATED"
    assert payload["created_at"]
    assert payload["secret_value"] == "[REDACTED]"


def test_request_trace_id_is_written_to_events() -> None:
    client = TestClient(app)

    created = client.post(
        "/api/tasks",
        headers={**AUTH_HEADERS, "x-trace-id": "trace-from-test"},
        json={
            "title": "Trace demo",
            "goal": "Verify trace propagation",
            "model_provider": "openai-compatible",
            "model_name": "default",
        },
    )
    task_id = created.json()["id"]

    events = client.get(f"/api/tasks/{task_id}/events", headers=AUTH_HEADERS).json()["items"]

    assert created.headers["x-trace-id"] == "trace-from-test"
    assert events[0]["trace_id"] == "trace-from-test"


def test_observability_summary_aggregates_current_organization(db_session: Session) -> None:
    task = Task(
        organization_id="dev-org",
        created_by="dev-engineer",
        title="Observe",
        goal="Aggregate runtime facts",
        status="FAILED",
        model_provider="openai-compatible",
        model_name="default",
        max_runtime_seconds=1800,
        max_subagents=5,
        enable_sandbox=True,
        enable_network=False,
        created_at=utc_now(),
        updated_at=utc_now(),
    )
    other = Task(
        organization_id="other-org",
        created_by="other",
        title="Other",
        goal="Should not count",
        status="COMPLETED",
        model_provider="openai-compatible",
        model_name="default",
        max_runtime_seconds=1800,
        max_subagents=5,
        enable_sandbox=True,
        enable_network=False,
        created_at=utc_now(),
        updated_at=utc_now(),
    )
    db_session.add_all([task, other])
    db_session.flush()
    db_session.add_all(
        [
            AgentRun(task_id=task.id, agent_type="subagent", status="FAILED", context_json={}),
            ModelCall(
                task_id=task.id,
                model_provider="openai-compatible",
                model_name="default",
                status="SUCCESS",
                request_json={},
                response_json={},
            ),
            ToolCall(
                task_id=task.id,
                tool_name="read_file",
                status="SUCCESS",
                risk_level="low",
                requires_sandbox=False,
                input_json={},
                output_json={},
            ),
            SandboxInstance(
                task_id=task.id,
                container_id="container-1",
                image="agent-runtime:latest",
                status="IDLE",
                cpu_limit="1.0",
                memory_limit_mb=1024,
                network_enabled=False,
                warm_pool_reused=False,
            ),
        ]
    )
    EventStore(db_session).append(
        task_id=task.id,
        event_type=EventType.TASK_FAILED,
        payload_json={"summary": "boom"},
    )
    db_session.commit()

    client = TestClient(app)
    response = client.get("/api/observability/summary", headers=AUTH_HEADERS)

    assert response.status_code == 200
    payload = response.json()
    assert payload["task_total"] == 1
    assert payload["failed_task_total"] == 1
    assert payload["event_total"] == 1
    assert payload["model_call_total"] == 1
    assert payload["tool_call_total"] == 1
    assert payload["sandbox_total"] == 1
    assert payload["tasks_by_status"] == [{"name": "FAILED", "count": 1}]
    assert payload["subagents_by_status"] == [{"name": "FAILED", "count": 1}]
