import json
import logging

from fastapi.testclient import TestClient

from app.core.logging import JsonFormatter
from app.main import app


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
        headers={"x-trace-id": "trace-from-test"},
        json={
            "title": "Trace demo",
            "goal": "Verify trace propagation",
            "model_provider": "openai-compatible",
            "model_name": "default",
        },
    )
    task_id = created.json()["id"]

    events = client.get(f"/api/tasks/{task_id}/events").json()["items"]

    assert created.headers["x-trace-id"] == "trace-from-test"
    assert events[0]["trace_id"] == "trace-from-test"
