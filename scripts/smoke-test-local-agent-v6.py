#!/usr/bin/env python3
from __future__ import annotations

# ruff: noqa: E402,I001

import argparse
import importlib
import os
import sys
from collections.abc import Generator
from datetime import timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
API_ROOT = ROOT / "services" / "api-server"
VENV_PYTHON = API_ROOT / ".venv" / "bin" / "python"


def _bootstrap_backend_python() -> None:
    if str(API_ROOT) not in sys.path:
        sys.path.insert(0, str(API_ROOT))
    try:
        import fastapi  # noqa: F401
        import sqlalchemy  # noqa: F401
    except ModuleNotFoundError:
        if VENV_PYTHON.exists() and Path(sys.executable).resolve() != VENV_PYTHON.resolve():
            os.execv(str(VENV_PYTHON), [str(VENV_PYTHON), *sys.argv])
        raise


_bootstrap_backend_python()

os.environ.setdefault("DATABASE_URL", "sqlite+pysqlite:///:memory:")
os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("AUTH_JWT_SECRET", "test-harness-jwt-secret-32-characters-min")
os.environ.setdefault(
    "HARNESS_SECRET_ENCRYPTION_KEY",
    "test-harness-secret-encryption-key-32-min",
)
os.environ.setdefault("DEEPSEEK_API_KEY", "")

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine, select  # noqa: E402
from sqlalchemy.orm import Session, sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from app.db.models import (  # noqa: E402
    Agent,
    AgentEvent,
    AgentMessage,
    Base,
    LocalAgentBridgeEventReceipt,
    LocalAgentBridgeTask,
    LocalAgentCommand,
    LocalAgentConnection,
    LocalAgentPairingToken,
    LocalAgentPendingChange,
    LocalAgentToolRequest,
    Task,
    ToolApproval,
    ToolCall,
    utc_now,
)
from app.db.session import get_db_session  # noqa: E402
from app.main import app  # noqa: E402
from app.tools.capabilities import CapabilityRegistry  # noqa: E402


AUTH_HEADERS = {"Authorization": "Bearer dev-engineer-token"}
ADMIN_HEADERS = {"Authorization": "Bearer dev-admin-token"}


def _new_session() -> tuple[TestClient, Session]:
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    testing_session_local = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = testing_session_local()

    def _get_db_session() -> Generator[Session, None, None]:
        yield session

    app.dependency_overrides[get_db_session] = _get_db_session
    return TestClient(app), session


def _ensure_agent(session: Session, agent_id: str = "default") -> None:
    local_tools = [
        "read_file",
        "list_files",
        "write_file",
        "run_shell",
        "run_tests",
        "git_command",
    ]
    agent = session.get(Agent, agent_id)
    if agent is not None:
        agent.tools_json = local_tools
        session.flush()
        CapabilityRegistry(session, agent.organization_id).backfill_agent_attachments(
            agent.id,
            attached_by="smoke-v6",
        )
        session.commit()
        return
    agent = Agent(
        id=agent_id,
        organization_id="dev-org",
        name="Default Agent",
        description="Default entry agent",
        role="assistant",
        status="ACTIVE",
        model_provider="default",
        model_name="default",
        system_prompt="Help the user.",
        tools_json=local_tools,
        routing_tags=["workspace"],
        max_parallel_assignments=1,
    )
    session.add(agent)
    session.flush()
    CapabilityRegistry(session, agent.organization_id).backfill_agent_attachments(
        agent.id,
        attached_by="smoke-v6",
    )
    session.commit()


def _claude_v6_capabilities() -> dict[str, Any]:
    return {
        "supports_streaming": True,
        "claude_permission_bridge_v1": True,
        "permission_bridge": "harness_local_tool_request_v1",
        "permission_bridge_mode": "sdk",
        "execution_mode": "agent_sdk_intent_capture_harness_executor",
        "permission_bridge_execution": "harness_owned_executor",
        "sdk_native_tool_execution_enabled": False,
        "permission_bridge_callback_configured": True,
        "permission_bridge_pre_tool_hook_configured": True,
        "permission_bridge_dummy_hook_only": True,
        "side_effect_tools_preapproval_disabled": True,
        "forbidden_permission_modes_disabled": True,
        "unmanaged_settings_disabled": True,
        "sdk_allowed_tools_preapproved": False,
        "allowed_tools": [],
        "remote_control_enabled": False,
        "mcp_enabled": False,
        "plugins_enabled": False,
        "hooks_enabled": False,
        "subagents_enabled": False,
        "browser_enabled": False,
        "computer_use_enabled": False,
        "native_resume_enabled": False,
        "background_sessions_enabled": False,
        "web_sessions_enabled": False,
        "cloud_sessions_enabled": False,
    }


def _claude_v6_safety_metadata() -> dict[str, Any]:
    safety = {
        "permission_bridge_callback_configured": True,
        "permission_bridge_pre_tool_hook_configured": True,
        "permission_bridge_dummy_hook_only": True,
        "side_effect_tools_preapproval_disabled": True,
        "forbidden_permission_modes_disabled": True,
        "unmanaged_settings_disabled": True,
        "mcp_disabled": True,
        "plugins_disabled": True,
        "hooks_disabled": True,
        "subagents_disabled": True,
        "browser_disabled": True,
        "computer_use_disabled": True,
        "remote_control_disabled": True,
        "permission_mode": "default",
        "allowed_tools": [],
        "forbidden_surfaces": [],
    }
    return {
        **safety,
        "permission_bridge_active": True,
        "permission_bridge_version": "harness_local_tool_request_v1",
        "permission_bridge_mode": "sdk",
        "permission_bridge_execution": "harness_owned_executor",
        "sdk_native_tool_execution_enabled": False,
        "supports_resume": False,
        "resume_mode": "context_replay_new_session",
        "safety": safety,
    }


