from datetime import timedelta

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import OtelSpan, Task, utc_now
from app.main import app
from app.observability.tracing import OTEL_SPAN_RETENTION_DAYS, persist_span, traced_operation
from tests.conftest import AUTH_HEADERS


def test_local_trace_list_and_detail_reconstruct_span_tree(db_session: Session) -> None:
    task = Task(
        id="trace-task-1",
        organization_id="dev-org",
        agent_id="default",
        created_by="dev-engineer",
        title="Trace local spans",
        goal="See spans",
        status="COMPLETED",
        model_provider="deepseek-flash",
        model_name="deepseek-v4-flash",
        max_runtime_seconds=1800,
        max_subagents=5,
        enable_sandbox=True,
        enable_network=False,
        created_at=utc_now(),
        updated_at=utc_now(),
    )
    other_task = Task(
        id="trace-task-other",
        organization_id="other-org",
        agent_id="default",
        created_by="other",
        title="Other",
        goal="Other",
        status="COMPLETED",
        model_provider="deepseek-flash",
        model_name="deepseek-v4-flash",
        max_runtime_seconds=1800,
        max_subagents=5,
        enable_sandbox=True,
        enable_network=False,
        created_at=utc_now(),
        updated_at=utc_now(),
    )
    db_session.add_all([task, other_task])
    db_session.flush()
    start = utc_now()
    persist_span(
        session=db_session,
        organization_id="dev-org",
        trace_id="trace-local-1",
        span_id="root",
        parent_span_id=None,
        name="POST /api/agents/default/runs",
        kind="server",
        start_time=start,
        end_time=start + timedelta(milliseconds=80),
        duration_ms=80,
        attributes={"service.name": "api-server", "task_id": task.id},
        status="OK",
        task_id=task.id,
    )
    persist_span(
        session=db_session,
        organization_id="dev-org",
        trace_id="trace-local-1",
        span_id="child",
        parent_span_id="root",
        name="model_call",
        kind="client",
        start_time=start + timedelta(milliseconds=10),
        end_time=start + timedelta(milliseconds=70),
        duration_ms=60,
        attributes={"service.name": "model-gateway", "model_name": "deepseek"},
        status="OK",
        task_id=task.id,
    )
    persist_span(
        session=db_session,
        organization_id="other-org",
        trace_id="trace-other",
        span_id="other",
        parent_span_id=None,
        name="hidden",
        kind="server",
        start_time=start,
        end_time=start,
        duration_ms=0,
        attributes={},
        status="OK",
        task_id=other_task.id,
    )
    db_session.commit()
    client = TestClient(app)

    listed = client.get("/api/observability/traces", headers=AUTH_HEADERS)
    assert listed.status_code == 200
    trace_ids = [item["trace_id"] for item in listed.json()["items"]]
    assert "trace-local-1" in trace_ids
    assert "trace-other" not in trace_ids

    detail = client.get("/api/observability/traces/trace-local-1", headers=AUTH_HEADERS)
    assert detail.status_code == 200
    payload = detail.json()
    assert payload["source"] == "local_otel"
    assert [span["span_id"] for span in payload["spans"]] == ["root", "child"]
    assert payload["spans"][1]["parent_span_id"] == "root"
    assert all(span["task_id"] != other_task.id for span in payload["spans"])
    assert payload["service_nodes"][0]["service"] == "api-server"
    assert payload["service_edges"][0]["source"] == "api-server"
    assert payload["service_edges"][0]["target"] == "model-gateway"


