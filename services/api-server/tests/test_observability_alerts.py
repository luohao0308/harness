from datetime import timedelta

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.db.models import AlertRule, SubagentOutput, Task, utc_now
from app.main import app
from app.observability.alert_evaluator import evaluate_alert_rules
from tests.conftest import AUTH_HEADERS


def _task(task_id: str = "alert-task-1") -> Task:
    return Task(
        id=task_id,
        organization_id="dev-org",
        agent_id="default",
        created_by="dev-engineer",
        title="Alert task",
        goal="Trigger alert",
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


def test_alert_rule_crud_validates_metric_and_clones_default_rule(db_session: Session) -> None:
    default_rule = AlertRule(
        id="default-budget-alert",
        organization_id=None,
        name="subagent_budget_exceeded_high",
        metric="subagent_budget_exceeded_count",
        comparator=">",
        threshold=3,
        window_seconds=300,
        enabled=True,
        severity="warning",
        notification_channels_json=["in_app"],
        created_at=utc_now(),
        updated_at=utc_now(),
    )
    db_session.add(default_rule)
    db_session.commit()
    client = TestClient(app)

    invalid = client.post(
        "/api/observability/alert-rules",
        headers=AUTH_HEADERS,
        json={
            "name": "bad",
            "metric": "raw_sql",
            "comparator": ">",
            "threshold": 1,
            "window_seconds": 300,
            "severity": "warning",
        },
    )
    assert invalid.status_code == 400

    created = client.post(
        "/api/observability/alert-rules",
        headers=AUTH_HEADERS,
        json={
            "name": "budget spike",
            "metric": "subagent_budget_exceeded_count",
            "comparator": ">",
            "threshold": 1,
            "window_seconds": 300,
            "severity": "warning",
            "notification_channels_json": ["in_app"],
        },
    )
    assert created.status_code == 201
    rule_id = created.json()["id"]

    patched_default = client.patch(
        "/api/observability/alert-rules/default-budget-alert",
        headers=AUTH_HEADERS,
        json={"enabled": False},
    )
    assert patched_default.status_code == 200
    assert patched_default.json()["organization_id"] == "dev-org"
    assert patched_default.json()["enabled"] is False

    deleted = client.delete(f"/api/observability/alert-rules/{rule_id}", headers=AUTH_HEADERS)
    assert deleted.status_code == 204


def test_alert_evaluator_writes_event_when_threshold_matches(db_session: Session) -> None:
    task = _task()
    rule = AlertRule(
        id="budget-rule",
        organization_id="dev-org",
        name="budget high",
        metric="subagent_budget_exceeded_count",
        comparator=">",
        threshold=0,
        window_seconds=300,
        enabled=True,
        severity="warning",
        notification_channels_json=["in_app"],
        created_at=utc_now(),
        updated_at=utc_now(),
    )
    output = SubagentOutput(
        agent_run_id="missing-agent-run-for-alert",
        task_id=task.id,
        specialist_id=None,
        output_json={},
        output_schema_sha256="b" * 64,
        budget_consumed_json={"cost_usd": "0.001"},
        budget_exceeded_json=["max_tokens"],
        written_at=utc_now(),
    )
    db_session.add_all([task, rule, output])
    db_session.commit()

    results = evaluate_alert_rules(session=db_session, organization_id="dev-org")
    db_session.commit()

    assert len(results) == 1
    assert results[0].triggered is True
    client = TestClient(app)
    events = client.get("/api/observability/alert-events", headers=AUTH_HEADERS)
    assert events.status_code == 200
    payload = events.json()
    assert payload["items"][0]["rule_id"] == "budget-rule"
    assert payload["items"][0]["observed_value"] == 1


def test_alert_evaluator_does_not_write_when_not_matching(db_session: Session) -> None:
    task = _task("alert-task-quiet")
    rule = AlertRule(
        id="quiet-budget-rule",
        organization_id="dev-org",
        name="budget quiet",
        metric="subagent_budget_exceeded_count",
        comparator=">",
        threshold=1,
        window_seconds=300,
        enabled=True,
        severity="warning",
        notification_channels_json=["in_app"],
        created_at=utc_now(),
        updated_at=utc_now(),
    )
    output = SubagentOutput(
        agent_run_id="missing-agent-run-for-alert-quiet",
        task_id=task.id,
        specialist_id=None,
        output_json={},
        output_schema_sha256="c" * 64,
        budget_consumed_json={},
        budget_exceeded_json=["max_tokens"],
        written_at=utc_now() - timedelta(seconds=600),
    )
    db_session.add_all([task, rule, output])
    db_session.commit()

    results = evaluate_alert_rules(session=db_session, organization_id="dev-org")
    db_session.commit()

    assert results[0].triggered is False
    client = TestClient(app)
    events = client.get("/api/observability/alert-events", headers=AUTH_HEADERS)
    assert events.status_code == 200
    assert events.json()["items"] == []
