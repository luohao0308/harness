import json
import logging
from datetime import datetime
from pathlib import Path
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
    AgentAssignment,
    AgentRun,
    ContextAssemblyManifest,
    EvalCase,
    EvalDataset,
    EvalResult,
    EvalRun,
    ModelCall,
    ObservabilityExportRecord,
    SandboxInstance,
    Task,
    ToolCall,
    WorkspaceContextCache,
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
    assert "agent_assignments_total" in body
    assert "agent_assignments_running" in body
    assert "agent_assignment_duration_seconds" in body
    assert "agent_handoffs_total" in body
    assert "agent_parallel_branches_running" in body
    assert "agent_reduce_duration_seconds" in body
    assert "sandbox_containers_total" in body
    assert "warm_pool_hit_total" in body
    assert "model_calls_total" in body
    assert "model_fallback_total" in body
    assert "sandbox_running_memory_limit_mb_total" in body
    assert "sandbox_running_cpu_limit_total" in body


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
            AgentAssignment(
                run_id=task.id,
                agent_id="reviewer",
                role="reviewer",
                status="QUEUED",
                input_json={},
                output_json={},
            ),
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
    assert payload["agent_assignments_by_status"] == [{"name": "QUEUED", "count": 1}]
    assert payload["subagent_queue"]["failed"] == 1
    assert payload["subagent_queue"]["active_total"] == 0
    assert payload["subagent_queue"]["capacity"] == 0
    assert payload["assignment_queue"]["queued"] == 1
    assert payload["assignment_queue"]["active_total"] == 1