def test_span_persistence_prunes_older_than_retention(db_session: Session) -> None:
    task = Task(
        id="trace-retention-task",
        organization_id="dev-org",
        agent_id="default",
        created_by="dev-engineer",
        title="Retention",
        goal="Prune old spans",
        status="COMPLETED",
        model_provider="deepseek-flash",
        model_name="deepseek-v4-flash",
        max_runtime_seconds=1800,
        max_subagents=5,
        enable_sandbox=True,
        enable_network=False,
        created_at=utc_now(),
        updated_at=utc_now(),
    )
    db_session.add(task)
    db_session.flush()
    old = utc_now() - timedelta(days=OTEL_SPAN_RETENTION_DAYS + 1)
    db_session.add(
        OtelSpan(
            organization_id="dev-org",
            trace_id="old-trace",
            span_id="old-span",
            parent_span_id=None,
            name="old",
            kind="internal",
            start_time=old,
            end_time=old,
            duration_ms=0,
            attributes_json={},
            status="OK",
            task_id=task.id,
            created_at=old,
        )
    )
    db_session.flush()
    now = utc_now()
    persist_span(
        session=db_session,
        organization_id="dev-org",
        trace_id="new-trace",
        span_id="new-span",
        parent_span_id=None,
        name="new",
        kind="internal",
        start_time=now,
        end_time=now,
        duration_ms=0,
        attributes={},
        status="OK",
        task_id=task.id,
    )
    db_session.commit()

    old_span = db_session.execute(
        select(OtelSpan).where(OtelSpan.trace_id == "old-trace")
    ).scalar_one_or_none()
    new_span = db_session.execute(
        select(OtelSpan).where(OtelSpan.trace_id == "new-trace")
    ).scalar_one_or_none()
    assert old_span is None
    assert new_span is not None


def test_traced_operation_links_nested_parent_span(db_session: Session) -> None:
    task = Task(
        id="trace-nested-task",
        organization_id="dev-org",
        agent_id="default",
        created_by="dev-engineer",
        title="Nested trace",
        goal="Keep parent links",
        status="COMPLETED",
        model_provider="deepseek-flash",
        model_name="deepseek-v4-flash",
        max_runtime_seconds=1800,
        max_subagents=5,
        enable_sandbox=True,
        enable_network=False,
        created_at=utc_now(),
        updated_at=utc_now(),
    )
    db_session.add(task)
    db_session.flush()

    with traced_operation(db_session, "outer", task_id=task.id):
        with traced_operation(db_session, "inner", task_id=task.id):
            pass
    db_session.flush()

    spans = {
        span.name: span
        for span in db_session.execute(
            select(OtelSpan).where(OtelSpan.trace_id == task.id)
        ).scalars()
    }
    assert spans["inner"].parent_span_id == spans["outer"].span_id


def test_local_trace_detail_does_not_leak_same_trace_id_across_orgs(
    db_session: Session,
) -> None:
    now = utc_now()
    task = Task(
        id="trace-shared-dev",
        organization_id="dev-org",
        agent_id="default",
        created_by="dev-engineer",
        title="Shared trace dev",
        goal="Keep tenant local",
        status="COMPLETED",
        model_provider="deepseek-flash",
        model_name="deepseek-v4-flash",
        max_runtime_seconds=1800,
        max_subagents=5,
        enable_sandbox=True,
        enable_network=False,
        created_at=now,
        updated_at=now,
    )
    other_task = Task(
        id="trace-shared-other",
        organization_id="other-org",
        agent_id="default",
        created_by="other",
        title="Shared trace other",
        goal="Hidden",
        status="COMPLETED",
        model_provider="deepseek-flash",
        model_name="deepseek-v4-flash",
        max_runtime_seconds=1800,
        max_subagents=5,
        enable_sandbox=True,
        enable_network=False,
        created_at=now,
        updated_at=now,
    )
    db_session.add_all([task, other_task])
    db_session.flush()
    persist_span(
        session=db_session,
        organization_id="dev-org",
        trace_id="shared-trace",
        span_id="dev-span",
        parent_span_id=None,
        name="visible",
        kind="server",
        start_time=now,
        end_time=now,
        duration_ms=1,
        attributes={"service.name": "api-server"},
        status="OK",
        task_id=task.id,
    )
    persist_span(
        session=db_session,
        organization_id="other-org",
        trace_id="shared-trace",
        span_id="other-span",
        parent_span_id=None,
        name="hidden",
        kind="server",
        start_time=now,
        end_time=now,
        duration_ms=1,
        attributes={"service.name": "api-server"},
        status="OK",
        task_id=other_task.id,
    )
    db_session.commit()

    client = TestClient(app)
    detail = client.get("/api/observability/traces/shared-trace", headers=AUTH_HEADERS)
    assert detail.status_code == 200
    payload = detail.json()
    assert [span["span_id"] for span in payload["spans"]] == ["dev-span"]

    listed = client.get("/api/observability/traces", headers=AUTH_HEADERS)
    assert listed.status_code == 200
    item = next(row for row in listed.json()["items"] if row["trace_id"] == "shared-trace")
    assert item["span_count"] == 1