def _pair_claude_v6(client: TestClient, session: Session) -> tuple[dict[str, Any], str]:
    _ensure_agent(session)
    created = client.post(
        "/api/agents/local-agent/pairing-tokens",
        headers=AUTH_HEADERS,
        json={
            "agent_id": "default",
            "scope": {
                "executable": True,
                "adapters": ["claude_code"],
                "permission_bridge": ["sdk"],
            },
        },
    )
    assert created.status_code == 201, created.text
    pairing = created.json()
    registered = client.post(
        "/api/agents/local-agent/connections/register",
        json={
            "pair_token": pairing["pair_token"],
            "pair_code": pairing["pair_code"],
            "adapter_kind": "claude_code",
            "display_name": "Claude Code V6 smoke",
            "protocol_version": "local-agent-v1",
            "bridge_version": "smoke-v6",
            "workspace_root": "/Users/luohao/private/claude-code-v6",
            "capabilities": _claude_v6_capabilities(),
            "risk_capabilities": [
                "workspace_read",
                "host_write_approval_required",
                "shell_approval_required",
                "git_approval_required",
                "pending_change",
                "command_lifecycle",
                "network",
                "secret_read",
            ],
            "metadata": {"workspace_identity_hash": "workspace-hash-v6"},
        },
    )
    assert registered.status_code == 201, registered.text
    payload = registered.json()
    return payload["connection"], payload["device_token"]


def _pair_claude_v5(client: TestClient, session: Session) -> tuple[dict[str, Any], str]:
    _ensure_agent(session)
    created = client.post(
        "/api/agents/local-agent/pairing-tokens",
        headers=AUTH_HEADERS,
        json={
            "agent_id": "default",
            "scope": {"executable": True, "adapters": ["claude_code"]},
        },
    )
    assert created.status_code == 201, created.text
    pairing = created.json()
    registered = client.post(
        "/api/agents/local-agent/connections/register",
        json={
            "pair_token": pairing["pair_token"],
            "pair_code": pairing["pair_code"],
            "adapter_kind": "claude_code",
            "display_name": "Claude Code V5 smoke",
            "protocol_version": "local-agent-v1",
            "bridge_version": "smoke-v6-v5",
            "workspace_root": "/Users/luohao/private/claude-code-v5",
            "capabilities": {"supports_streaming": True},
        },
    )
    assert registered.status_code == 201, registered.text
    payload = registered.json()
    return payload["connection"], payload["device_token"]