def test_grounding_quality_projects_eval_owned_trace_without_forbidden_snippets(
    db_session: Session,
) -> None:
    dataset = EvalDataset(
        organization_id="dev-org",
        name="P6 Grounding Quality",
        description="Projection source",
        status="ACTIVE",
        created_by="dev-engineer",
    )
    other_dataset = EvalDataset(
        organization_id="other-org",
        name="Other",
        description="Out of scope",
        status="ACTIVE",
        created_by="other",
    )
    db_session.add_all([dataset, other_dataset])
    db_session.flush()
    eval_case = EvalCase(
        dataset_id=dataset.id,
        source_task_id=None,
        input_json={},
        expected_json={},
        tags_json=["p6"],
    )
    eval_run = EvalRun(
        dataset_id=dataset.id,
        organization_id="dev-org",
        agent_id="default",
        status="COMPLETED",
        metrics_json={"grounding_pass_rate": 0, "forbidden_evidence_leak_rate": 1},
        created_by="dev-engineer",
        started_at=utc_now(),
        completed_at=utc_now(),
    )
    other_run = EvalRun(
        dataset_id=other_dataset.id,
        organization_id="other-org",
        agent_id="default",
        status="COMPLETED",
        metrics_json={},
        created_by="other",
        started_at=utc_now(),
        completed_at=utc_now(),
    )
    db_session.add_all([eval_case, eval_run, other_run])
    db_session.flush()
    db_session.add_all(
        [
            EvalResult(
                eval_run_id=eval_run.id,
                eval_case_id=eval_case.id,
                task_id=None,
                status="FAILED",
                scores_json={"task_success": 0},
                grader_trace_json={
                    "grader_trace_schema_version": 1,
                    "passed": False,
                    "grounding_failures": ["forbidden_evidence_leaked"],
                    "forbidden_evidence_leaked": True,
                    "forbidden_leak_sources": ["prompt_manifest"],
                    "forbidden_evidence_snippets": ["do-not-render-this"],
                    "fallback_expected": True,
                    "fallback_observed": False,
                    "citation_keys": ["c1"],
                    "citation_hit_ids": ["h1"],
                },
                latency_ms=0,
                cost_usd="0",
            ),
            EvalResult(
                eval_run_id=other_run.id,
                eval_case_id=eval_case.id,
                task_id=None,
                status="PASSED",
                scores_json={"task_success": 1},
                grader_trace_json={"passed": True},
                latency_ms=0,
                cost_usd="0",
            ),
            EvalResult(
                eval_run_id=eval_run.id,
                eval_case_id=eval_case.id,
                task_id=None,
                status="PASSED",
                scores_json={"task_success": 1},
                grader_trace_json={
                    "grader_trace_schema_version": 1,
                    "passed": True,
                    "grounding_failures": [],
                    "forbidden_evidence_leaked": False,
                },
                latency_ms=0,
                cost_usd="0",
            ),
        ]
    )
    db_session.commit()

    client = TestClient(app)
    response = client.get(
        "/api/observability/grounding-quality?forbidden_evidence_leaked=true&limit=1",
        headers=AUTH_HEADERS,
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    item = payload["items"][0]
    assert item["eval_run_id"] == eval_run.id
    assert item["forbidden_evidence_leaked"] is True
    assert item["forbidden_leak_sources"] == ["prompt_manifest"]
    assert "forbidden_evidence_snippets" not in item
    assert "do-not-render-this" not in response.text
    assert payload["metrics"]["citation_coverage_rate"] == 1.0
    assert payload["metrics"]["fallback_mismatch_rate"] == 1.0
    assert payload["failure_facets"] == [{"name": "forbidden_evidence_leaked", "count": 1}]

    short_eval_run_response = client.get(
        (
            "/api/observability/grounding-quality"
            f"?eval_run_id={eval_run.id[:8]}&failure_type=forbidden&limit=10"
        ),
        headers=AUTH_HEADERS,
    )
    assert short_eval_run_response.status_code == 200
    short_eval_run_payload = short_eval_run_response.json()
    assert short_eval_run_payload["total"] == 1
    assert short_eval_run_payload["items"][0]["eval_run_id"] == eval_run.id

    short_dataset_response = client.get(
        (
            "/api/observability/grounding-quality"
            f"?dataset_id={dataset.id[:8]}&failure_type=evidence_leaked&limit=10"
        ),
        headers=AUTH_HEADERS,
    )
    assert short_dataset_response.status_code == 200
    short_dataset_payload = short_dataset_response.json()
    assert short_dataset_payload["total"] == 1
    assert short_dataset_payload["items"][0]["dataset_id"] == dataset.id


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
    assert payload["facets"]["event_type"] == [{"name": "TASK_STARTED", "count": 1}]
    assert payload["facets"]["service"] == [{"name": "api-server", "count": 1}]


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
    assert payload["service_nodes"] == [
        {
            "service": "api-server",
            "span_count": 2,
            "error_count": 0,
            "total_duration_ms": 0,
        }
    ]
    assert payload["service_edges"] == [
        {
            "source": "api-server",
            "target": "api-server",
            "span_count": 1,
            "total_duration_ms": 0,
        }
    ]


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
                    "attributes": [{"key": "service.name", "value": {"stringValue": "api-server"}}]
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
                            },
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
    assert payload["service_nodes"][0]["service"] == "api-server"
    assert payload["service_nodes"][0]["span_count"] == 1
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


def test_grafana_dashboard_json_covers_enterprise_operating_metrics() -> None:
    dashboard_path = Path(__file__).resolve().parents[3] / (
        "deploy/monitoring/grafana-dashboard-agent-harness.json"
    )
    dashboard = json.loads(dashboard_path.read_text(encoding="utf-8"))
    panels = dashboard["panels"]
    titles = {panel["title"] for panel in panels}
    expressions = {
        target["expr"]
        for panel in panels
        for target in panel.get("targets", [])
        if "expr" in target
    }

    assert {
        "Subagent Recovery",
        "Model Fallback",
        "Sandbox Quota",
        "Replay & Recovery",
        "API Logs",
    }.issubset(titles)
    assert "model_fallback_total" in expressions
    assert "sandbox_running_memory_limit_mb_total" in expressions
    assert "agent_subagent_recovery_sweeps_total" in expressions


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
    assert {service["alert_status"] for service in payload["services"]}.issubset({"ok", "firing"})
    assert all(service["runbook_url"].endswith("#observability") for service in payload["services"])


def test_observability_services_health_requires_operator_role() -> None:
    response = TestClient(app).get("/api/observability/services/health", headers=AUTH_HEADERS)

    assert response.status_code == 403


