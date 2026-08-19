from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    Agent,
    AgentEvent,
    ExecutionPlan,
    SystemSetting,
    Task,
    TaskStep,
    ToolApproval,
    ToolCall,
    Trigger,
    TriggerInvocation,
    utc_now,
)
from app.events.event_store import EventStore
from app.events.event_types import EventType
from app.main import app
from app.tools.capabilities import CapabilityRegistry
from app.triggers import service as trigger_service
from tests.conftest import AUTH_HEADERS

ADMIN_HEADERS = {"Authorization": "Bearer dev-admin-token"}


def _create_task(db_session: Session) -> str:
    db_session.add(
        Agent(
            id="approval-agent",
            organization_id=None,
            name="Approval Agent",
            description="Owns read_file for approval tests",
            role="tester",
            status="ACTIVE",
            model_provider="default",
            model_name="default",
            system_prompt="Request approvals through capability attachments.",
            tools_json=["read_file"],
            routing_tags=[],
        )
    )
    task = Task(
        organization_id="dev-org",
        agent_id="approval-agent",
        created_by="dev-engineer",
        title="Approval run",
        goal="Request a high-risk tool approval",
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
    CapabilityRegistry(db_session, task.organization_id).backfill_agent_attachments(
        "approval-agent",
        attached_by="test",
    )
    return task.id


def _force_read_file_admin_approval(task_id: str, db_session) -> None:
    db_session.add(
        SystemSetting(
            organization_id="dev-org",
            key="settings.policies",
            value_json={
                "risk_levels": [
                    {
                        "name": "low",
                        "requires_sandbox": False,
                        "approval": "admin",
                        "allowed_roles": ["admin", "engineer"],
                    }
                ],
                "approvals": {"manual_review": True, "deny_on_missing_policy": True},
                "sandbox": {"default_network": False, "default_timeout_seconds": 60},
                "audit": {"model_calls": True, "tool_calls": True, "policy_actions": True},
            },
            updated_by="dev-admin",
            updated_at=utc_now(),
        )
    )
    db_session.flush()
    assert task_id


def _create_pending_trigger_approval(
    *,
    task_id: str,
    db_session: Session,
    workspace_root: str | None = None,
    trigger_type: str = "webhook",
) -> tuple[Trigger, TriggerInvocation, ToolCall, ToolApproval]:
    root_field = "workspace_root" if trigger_type == "file" else "repo_root"
    trigger = Trigger(
        organization_id="dev-org",
        agent_id="approval-agent",
        type=trigger_type,
        name="Approval trigger",
        config_json={root_field: workspace_root} if workspace_root is not None else {},
        enabled=True,
        created_at=utc_now(),
        updated_at=utc_now(),
    )
    db_session.add(trigger)
    db_session.flush()
    invocation = TriggerInvocation(
        trigger_id=trigger.id,
        organization_id="dev-org",
        workspace_root=workspace_root,
        status="WAITING_APPROVAL",
        run_id=task_id,
    )
    tool_call = ToolCall(
        task_id=task_id,
        tool_name="read_file",
        status="PENDING_APPROVAL",
        risk_level="low",
        requires_sandbox=False,
        input_json={"path": "marker.txt"},
        output_json={},
    )
    db_session.add_all([invocation, tool_call])
    db_session.flush()
    approval = ToolApproval(
        task_id=task_id,
        tool_call_id=tool_call.id,
        organization_id="dev-org",
        status="PENDING",
        risk_level="low",
        reason="Trigger approval test",
        request_json={"tool_name": "read_file", "input_json": {"path": "marker.txt"}},
        decision_json={},
    )
    task = db_session.get(Task, task_id)
    assert task is not None
    task.status = "WAITING_APPROVAL"
    db_session.add(approval)
    db_session.commit()
    return trigger, invocation, tool_call, approval


def test_tool_approval_request_and_admin_approve(db_session) -> None:
    client = TestClient(app)
    task_id = _create_task(db_session)
    _force_read_file_admin_approval(task_id, db_session)

    requested = client.post(
        f"/api/tasks/{task_id}/tools/execute",
        headers=AUTH_HEADERS,
        json={
            "tool_name": "read_file",
            "input_json": {"path": "pyproject.toml", "api_key": "clear-secret"},
        },
    )
    assert requested.status_code == 202
    tool_call = requested.json()["tool_call"]
    assert tool_call["status"] == "PENDING_APPROVAL"
    assert requested.json()["output"]["status"] == "PENDING"

    listed = client.get(f"/api/tasks/{task_id}/tool-approvals", headers=AUTH_HEADERS)
    assert listed.status_code == 200
    approval = listed.json()["items"][0]
    assert approval["status"] == "PENDING"
    assert approval["tool_call_id"] == tool_call["id"]

    approved = client.post(
        f"/api/tasks/{task_id}/tool-approvals/{approval['id']}/approve",
        headers=ADMIN_HEADERS,
        json={"reason": "Approved for regression test"},
    )
    assert approved.status_code == 202
    assert approved.json()["items"][0]["status"] == "APPROVED"

    db_session.expire_all()
    stored_tool_call = db_session.get(ToolCall, tool_call["id"])
    stored_approval = db_session.get(ToolApproval, approval["id"])
    stored_task = db_session.get(Task, task_id)
    assert stored_tool_call is not None
    assert stored_tool_call.status == "SUCCESS"
    assert isinstance(stored_tool_call.output_json.get("content"), str)
    assert stored_approval is not None
    assert stored_approval.request_json["input_json"]["api_key"] == "[REDACTED]"
    assert stored_tool_call.input_json["api_key"] == "[REDACTED]"
    assert stored_approval.decided_by == "dev-admin"
    assert stored_task is not None
    assert stored_task.status == "COMPLETED"
    event_types = [
        event.event_type
        for event in db_session.execute(
            select(AgentEvent).where(AgentEvent.task_id == task_id).order_by(AgentEvent.sequence)
        ).scalars()
    ]
    assert "TOOL_APPROVAL_REQUESTED" in event_types
    assert "TOOL_APPROVAL_APPROVED" in event_types
    assert "TOOL_RESULT_RECEIVED" in event_types
    assert "TASK_COMPLETED" in event_types


def test_trigger_tool_approval_continuation_uses_invocation_and_rolls_back_on_busy_lease(
    db_session: Session,
    monkeypatch,
    tmp_path: Path,
) -> None:
    task_id = _create_task(db_session)
    _force_read_file_admin_approval(task_id, db_session)
    trigger, invocation, tool_call, approval = _create_pending_trigger_approval(
        task_id=task_id,
        db_session=db_session,
        workspace_root=str(tmp_path.resolve()),
        trigger_type="file",
    )
    plan = ExecutionPlan(
        task_id=task_id,
        version=1,
        status="READY",
        plan_json={"steps": [{"key": "approval-step", "description": "resume"}]},
        created_at=utc_now(),
    )
    db_session.add(plan)
    db_session.flush()
    step = TaskStep(
        task_id=task_id,
        plan_id=plan.id,
        step_key="approval-step",
        description="resume",
        status="STEP_FAILED",
        execution_mode="sync",
    )
    db_session.add(step)
    db_session.flush()
    EventStore(db_session).append(
        task_id=task_id,
        event_type=EventType.STEP_FAILED,
        payload_json={
            "step_id": step.id,
            "step_key": step.step_key,
            "tool_call_id": tool_call.id,
        },
    )
    invocation.status = "RUNNING"
    invocation.lease_owner = "other-worker"
    invocation.lease_until = utc_now() + trigger_service.TRIGGER_EXECUTION_LEASE_GRACE
    db_session.commit()

    tool_runner_calls: list[str] = []

    class FakeToolRunner:
        def __init__(self, *args, **kwargs):
            pass

        def execute_approved_call(self, *, tool_call, sandbox):
            tool_runner_calls.append(tool_call.id)
            tool_call.status = "SUCCESS"
            tool_call.output_json = {"content": "approved"}
            return SimpleNamespace(tool_call=tool_call)

    bare_resume_calls: list[str] = []

    def bare_resume(*_args, **_kwargs):
        bare_resume_calls.append("called")
        raise AssertionError("Trigger-owned approval must not resume through bare Executor")

    monkeypatch.setattr("app.api.tasks.ToolRunner", FakeToolRunner)
    monkeypatch.setattr("app.api.tasks.Executor.resume_task", bare_resume)
    monkeypatch.setattr(
        trigger_service,
        "get_settings",
        lambda: type(
            "LocalSettings",
            (),
            {"trigger_automation_enabled": True, "runtime_profile": "local"},
        )(),
    )

    response = TestClient(app).post(
        f"/api/tasks/{task_id}/tool-approvals/{approval.id}/approve",
        headers=ADMIN_HEADERS,
        json={"reason": "approve trigger continuation"},
    )

    assert response.status_code == 409
    assert "already executing" in response.json()["detail"]
    assert tool_runner_calls == [tool_call.id]
    assert bare_resume_calls == []
    db_session.expire_all()
    stored_task = db_session.get(Task, task_id)
    stored_approval = db_session.get(ToolApproval, approval.id)
    stored_tool_call = db_session.get(ToolCall, tool_call.id)
    stored_invocation = db_session.get(TriggerInvocation, invocation.id)
    assert stored_task is not None and stored_task.status == "WAITING_APPROVAL"
    assert stored_approval is not None and stored_approval.status == "PENDING"
    assert stored_tool_call is not None and stored_tool_call.status == "PENDING_APPROVAL"
    assert stored_invocation is not None
    assert stored_invocation.lease_owner == "other-worker"


def test_trigger_tool_approval_continuation_calls_invocation_executor(
    db_session: Session,
    monkeypatch,
    tmp_path: Path,
) -> None:
    task_id = _create_task(db_session)
    _force_read_file_admin_approval(task_id, db_session)
    _trigger, invocation, tool_call, approval = _create_pending_trigger_approval(
        task_id=task_id,
        db_session=db_session,
        workspace_root=str(tmp_path.resolve()),
        trigger_type="file",
    )
    plan = ExecutionPlan(
        task_id=task_id,
        version=1,
        status="READY",
        plan_json={"steps": [{"key": "approval-step", "description": "resume"}]},
        created_at=utc_now(),
    )
    db_session.add(plan)
    db_session.flush()
    step = TaskStep(
        task_id=task_id,
        plan_id=plan.id,
        step_key="approval-step",
        description="resume",
        status="STEP_FAILED",
        execution_mode="sync",
    )
    db_session.add(step)
    db_session.flush()
    EventStore(db_session).append(
        task_id=task_id,
        event_type=EventType.STEP_FAILED,
        payload_json={
            "step_id": step.id,
            "step_key": step.step_key,
            "tool_call_id": tool_call.id,
        },
    )
    invocation.status = "RUNNING"
    db_session.commit()
    calls: list[str] = []

    class FakeToolRunner:
        def __init__(self, *args, **kwargs):
            pass

        def execute_approved_call(self, *, tool_call, sandbox):
            tool_call.status = "SUCCESS"
            tool_call.output_json = {"content": "approved"}
            return SimpleNamespace(tool_call=tool_call)

    def execute_invocation(*, invocation_id: str, session: Session):
        calls.append(invocation_id)
        stored = session.get(TriggerInvocation, invocation_id)
        assert stored is not None
        stored.status = "SUCCEEDED"
        session.flush()
        return stored

    bare_resume_calls: list[str] = []

    def bare_resume(*_args, **_kwargs):
        bare_resume_calls.append("called")
        raise AssertionError("Trigger-owned approval must not resume through bare Executor")

    monkeypatch.setattr("app.api.tasks.ToolRunner", FakeToolRunner)
    monkeypatch.setattr("app.api.tasks.Executor.resume_task", bare_resume)
    monkeypatch.setattr(trigger_service, "execute_trigger_invocation", execute_invocation)
    monkeypatch.setattr(
        trigger_service,
        "get_settings",
        lambda: type(
            "LocalSettings",
            (),
            {"trigger_automation_enabled": True, "runtime_profile": "local"},
        )(),
    )

    response = TestClient(app).post(
        f"/api/tasks/{task_id}/tool-approvals/{approval.id}/approve",
        headers=ADMIN_HEADERS,
        json={"reason": "approve trigger continuation"},
    )

    assert response.status_code == 202, response.text
    assert calls == [invocation.id]
    assert bare_resume_calls == []
    db_session.expire_all()
    stored_approval = db_session.get(ToolApproval, approval.id)
    stored_tool_call = db_session.get(ToolCall, tool_call.id)
    stored_task = db_session.get(Task, task_id)
    assert stored_approval is not None and stored_approval.status == "APPROVED"
    assert stored_tool_call is not None and stored_tool_call.status == "SUCCESS"
    assert stored_task is not None and stored_task.status == "RUNNING"


def test_tool_approval_reject_requires_admin(db_session) -> None:
    client = TestClient(app)
    task_id = _create_task(db_session)
    _force_read_file_admin_approval(task_id, db_session)
    requested = client.post(
        f"/api/tasks/{task_id}/tools/execute",
        headers=AUTH_HEADERS,
        json={"tool_name": "read_file", "input_json": {"path": "pyproject.toml"}},
    ).json()
    approval_id = requested["output"]["approval_id"]

    forbidden = client.post(
        f"/api/tasks/{task_id}/tool-approvals/{approval_id}/reject",
        headers=AUTH_HEADERS,
        json={"reason": "engineer cannot reject"},
    )
    assert forbidden.status_code == 403

    rejected = client.post(
        f"/api/tasks/{task_id}/tool-approvals/{approval_id}/reject",
        headers=ADMIN_HEADERS,
        json={"reason": "Too risky"},
    )
    assert rejected.status_code == 202
    assert rejected.json()["items"][0]["status"] == "REJECTED"
    db_session.expire_all()
    stored_task = db_session.get(Task, task_id)
    stored_tool_call = db_session.get(ToolCall, requested["tool_call"]["id"])
    assert stored_task is not None
    assert stored_task.status == "FAILED"
    assert stored_tool_call is not None
    assert stored_tool_call.status == "DENIED"


def test_tool_approval_modify_updates_input_and_approves(db_session) -> None:
    client = TestClient(app)
    task_id = _create_task(db_session)
    _force_read_file_admin_approval(task_id, db_session)
    requested = client.post(
        f"/api/tasks/{task_id}/tools/execute",
        headers=AUTH_HEADERS,
        json={
            "tool_name": "read_file",
            "input_json": {"path": "pyproject.toml", "api_key": "clear-secret"},
        },
    ).json()
    approval_id = requested["output"]["approval_id"]
    tool_call_id = requested["tool_call"]["id"]

    modified = client.post(
        f"/api/tasks/{task_id}/tool-approvals/{approval_id}/modify",
        headers=ADMIN_HEADERS,
        json={
            "modified_input_json": {"path": "app/main.py"},
            "reason": "Use a safer preview file",
        },
    )

    assert modified.status_code == 202
    approval = db_session.get(ToolApproval, approval_id)
    tool_call = db_session.get(ToolCall, tool_call_id)
    assert approval is not None
    assert approval.status == "APPROVED"
    assert approval.request_json["input_json"] == {"path": "app/main.py"}
    assert approval.decision_json["modified"] is True
    assert tool_call is not None
    assert tool_call.status == "SUCCESS"
    assert tool_call.input_json == {"path": "app/main.py"}


@pytest.mark.parametrize("safety_gate", ["disabled_trigger", "kill_switch"])
def test_trigger_tool_approval_rechecks_safety_gate_before_execution(
    db_session: Session,
    monkeypatch,
    safety_gate: str,
) -> None:
    client = TestClient(app)
    task_id = _create_task(db_session)
    trigger, _invocation, tool_call, approval = _create_pending_trigger_approval(
        task_id=task_id,
        db_session=db_session,
    )
    if safety_gate == "disabled_trigger":
        trigger.enabled = False
        db_session.commit()
    else:
        monkeypatch.setattr(
            trigger_service,
            "get_settings",
            lambda: type(
                "PausedSettings",
                (),
                {"trigger_automation_enabled": False, "runtime_profile": "server"},
            )(),
        )

    response = client.post(
        f"/api/tasks/{task_id}/tool-approvals/{approval.id}/approve",
        headers=ADMIN_HEADERS,
        json={"reason": "Must recheck Trigger state"},
    )

    assert response.status_code == 409
    db_session.expire_all()
    stored_approval = db_session.get(ToolApproval, approval.id)
    stored_tool_call = db_session.get(ToolCall, tool_call.id)
    assert stored_approval is not None and stored_approval.status == "PENDING"
    assert stored_tool_call is not None and stored_tool_call.status == "PENDING_APPROVAL"


@pytest.mark.parametrize("trigger_type", ["file", "git"])
def test_file_or_git_trigger_approval_uses_persisted_invocation_workspace(
    db_session: Session,
    monkeypatch,
    tmp_path,
    trigger_type: str,
) -> None:
    marker = tmp_path / "marker.txt"
    marker.write_text("trigger workspace marker")
    client = TestClient(app)
    task_id = _create_task(db_session)
    _trigger, _invocation, tool_call, approval = _create_pending_trigger_approval(
        task_id=task_id,
        db_session=db_session,
        workspace_root=str(tmp_path.resolve()),
        trigger_type=trigger_type,
    )
    monkeypatch.setattr(
        trigger_service,
        "get_settings",
        lambda: type(
            "LocalSettings",
            (),
            {"trigger_automation_enabled": True, "runtime_profile": "local"},
        )(),
    )

    response = client.post(
        f"/api/tasks/{task_id}/tool-approvals/{approval.id}/approve",
        headers=ADMIN_HEADERS,
        json={"reason": "Read from the bound Trigger workspace"},
    )

    assert response.status_code == 202
    db_session.expire_all()
    stored_tool_call = db_session.get(ToolCall, tool_call.id)
    assert stored_tool_call is not None and stored_tool_call.status == "SUCCESS"
    assert stored_tool_call.output_json["content"] == "trigger workspace marker"
