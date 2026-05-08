from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db.models import AgentEvent, SystemSetting, ToolApproval, ToolCall, utc_now
from app.main import app
from tests.conftest import AUTH_HEADERS

ADMIN_HEADERS = {"Authorization": "Bearer dev-admin-token"}


def _create_task(client: TestClient) -> str:
    response = client.post(
        "/api/tasks",
        headers=AUTH_HEADERS,
        json={
            "title": "Approval run",
            "goal": "Request a high-risk tool approval",
            "model_provider": "openai-compatible",
            "model_name": "default",
            "max_runtime_seconds": 1800,
            "max_subagents": 5,
            "enable_sandbox": True,
            "enable_network": False,
        },
    )
    assert response.status_code == 201
    return response.json()["id"]


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
    task_id = _create_task(client)
    _force_read_file_admin_approval(task_id, db_session)

    requested = client.post(
        f"/api/tasks/{task_id}/tools/execute",
        headers=AUTH_HEADERS,
        json={"tool_name": "read_file", "input_json": {"path": "pyproject.toml"}},
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

    stored_tool_call = db_session.get(ToolCall, tool_call["id"])
    stored_approval = db_session.get(ToolApproval, approval["id"])
    assert stored_tool_call is not None
    assert stored_tool_call.status == "APPROVED"
    assert stored_approval is not None
    assert stored_approval.decided_by == "dev-admin"
    event_types = [
        event.event_type
        for event in db_session.execute(
            select(AgentEvent).where(AgentEvent.task_id == task_id).order_by(AgentEvent.sequence)
        ).scalars()
    ]
    assert "TOOL_APPROVAL_REQUESTED" in event_types
    assert "TOOL_APPROVAL_APPROVED" in event_types


def test_tool_approval_reject_requires_admin(db_session) -> None:
    client = TestClient(app)
    task_id = _create_task(client)
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
