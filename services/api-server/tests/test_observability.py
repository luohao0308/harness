import json
import logging
from datetime import datetime
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.observability import (
    _grafana_auth_headers,
    _loki_label_selector,
    _query_loki_logs,
    _tempo_trace_spans,
)
from app.core.config import Settings
from app.core.logging import JsonFormatter
from app.db.models import (
    AgentRun,
    ModelCall,
    ObservabilityExportRecord,
    SandboxInstance,
    Task,
    ToolCall,
    utc_now,
)
from app.events.event_store import EventStore
from app.events.event_types import EventType
from app.main import app
from tests.conftest import AUTH_HEADERS

ADMIN_HEADERS = {"Authorization": "Bearer dev-admin-token"}
OPERATOR_HEADERS = {"Authorization": "Bearer dev-operator-token"}


def test_metrics_endpoint_exposes_required_metrics() -> None:
    client = TestClient(app)

    response = client.get("/metrics")

    assert response.status_code == 200
    body = response.text
    assert "agent_tasks_total" in body
    assert "agent_subagents_running" in body
    assert "agent_subagent_recovery_total" in body
    assert "agent_subagent_recovery_sweeps_total" in body
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
    assert payload["subagent_queue"]["failed"] == 1
    assert payload["subagent_queue"]["active_total"] == 0
    assert payload["subagent_queue"]["capacity"] == 0