def test_observability_summary_projects_token_optimization_evidence(
    db_session: Session,
) -> None:
    task = Task(
        organization_id="dev-org",
        created_by="dev-engineer",
        title="Token evidence",
        goal="Record optimization",
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
    db_session.add(task)
    db_session.flush()
    db_session.add(
        ContextAssemblyManifest(
            organization_id="dev-org",
            agent_id="default",
            run_id=task.id,
            mode="authoritative",
            token_budget_json={
                "pruning_applied": True,
                    "optimized_vs_baseline": {"estimated_saved_tokens": 44},
                    "retrieval_cache": {"hit_count": 3, "miss_count": 1},
                    "context_cache": {
                        "hit_count": 3,
                        "miss_count": 1,
                        "stale_count": 1,
                        "sources": [
                            {
                                "cache_source": "compression_summary",
                                "label": "摘要缓存",
                                "hit_count": 2,
                                "miss_count": 1,
                                "stale_count": 0,
                                "estimated_saved_tokens": 20,
                            },
                            {
                                "cache_source": "rag_retrieval",
                                "label": "RAG 检索",
                                "hit_count": 1,
                                "miss_count": 0,
                                "stale_count": 1,
                                "estimated_saved_tokens": 24,
                            },
                        ],
                    },
                },
            sections_json=[],
            included_refs_json=[],
            omitted_refs_json=[],
            policy_decisions_json=[],
            tombstoned_refs_json=[],
            context_text_sha256="empty",
            metadata_json={},
            created_at=utc_now(),
        )
    )
    db_session.add(
        ModelCall(
            task_id=task.id,
            model_provider="openai-compatible",
            model_name="cheap-model",
            status="SUCCESS",
            prompt_tokens=20,
            completion_tokens=5,
            request_json={"low_cost_route": True},
            response_json={},
            created_at=utc_now(),
        )
    )
    db_session.commit()

    response = TestClient(app).get("/api/observability/summary", headers=AUTH_HEADERS)

    assert response.status_code == 200
    token_optimization = response.json()["token_optimization"]
    assert token_optimization["actual_total_tokens"] == 25
    assert token_optimization["estimated_saved_tokens"] == 44
    assert token_optimization["pruning_manifest_count"] == 1
    assert token_optimization["retrieval_cache_hit_count"] == 3
    assert token_optimization["retrieval_cache_miss_count"] == 1
    assert token_optimization["retrieval_cache_stale_count"] == 1
    assert token_optimization["cache_sources"][0]["cache_source"] == "compression_summary"
    assert token_optimization["low_cost_route_count"] == 1


def test_token_savings_page_projects_recent_run_evidence(db_session: Session) -> None:
    task = Task(
        organization_id="dev-org",
        agent_id="default",
        created_by="dev-engineer",
        title="Balanced optimizer run",
        goal="Show saved tokens",
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
    other = Task(
        organization_id="other-org",
        agent_id="default",
        created_by="other",
        title="Other optimizer run",
        goal="Should not leak",
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
            ContextAssemblyManifest(
                id="manifest-token-savings",
                organization_id="dev-org",
                agent_id="default",
                run_id=task.id,
                mode="authoritative",
                token_budget_json={
                    "pruning_applied": True,
                    "estimated_candidate_tokens": 1000,
                    "estimated_included_tokens": 600,
                    "estimated_omitted_tokens": 400,
                    "optimized_vs_baseline": {
                        "estimated_saved_tokens": 400,
                        "estimated_savings_percent": 40,
                    },
                    "retrieval_cache": {"hit_count": 2, "miss_count": 1},
                    "context_cache": {
                        "hit_count": 2,
                        "miss_count": 1,
                        "stale_count": 0,
                        "sources": [
                            {
                                "cache_source": "compression_summary",
                                "label": "摘要缓存",
                                "hit_count": 1,
                                "miss_count": 1,
                                "stale_count": 0,
                                "estimated_saved_tokens": 80,
                            },
                            {
                                "cache_source": "long_term_memory",
                                "label": "长期记忆",
                                "hit_count": 1,
                                "miss_count": 0,
                                "stale_count": 0,
                                "estimated_saved_tokens": 24,
                            },
                        ],
                    },
                    "optimizer_capability_version_ids": ["balanced-version-1"],
                    "optimizer_policy_hash": "policy-hash",
                    "optimizer_decisions": [
                        {
                            "decision": "optimizer_applied",
                            "package_name": "builtin-token-optimizer-balanced",
                        }
                    ],
                },
                sections_json=[],
                included_refs_json=[{"section_id": "recent-1"}],
                omitted_refs_json=[
                    {
                        "section_id": "rag-1",
                        "omission_reason": "optimizer_budget",
                    },
                    {
                        "section_id": "memory-1",
                        "omission_reason": "optimizer_section_limit",
                    },
                    {
                        "section_id": "memory-2",
                        "omission_reason": "optimizer_section_limit",
                    },
                ],
                policy_decisions_json=[],
                tombstoned_refs_json=[],
                context_text_sha256="empty",
                metadata_json={},
                created_at=utc_now(),
            ),
            ContextAssemblyManifest(
                organization_id="other-org",
                agent_id="default",
                run_id=other.id,
                mode="authoritative",
                token_budget_json={
                    "optimized_vs_baseline": {"estimated_saved_tokens": 9000}
                },
                sections_json=[],
                included_refs_json=[],
                omitted_refs_json=[],
                policy_decisions_json=[],
                tombstoned_refs_json=[],
                context_text_sha256="empty",
                metadata_json={},
                created_at=utc_now(),
            ),
        ]
    )
    db_session.add_all(
        [
            ModelCall(
                id="call-token-savings",
                task_id=task.id,
                model_provider="openai-compatible",
                model_name="cheap-model",
                status="SUCCESS",
                prompt_tokens=550,
                completion_tokens=50,
                request_json={"low_cost_routing_reason": "balanced summarization under budget"},
                response_json={},
                created_at=utc_now(),
            ),
            ModelCall(
                task_id=other.id,
                model_provider="openai-compatible",
                model_name="default",
                status="SUCCESS",
                prompt_tokens=9000,
                completion_tokens=1,
                request_json={},
                response_json={},
                created_at=utc_now(),
            ),
        ]
    )
    db_session.add(
        WorkspaceContextCache(
            organization_id="dev-org",
            agent_id="default",
            cache_source="compression_summary",
            cache_key_hash="summary-cache-hit",
            schema_version="workspace-context-cache-v1",
            status="active",
            payload_json={},
            metadata_json={"reason": "compression_summary_accepted"},
            hit_count=3,
            miss_count=1,
            stale_count=0,
            estimated_saved_tokens=96,
            created_at=utc_now(),
            updated_at=utc_now(),
        )
    )
    db_session.commit()

    response = TestClient(app).get("/api/observability/token-savings", headers=AUTH_HEADERS)

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["estimated_saved_tokens"] == 400
    assert payload["summary"]["estimated_savings_percent"] == 40
    assert payload["summary"]["actual_total_tokens"] == 600
    assert payload["summary"]["optimizer_labels"] == ["均衡"]
    assert payload["summary"]["retrieval_cache_hit_count"] == 5
    assert payload["summary"]["retrieval_cache_miss_count"] == 2
    assert [item["cache_source"] for item in payload["summary"]["cache_sources"][:3]] == [
        "compression_summary",
        "rag_retrieval",
        "long_term_memory",
    ]
    summary_cache = payload["summary"]["cache_sources"][0]
    assert summary_cache["hit_count"] == 4
    assert summary_cache["miss_count"] == 2
    assert summary_cache["hit_rate"] == 66.67
    assert len(payload["runs"]) == 1
    run = payload["runs"][0]
    assert run["run_id"] == task.id
    assert run["context_manifest_id"] == "manifest-token-savings"
    assert run["estimated_saved_tokens"] == 400
    assert run["actual_prompt_tokens"] == 550
    assert run["optimizer_labels"] == ["均衡"]
    assert run["optimizer_decision_count"] == 1
    assert run["cache_sources"][0]["cache_source"] == "compression_summary"
    assert run["cache_sources"][0]["hit_rate"] == 50
    assert [item["cache_source"] for item in run["cache_sources"]] == [
        "compression_summary",
        "rag_retrieval",
        "long_term_memory",
    ]
    assert run["low_cost_routes"] == [
        {
            "model_call_id": "call-token-savings",
            "model_name": "cheap-model",
            "reason": "balanced summarization under budget",
        }
    ]
    assert run["omission_reasons"] == [
        {"reason": "optimizer_section_limit", "count": 2},
        {"reason": "optimizer_budget", "count": 1},
    ]
