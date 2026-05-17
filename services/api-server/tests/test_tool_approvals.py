from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Agent, AgentEvent, SystemSetting, Task, ToolApproval, ToolCall, utc_now
from app.main import app
from app.tools.capabilities import CapabilityRegistry
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