def _bind_and_lease(
    client: TestClient,
    *,
    connection_id: str,
    device_token: str,
    title: str,
    message: str,
    client_message_id: str,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    bridge_headers = {"X-Local-Agent-Device-Token": device_token}
    binding = client.post(
        f"/api/agents/local-agent/connections/{connection_id}/bindings",
        headers=AUTH_HEADERS,
        json={"title": title, "resume_mode": "native_resume"},
    )
    assert binding.status_code == 201, binding.text
    sent = client.post(
        f"/api/agents/local-agent/bindings/{binding.json()['id']}/messages",
        headers=AUTH_HEADERS,
        json={"content": message, "client_message_id": client_message_id},
    )
    assert sent.status_code == 202, sent.text
    pulled = client.get(
        "/api/agents/local-agent/bridge/tasks",
        headers=bridge_headers,
    )
    assert pulled.status_code == 200, pulled.text
    task = pulled.json()["items"][0]
    ack = client.post(
        f"/api/agents/local-agent/bridge/tasks/{task['id']}/ack",
        headers=bridge_headers,
        json={"status": "running"},
    )
    assert ack.status_code == 200, ack.text
    return binding.json(), sent.json(), task


def _bridge_headers(device_token: str) -> dict[str, str]:
    return {"X-Local-Agent-Device-Token": device_token}


def _assert_no_successful_tool_calls(session: Session) -> None:
    success_count = session.execute(
        select(ToolCall).where(ToolCall.status == "SUCCESS")
    ).scalars().all()
    assert success_count == []


def claude_sdk_unavailable() -> dict[str, Any]:
    client, session = _new_session()
    _ensure_agent(session)
    created = client.post(
        "/api/agents/local-agent/pairing-tokens",
        headers=AUTH_HEADERS,
        json={
            "agent_id": "default",
            "scope": {
                "executable": True,
                "adapters": ["claude_code"],
                "permission_bridge": ["sdk"],
            },
        },
    )
    assert created.status_code == 201, created.text
    pairing = created.json()
    rejected = client.post(
        "/api/agents/local-agent/connections/register",
        json={
            "pair_token": pairing["pair_token"],
            "pair_code": pairing["pair_code"],
            "adapter_kind": "claude_code",
            "protocol_version": "local-agent-v1",
            "workspace_root": "/Users/luohao/private/claude-sdk-unavailable",
            "capabilities": {"supports_streaming": True},
        },
    )
    assert rejected.status_code == 403, rejected.text
    token = session.get(LocalAgentPairingToken, pairing["id"])
    assert token is not None
    assert token.status == "active"
    assert token.consumed_at is None
    return _evidence(session, scenario="claude-sdk-unavailable")


def claude_permission_bridge_approved() -> dict[str, Any]:
    client, session = _new_session()
    connection, device_token = _pair_claude_v6(client, session)
    bridge_headers = {"X-Local-Agent-Device-Token": device_token}
    _binding, sent, task = _bind_and_lease(
        client,
        connection_id=connection["id"],
        device_token=device_token,
        title="Claude V6 approval smoke",
        message="run approved shell",
        client_message_id="smoke-v6-approved",
    )
    tool_request = client.post(
        "/api/agents/local-agent/bridge/tool-requests",
        headers=bridge_headers,
        json={
            "tool_request_id": "smoke-v6-run-shell",
            "bridge_task_id": task["id"],
            "tool_name": "run_shell",
            "input_json": {"command": "printf approved"},
            "execution_target": "host",
            "risk_level": "low",
            "permission_mode": "confirm",
        },
    )
    assert tool_request.status_code == 201, tool_request.text
    decision = tool_request.json()
    assert decision["decision"] == "approval_required"
    approved = client.post(
        f"/api/tasks/{sent['run_id']}/tool-approvals/{decision['approval_id']}/approve",
        headers=ADMIN_HEADERS,
        json={"reason": "smoke approve"},
    )
    assert approved.status_code == 202, approved.text
    polled = client.get(
        "/api/agents/local-agent/bridge/tool-requests/smoke-v6-run-shell/decision",
        headers=bridge_headers,
    )
    assert polled.status_code == 200, polled.text
    assert polled.json()["decision"] == "approved"
    assert polled.json()["executable"] is True
    for event_type, payload in (
        ("started", {"command": "printf approved"}),
        ("output", {"stdout": "approved"}),
        ("finished", {"status": "success", "exit_code": 0, "duration_ms": 1}),
    ):
        event = client.post(
            "/api/agents/local-agent/bridge/commands/smoke-v6-cmd-1/events",
            headers=bridge_headers,
            json={
                "event_id": f"smoke-v6-cmd-1-{event_type}",
                "tool_request_id": "smoke-v6-run-shell",
                "event_type": event_type,
                **payload,
            },
        )
        assert event.status_code == 202, event.text
    result = client.post(
        "/api/agents/local-agent/bridge/tool-requests/smoke-v6-run-shell/result",
        headers=bridge_headers,
        json={
            "event_id": "smoke-v6-run-shell-result",
            "status": "SUCCESS",
            "output_json": {"stdout": "approved"},
            "command_id": "smoke-v6-cmd-1",
            "duration_ms": 1,
        },
    )
    assert result.status_code == 202, result.text
    done = client.post(
        "/api/agents/local-agent/bridge/events",
        headers=bridge_headers,
        json={
            "event_id": "smoke-v6-run-shell-done",
            "bridge_task_id": task["id"],
            "event_type": "assistant_done",
            "content": "approved through Harness executor",
            "metadata": _claude_v6_safety_metadata(),
        },
    )
    assert done.status_code == 201, done.text
    session.expire_all()
    request_row = session.execute(
        select(LocalAgentToolRequest).where(
            LocalAgentToolRequest.tool_request_id == "smoke-v6-run-shell"
        )
    ).scalar_one()
    messages = list(
        session.execute(
            select(AgentMessage).where(AgentMessage.session_id == sent["agent_session_id"])
        ).scalars()
    )
    assert request_row.status == "succeeded"
    assert [message.role for message in messages] == ["user", "assistant"]
    assert messages[-1].content == "approved through Harness executor"
    return _evidence(
        session,
        scenario="claude-permission-bridge-approved",
        run_id=sent["run_id"],
    )


def claude_modified_approval() -> dict[str, Any]:
    client, session = _new_session()
    connection, device_token = _pair_claude_v6(client, session)
    bridge_headers = {"X-Local-Agent-Device-Token": device_token}
    _binding, sent, task = _bind_and_lease(
        client,
        connection_id=connection["id"],
        device_token=device_token,
        title="Claude V6 modified approval smoke",
        message="sanitize write through Harness",
        client_message_id="smoke-v6-modified",
    )
    stale_request = client.post(
        "/api/agents/local-agent/bridge/tool-requests",
        headers=bridge_headers,
        json={
            "tool_request_id": "smoke-v6-modified-write-stale",
            "bridge_task_id": task["id"],
            "tool_name": "write_file",
            "input_json": {"path": "notes.md", "content": "original\n"},
            "execution_target": "host",
            "risk_level": "low",
            "permission_mode": "confirm",
            "target_paths": ["notes.md"],
            "pending_change_preview": {
                "change_id": "smoke-v6-modified-original",
                "target_paths": ["notes.md"],
                "diff_sha256": "a" * 64,
            },
        },
    )
    assert stale_request.status_code == 201, stale_request.text
    decision = stale_request.json()
    assert decision["decision"] == "approval_required"

    modified = client.post(
        f"/api/tasks/{sent['run_id']}/tool-approvals/{decision['approval_id']}/modify",
        headers=ADMIN_HEADERS,
        json={
            "modified_input_json": {
                "path": "safe.md",
                "content": "sanitized\n",
            },
            "reason": "smoke sanitize write target",
        },
    )
    assert modified.status_code == 202, modified.text

    polled = client.get(
        "/api/agents/local-agent/bridge/tool-requests/smoke-v6-modified-write-stale/decision",
        headers=bridge_headers,
    )
    assert polled.status_code == 200, polled.text
    assert polled.json()["input_json"] == {"path": "safe.md", "content": "sanitized\n"}

    stale_result = client.post(
        "/api/agents/local-agent/bridge/tool-requests/smoke-v6-modified-write-stale/result",
        headers=bridge_headers,
        json={
            "event_id": "smoke-v6-modified-stale-result",
            "status": "SUCCESS",
            "output_json": {"path": "notes.md"},
            "duration_ms": 1,
            "change_id": "smoke-v6-modified-original",
            "diff_sha256": "a" * 64,
        },
    )
    assert stale_result.status_code == 409, stale_result.text

    refresh_request = client.post(
        "/api/agents/local-agent/bridge/tool-requests",
        headers=bridge_headers,
        json={
            "tool_request_id": "smoke-v6-modified-write",
            "bridge_task_id": task["id"],
            "tool_name": "write_file",
            "input_json": {"path": "notes.md", "content": "original\n"},
            "execution_target": "host",
            "risk_level": "low",
            "permission_mode": "confirm",
            "target_paths": ["notes.md"],
            "pending_change_preview": {
                "change_id": "smoke-v6-modified-original-2",
                "target_paths": ["notes.md"],
                "diff_sha256": "c" * 64,
            },
        },
    )
    assert refresh_request.status_code == 201, refresh_request.text
    refresh_decision = refresh_request.json()
    assert refresh_decision["decision"] == "approval_required"

    refreshed_approval = client.post(
        f"/api/tasks/{sent['run_id']}/tool-approvals/{refresh_decision['approval_id']}/modify",
        headers=ADMIN_HEADERS,
        json={
            "modified_input_json": {
                "path": "safe.md",
                "content": "sanitized\n",
            },
            "reason": "smoke sanitize write target refresh path",
        },
    )
    assert refreshed_approval.status_code == 202, refreshed_approval.text

    refreshed = client.post(
        "/api/agents/local-agent/bridge/tool-requests/smoke-v6-modified-write/pending-change-refresh",
        headers=bridge_headers,
        json={
            "input_json": {"path": "safe.md", "content": "sanitized\n"},
            "target_paths": ["safe.md"],
            "pending_change_preview": {
                "change_id": "smoke-v6-modified-sanitized",
                "target_paths": ["safe.md"],
                "diff_sha256": "b" * 64,
            },
        },
    )
    assert refreshed.status_code == 202, refreshed.text

    result = client.post(
        "/api/agents/local-agent/bridge/tool-requests/smoke-v6-modified-write/result",
        headers=bridge_headers,
        json={
            "event_id": "smoke-v6-modified-result",
            "status": "SUCCESS",
            "output_json": {"path": "safe.md"},
            "duration_ms": 1,
            "change_id": "smoke-v6-modified-sanitized",
            "diff_sha256": "b" * 64,
        },
    )
    assert result.status_code == 202, result.text

    done = client.post(
        "/api/agents/local-agent/bridge/events",
        headers=bridge_headers,
        json={
            "event_id": "smoke-v6-modified-done",
            "bridge_task_id": task["id"],
            "event_type": "assistant_done",
            "content": "modified approval executed through Harness",
            "metadata": _claude_v6_safety_metadata(),
        },
    )
    assert done.status_code == 201, done.text

    session.expire_all()
    request_row = session.execute(
        select(LocalAgentToolRequest).where(
            LocalAgentToolRequest.tool_request_id == "smoke-v6-modified-write"
        )
    ).scalar_one()
    pending_change = session.execute(
        select(LocalAgentPendingChange).where(
            LocalAgentPendingChange.local_agent_tool_request_id == request_row.id
        )
    ).scalar_one()
    assert request_row.status == "succeeded"
    assert request_row.decision_json["input_json"] == {"path": "safe.md", "content": "sanitized\n"}
    assert pending_change.change_id == "smoke-v6-modified-sanitized"
    assert pending_change.target_paths_json == ["safe.md"]
    assert pending_change.diff_sha256 == "b" * 64
    return _evidence(
        session,
        scenario="claude-modified-approval",
        run_id=sent["run_id"],
    )


def claude_approve_write() -> dict[str, Any]:
    client, session = _new_session()
    connection, device_token = _pair_claude_v6(client, session)
    bridge_headers = _bridge_headers(device_token)
    _binding, sent, task = _bind_and_lease(
        client,
        connection_id=connection["id"],
        device_token=device_token,
        title="Claude V6 approve write smoke",
        message="write after Harness approval",
        client_message_id="smoke-v6-approve-write",
    )
    requested = client.post(
        "/api/agents/local-agent/bridge/tool-requests",
        headers=bridge_headers,
        json={
            "tool_request_id": "smoke-v6-approve-write-tool",
            "bridge_task_id": task["id"],
            "tool_name": "write_file",
            "input_json": {"path": "notes.md", "content": "approved\n"},
            "execution_target": "host",
            "risk_level": "low",
            "permission_mode": "confirm",
            "target_paths": ["notes.md"],
            "pending_change_preview": {
                "change_id": "smoke-v6-approve-write-change",
                "target_paths": ["notes.md"],
                "diff_sha256": "d" * 64,
            },
        },
    )
    assert requested.status_code == 201, requested.text
    decision = requested.json()
    assert decision["decision"] == "approval_required"
    approved = client.post(
        f"/api/tasks/{sent['run_id']}/tool-approvals/{decision['approval_id']}/approve",
        headers=ADMIN_HEADERS,
        json={"reason": "approve write smoke"},
    )
    assert approved.status_code == 202, approved.text
    polled = client.get(
        "/api/agents/local-agent/bridge/tool-requests/smoke-v6-approve-write-tool/decision",
        headers=bridge_headers,
    )
    assert polled.status_code == 200, polled.text
    assert polled.json()["decision"] == "approved"
    result = client.post(
        "/api/agents/local-agent/bridge/tool-requests/smoke-v6-approve-write-tool/result",
        headers=bridge_headers,
        json={
            "event_id": "smoke-v6-approve-write-result",
            "status": "SUCCESS",
            "output_json": {"path": "notes.md"},
            "duration_ms": 1,
            "change_id": "smoke-v6-approve-write-change",
            "diff_sha256": "d" * 64,
        },
    )
    assert result.status_code == 202, result.text
    done = client.post(
        "/api/agents/local-agent/bridge/events",
        headers=bridge_headers,
        json={
            "event_id": "smoke-v6-approve-write-done",
            "bridge_task_id": task["id"],
            "event_type": "assistant_done",
            "content": "write approved through Harness executor",
            "metadata": _claude_v6_safety_metadata(),
        },
    )
    assert done.status_code == 201, done.text
    session.expire_all()
    request_row = session.execute(
        select(LocalAgentToolRequest).where(
            LocalAgentToolRequest.tool_request_id == "smoke-v6-approve-write-tool"
        )
    ).scalar_one()
    pending_change = session.execute(
        select(LocalAgentPendingChange).where(
            LocalAgentPendingChange.local_agent_tool_request_id == request_row.id
        )
    ).scalar_one()
    tool_call = session.get(ToolCall, decision["tool_call_id"])
    assert request_row.status == "succeeded"
    assert pending_change.status == "committed"
    assert tool_call is not None and tool_call.status == "SUCCESS"
    return _evidence(session, scenario="claude-approve-write", run_id=sent["run_id"])


def claude_reject_bash() -> dict[str, Any]:
    client, session = _new_session()
    connection, device_token = _pair_claude_v6(client, session)
    bridge_headers = _bridge_headers(device_token)
    _binding, sent, task = _bind_and_lease(
        client,
        connection_id=connection["id"],
        device_token=device_token,
        title="Claude V6 reject bash smoke",
        message="reject bash",
        client_message_id="smoke-v6-reject-bash",
    )
    requested = client.post(
        "/api/agents/local-agent/bridge/tool-requests",
        headers=bridge_headers,
        json={
            "tool_request_id": "smoke-v6-reject-bash-tool",
            "bridge_task_id": task["id"],
            "tool_name": "run_shell",
            "input_json": {"command": "printf denied"},
            "execution_target": "host",
            "risk_level": "low",
            "permission_mode": "confirm",
        },
    )
    assert requested.status_code == 201, requested.text
    decision = requested.json()
    assert decision["decision"] == "approval_required"
    rejected = client.post(
        f"/api/tasks/{sent['run_id']}/tool-approvals/{decision['approval_id']}/reject",
        headers=ADMIN_HEADERS,
        json={"reason": "reject bash smoke"},
    )
    assert rejected.status_code == 202, rejected.text
    polled = client.get(
        "/api/agents/local-agent/bridge/tool-requests/smoke-v6-reject-bash-tool/decision",
        headers=bridge_headers,
    )
    assert polled.status_code == 200, polled.text
    assert polled.json()["decision"] == "denied"
    assert polled.json()["executable"] is False
    late_result = client.post(
        "/api/agents/local-agent/bridge/tool-requests/smoke-v6-reject-bash-tool/result",
        headers=bridge_headers,
        json={
            "event_id": "smoke-v6-reject-bash-late-result",
            "status": "SUCCESS",
            "output_json": {"stdout": "should not land"},
            "command_id": "smoke-v6-reject-bash-cmd",
        },
    )
    assert late_result.status_code == 409, late_result.text
    session.expire_all()
    request_row = session.execute(
        select(LocalAgentToolRequest).where(
            LocalAgentToolRequest.tool_request_id == "smoke-v6-reject-bash-tool"
        )
    ).scalar_one()
    tool_call = session.get(ToolCall, decision["tool_call_id"])
    assert request_row.status == "denied"
    assert tool_call is not None and tool_call.status == "DENIED"
    assert session.execute(select(LocalAgentCommand)).scalars().all() == []
    _assert_no_successful_tool_calls(session)
    return _evidence(session, scenario="claude-reject-bash", run_id=sent["run_id"])


def claude_permission_bridge_cancel() -> dict[str, Any]:
    client, session = _new_session()
    connection, device_token = _pair_claude_v6(client, session)
    bridge_headers = {"X-Local-Agent-Device-Token": device_token}
    _binding, sent, task = _bind_and_lease(
        client,
        connection_id=connection["id"],
        device_token=device_token,
        title="Claude V6 cancel smoke",
        message="request write then cancel",
        client_message_id="smoke-v6-cancel",
    )
    tool_request = client.post(
        "/api/agents/local-agent/bridge/tool-requests",
        headers=bridge_headers,
        json={
            "tool_request_id": "smoke-v6-cancel-tool",
            "bridge_task_id": task["id"],
            "tool_name": "write_file",
            "input_json": {"path": "notes.md", "content": "new\n"},
            "execution_target": "host",
            "risk_level": "low",
            "permission_mode": "confirm",
            "target_paths": ["notes.md"],
            "pending_change_preview": {
                "change_id": "smoke-v6-cancel-change",
                "target_paths": ["notes.md"],
                "diff_sha256": "c" * 64,
            },
        },
    )
    assert tool_request.status_code == 201, tool_request.text
    decision = tool_request.json()
    local_request_id = session.execute(
        select(LocalAgentToolRequest.id).where(
            LocalAgentToolRequest.tool_request_id == "smoke-v6-cancel-tool"
        )
    ).scalar_one()
    session.add(
        LocalAgentCommand(
            organization_id=connection.get("organization_id"),
            connection_id=connection["id"],
            binding_id=task["binding_id"],
            bridge_task_id=task["id"],
            task_id=sent["run_id"],
            local_agent_tool_request_id=local_request_id,
            tool_request_id="smoke-v6-cancel-tool",
            command_id="smoke-v6-cancel-cmd",
            tool_name="write_file",
            command="write notes.md",
            status="pending",
            output_summary_json={},
            event_receipts_json={},
        )
    )
    session.commit()
    cancelled = client.post(f"/api/tasks/{sent['run_id']}/cancel", headers=AUTH_HEADERS)
    assert cancelled.status_code == 202, cancelled.text
    session.expire_all()
    request_row = session.execute(
        select(LocalAgentToolRequest).where(
            LocalAgentToolRequest.tool_request_id == "smoke-v6-cancel-tool"
        )
    ).scalar_one()
    approval = session.get(ToolApproval, decision["approval_id"])
    tool_call = session.get(ToolCall, decision["tool_call_id"])
    change = session.execute(select(LocalAgentPendingChange)).scalar_one()
    command = session.execute(
        select(LocalAgentCommand).where(LocalAgentCommand.command_id == "smoke-v6-cancel-cmd")
    ).scalar_one()
    bridge_task = session.get(LocalAgentBridgeTask, task["id"])
    run = session.get(Task, sent["run_id"])
    assert request_row.status == "cancelled"
    assert approval is not None and approval.status == "DENIED"
    assert tool_call is not None and tool_call.status == "CANCELLED"
    assert change.status == "denied"
    assert command.status == "cancelled"
    assert bridge_task is not None and bridge_task.status == "cancelled"
    assert run is not None and run.status == "CANCELLED"
    polled = client.get(
        "/api/agents/local-agent/bridge/tool-requests/smoke-v6-cancel-tool/decision",
        headers=bridge_headers,
    )
    assert polled.status_code == 200, polled.text
    assert polled.json()["decision"] == "cancelled"
    assert polled.json()["executable"] is False
    return _evidence(
        session,
        scenario="claude-permission-bridge-cancel",
        run_id=sent["run_id"],
    )


def claude_revoke_pending() -> dict[str, Any]:
    client, session = _new_session()
    connection, device_token = _pair_claude_v6(client, session)
    bridge_headers = _bridge_headers(device_token)
    _binding, sent, task = _bind_and_lease(
        client,
        connection_id=connection["id"],
        device_token=device_token,
        title="Claude V6 revoke pending smoke",
        message="request write then revoke connection",
        client_message_id="smoke-v6-revoke-pending",
    )
    requested = client.post(
        "/api/agents/local-agent/bridge/tool-requests",
        headers=bridge_headers,
        json={
            "tool_request_id": "smoke-v6-revoke-pending-tool",
            "bridge_task_id": task["id"],
            "tool_name": "write_file",
            "input_json": {"path": "notes.md", "content": "new\n"},
            "execution_target": "host",
            "risk_level": "low",
            "permission_mode": "confirm",
            "target_paths": ["notes.md"],
            "pending_change_preview": {
                "change_id": "smoke-v6-revoke-pending-change",
                "target_paths": ["notes.md"],
                "diff_sha256": "e" * 64,
            },
        },
    )
    assert requested.status_code == 201, requested.text
    decision = requested.json()
    local_request_id = session.execute(
        select(LocalAgentToolRequest.id).where(
            LocalAgentToolRequest.tool_request_id == "smoke-v6-revoke-pending-tool"
        )
    ).scalar_one()
    session.add(
        LocalAgentCommand(
            organization_id=connection.get("organization_id"),
            connection_id=connection["id"],
            binding_id=task["binding_id"],
            bridge_task_id=task["id"],
            task_id=sent["run_id"],
            local_agent_tool_request_id=local_request_id,
            tool_request_id="smoke-v6-revoke-pending-tool",
            command_id="smoke-v6-revoke-pending-cmd",
            tool_name="write_file",
            command="write notes.md",
            status="pending",
            output_summary_json={},
            event_receipts_json={},
        )
    )
    session.commit()
    revoked = client.post(
        f"/api/agents/local-agent/connections/{connection['id']}/revoke",
        headers=ADMIN_HEADERS,
    )
    assert revoked.status_code == 200, revoked.text
    session.expire_all()
    request_row = session.execute(
        select(LocalAgentToolRequest).where(
            LocalAgentToolRequest.tool_request_id == "smoke-v6-revoke-pending-tool"
        )
    ).scalar_one()
    approval = session.get(ToolApproval, decision["approval_id"])
    tool_call = session.get(ToolCall, decision["tool_call_id"])
    change = session.execute(select(LocalAgentPendingChange)).scalar_one()
    command = session.execute(
        select(LocalAgentCommand).where(
            LocalAgentCommand.command_id == "smoke-v6-revoke-pending-cmd"
        )
    ).scalar_one()
    bridge_task = session.get(LocalAgentBridgeTask, task["id"])
    run = session.get(Task, sent["run_id"])
    assert request_row.status == "cancelled"
    assert approval is not None and approval.status == "DENIED"
    assert tool_call is not None and tool_call.status == "CANCELLED"
    assert change.status == "denied"
    assert command.status == "cancelled"
    assert bridge_task is not None and bridge_task.status == "cancelled"
    assert run is not None and run.status == "CANCELLED"
    late_result = client.post(
        "/api/agents/local-agent/bridge/tool-requests/smoke-v6-revoke-pending-tool/result",
        headers=bridge_headers,
        json={
            "event_id": "smoke-v6-revoke-pending-late-result",
            "status": "SUCCESS",
            "output_json": {"changed": True},
            "change_id": "smoke-v6-revoke-pending-change",
            "diff_sha256": "e" * 64,
        },
    )
    assert late_result.status_code == 403, late_result.text
    _assert_no_successful_tool_calls(session)
    return _evidence(session, scenario="claude-revoke-pending", run_id=sent["run_id"])


def claude_approval_timeout() -> dict[str, Any]:
    client, session = _new_session()
    connection, device_token = _pair_claude_v6(client, session)
    bridge_headers = _bridge_headers(device_token)
    _binding, sent, task = _bind_and_lease(
        client,
        connection_id=connection["id"],
        device_token=device_token,
        title="Claude V6 approval timeout smoke",
        message="approval expires before execution",
        client_message_id="smoke-v6-approval-timeout",
    )
    requested = client.post(
        "/api/agents/local-agent/bridge/tool-requests",
        headers=bridge_headers,
        json={
            "tool_request_id": "smoke-v6-approval-timeout-tool",
            "bridge_task_id": task["id"],
            "tool_name": "write_file",
            "input_json": {"path": "notes.md", "content": "expired\n"},
            "execution_target": "host",
            "risk_level": "low",
            "permission_mode": "confirm",
            "target_paths": ["notes.md"],
            "pending_change_preview": {
                "change_id": "smoke-v6-approval-timeout-change",
                "target_paths": ["notes.md"],
                "diff_sha256": "f" * 64,
            },
        },
    )
    assert requested.status_code == 201, requested.text
    decision = requested.json()
    request_row = session.execute(
        select(LocalAgentToolRequest).where(
            LocalAgentToolRequest.tool_request_id == "smoke-v6-approval-timeout-tool"
        )
    ).scalar_one()
    request_row.decision_expires_at = utc_now() - timedelta(minutes=1)
    session.commit()
    too_late = client.post(
        f"/api/tasks/{sent['run_id']}/tool-approvals/{decision['approval_id']}/approve",
        headers=ADMIN_HEADERS,
        json={"reason": "too late"},
    )
    assert too_late.status_code == 409, too_late.text
    assert "expired" in too_late.text
    session.expire_all()
    request_row = session.execute(
        select(LocalAgentToolRequest).where(
            LocalAgentToolRequest.tool_request_id == "smoke-v6-approval-timeout-tool"
        )
    ).scalar_one()
    approval = session.get(ToolApproval, decision["approval_id"])
    tool_call = session.get(ToolCall, decision["tool_call_id"])
    change = session.execute(select(LocalAgentPendingChange)).scalar_one()
    assert request_row.status == "expired"
    assert approval is not None and approval.status == "EXPIRED"
    assert tool_call is not None and tool_call.status == "DENIED"
    assert change.status == "denied"
    _assert_no_successful_tool_calls(session)
    return _evidence(session, scenario="claude-approval-timeout", run_id=sent["run_id"])


def claude_bypass_attempt() -> dict[str, Any]:
    client, session = _new_session()
    connection, device_token = _pair_claude_v6(client, session)
    bridge_headers = _bridge_headers(device_token)
    _binding, sent, task = _bind_and_lease(
        client,
        connection_id=connection["id"],
        device_token=device_token,
        title="Claude V6 bypass attempt smoke",
        message="attempt unsafe bypass",
        client_message_id="smoke-v6-bypass",
    )
    unsafe_metadata = _claude_v6_safety_metadata()
    unsafe_safety = dict(unsafe_metadata["safety"])
    unsafe_safety.update(
        {
            "permission_mode": "bypassPermissions",
            "allowed_tools": ["Bash"],
            "forbidden_surfaces": ["mcp"],
        }
    )
    unsafe_metadata.update(unsafe_safety)
    unsafe_metadata["safety"] = unsafe_safety
    done = client.post(
        "/api/agents/local-agent/bridge/events",
        headers=bridge_headers,
        json={
            "event_id": "smoke-v6-bypass-done",
            "bridge_task_id": task["id"],
            "event_type": "assistant_done",
            "content": "unsafe bypass",
            "metadata": unsafe_metadata,
        },
    )
    assert done.status_code == 409, done.text
    legacy_tool_result = client.post(
        "/api/agents/local-agent/bridge/events",
        headers=bridge_headers,
        json={
            "event_id": "smoke-v6-bypass-legacy-tool",
            "bridge_task_id": task["id"],
            "event_type": "tool_result",
            "tool_name": "run_shell",
            "status": "SUCCESS",
            "input_json": {"command": "printf bypass"},
            "output_json": {"stdout": "bypass"},
            "metadata": {"permission_mode": "bypassPermissions"},
        },
    )
    assert legacy_tool_result.status_code == 409, legacy_tool_result.text
    session.expire_all()
    messages = list(
        session.execute(
            select(AgentMessage).where(AgentMessage.session_id == sent["agent_session_id"])
        ).scalars()
    )
    assert [message.role for message in messages] == ["user"]
    _assert_no_successful_tool_calls(session)
    return _evidence(session, scenario="claude-bypass-attempt", run_id=sent["run_id"])


def claude_api_failure_fail_closed() -> dict[str, Any]:
    previous_env = os.environ.get("HAO_CLAUDE_PERMISSION_BRIDGE_FAKE_SDK")
    os.environ["HAO_CLAUDE_PERMISSION_BRIDGE_FAKE_SDK"] = "1"
    try:
        hao_main_module = importlib.import_module("app.cli.hao.main")
        with TemporaryDirectory(prefix="harness-v6-smoke-") as tmp_name:
            tmp_path = Path(tmp_name)
            workspace = tmp_path / "workspace"
            workspace.mkdir()
            config = type(
                "Config",
                (),
                {
                    "home": tmp_path / "hao-home",
                    "session_db_path": tmp_path / "hao.db",
                    "sessions_dir": tmp_path / "sessions",
                },
            )()
            root_ref = hao_main_module._save_bridge_workspace_root(config, workspace)
            state = {
                "adapter_kind": "claude_code",
                "permission_bridge": "sdk",
                "workspace_root_ref": root_ref,
                "workspace_identity_hash": hao_main_module._workspace_identity_hash(
                    workspace,
                    adapter_kind="claude_code",
                ),
            }
            calls: list[str] = []

            class FakeClient:
                def create_local_agent_tool_request(
                    self,
                    *,
                    device_token: str,
                    payload: dict,
                ) -> dict:
                    del device_token
                    calls.append("tool_request")
                    return {
                        "tool_request_id": payload["tool_request_id"],
                        "bridge_task_id": payload["bridge_task_id"],
                        "tool_call_id": "server-claude-tool",
                        "approval_id": "approval-claude-tool",
                        "decision": "approval_required",
                        "status": "approval_required",
                        "executable": False,
                        "server_execution": False,
                        "tool_name": payload["tool_name"],
                        "input_json": payload["input_json"],
                        "reason": "approval required",
                        "decision_json": {},
                        "expires_at": None,
                    }

                def get_local_agent_tool_decision(
                    self,
                    *,
                    device_token: str,
                    tool_request_id: str,
                ) -> dict:
                    del device_token, tool_request_id
                    calls.append("decision")
                    raise RuntimeError("decision api unavailable")

            original_execute = hao_main_module.execute_local_tool
            original_poll_seconds = hao_main_module.CLAUDE_PERMISSION_DECISION_POLL_SECONDS

            def fail_local_tool(*args, **kwargs):
                del args, kwargs
                raise AssertionError("SDK bridge must fail closed before local execution")

            hao_main_module.execute_local_tool = fail_local_tool
            hao_main_module.CLAUDE_PERMISSION_DECISION_POLL_SECONDS = 0.001
            try:
                result = hao_main_module._run_claude_permission_bridge_sdk(
                    client=FakeClient(),
                    device_token="device-token-claude",
                    bridge_task_id="bridge-task-claude",
                    config=config,
                    state=state,
                    payload={
                        "message": "fake claude",
                        "agent_id": "default",
                        "run_id": "run-claude-v6",
                        "workspace_identity_hash": state["workspace_identity_hash"],
                        "test_fixture_mode": "claude_permission_bridge_fake_sdk",
                        "fake_sdk_events": [
                            {
                                "type": "tool_request",
                                "tool_name": "Bash",
                                "tool_use_id": "bash-1",
                                "input": {"command": "printf model-proposed"},
                            },
                        ],
                    },
                )
            finally:
                hao_main_module.execute_local_tool = original_execute
                hao_main_module.CLAUDE_PERMISSION_DECISION_POLL_SECONDS = original_poll_seconds
            assert result.status == "error"
            assert result.error_message is not None
            assert "approval polling failed" in result.error_message
            assert calls == ["tool_request", "decision"]
    finally:
        if previous_env is None:
            os.environ.pop("HAO_CLAUDE_PERMISSION_BRIDGE_FAKE_SDK", None)
        else:
            os.environ["HAO_CLAUDE_PERMISSION_BRIDGE_FAKE_SDK"] = previous_env
    client, session = _new_session()
    _ensure_agent(session)
    return _evidence(session, scenario="claude-api-failure-fail-closed")


def claude_v5_heartbeat_upgrade_denied() -> dict[str, Any]:
    client, session = _new_session()
    connection, device_token = _pair_claude_v5(client, session)
    heartbeat = client.post(
        f"/api/agents/local-agent/connections/{connection['id']}/heartbeat",
        headers={"X-Local-Agent-Device-Token": device_token},
        json={
            "status": "online",
            "protocol_version": "local-agent-v1",
            "bridge_version": "smoke-v6-upgrade",
            "capabilities": _claude_v6_capabilities(),
        },
    )
    assert heartbeat.status_code == 200, heartbeat.text
    capabilities = heartbeat.json()["connection"]["capabilities_json"]
    assert capabilities["enabled_in_v6"] is False
    assert capabilities["host_tools_authorized"] is False
    assert capabilities["permission_bridge"] is None
    _binding, _sent, task = _bind_and_lease(
        client,
        connection_id=connection["id"],
        device_token=device_token,
        title="Claude V5 heartbeat deny",
        message="try to self-upgrade",
        client_message_id="smoke-v6-heartbeat-deny",
    )
    denied = client.post(
        "/api/agents/local-agent/bridge/tool-requests",
        headers={"X-Local-Agent-Device-Token": device_token},
        json={
            "tool_request_id": "smoke-v6-v5-upgrade-tool",
            "bridge_task_id": task["id"],
            "tool_name": "run_shell",
            "input_json": {"command": "printf denied"},
            "execution_target": "host",
            "risk_level": "low",
            "permission_mode": "confirm",
        },
    )
    assert denied.status_code == 409, denied.text
    return _evidence(session, scenario="claude-v5-heartbeat-upgrade-denied")


def _evidence(session: Session, *, scenario: str, run_id: str | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "scenario": scenario,
        "connections": len(session.execute(select(LocalAgentConnection)).scalars().all()),
        "bridge_tasks": len(session.execute(select(LocalAgentBridgeTask)).scalars().all()),
        "receipts": len(session.execute(select(LocalAgentBridgeEventReceipt)).scalars().all()),
        "messages": len(session.execute(select(AgentMessage)).scalars().all()),
        "tool_calls": len(session.execute(select(ToolCall)).scalars().all()),
        "events": len(session.execute(select(AgentEvent)).scalars().all()),
    }
    if run_id is not None:
        payload["run_id"] = run_id
    return payload


SCENARIOS = {
    "claude-api-failure-fail-closed": claude_api_failure_fail_closed,
    "claude-approval-timeout": claude_approval_timeout,
    "claude-approve-write": claude_approve_write,
    "claude-bypass-attempt": claude_bypass_attempt,
    "claude-sdk-unavailable": claude_sdk_unavailable,
    "claude-modified-approval": claude_modified_approval,
    "claude-permission-bridge-approved": claude_permission_bridge_approved,
    "claude-permission-bridge-cancel": claude_permission_bridge_cancel,
    "claude-reject-bash": claude_reject_bash,
    "claude-revoke-pending": claude_revoke_pending,
    "claude-v5-heartbeat-upgrade-denied": claude_v5_heartbeat_upgrade_denied,
}


def main() -> int:
    parser = argparse.ArgumentParser(description="Deterministic Local Agent V6 smoke scenarios.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--scenario", choices=sorted(SCENARIOS))
    group.add_argument("--all", action="store_true", help="Run every deterministic V6 smoke scenario.")
    args = parser.parse_args()
    scenario_names = sorted(SCENARIOS) if args.all else [args.scenario]
    for scenario_name in scenario_names:
        try:
            evidence = SCENARIOS[scenario_name]()
            print(f"PASS local-agent-v6 {evidence}")
        finally:
            app.dependency_overrides.clear()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
