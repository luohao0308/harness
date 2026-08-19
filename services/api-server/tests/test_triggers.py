import json
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.executor import Executor
from app.agents.schemas import StepResult
from app.api.schemas import AgentTriggerCreateRequest
from app.api.triggers import _validated_runtime_config
from app.core.config import get_settings
from app.db.models import AgentEvent, RuntimeJob, Task, Trigger, TriggerInvocation, utc_now
from app.events.event_types import EventType
from app.local_runtime.workspace_authorization import WORKSPACE_AUTHORIZATION_STORE
from app.main import app
from app.triggers import service as trigger_service
from app.workers.trigger_dispatch_worker import TRIGGER_DISPATCH_JOB_KIND

AUTH_HEADERS = {"Authorization": "Bearer dev-engineer-token"}
ADMIN_AUTH_HEADERS = {"Authorization": "Bearer dev-admin-token"}
TEST_WORKSPACE_SIGNING_SECRET = "test-workspace-signing-secret-at-least-32-characters"


def _workspace_authorization(root: Path) -> str:
    token, _expires_at = WORKSPACE_AUTHORIZATION_STORE.issue(
        signing_secret=TEST_WORKSPACE_SIGNING_SECRET,
        user_id="dev-engineer",
        organization_id="dev-org",
        profile_id="test-profile",
        root_path=root.resolve(),
        label=root.name,
        ttl_seconds=300,
    )
    return token


def test_trigger_crud_flow(db_session: Session) -> None:
    client = TestClient(app)

    created = client.post(
        "/api/agents/default/triggers",
        headers=AUTH_HEADERS,
        json={"endpoint_path": "release-check", "enabled": True},
    )

    assert created.status_code == 201
    body = created.json()
    assert body["secret"].startswith("htrg_")
    assert body["trigger"]["endpoint_path"] == "release-check"
    assert body["trigger"]["enabled"] is True
    assert body["trigger"]["type"] == "webhook"
    assert "secret_hash" not in body["trigger"]

    trigger_id = body["trigger"]["id"]
    assert db_session.execute(select(Trigger)).scalar_one().secret_hash != body["secret"]

    listed = client.get("/api/agents/default/triggers", headers=AUTH_HEADERS)
    assert listed.status_code == 200
    assert [item["id"] for item in listed.json()["items"]] == [trigger_id]
    assert "secret" not in listed.json()["items"][0]

    updated = client.patch(
        f"/api/agents/default/triggers/{trigger_id}",
        headers=AUTH_HEADERS,
        json={"enabled": False},
    )
    assert updated.status_code == 200
    assert updated.json()["enabled"] is False

    deleted = client.delete(
        f"/api/agents/default/triggers/{trigger_id}",
        headers=ADMIN_AUTH_HEADERS,
    )
    assert deleted.status_code == 204
    assert client.get("/api/agents/default/triggers", headers=AUTH_HEADERS).json()["items"] == []
    deleted_trigger = db_session.get(Trigger, trigger_id)
    assert deleted_trigger is not None
    assert deleted_trigger.deleted_at is not None
    assert deleted_trigger.enabled is False