def test_observability_logs_returns_event_store_entries(db_session: Session) -> None:
    task = Task(
        organization_id="dev-org",
        created_by="dev-engineer",
        title="Logs",
        goal="Query logs",
        status="RUNNING",
        model_provider="openai-compatible",
        model_name="default",
        max_runtime_seconds=1800,
        max_subagents=5,
        enable_sandbox=True,
        enable_network=False,
        created_at=utc_now(),
        updated_at=utc_now(),
    )
    db_session.add(task)
    db_session.flush()
    EventStore(db_session).append(
        task_id=task.id,
        event_type=EventType.TASK_STARTED,
        payload_json={"summary": "started"},
        trace_id="trace-logs",
    )
    db_session.commit()

    response = TestClient(app).get(
        "/api/observability/logs",
        headers=AUTH_HEADERS,
        params={"task_id": task.id, "trace_id": "trace-logs"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["source"] == "event_store"
    assert payload["items"][0]["task_id"] == task.id
    assert payload["items"][0]["trace_id"] == "trace-logs"
    assert payload["items"][0]["event_type"] == "TASK_STARTED"


def test_observability_exports_require_operator_role() -> None:
    client = TestClient(app)

    engineer = client.get("/api/observability/exports", headers=AUTH_HEADERS)
    operator = client.get("/api/observability/exports", headers=OPERATOR_HEADERS)

    assert engineer.status_code == 403
    assert operator.status_code == 200
    assert {item["name"] for item in operator.json()["items"]} == {
        "logs_jsonl",
        "trace_json",
        "grafana_dashboards_json",
        "services_health_json",
    }


def test_export_observability_logs_returns_jsonl(db_session: Session) -> None:
    task = Task(
        organization_id="dev-org",
        created_by="dev-engineer",
        title="Export logs",
        goal="Export logs",
        status="RUNNING",
        model_provider="openai-compatible",
        model_name="default",
        max_runtime_seconds=1800,
        max_subagents=5,
        enable_sandbox=True,
        enable_network=False,
        created_at=utc_now(),
        updated_at=utc_now(),
    )
    db_session.add(task)
    db_session.flush()
    EventStore(db_session).append(
        task_id=task.id,
        event_type=EventType.TASK_STARTED,
        payload_json={"summary": "started"},
        trace_id="trace-export",
    )
    db_session.commit()

    response = TestClient(app).get(
        "/api/observability/exports/logs",
        headers=OPERATOR_HEADERS,
        params={"task_id": task.id, "trace_id": "trace-export"},
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/x-ndjson")
    assert response.headers["x-harness-export-count"] == "1"
    assert response.headers["x-harness-export-id"]
    payload = json.loads(response.text.strip())
    assert payload["task_id"] == task.id
    assert payload["trace_id"] == "trace-export"
    record = db_session.get(ObservabilityExportRecord, response.headers["x-harness-export-id"])
    assert record is not None
    assert record.export_type == "logs_jsonl"
    assert record.row_count == 1

    history = TestClient(app).get(
        "/api/observability/exports/history",
        headers=OPERATOR_HEADERS,
    )
    engineer_history = TestClient(app).get(
        "/api/observability/exports/history",
        headers=AUTH_HEADERS,
    )
    download = TestClient(app).get(
        f"/api/observability/exports/history/{record.id}/download",
        headers=OPERATOR_HEADERS,
    )

    assert history.status_code == 200
    assert history.json()["items"][0]["id"] == record.id
    assert history.json()["items"][0]["download_url"].endswith(f"{record.id}/download")
    assert engineer_history.status_code == 403
    assert download.status_code == 200
    assert download.text == response.text


def test_loki_label_selector_uses_filter_labels() -> None:
    selector = _loki_label_selector(
        service=None,
        task_id='task-"quoted"',
        trace_id="trace-logs",
        event_type="TASK_STARTED",
    )

    assert selector == (
        '{service="api-server",task_id="task-\\"quoted\\"",trace_id="trace-logs",'
        'event_type="TASK_STARTED"}'
    )


def test_loki_logs_query_uses_label_selector_and_created_at() -> None:
    payload = {
        "data": {
            "result": [
                {
                    "stream": {
                        "service": "api-server",
                        "task_id": "task-1",
                        "trace_id": "trace-1",
                        "event_type": "TASK_STARTED",
                    },
                    "values": [
                        [
                            "1",
                            json.dumps(
                                {
                                    "created_at": "2026-05-06T10:20:00+00:00",
                                    "level": "INFO",
                                    "service": "api-server",
                                    "message": "TASK_STARTED",
                                    "task_id": "task-1",
                                    "trace_id": "trace-1",
                                    "event_type": "TASK_STARTED",
                                }
                            ),
                        ]
                    ],
                }
            ]
        }
    }

    with patch("app.api.observability._get_json", return_value=payload) as get_json:
        entries = _query_loki_logs(
            task_id="task-1",
            trace_id="trace-1",
            service=None,
            event_type="TASK_STARTED",
            limit=20,
        )

    called_url = get_json.call_args.args[0]
    assert "%7Bservice%3D%22api-server%22%2Ctask_id%3D%22task-1%22" in called_url
    assert entries[0].source == "loki"
    assert entries[0].timestamp == datetime.fromisoformat("2026-05-06T10:20:00+00:00")


def test_observability_trace_returns_event_spans(db_session: Session) -> None:
    task = Task(
        organization_id="dev-org",
        created_by="dev-engineer",
        title="Trace",
        goal="Query trace",
        status="RUNNING",
        model_provider="openai-compatible",
        model_name="default",
        max_runtime_seconds=1800,
        max_subagents=5,
        enable_sandbox=True,
        enable_network=False,
        created_at=utc_now(),
        updated_at=utc_now(),
    )
    db_session.add(task)
    db_session.flush()
    EventStore(db_session).append(
        task_id=task.id,
        event_type=EventType.TASK_STARTED,
        payload_json={"summary": "started"},
        trace_id="trace-chain",
    )
    EventStore(db_session).append(
        task_id=task.id,
        event_type=EventType.TASK_COMPLETED,
        payload_json={"summary": "done"},
        trace_id="trace-chain",
    )
    db_session.commit()

    response = TestClient(app).get(
        "/api/observability/traces/trace-chain",
        headers=AUTH_HEADERS,
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["trace_id"] == "trace-chain"
    assert payload["source"] == "event_store"
    assert [span["name"] for span in payload["spans"]] == ["TASK_STARTED", "TASK_COMPLETED"]
    assert payload["spans"][1]["parent_span_id"] == "event-1"


def test_export_observability_trace_uses_operator_role(db_session: Session) -> None:
    task = Task(
        organization_id="dev-org",
        created_by="dev-engineer",
        title="Export trace",
        goal="Export trace",
        status="RUNNING",
        model_provider="openai-compatible",
        model_name="default",
        max_runtime_seconds=1800,
        max_subagents=5,
        enable_sandbox=True,
        enable_network=False,
        created_at=utc_now(),
        updated_at=utc_now(),
    )
    db_session.add(task)
    db_session.flush()
    EventStore(db_session).append(
        task_id=task.id,
        event_type=EventType.TASK_STARTED,
        payload_json={"summary": "started"},
        trace_id="trace-export-chain",
    )
    db_session.commit()

    client = TestClient(app)
    engineer = client.get(
        "/api/observability/exports/traces/trace-export-chain",
        headers=AUTH_HEADERS,
    )
    operator = client.get(
        "/api/observability/exports/traces/trace-export-chain",
        headers=OPERATOR_HEADERS,
    )

    assert engineer.status_code == 403
    assert operator.status_code == 200
    assert operator.headers["content-disposition"].startswith("attachment;")
    assert operator.json()["trace_id"] == "trace-export-chain"


def test_observability_trace_prefers_tempo_spans(db_session: Session) -> None:
    tempo_payload = {
        "batches": [
            {
                "resource": {
                    "attributes": [
                        {"key": "service.name", "value": {"stringValue": "api-server"}}
                    ]
                },
                "scopeSpans": [
                    {
                        "spans": [
                            {
                                "traceId": "otel-trace-1",
                                "spanId": "span-1",
                                "name": "GET /api/tasks",
                                "startTimeUnixNano": "1000000000",
                                "endTimeUnixNano": "1250000000",
                                "attributes": [
                                    {
                                        "key": "harness.trace_id",
                                        "value": {"stringValue": "trace-chain"},
                                    },
                                    {"key": "url.path", "value": {"stringValue": "/api/tasks"}},
                                ],
                            },
                            {
                                "traceId": "otel-trace-1",
                                "spanId": "span-2",
                                "name": "POST /api/tasks",
                                "startTimeUnixNano": "1300000000",
                                "endTimeUnixNano": "1500000000",
                                "attributes": [
                                    {
                                        "key": "harness.trace_id",
                                        "value": {"stringValue": "trace-chain"},
                                    },
                                    {
                                        "key": "url.path",
                                        "value": {"stringValue": "/api/tasks"},
                                    },
                                    {
                                        "key": "http.request.method",
                                        "value": {"stringValue": "POST"},
                                    },
                                ],
                            }
                        ]
                    }
                ],
            }
        ]
    }

    with patch("app.api.observability._get_json") as get_json:
        get_json.side_effect = [
            {"traces": [{"traceID": "otel-trace-1"}]},
            tempo_payload,
        ]
        response = TestClient(app).get(
            "/api/observability/traces/trace-chain",
            headers=AUTH_HEADERS,
            params={
                "attribute_key": "http.request.method",
                "attribute_value": "POST",
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["source"] == "tempo"
    assert payload["spans"][0]["trace_id"] == "trace-chain"
    assert payload["spans"][0]["span_id"] == "span-2"
    assert payload["spans"][0]["duration_ms"] == 200
    assert len(payload["spans"]) == 1


def test_tempo_trace_span_parser_handles_resource_spans() -> None:
    spans = _tempo_trace_spans(
        requested_trace_id="trace-parser",
        payload={
            "resourceSpans": [
                {
                    "resource": {
                        "attributes": [
                            {"key": "service.name", "value": {"stringValue": "api-server"}}
                        ]
                    },
                    "scopeSpans": [
                        {
                            "spans": [
                                {
                                    "traceId": "otel-trace-2",
                                    "spanId": "span-2",
                                    "parentSpanId": "span-1",
                                    "name": "POST /api/tasks",
                                    "startTimeUnixNano": "2000000000",
                                    "endTimeUnixNano": "3000000000",
                                    "attributes": [],
                                }
                            ]
                        }
                    ],
                }
            ]
        },
    )

    assert spans[0].service == "api-server"
    assert spans[0].parent_span_id == "span-1"
    assert spans[0].duration_ms == 1000


def test_grafana_dashboards_returns_configured_fallback() -> None:
    response = TestClient(app).get(
        "/api/observability/grafana/dashboards",
        headers=OPERATOR_HEADERS,
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["items"][0]["uid"] == "agent-harness"
    assert payload["items"][0]["source"] in {"configured", "grafana"}


def test_grafana_dashboards_require_operator_role() -> None:
    client = TestClient(app)

    engineer = client.get("/api/observability/grafana/dashboards", headers=AUTH_HEADERS)
    admin = client.get("/api/observability/grafana/dashboards", headers=ADMIN_HEADERS)

    assert engineer.status_code == 403
    assert admin.status_code == 200


def test_grafana_auth_headers_use_basic_auth_settings() -> None:
    settings = Settings(GRAFANA_USERNAME="viewer", GRAFANA_PASSWORD="secret")

    assert _grafana_auth_headers(settings) == {"Authorization": "Basic dmlld2VyOnNlY3JldA=="}


def test_observability_services_health_returns_all_services() -> None:
    response = TestClient(app).get(
        "/api/observability/services/health",
        headers=OPERATOR_HEADERS,
    )

    assert response.status_code == 200
    payload = response.json()
    assert {service["name"] for service in payload["services"]} == {
        "prometheus",
        "grafana",
        "loki",
        "otel-collector",
        "tempo",
    }


def test_observability_services_health_requires_operator_role() -> None:
    response = TestClient(app).get("/api/observability/services/health", headers=AUTH_HEADERS)

    assert response.status_code == 403