def test_non_webhook_trigger_types_use_validated_config_without_secret(
    db_session: Session,
    monkeypatch,
) -> None:
    client = TestClient(app)
    config = {"interval_seconds": 60}
    monkeypatch.setattr(
        "app.api.triggers.get_settings",
        lambda: type(
            "LocalSettings",
            (),
            {
                "runtime_profile": "local",
                "local_desktop_bootstrap_token": TEST_WORKSPACE_SIGNING_SECRET,
            },
        )(),
    )
    response = client.post(
        "/api/agents/default/triggers",
        headers=AUTH_HEADERS,
        json={"type": "schedule", "name": "schedule trigger", "config_json": config},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["secret"] is None
    assert body["trigger"]["endpoint_path"] is None
    assert body["trigger"]["config_json"] == config
    trigger = db_session.get(Trigger, body["trigger"]["id"])
    assert trigger is not None
    trigger.runtime_state_json = {"next_run_at": 999}
    db_session.commit()
    updated = client.patch(
        f"/api/agents/default/triggers/{body['trigger']['id']}",
        headers=AUTH_HEADERS,
        json={"name": "updated schedule", "config_json": {"interval_seconds": 120}},
    )
    assert updated.status_code == 200
    assert updated.json()["name"] == "updated schedule"
    assert updated.json()["config_json"] == {"interval_seconds": 120}
    assert "runtime_state_json" not in updated.json()

    AgentTriggerCreateRequest.model_validate(
        {
            "type": "file",
            "config_json": {"workspace_root": "/tmp/workspace", "pattern": "**/*.md"},
        }
    )
    AgentTriggerCreateRequest.model_validate(
        {
            "type": "git",
            "config_json": {"repo_root": "/tmp/repository", "branch": "main"},
        }
    )
    AgentTriggerCreateRequest.model_validate(
        {
            "type": "git",
            "config_json": {
                "workspace_root": "/tmp/workspace",
                "repo_root": ".",
                "branch": "main",
            },
        }
    )
    local_only = client.post(
        "/api/agents/default/triggers",
        headers=AUTH_HEADERS,
        json={"type": "file", "config_json": {"workspace_root": "/tmp/workspace"}},
    )
    assert local_only.status_code == 403


def test_trigger_type_config_rejects_unknown_or_invalid_fields() -> None:
    client = TestClient(app)

    unknown = client.post(
        "/api/agents/default/triggers",
        headers=AUTH_HEADERS,
        json={"type": "webhook", "config_json": {"command": "rm -rf /"}},
    )
    too_fast = client.post(
        "/api/agents/default/triggers",
        headers=AUTH_HEADERS,
        json={"type": "schedule", "config_json": {"interval_seconds": 1}},
    )

    assert unknown.status_code == 422
    assert too_fast.status_code == 422

    for field_name, value in (("goal", "g" * 4097), ("title", "t" * 257)):
        oversized_text = client.post(
            "/api/agents/default/triggers",
            headers=AUTH_HEADERS,
            json={"type": "webhook", "config_json": {field_name: value}},
        )
        assert oversized_text.status_code == 422

    schedule_on_server = client.post(
        "/api/agents/default/triggers",
        headers=AUTH_HEADERS,
        json={"type": "schedule", "config_json": {"interval_seconds": 60}},
    )
    assert schedule_on_server.status_code == 422

    normalized = AgentTriggerCreateRequest.model_validate(
        {
            "type": "file",
            "config_json": {"workspace_root": "/tmp/workspace", "pattern": "src\\**\\*.py"},
        }
    )
    assert normalized.config_json["pattern"] == "src/**/*.py"
    for unsafe_pattern in ("..\\secret", "src/\x00secret"):
        with pytest.raises(ValueError):
            AgentTriggerCreateRequest.model_validate(
                {
                    "type": "file",
                    "config_json": {
                        "workspace_root": "/tmp/workspace",
                        "pattern": unsafe_pattern,
                    },
                }
            )


def test_local_source_config_resolves_existing_roots_and_rejects_invalid_paths(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    repo = workspace / "repo"
    repo.mkdir()
    subprocess.run(
        ["git", "init", "-q", str(repo)],
        check=True,
        shell=False,
        timeout=5,
    )

    file_config = _validated_runtime_config(
        AgentTriggerCreateRequest(
            type="file",
            config_json={"workspace_root": str(workspace), "max_bytes": 1024},
        )
    )
    git_config = _validated_runtime_config(
        AgentTriggerCreateRequest(
            type="git",
            config_json={"workspace_root": str(workspace), "repo_root": "repo"},
        )
    )
    direct_git_config = _validated_runtime_config(
        AgentTriggerCreateRequest(
            type="git",
            config_json={"repo_root": str(repo)},
        )
    )

    assert file_config["workspace_root"] == str(workspace.resolve())
    assert file_config["max_file_bytes"] == 1024
    assert "max_bytes" not in file_config
    assert git_config["repo_root"] == str(repo.resolve())
    assert direct_git_config["repo_root"] == str(repo.resolve())
    with pytest.raises(HTTPException) as exc_info:
        _validated_runtime_config(
            AgentTriggerCreateRequest(
                type="file",
                config_json={"workspace_root": str(tmp_path / "missing")},
            )
        )
    assert exc_info.value.status_code == 422


@pytest.mark.parametrize("trigger_type", ["file", "git"])
def test_local_source_config_update_resets_persisted_cursor(
    trigger_type: str,
    db_session: Session,
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        "app.api.triggers.get_settings",
        lambda: type(
            "LocalSettings",
            (),
            {
                "runtime_profile": "local",
                "local_desktop_bootstrap_token": TEST_WORKSPACE_SIGNING_SECRET,
            },
        )(),
    )
    roots = [tmp_path / "first", tmp_path / "second"]
    for root in roots:
        root.mkdir()
        if trigger_type == "git":
            subprocess.run(["git", "init", "-q", str(root)], check=True, shell=False)
    client = TestClient(app)
    created = client.post(
        "/api/agents/default/triggers",
        headers=AUTH_HEADERS,
        json={
            "type": trigger_type,
            "config_json": {
                "workspace_authorization": _workspace_authorization(roots[0])
            },
        },
    )
    assert created.status_code == 201
    created_trigger = created.json()["trigger"]
    trigger_id = created_trigger["id"]
    path_field = "workspace_root" if trigger_type == "file" else "repo_root"
    assert path_field not in created_trigger["config_json"]
    assert created_trigger["config_json"][f"{path_field}_label"] == roots[0].name
    trigger = db_session.get(Trigger, trigger_id)
    assert trigger is not None
    trigger.runtime_state_json = {"snapshot": {"old": "state"}}
    db_session.commit()

    updated = client.patch(
        f"/api/agents/default/triggers/{trigger_id}",
        headers=AUTH_HEADERS,
        json={
            "config_json": {
                "workspace_authorization": _workspace_authorization(roots[1])
            }
        },
    )

    assert updated.status_code == 200
    assert "runtime_state_json" not in updated.json()
    assert path_field not in updated.json()["config_json"]
    assert updated.json()["config_json"][f"{path_field}_label"] == roots[1].name
    db_session.refresh(trigger)
    assert trigger.runtime_state_json == {}


def test_webhook_trigger_creates_planned_run_and_event(db_session: Session) -> None:
    client = TestClient(app)
    created = client.post(
        "/api/agents/default/triggers",
        headers=AUTH_HEADERS,
        json={"endpoint_path": "ci-run"},
    ).json()

    response = client.post(
        "/api/webhook/trigger/ci-run",
        headers={"X-Harness-Trigger-Secret": created["secret"]},
        json={"goal": "Review release", "title": "CI release", "payload": {"sha": "abc123"}},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["agent_id"] == "default"
    assert body["trigger_id"] == created["trigger"]["id"]
    assert body["status"] == "PLANNED"
    assert body["invocation_id"]

    run = db_session.get(Task, body["run_id"])
    assert run is not None
    assert run.agent_id == "default"
    assert run.status == "PLANNED"
    assert run.goal.startswith("Review release\n\nWebhook payload (sanitized):")
    assert '"sha":"abc123"' in run.goal
    trigger = db_session.get(Trigger, created["trigger"]["id"])
    assert trigger is not None
    assert run.created_by == trigger.created_by
    assert run.created_by is None or len(run.created_by) <= 36

    event_types = [
        row.event_type
        for row in db_session.execute(
            select(AgentEvent)
            .where(AgentEvent.task_id == body["run_id"])
            .order_by(AgentEvent.sequence)
        ).scalars()
    ]
    assert event_types == [
        EventType.TASK_CREATED.value,
        EventType.TRIGGER_INVOKED.value,
        EventType.PLAN_REQUESTED.value,
        EventType.PLAN_GENERATED.value,
    ]

    invocation = db_session.get(TriggerInvocation, body["invocation_id"])
    assert invocation is not None
    assert invocation.run_id == body["run_id"]
    assert invocation.status == "PLANNED"
    assert invocation.completed_at is None


def test_webhook_idempotency_reuses_invocation_and_run(db_session: Session) -> None:
    client = TestClient(app)
    created = client.post(
        "/api/agents/default/triggers",
        headers=AUTH_HEADERS,
        json={"endpoint_path": "dedupe-hook"},
    ).json()
    headers = {
        "X-Harness-Trigger-Secret": created["secret"],
        "Idempotency-Key": "  delivery-42  ",
    }

    first = client.post(
        "/api/webhook/trigger/dedupe-hook",
        headers=headers,
        json={
            "goal": "Review delivery",
            "payload": {
                "action": "released",
                "token": "must-not-be-stored",
                "metadata": {"authorization": "Bearer private-value"},
            },
        },
    )
    replay = client.post(
        "/api/webhook/trigger/dedupe-hook",
        headers=headers,
        json={"goal": "Changed goal must not replace the receipt"},
    )

    assert first.status_code == 200
    assert replay.status_code == 200
    assert replay.json()["invocation_id"] == first.json()["invocation_id"]
    assert replay.json()["run_id"] == first.json()["run_id"]
    assert len(db_session.execute(select(Task)).scalars().all()) == 1
    invocation = db_session.get(TriggerInvocation, first.json()["invocation_id"])
    assert invocation is not None
    assert invocation.idempotency_key == "delivery-42"
    assert "must-not-be-stored" not in str(invocation.payload_summary_json)
    assert "private-value" not in str(invocation.payload_summary_json)
    assert invocation.payload_summary_json["keys"] == ["action", "metadata", "token"]
    assert invocation.payload_summary_json["key_count"] == 3
    assert invocation.payload_summary_json["redaction_count"] == 2
    assert '"action":"released"' in invocation.payload_summary_json["preview_json"]
    assert invocation.payload_summary_json["preview_json"].count("[REDACTED]") == 2
    run = db_session.get(Task, first.json()["run_id"])
    assert run is not None
    assert '"action":"released"' in run.goal
    assert "must-not-be-stored" not in run.goal
    assert "private-value" not in run.goal
    event_payloads = [
        event.payload_json
        for event in db_session.execute(
            select(AgentEvent).where(AgentEvent.task_id == run.id)
        ).scalars()
    ]
    assert "must-not-be-stored" not in json.dumps(event_payloads)
    assert "private-value" not in json.dumps(event_payloads)

    history = client.get(
        f"/api/agents/default/triggers/{created['trigger']['id']}/invocations",
        headers=AUTH_HEADERS,
    )
    assert history.status_code == 200
    assert [item["id"] for item in history.json()["items"]] == [invocation.id]

    detail = client.get(
        f"/api/agents/default/triggers/{created['trigger']['id']}/invocations/{invocation.id}",
        headers=AUTH_HEADERS,
    )
    assert detail.status_code == 200
    assert detail.json()["id"] == invocation.id
    not_owned = client.get(
        f"/api/agents/default/triggers/{created['trigger']['id']}/invocations/not-present",
        headers=AUTH_HEADERS,
    )
    assert not_owned.status_code == 404

    assert (
        client.delete(
            f"/api/agents/default/triggers/{created['trigger']['id']}",
            headers=ADMIN_AUTH_HEADERS,
        ).status_code
        == 204
    )
    retained_history = client.get(
        f"/api/agents/default/triggers/{created['trigger']['id']}/invocations",
        headers=AUTH_HEADERS,
    )
    assert retained_history.status_code == 200
    assert retained_history.json()["items"][0]["id"] == invocation.id


def test_webhook_commit_persists_dispatch_outbox_with_invocation_and_run(
    db_session: Session,
) -> None:
    client = TestClient(app)
    created = client.post(
        "/api/agents/default/triggers",
        headers=AUTH_HEADERS,
        json={"endpoint_path": "dispatch-outbox"},
    ).json()
    response = client.post(
        "/api/webhook/trigger/dispatch-outbox",
        headers={"X-Harness-Trigger-Secret": created["secret"]},
        json={},
    )

    assert response.status_code == 200
    body = response.json()
    invocation = db_session.get(TriggerInvocation, body["invocation_id"])
    run = db_session.get(Task, body["run_id"])
    outbox = db_session.execute(
        select(RuntimeJob).where(RuntimeJob.kind == TRIGGER_DISPATCH_JOB_KIND)
    ).scalar_one()
    assert invocation is not None
    assert run is not None
    assert invocation.run_id == run.id
    assert outbox.status == "queued"
    assert outbox.payload == {"invocation_id": invocation.id}
    assert outbox.dedupe_key == f"trigger-dispatch:{invocation.id}"


def test_webhook_idempotency_creates_one_dispatch_outbox(db_session: Session) -> None:
    client = TestClient(app)
    created = client.post(
        "/api/agents/default/triggers",
        headers=AUTH_HEADERS,
        json={"endpoint_path": "dispatch-dedupe"},
    ).json()
    headers = {
        "X-Harness-Trigger-Secret": created["secret"],
        "Idempotency-Key": "dispatch-delivery-42",
    }

    first = client.post("/api/webhook/trigger/dispatch-dedupe", headers=headers, json={})
    replay = client.post("/api/webhook/trigger/dispatch-dedupe", headers=headers, json={})

    assert first.status_code == 200
    assert replay.status_code == 200
    assert replay.json()["invocation_id"] == first.json()["invocation_id"]
    assert replay.json()["run_id"] == first.json()["run_id"]
    assert len(db_session.execute(select(TriggerInvocation)).scalars().all()) == 1
    assert len(db_session.execute(select(Task)).scalars().all()) == 1
    jobs = list(
        db_session.execute(
            select(RuntimeJob).where(RuntimeJob.kind == TRIGGER_DISPATCH_JOB_KIND)
        ).scalars()
    )
    assert len(jobs) == 1
    assert jobs[0].payload["invocation_id"] == first.json()["invocation_id"]


def test_webhook_without_idempotency_creates_distinct_dispatch_outboxes(
    db_session: Session,
) -> None:
    client = TestClient(app)
    created = client.post(
        "/api/agents/default/triggers",
        headers=AUTH_HEADERS,
        json={"endpoint_path": "dispatch-repeat"},
    ).json()
    headers = {"X-Harness-Trigger-Secret": created["secret"]}

    first = client.post("/api/webhook/trigger/dispatch-repeat", headers=headers, json={})
    second = client.post("/api/webhook/trigger/dispatch-repeat", headers=headers, json={})

    invocation_ids = {first.json()["invocation_id"], second.json()["invocation_id"]}
    jobs = list(
        db_session.execute(
            select(RuntimeJob).where(RuntimeJob.kind == TRIGGER_DISPATCH_JOB_KIND)
        ).scalars()
    )
    assert first.status_code == 200
    assert second.status_code == 200
    assert len(invocation_ids) == 2
    assert len(db_session.execute(select(Task)).scalars().all()) == 2
    assert len(jobs) == 2
    assert {job.payload["invocation_id"] for job in jobs} == invocation_ids


def test_server_trigger_worker_retries_same_receipt_with_safe_error(
    db_session: Session,
    monkeypatch,
) -> None:
    from app.workers import trigger_invocation_worker

    client = TestClient(app)
    created = client.post(
        "/api/agents/default/triggers",
        headers=AUTH_HEADERS,
        json={"endpoint_path": "server-worker", "config_json": {"max_attempts": 3}},
    ).json()
    invoked = client.post(
        "/api/webhook/trigger/server-worker",
        headers={"X-Harness-Trigger-Secret": created["secret"]},
        json={},
    ).json()

    def fail_execution(**_kwargs):
        raise RuntimeError("private upstream diagnostics")

    monkeypatch.setattr(trigger_invocation_worker, "execute_trigger_invocation", fail_execution)
    with pytest.raises(RuntimeError, match="private upstream diagnostics"):
        trigger_invocation_worker.execute_server_trigger_invocation(
            invoked["invocation_id"],
            session=db_session,
        )
    invocation = db_session.get(TriggerInvocation, invoked["invocation_id"])
    assert invocation is not None
    assert invocation.status == "PLANNED"
    assert invocation.attempt == 2
    assert invocation.error == "Trigger execution attempt 1 failed"

    def complete_execution(*, invocation_id: str, session: Session):
        current = session.get(TriggerInvocation, invocation_id)
        assert current is not None
        current.status = "SUCCEEDED"
        return SimpleNamespace(status=current.status)

    monkeypatch.setattr(
        trigger_invocation_worker,
        "execute_trigger_invocation",
        complete_execution,
    )
    status_value = trigger_invocation_worker.execute_server_trigger_invocation(
        invoked["invocation_id"],
        session=db_session,
    )
    assert status_value == "SUCCEEDED"
    assert len(db_session.execute(select(Task)).scalars().all()) == 1


def test_webhook_payload_and_summary_are_bounded(db_session: Session) -> None:
    client = TestClient(app)
    created = client.post(
        "/api/agents/default/triggers",
        headers=AUTH_HEADERS,
        json={"endpoint_path": "bounded-payload"},
    ).json()
    payload = {f"key-{index:03d}": "value" for index in range(150)}
    response = client.post(
        "/api/webhook/trigger/bounded-payload",
        headers={"X-Harness-Trigger-Secret": created["secret"]},
        json={"payload": payload},
    )

    assert response.status_code == 200
    invocation = db_session.get(TriggerInvocation, response.json()["invocation_id"])
    assert invocation is not None
    summary = invocation.payload_summary_json
    assert len(summary["keys"]) == 100
    assert summary["key_count"] == 150
    assert len(summary["keys_sha256"]) == 64
    assert summary["truncated"] is True
    assert '"key-000":"value"' in summary["preview_json"]
    assert len(summary["preview_json"].encode("utf-8")) <= 1540
    assert len(json.dumps(summary, separators=(",", ":")).encode("utf-8")) <= 4096

    oversized = client.post(
        "/api/webhook/trigger/bounded-payload",
        headers={"X-Harness-Trigger-Secret": created["secret"]},
        json={"payload": {"body": "x" * (1024 * 1024 + 1)}},
    )
    assert oversized.status_code == 422


def test_invocation_history_projects_terminal_run_completion(db_session: Session) -> None:
    client = TestClient(app)
    created = client.post(
        "/api/agents/default/triggers",
        headers=AUTH_HEADERS,
        json={"endpoint_path": "completed-history"},
    ).json()
    invoked = client.post(
        "/api/webhook/trigger/completed-history",
        headers={"X-Harness-Trigger-Secret": created["secret"]},
        json={},
    ).json()
    run = db_session.get(Task, invoked["run_id"])
    assert run is not None
    run.status = "COMPLETED"
    run.completed_at = utc_now()
    db_session.commit()

    history = client.get(
        f"/api/agents/default/triggers/{created['trigger']['id']}/invocations",
        headers=AUTH_HEADERS,
    )
    item = history.json()["items"][0]
    assert item["status"] == "SUCCEEDED"
    assert item["completed_at"] == run.completed_at.isoformat()


def test_webhook_without_idempotency_key_creates_distinct_runs(db_session: Session) -> None:
    client = TestClient(app)
    created = client.post(
        "/api/agents/default/triggers",
        headers=AUTH_HEADERS,
        json={"endpoint_path": "repeat-hook"},
    ).json()
    headers = {"X-Harness-Trigger-Secret": created["secret"]}

    first = client.post("/api/webhook/trigger/repeat-hook", headers=headers, json={})
    second = client.post("/api/webhook/trigger/repeat-hook", headers=headers, json={})

    assert first.json()["run_id"] != second.json()["run_id"]
    assert len(db_session.execute(select(TriggerInvocation)).scalars().all()) == 2


def test_trigger_kill_switch_rejects_new_webhook_invocations(
    db_session: Session,
    monkeypatch,
) -> None:
    client = TestClient(app)
    created = client.post(
        "/api/agents/default/triggers",
        headers=AUTH_HEADERS,
        json={"endpoint_path": "stopped-hook"},
    ).json()
    monkeypatch.setenv("TRIGGER_AUTOMATION_ENABLED", "false")
    get_settings.cache_clear()

    response = client.post(
        "/api/webhook/trigger/stopped-hook",
        headers={"X-Harness-Trigger-Secret": created["secret"]},
        json={},
    )

    assert response.status_code == 503
    assert db_session.execute(select(TriggerInvocation)).scalars().all() == []
    assert db_session.execute(select(Task)).scalars().all() == []


def test_execute_invocation_failure_keeps_same_planned_run_for_runtime_retry(
    db_session: Session,
    monkeypatch,
) -> None:
    client = TestClient(app)
    created = client.post(
        "/api/agents/default/triggers",
        headers=AUTH_HEADERS,
        json={"endpoint_path": "retry-hook"},
    ).json()
    response = client.post(
        "/api/webhook/trigger/retry-hook",
        headers={"X-Harness-Trigger-Secret": created["secret"]},
        json={"goal": "Retry this exact run"},
    ).json()

    class FailingExecutor:
        def __init__(self, session: Session, **_kwargs) -> None:
            self.session = session

        def execute_existing_plan(self, task: Task) -> Task:
            task.status = "RUNNING"
            self.session.flush()
            raise RuntimeError("transient executor failure")

    monkeypatch.setattr(trigger_service, "Executor", FailingExecutor)
    with pytest.raises(RuntimeError, match="transient executor failure"):
        trigger_service.execute_trigger_invocation(
            invocation_id=response["invocation_id"],
            session=db_session,
        )
    db_session.rollback()

    invocation = db_session.get(TriggerInvocation, response["invocation_id"])
    run = db_session.get(Task, response["run_id"])
    assert invocation is not None
    assert invocation.status == "RETRYING"
    assert invocation.run_id == response["run_id"]
    assert run is not None
    assert run.status == "PLANNED"

    class CompletingExecutor:
        def __init__(self, session: Session, **_kwargs) -> None:
            self.session = session

        def execute_existing_plan(self, task: Task) -> Task:
            task.status = "COMPLETED"
            self.session.flush()
            return task

    monkeypatch.setattr(trigger_service, "Executor", CompletingExecutor)
    completed = trigger_service.execute_trigger_invocation(
        invocation_id=response["invocation_id"],
        session=db_session,
    )
    db_session.commit()
    assert completed.status == "SUCCEEDED"
    assert completed.run_id == response["run_id"]
    assert len(db_session.execute(select(Task)).scalars().all()) == 1


def test_checkpointed_trigger_crash_reclaims_lease_and_skips_completed_step(
    db_session: Session,
    monkeypatch,
) -> None:
    client = TestClient(app)
    created = client.post(
        "/api/agents/default/triggers",
        headers=AUTH_HEADERS,
        json={"endpoint_path": "checkpoint-recovery"},
    ).json()
    invoked = client.post(
        "/api/webhook/trigger/checkpoint-recovery",
        headers={"X-Harness-Trigger-Secret": created["secret"]},
        json={"goal": "Resume the same planned run after a crash"},
    ).json()
    executed_steps: list[str] = []

    def complete_step(self, task, _plan_row, step):
        executed_steps.append(step.key)
        self.event_store.append(
            task_id=task.id,
            event_type=EventType.STEP_COMPLETED,
            payload_json={"step_key": step.key, "summary": "checkpointed test step"},
        )
        return StepResult(
            step_key=step.key,
            status="STEP_COMPLETED",
            summary="completed",
        )

    monkeypatch.setattr(Executor, "_execute_step", complete_step)

    def crash_after_commit() -> None:
        db_session.commit()
        raise SystemExit("simulated process crash after checkpoint")

    db_session.info["runtime_job_step_checkpoint"] = crash_after_commit
    with pytest.raises(SystemExit, match="simulated process crash"):
        trigger_service.execute_trigger_invocation(
            invocation_id=invoked["invocation_id"],
            session=db_session,
            lease_owner="crashed-worker",
        )
    db_session.rollback()

    invocation = db_session.get(TriggerInvocation, invoked["invocation_id"])
    run = db_session.get(Task, invoked["run_id"])
    assert invocation is not None and invocation.status == "RUNNING"
    assert invocation.lease_owner == "crashed-worker"
    assert run is not None and run.status == "RUNNING"
    first_step = executed_steps[0]

    invocation.lease_until = utc_now() - trigger_service.TRIGGER_EXECUTION_LEASE_GRACE
    db_session.commit()
    db_session.info["runtime_job_step_checkpoint"] = db_session.commit
    completed = trigger_service.execute_trigger_invocation(
        invocation_id=invoked["invocation_id"],
        session=db_session,
        lease_owner="recovery-worker",
    )
    db_session.commit()

    assert completed.status == "SUCCEEDED"
    assert completed.run_id == invoked["run_id"]
    assert executed_steps.count(first_step) == 1
    assert len(executed_steps) >= 2
    skipped = list(
        db_session.execute(
            select(AgentEvent).where(
                AgentEvent.task_id == invoked["run_id"],
                AgentEvent.event_type == EventType.STEP_SKIPPED.value,
            )
        ).scalars()
    )
    assert any(event.payload_json.get("step_key") == first_step for event in skipped)


def test_webhook_trigger_rejects_bad_secret_without_run(db_session: Session) -> None:
    client = TestClient(app)
    client.post(
        "/api/agents/default/triggers",
        headers=AUTH_HEADERS,
        json={"endpoint_path": "secure-hook"},
    )

    response = client.post(
        "/api/webhook/trigger/secure-hook",
        headers={"X-Harness-Trigger-Secret": "wrong"},
        json={"goal": "Do not run"},
    )

    assert response.status_code == 401
    assert db_session.execute(select(Task)).scalars().all() == []


def test_webhook_trigger_rejects_disabled_trigger(db_session: Session) -> None:
    client = TestClient(app)
    created = client.post(
        "/api/agents/default/triggers",
        headers=AUTH_HEADERS,
        json={"endpoint_path": "disabled-hook"},
    ).json()
    client.patch(
        f"/api/agents/default/triggers/{created['trigger']['id']}",
        headers=AUTH_HEADERS,
        json={"enabled": False},
    )

    response = client.post(
        "/api/webhook/trigger/disabled-hook",
        headers={"X-Harness-Trigger-Secret": created["secret"]},
        json={"goal": "Do not run"},
    )

    assert response.status_code == 404
    assert db_session.execute(select(Task)).scalars().all() == []


def test_trigger_run_resume_returns_conflict_when_trigger_is_disabled(
    db_session: Session,
) -> None:
    client = TestClient(app)
    created = client.post(
        "/api/agents/default/triggers",
        headers=AUTH_HEADERS,
        json={"endpoint_path": "resume-disabled"},
    ).json()
    invoked = client.post(
        "/api/webhook/trigger/resume-disabled",
        headers={"X-Harness-Trigger-Secret": created["secret"]},
        json={},
    ).json()
    run = db_session.get(Task, invoked["run_id"])
    invocation = db_session.get(TriggerInvocation, invoked["invocation_id"])
    assert run is not None and invocation is not None
    run.status = "FAILED"
    invocation.status = "FAILED"
    db_session.commit()
    client.patch(
        f"/api/agents/default/triggers/{created['trigger']['id']}",
        headers=AUTH_HEADERS,
        json={"enabled": False},
    )

    response = client.post(f"/api/tasks/{run.id}/resume", headers=AUTH_HEADERS)

    assert response.status_code == 409
    assert response.json()["detail"] == "Trigger is disabled"


def test_trigger_run_resume_enqueues_dispatch_without_executing_inline(
    db_session: Session,
    monkeypatch,
) -> None:
    client = TestClient(app)
    created = client.post(
        "/api/agents/default/triggers",
        headers=AUTH_HEADERS,
        json={"endpoint_path": "resume-dispatch"},
    ).json()
    invoked = client.post(
        "/api/webhook/trigger/resume-dispatch",
        headers={"X-Harness-Trigger-Secret": created["secret"]},
        json={},
    ).json()
    run = db_session.get(Task, invoked["run_id"])
    invocation = db_session.get(TriggerInvocation, invoked["invocation_id"])
    initial_dispatch = db_session.execute(
        select(RuntimeJob).where(
            RuntimeJob.kind == TRIGGER_DISPATCH_JOB_KIND,
            RuntimeJob.dedupe_key == f"trigger-dispatch:{invocation.id}",
        )
    ).scalar_one()
    assert run is not None and invocation is not None
    initial_dispatch.status = "succeeded"
    initial_dispatch.finished_at = utc_now()
    run.status = "FAILED"
    invocation.status = "FAILED"
    invocation.completed_at = utc_now()
    db_session.commit()

    def forbidden_inline_execution(*_args, **_kwargs):
        raise AssertionError("resume must not execute a Trigger Plan in the HTTP request")

    monkeypatch.setattr(
        trigger_service,
        "execute_trigger_invocation",
        forbidden_inline_execution,
    )

    response = client.post(f"/api/tasks/{run.id}/resume", headers=AUTH_HEADERS)

    assert response.status_code == 202
    assert response.json()["status"] == "PLANNED"
    db_session.refresh(invocation)
    assert invocation.status == "RETRYING"
    active_dispatches = list(
        db_session.execute(
            select(RuntimeJob).where(
                RuntimeJob.kind == TRIGGER_DISPATCH_JOB_KIND,
                RuntimeJob.dedupe_key == f"trigger-dispatch:{invocation.id}",
                RuntimeJob.status.in_(("queued", "running")),
            )
        ).scalars()
    )
    assert len(active_dispatches) == 1
    assert active_dispatches[0].payload == {"invocation_id": invocation.id}

    duplicate = client.post(f"/api/tasks/{run.id}/resume", headers=AUTH_HEADERS)

    assert duplicate.status_code == 409
    assert len(
        list(
            db_session.execute(
                select(RuntimeJob).where(
                    RuntimeJob.dedupe_key == f"trigger-dispatch:{invocation.id}",
                    RuntimeJob.status.in_(("queued", "running")),
                )
            ).scalars()
        )
    ) == 1


def test_trigger_run_execute_uses_invocation_lease_instead_of_bare_executor(
    db_session: Session,
    monkeypatch,
) -> None:
    client = TestClient(app)
    created = client.post(
        "/api/agents/default/triggers",
        headers=AUTH_HEADERS,
        json={"endpoint_path": "execute-owned"},
    ).json()
    invoked = client.post(
        "/api/webhook/trigger/execute-owned",
        headers={"X-Harness-Trigger-Secret": created["secret"]},
        json={"goal": "execute through invocation"},
    ).json()
    calls: list[str] = []

    def execute_invocation(*, invocation_id: str, session: Session):
        calls.append(invocation_id)
        invocation = session.get(TriggerInvocation, invocation_id)
        assert invocation is not None
        task = session.get(Task, invoked["run_id"])
        assert task is not None
        invocation.status = "SUCCEEDED"
        task.status = "COMPLETED"
        session.flush()
        return invocation

    def forbidden_executor(*_args, **_kwargs):
        raise AssertionError("Trigger-owned Run must not use bare Executor")

    monkeypatch.setattr(trigger_service, "execute_trigger_invocation", execute_invocation)
    monkeypatch.setattr("app.api.agents.agent_runs.Executor", forbidden_executor)

    response = client.post(
        f"/api/agents/runs/{invoked['run_id']}/execute",
        headers=AUTH_HEADERS,
    )

    assert response.status_code == 202
    assert calls == [invoked["invocation_id"]]
    assert response.json()["status"] == "COMPLETED"


def test_trigger_run_step_selective_resume_is_rejected(
    db_session: Session,
) -> None:
    client = TestClient(app)
    created = client.post(
        "/api/agents/default/triggers",
        headers=AUTH_HEADERS,
        json={"endpoint_path": "step-resume-owned"},
    ).json()
    invoked = client.post(
        "/api/webhook/trigger/step-resume-owned",
        headers={"X-Harness-Trigger-Secret": created["secret"]},
        json={},
    ).json()
    run = db_session.get(Task, invoked["run_id"])
    invocation = db_session.get(TriggerInvocation, invoked["invocation_id"])
    assert run is not None and invocation is not None
    run.status = "FAILED"
    invocation.status = "FAILED"
    db_session.commit()

    response = client.post(
        f"/api/tasks/{run.id}/steps/resume",
        headers=AUTH_HEADERS,
        json={"step_keys": ["first"]},
    )

    assert response.status_code == 409
    assert "step-selective resume is unavailable" in response.json()["detail"]
