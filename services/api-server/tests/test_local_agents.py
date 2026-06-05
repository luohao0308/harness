import json
import sys
from datetime import timedelta

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    AdminAuditEvent,
    Agent,
    AgentEvent,
    AgentMessage,
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
from app.main import app
from app.tools.capabilities import CapabilityRegistry
from tests.conftest import AUTH_HEADERS

ADMIN_HEADERS = {"Authorization": "Bearer dev-admin-token"}
OPERATOR_HEADERS = {"Authorization": "Bearer dev-operator-token"}
OTHER_ORG_HEADERS = {"Authorization": "Bearer dev-other-org-token"}


def _ensure_agent(session: Session, agent_id: str = "default") -> Agent:
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
            attached_by="test",
        )
        session.commit()
        return agent
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
        attached_by="test",
    )
    session.commit()
    return agent


def _create_limited_agent(session: Session) -> Agent:
    agent = Agent(
        id="limited-local-agent",
        organization_id="dev-org",
        name="Limited Local Agent",
        description="Only read capability is attached.",
        role="assistant",
        status="ACTIVE",
        model_provider="default",
        model_name="default",
        system_prompt="Help the user.",
        tools_json=["read_file"],
        routing_tags=["workspace"],
        max_parallel_assignments=1,
    )
    session.add(agent)
    session.flush()
    CapabilityRegistry(session, agent.organization_id).backfill_agent_attachments(
        agent.id,
        attached_by="test",
    )
    session.commit()
    return agent


def _registered_connection(client: TestClient, db_session: Session) -> tuple[dict, str]:
    _ensure_agent(db_session)
    created = client.post(
        "/api/agents/local-agent/pairing-tokens",
        headers=AUTH_HEADERS,
        json={"agent_id": "default", "ttl_minutes": 5},
    )
    assert created.status_code == 201, created.text
    pairing = created.json()
    registered = client.post(
        "/api/agents/local-agent/connections/register",
        json={
            "pair_token": pairing["pair_token"],
            "pair_code": pairing["pair_code"],
            "adapter_kind": "hao",
            "display_name": "hao Local",
            "protocol_version": "local-agent-v1",
            "bridge_version": "0.1.0",
            "workspace_root": "/Users/luohao/projects/demo",
            "capabilities": {"supports_resume": True, "supports_streaming": True},
            "risk_capabilities": ["host_read", "host_write", "shell"],
        },
    )
    assert registered.status_code == 201, registered.text
    payload = registered.json()
    return payload["connection"], payload["device_token"]


def _registered_connection_for_agent(
    client: TestClient,
    agent_id: str,
) -> tuple[dict, str]:
    created = client.post(
        "/api/agents/local-agent/pairing-tokens",
        headers=AUTH_HEADERS,
        json={"agent_id": agent_id, "ttl_minutes": 5},
    )
    assert created.status_code == 201, created.text
    pairing = created.json()
    registered = client.post(
        "/api/agents/local-agent/connections/register",
        json={
            "pair_token": pairing["pair_token"],
            "pair_code": pairing["pair_code"],
            "adapter_kind": "hao",
            "display_name": "hao Local",
            "protocol_version": "local-agent-v1",
            "bridge_version": "0.1.0",
            "workspace_root": "/Users/luohao/projects/demo",
            "capabilities": {"supports_resume": True, "supports_streaming": True},
            "risk_capabilities": ["host_read", "host_write", "shell"],
        },
    )
    assert registered.status_code == 201, registered.text
    payload = registered.json()
    return payload["connection"], payload["device_token"]


def _claude_v6_capabilities(**overrides: object) -> dict:
    capabilities = {
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
    capabilities.update(overrides)
    return capabilities


def _claude_v6_safety_metadata(**overrides: object) -> dict:
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
    metadata = {
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
    metadata.update(overrides)
    return metadata


def _registered_claude_v6_connection(
    client: TestClient,
    db_session: Session,
    *,
    capabilities: dict | None = None,
) -> tuple[dict, str]:
    _ensure_agent(db_session)
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
            "protocol_version": "local-agent-v1",
            "workspace_root": "/Users/luohao/projects/claude-demo",
            "capabilities": capabilities or _claude_v6_capabilities(),
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
            "metadata": {"workspace_identity_hash": "hash-claude-v6"},
        },
    )
    assert registered.status_code == 201, registered.text
    payload = registered.json()
    return payload["connection"], payload["device_token"]


def _leased_bridge_task(
    client: TestClient,
    connection_id: str,
    device_token: str,
    *,
    binding_title: str = "Local coding session",
    message: str = "run local task",
    client_message_id: str = "msg-lease",
) -> tuple[dict, dict]:
    bridge_headers = {"X-Local-Agent-Device-Token": device_token}
    binding = client.post(
        f"/api/agents/local-agent/connections/{connection_id}/bindings",
        headers=AUTH_HEADERS,
        json={"title": binding_title, "resume_mode": "native_resume"},
    )
    assert binding.status_code == 201, binding.text
    sent = client.post(
        f"/api/agents/local-agent/bindings/{binding.json()['id']}/messages",
        headers=AUTH_HEADERS,
        json={"content": message, "client_message_id": client_message_id},
    )
    assert sent.status_code == 202, sent.text
    pull = client.get("/api/agents/local-agent/bridge/tasks", headers=bridge_headers)
    assert pull.status_code == 200, pull.text
    task = pull.json()["items"][0]
    ack = client.post(
        f"/api/agents/local-agent/bridge/tasks/{task['id']}/ack",
        headers=bridge_headers,
        json={"status": "running"},
    )
    assert ack.status_code == 200, ack.text
    return sent.json(), task


def _approved_local_tool_request(
    client: TestClient,
    *,
    bridge_headers: dict[str, str],
    task: dict,
    run_id: str,
    tool_request_id: str,
    tool_name: str = "run_shell",
    input_json: dict | None = None,
    pending_change_preview: dict | None = None,
    target_paths: list[str] | None = None,
) -> dict:
    payload = {
        "tool_request_id": tool_request_id,
        "bridge_task_id": task["id"],
        "tool_name": tool_name,
        "input_json": input_json or {"command": "printf ok"},
        "execution_target": "host",
        "risk_level": "low",
        "permission_mode": "full-auto",
        "metadata": {
            "run_id": run_id,
            "agent_id": "default",
            "local_session_id": task.get("agent_session_id"),
            "command": "act",
            "tool_call_id": f"model-{tool_request_id}",
        },
    }
    if pending_change_preview is not None:
        payload["pending_change_preview"] = pending_change_preview
    if target_paths is not None:
        payload["target_paths"] = target_paths
    tool_request = client.post(
        "/api/agents/local-agent/bridge/tool-requests",
        headers=bridge_headers,
        json=payload,
    )
    assert tool_request.status_code == 201, tool_request.text
    decision = tool_request.json()
    assert decision["decision"] == "approval_required"
    approved = client.post(
        f"/api/tasks/{run_id}/tool-approvals/{decision['approval_id']}/approve",
        headers=ADMIN_HEADERS,
        json={"reason": "approve local test tool"},
    )
    assert approved.status_code == 202, approved.text
    return decision


def _start_and_finish_command(
    client: TestClient,
    *,
    bridge_headers: dict[str, str],
    tool_request_id: str,
    command_id: str,
    status_value: str = "success",
    command: str = "printf ok",
    tool_name: str = "run_shell",
    retry_of_command_id: str | None = None,
) -> None:
    start_payload = {
        "event_id": f"{command_id}-start",
        "tool_request_id": tool_request_id,
        "event_type": "started",
        "tool_name": tool_name,
        "command": command,
    }
    if retry_of_command_id is not None:
        start_payload["retry_of_command_id"] = retry_of_command_id
    started = client.post(
        f"/api/agents/local-agent/bridge/commands/{command_id}/events",
        headers=bridge_headers,
        json=start_payload,
    )
    assert started.status_code == 202, started.text
    finished = client.post(
        f"/api/agents/local-agent/bridge/commands/{command_id}/events",
        headers=bridge_headers,
        json={
            "event_id": f"{command_id}-finish",
            "tool_request_id": tool_request_id,
            "event_type": "finished",
            "status": status_value,
            "exit_code": 0 if status_value == "success" else 1,
            "duration_ms": 1,
        },
    )
    assert finished.status_code == 202, finished.text


def test_local_agent_pairing_registers_with_hashed_single_use_token(
    db_session: Session,
) -> None:
    client = TestClient(app)
    _ensure_agent(db_session)

    created = client.post(
        "/api/agents/local-agent/pairing-tokens",
        headers=AUTH_HEADERS,
        json={"agent_id": "default", "ttl_minutes": 5},
    )
    assert created.status_code == 201, created.text
    payload = created.json()
    assert payload["pair_token"]
    assert payload["pair_token"] in payload["command"]

    token = db_session.get(LocalAgentPairingToken, payload["id"])
    assert token is not None
    assert token.token_hash != payload["pair_token"]
    assert len(token.token_hash) == 64

    registered = client.post(
        "/api/agents/local-agent/connections/register",
        json={
            "pair_token": payload["pair_token"],
            "pair_code": payload["pair_code"],
            "adapter_kind": "fake",
            "display_name": "Fake Local",
            "protocol_version": "local-agent-v1",
        },
    )
    assert registered.status_code == 201, registered.text
    assert registered.json()["device_token"]
    assert registered.json()["connection"]["workspace_root"] is None

    reused = client.post(
        "/api/agents/local-agent/connections/register",
        json={
            "pair_token": payload["pair_token"],
            "pair_code": payload["pair_code"],
            "adapter_kind": "fake",
            "protocol_version": "local-agent-v1",
        },
    )
    assert reused.status_code == 410
    db_session.refresh(token)
    assert token.status == "consumed"
    connection = db_session.execute(select(LocalAgentConnection)).scalar_one()
    assert connection.device_token_hash != registered.json()["device_token"]
    audit_actions = {
        event.action
        for event in db_session.execute(
            select(AdminAuditEvent).where(AdminAuditEvent.event_type == "LOCAL_AGENT_LIFECYCLE")
        ).scalars()
    }
    assert audit_actions >= {
        "local_agent.pairing.create",
        "local_agent.connection.register",
    }


def test_local_agent_v5_supports_restricted_assistant_adapters(
    db_session: Session,
) -> None:
    client = TestClient(app)
    _ensure_agent(db_session)

    expected = {
        "codex": {
            "display_name": "Codex CLI",
            "workspace_identity_hash": "hash-codex",
            "enabled_flag": "enabled_in_v4",
            "risk_capabilities": ["workspace_read_constrained", "host_write", "shell"],
            "normalized_risk_capabilities": ["workspace_read_constrained"],
        },
        "claude_code": {
            "display_name": "Claude Code",
            "workspace_identity_hash": "hash-claude",
            "enabled_flag": "enabled_in_v5",
            "risk_capabilities": [
                "workspace_read_constrained",
                "host_write",
                "shell",
                "git",
                "network",
                "secret_read",
                "mcp",
                "plugin",
                "hook",
                "subagent",
            ],
            "normalized_risk_capabilities": [],
        },
    }

    for adapter_kind, config in expected.items():
        created = client.post(
            "/api/agents/local-agent/pairing-tokens",
            headers=AUTH_HEADERS,
            json={"agent_id": "default"},
        ).json()
        registered = client.post(
            "/api/agents/local-agent/connections/register",
            json={
                "pair_token": created["pair_token"],
                "pair_code": created["pair_code"],
                "adapter_kind": adapter_kind,
                "display_name": config["display_name"],
                "protocol_version": "local-agent-v1",
                "workspace_root": "/Users/luohao/private-demo",
                "capabilities": {
                    "supports_streaming": True,
                    "supports_resume": True,
                    "supports_cancel": True,
                    "host_tools_authorized": True,
                    "deterministic_session_id": False,
                },
                "risk_capabilities": config["risk_capabilities"],
                "metadata": {"workspace_identity_hash": config["workspace_identity_hash"]},
            },
        )

        assert registered.status_code == 201, registered.text
        connection = registered.json()["connection"]
        assert connection["adapter_kind"] == adapter_kind
        assert connection["capabilities_json"][config["enabled_flag"]] is True
        assert connection["capabilities_json"]["supports_resume"] is False
        assert connection["capabilities_json"]["supports_cancel"] is False
        assert connection["capabilities_json"]["host_tools_authorized"] is False
        assert connection["capabilities_json"]["resume_mode"] == "context_replay_new_session"
        if adapter_kind == "claude_code":
            assert (
                connection["capabilities_json"]["execution_mode"]
                == "headless_bare_no_session_no_tools"
            )
        assert connection["risk_capabilities_json"] == config["normalized_risk_capabilities"]
        assert connection["workspace_root"] == ".../private-demo"
        row = db_session.get(LocalAgentConnection, connection["id"])
        assert row is not None
        assert row.metadata_json["workspace_identity_hash"] == config["workspace_identity_hash"]


def test_local_agent_v4_adapter_scope_rejects_codex_before_consuming_token(
    db_session: Session,
) -> None:
    client = TestClient(app)
    _ensure_agent(db_session)
    created_response = client.post(
        "/api/agents/local-agent/pairing-tokens",
        headers=AUTH_HEADERS,
        json={"agent_id": "default", "scope": {"executable": True, "adapters": ["hao"]}},
    )
    assert created_response.status_code == 201, created_response.text
    created = created_response.json()

    rejected = client.post(
        "/api/agents/local-agent/connections/register",
        json={
            "pair_token": created["pair_token"],
            "pair_code": created["pair_code"],
            "adapter_kind": "codex",
            "protocol_version": "local-agent-v1",
        },
    )
    assert rejected.status_code == 403, rejected.text
    token = db_session.get(LocalAgentPairingToken, created["id"])
    assert token is not None
    assert token.status == "active"
    assert token.consumed_at is None

    accepted = client.post(
        "/api/agents/local-agent/connections/register",
        json={
            "pair_token": created["pair_token"],
            "pair_code": created["pair_code"],
            "adapter_kind": "hao",
            "protocol_version": "local-agent-v1",
        },
    )
    assert accepted.status_code == 201, accepted.text
    db_session.refresh(token)
    assert token.status == "consumed"


def test_local_agent_v5_adapter_scope_rejects_claude_code_before_consuming_token(
    db_session: Session,
) -> None:
    client = TestClient(app)
    _ensure_agent(db_session)
    created_response = client.post(
        "/api/agents/local-agent/pairing-tokens",
        headers=AUTH_HEADERS,
        json={"agent_id": "default", "scope": {"executable": True, "adapters": ["codex"]}},
    )
    assert created_response.status_code == 201, created_response.text
    created = created_response.json()

    rejected = client.post(
        "/api/agents/local-agent/connections/register",
        json={
            "pair_token": created["pair_token"],
            "pair_code": created["pair_code"],
            "adapter_kind": "claude_code",
            "protocol_version": "local-agent-v1",
        },
    )
    assert rejected.status_code == 403, rejected.text
    token = db_session.get(LocalAgentPairingToken, created["id"])
    assert token is not None
    assert token.status == "active"
    assert token.consumed_at is None

    accepted = client.post(
        "/api/agents/local-agent/connections/register",
        json={
            "pair_token": created["pair_token"],
            "pair_code": created["pair_code"],
            "adapter_kind": "codex",
            "protocol_version": "local-agent-v1",
        },
    )
    assert accepted.status_code == 201, accepted.text
    db_session.refresh(token)
    assert token.status == "consumed"


def test_local_agent_v4_custom_scope_requires_explicit_adapters_before_consuming_token(
    db_session: Session,
) -> None:
    client = TestClient(app)
    _ensure_agent(db_session)
    created_response = client.post(
        "/api/agents/local-agent/pairing-tokens",
        headers=AUTH_HEADERS,
        json={"agent_id": "default", "scope": {"executable": True}},
    )
    assert created_response.status_code == 201, created_response.text
    created = created_response.json()

    rejected = client.post(
        "/api/agents/local-agent/connections/register",
        json={
            "pair_token": created["pair_token"],
            "pair_code": created["pair_code"],
            "adapter_kind": "codex",
            "protocol_version": "local-agent-v1",
        },
    )

    assert rejected.status_code == 403, rejected.text
    assert "explicit adapter scope" in rejected.text
    token = db_session.get(LocalAgentPairingToken, created["id"])
    assert token is not None
    assert token.status == "active"
    assert token.consumed_at is None


def test_local_agent_v4_pairing_command_is_adapter_scoped(
    db_session: Session,
) -> None:
    client = TestClient(app)
    _ensure_agent(db_session)

    default_pairing = client.post(
        "/api/agents/local-agent/pairing-tokens",
        headers=AUTH_HEADERS,
        json={"agent_id": "default"},
    )
    assert default_pairing.status_code == 201, default_pairing.text
    assert "--adapter codex" not in default_pairing.json()["command"]

    codex_pairing = client.post(
        "/api/agents/local-agent/pairing-tokens",
        headers=AUTH_HEADERS,
        json={
            "agent_id": "default",
            "scope": {"executable": True, "adapters": ["codex"]},
        },
    )
    assert codex_pairing.status_code == 201, codex_pairing.text
    assert "--adapter codex" in codex_pairing.json()["command"]

    claude_pairing = client.post(
        "/api/agents/local-agent/pairing-tokens",
        headers=AUTH_HEADERS,
        json={
            "agent_id": "default",
            "scope": {"executable": True, "adapters": ["claude_code"]},
        },
    )
    assert claude_pairing.status_code == 201, claude_pairing.text
    assert "--adapter claude_code" in claude_pairing.json()["command"]


def test_local_agent_v6_claude_pairing_command_includes_permission_bridge(
    db_session: Session,
) -> None:
    client = TestClient(app)
    _ensure_agent(db_session)

    pairing = client.post(
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

    assert pairing.status_code == 201, pairing.text
    command = pairing.json()["command"]
    assert "--adapter claude_code" in command
    assert "--permission-bridge sdk" in command


def test_local_agent_v5_claude_done_requires_server_side_safety_proof(
    db_session: Session,
) -> None:
    client = TestClient(app)
    _ensure_agent(db_session)
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
            "protocol_version": "local-agent-v1",
            "capabilities": {"supports_streaming": True, "supports_resume": True},
            "metadata": {"workspace_identity_hash": "hash-claude"},
        },
    )
    assert registered.status_code == 201, registered.text
    connection = registered.json()["connection"]
    device_token = registered.json()["device_token"]
    sent, task = _leased_bridge_task(
        client,
        connection["id"],
        device_token,
        client_message_id="claude-safety-proof-test",
    )
    bridge_headers = {"X-Local-Agent-Device-Token": device_token}

    missing_proof = client.post(
        "/api/agents/local-agent/bridge/events",
        headers=bridge_headers,
        json={
            "event_id": "claude-done-missing-proof",
            "bridge_task_id": task["id"],
            "event_type": "assistant_done",
            "content": "unsafe success",
            "metadata": {"adapter_kind": "claude_code"},
        },
    )
    assert missing_proof.status_code == 409, missing_proof.text
    assert "system/init safety proof" in missing_proof.text
    assert (
        db_session.execute(
            select(LocalAgentBridgeEventReceipt).where(
                LocalAgentBridgeEventReceipt.event_id == "claude-done-missing-proof"
            )
        ).scalar_one_or_none()
        is None
    )
    messages = db_session.execute(
        select(AgentMessage).where(AgentMessage.session_id == sent["agent_session_id"])
    ).scalars()
    assert [message.role for message in messages] == ["user"]

    unsafe_tools_count = client.post(
        "/api/agents/local-agent/bridge/events",
        headers=bridge_headers,
        json={
            "event_id": "claude-done-tools-present",
            "bridge_task_id": task["id"],
            "event_type": "assistant_done",
            "content": "unsafe success",
            "metadata": {
                "adapter_kind": "claude_code",
                "system_init_safe": True,
                "tools_count": 1,
                "mcp_servers_count": 0,
            },
        },
    )
    assert unsafe_tools_count.status_code == 409, unsafe_tools_count.text

    accepted = client.post(
        "/api/agents/local-agent/bridge/events",
        headers=bridge_headers,
        json={
            "event_id": "claude-done-safe-proof",
            "bridge_task_id": task["id"],
            "event_type": "assistant_done",
            "content": "safe success",
            "metadata": {
                "adapter_kind": "claude_code",
                "system_init_safe": True,
                "tools_count": 0,
                "mcp_servers_count": 0,
            },
        },
    )
    assert accepted.status_code == 201, accepted.text
    db_session.expire_all()
    bridge_task = db_session.get(LocalAgentBridgeTask, task["id"])
    assert bridge_task is not None
    assert bridge_task.status == "completed"
    messages = list(
        db_session.execute(
            select(AgentMessage).where(AgentMessage.session_id == sent["agent_session_id"])
        ).scalars()
    )
    assert [message.role for message in messages] == ["user", "assistant"]
    assert messages[-1].content == "safe success"


def test_local_agent_v6_claude_registration_requires_permission_bridge_capability(
    db_session: Session,
) -> None:
    client = TestClient(app)
    _ensure_agent(db_session)

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
            "capabilities": _claude_v6_capabilities(allowed_tools=["Bash"]),
        },
    )
    assert rejected.status_code == 403, rejected.text
    token = db_session.get(LocalAgentPairingToken, pairing["id"])
    assert token is not None
    assert token.status == "active"

    connection, _device_token = _registered_claude_v6_connection(client, db_session)
    capabilities = connection["capabilities_json"]
    assert capabilities["enabled_in_v6"] is True
    assert capabilities["host_tools_authorized"] is True
    assert capabilities["supports_cancel"] is True
    assert capabilities["permission_bridge"] == "harness_local_tool_request_v1"
    assert capabilities["execution_mode"] == "agent_sdk_intent_capture_harness_executor"
    assert capabilities["permission_bridge_execution"] == "harness_owned_executor"
    assert capabilities["sdk_native_tool_execution_enabled"] is False
    assert capabilities["allowed_tools"] == []
    assert connection["risk_capabilities_json"] == [
        "workspace_read",
        "host_write_approval_required",
        "shell_approval_required",
        "git_approval_required",
        "pending_change",
        "command_lifecycle",
    ]


def test_local_agent_v6_claude_host_tool_protocol_is_capability_gated(
    db_session: Session,
) -> None:
    client = TestClient(app)
    _ensure_agent(db_session)

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
            "protocol_version": "local-agent-v1",
            "capabilities": {"supports_streaming": True},
        },
    )
    assert registered.status_code == 201, registered.text
    connection = registered.json()["connection"]
    device_token = registered.json()["device_token"]
    _sent, task = _leased_bridge_task(
        client,
        connection["id"],
        device_token,
        client_message_id="claude-v5-host-tool-denied",
    )
    bridge_headers = {"X-Local-Agent-Device-Token": device_token}

    denied = client.post(
        "/api/agents/local-agent/bridge/tool-requests",
        headers=bridge_headers,
        json={
            "tool_request_id": "claude-v5-tool-req",
            "bridge_task_id": task["id"],
            "tool_name": "run_shell",
            "input_json": {"command": "printf denied"},
            "execution_target": "host",
            "risk_level": "low",
            "permission_mode": "confirm",
        },
    )
    assert denied.status_code == 409, denied.text
    assert "cannot use local host tool protocol" in denied.text

    connection, device_token = _registered_claude_v6_connection(client, db_session)
    sent, task = _leased_bridge_task(
        client,
        connection["id"],
        device_token,
        client_message_id="claude-v6-host-tool-allowed",
    )
    bridge_headers = {"X-Local-Agent-Device-Token": device_token}
    allowed = client.post(
        "/api/agents/local-agent/bridge/tool-requests",
        headers=bridge_headers,
        json={
            "tool_request_id": "claude-v6-tool-req",
            "bridge_task_id": task["id"],
            "tool_name": "run_shell",
            "input_json": {"command": "printf ok"},
            "execution_target": "host",
            "risk_level": "low",
            "permission_mode": "confirm",
        },
    )
    assert allowed.status_code == 201, allowed.text
    assert allowed.json()["decision"] == "approval_required"
    assert allowed.json()["approval_id"]
    assert sent["run_id"]


def test_local_agent_v6_claude_heartbeat_cannot_self_upgrade_v5_connection(
    db_session: Session,
) -> None:
    client = TestClient(app)
    _ensure_agent(db_session)

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
            "protocol_version": "local-agent-v1",
            "bridge_version": "0.1.0",
            "workspace_root": "/Users/luohao/projects/claude-v5",
            "capabilities": {"supports_streaming": True},
        },
    )
    assert registered.status_code == 201, registered.text
    connection = registered.json()["connection"]
    device_token = registered.json()["device_token"]

    heartbeat = client.post(
        f"/api/agents/local-agent/connections/{connection['id']}/heartbeat",
        headers={"X-Local-Agent-Device-Token": device_token},
        json={
            "status": "online",
            "protocol_version": "local-agent-v1",
            "bridge_version": "0.1.1",
            "capabilities": _claude_v6_capabilities(),
        },
    )
    assert heartbeat.status_code == 200, heartbeat.text
    capabilities = heartbeat.json()["connection"]["capabilities_json"]
    assert capabilities["enabled_in_v6"] is False
    assert capabilities["host_tools_authorized"] is False
    assert capabilities["permission_bridge"] is None
    assert capabilities["execution_mode"] == "headless_bare_no_session_no_tools"

    _sent, task = _leased_bridge_task(
        client,
        connection["id"],
        device_token,
        client_message_id="claude-v5-heartbeat-upgrade-denied",
    )
    denied = client.post(
        "/api/agents/local-agent/bridge/tool-requests",
        headers={"X-Local-Agent-Device-Token": device_token},
        json={
            "tool_request_id": "claude-v5-heartbeat-tool",
            "bridge_task_id": task["id"],
            "tool_name": "run_shell",
            "input_json": {"command": "printf denied"},
            "execution_target": "host",
            "risk_level": "low",
            "permission_mode": "confirm",
        },
    )
    assert denied.status_code == 409, denied.text


def test_local_agent_v6_claude_done_requires_permission_bridge_proof_and_resolved_tools(
    db_session: Session,
) -> None:
    client = TestClient(app)
    connection, device_token = _registered_claude_v6_connection(client, db_session)
    sent, task = _leased_bridge_task(
        client,
        connection["id"],
        device_token,
        client_message_id="claude-v6-done-proof",
    )
    bridge_headers = {"X-Local-Agent-Device-Token": device_token}

    v5_proof = client.post(
        "/api/agents/local-agent/bridge/events",
        headers=bridge_headers,
        json={
            "event_id": "claude-v6-v5-proof",
            "bridge_task_id": task["id"],
            "event_type": "assistant_done",
            "content": "wrong proof",
            "metadata": {
                "adapter_kind": "claude_code",
                "system_init_safe": True,
                "tools_count": 0,
                "mcp_servers_count": 0,
            },
        },
    )
    assert v5_proof.status_code == 409, v5_proof.text
    assert "permission bridge proof" in v5_proof.text

    forbidden_surface = client.post(
        "/api/agents/local-agent/bridge/events",
        headers=bridge_headers,
        json={
            "event_id": "claude-v6-forbidden-proof",
            "bridge_task_id": task["id"],
            "event_type": "assistant_done",
            "content": "bad proof",
            "metadata": _claude_v6_safety_metadata(
                safety={
                    **_claude_v6_safety_metadata()["safety"],
                    "forbidden_surfaces": ["mcp"],
                }
            ),
        },
    )
    assert forbidden_surface.status_code == 409, forbidden_surface.text
    assert "forbidden capability surface" in forbidden_surface.text

    tool_request = client.post(
        "/api/agents/local-agent/bridge/tool-requests",
        headers=bridge_headers,
        json={
            "tool_request_id": "claude-v6-run-shell",
            "bridge_task_id": task["id"],
            "tool_name": "run_shell",
            "input_json": {"command": "printf ok"},
            "execution_target": "host",
            "risk_level": "low",
            "permission_mode": "confirm",
        },
    )
    assert tool_request.status_code == 201, tool_request.text
    decision = tool_request.json()
    assert decision["decision"] == "approval_required"

    early_done = client.post(
        "/api/agents/local-agent/bridge/events",
        headers=bridge_headers,
        json={
            "event_id": "claude-v6-done-too-early",
            "bridge_task_id": task["id"],
            "event_type": "assistant_done",
            "content": "too early",
            "metadata": _claude_v6_safety_metadata(),
        },
    )
    assert early_done.status_code == 409, early_done.text
    assert "unresolved local tool state" in early_done.text

    approved = client.post(
        f"/api/tasks/{sent['run_id']}/tool-approvals/{decision['approval_id']}/approve",
        headers=ADMIN_HEADERS,
        json={"reason": "allow V6 permission bridge shell"},
    )
    assert approved.status_code == 202, approved.text
    polled = client.get(
        "/api/agents/local-agent/bridge/tool-requests/claude-v6-run-shell/decision",
        headers=bridge_headers,
    )
    assert polled.status_code == 200, polled.text
    assert polled.json()["executable"] is True
    _start_and_finish_command(
        client,
        bridge_headers=bridge_headers,
        tool_request_id="claude-v6-run-shell",
        command_id="claude-v6-command-1",
        command="printf ok",
    )
    result = client.post(
        "/api/agents/local-agent/bridge/tool-requests/claude-v6-run-shell/result",
        headers=bridge_headers,
        json={
            "event_id": "claude-v6-run-shell-result",
            "status": "SUCCESS",
            "output_json": {"stdout": "ok"},
            "duration_ms": 1,
            "command_id": "claude-v6-command-1",
        },
    )
    assert result.status_code == 202, result.text

    accepted = client.post(
        "/api/agents/local-agent/bridge/events",
        headers=bridge_headers,
        json={
            "event_id": "claude-v6-done",
            "bridge_task_id": task["id"],
            "event_type": "assistant_done",
            "content": "safe V6 success",
            "metadata": _claude_v6_safety_metadata(),
        },
    )
    assert accepted.status_code == 201, accepted.text
    db_session.expire_all()
    bridge_task = db_session.get(LocalAgentBridgeTask, task["id"])
    assert bridge_task is not None
    assert bridge_task.status == "completed"
    messages = list(
        db_session.execute(
            select(AgentMessage).where(AgentMessage.session_id == sent["agent_session_id"])
        ).scalars()
    )
    assert [message.role for message in messages] == ["user", "assistant"]
    assert messages[-1].content == "safe V6 success"
    assert db_session.execute(select(LocalAgentToolRequest)).scalar_one().status == "succeeded"


def test_local_agent_v6_modify_can_replace_shell_command_and_enforce_modified_execution(
    db_session: Session,
) -> None:
    client = TestClient(app)
    connection, device_token = _registered_claude_v6_connection(client, db_session)
    sent, task = _leased_bridge_task(
        client,
        connection["id"],
        device_token,
        client_message_id="claude-v6-modify-shell",
    )
    bridge_headers = {"X-Local-Agent-Device-Token": device_token}
    tool_request = client.post(
        "/api/agents/local-agent/bridge/tool-requests",
        headers=bridge_headers,
        json={
            "tool_request_id": "claude-v6-modify-shell",
            "bridge_task_id": task["id"],
            "tool_name": "run_shell",
            "input_json": {"command": "printf original"},
            "execution_target": "host",
            "risk_level": "low",
            "permission_mode": "confirm",
        },
    )
    assert tool_request.status_code == 201, tool_request.text
    decision = tool_request.json()

    modified = client.post(
        f"/api/tasks/{sent['run_id']}/tool-approvals/{decision['approval_id']}/modify",
        headers=ADMIN_HEADERS,
        json={
            "modified_input_json": {"command": "printf sanitized"},
            "reason": "sanitize shell command",
        },
    )
    assert modified.status_code == 202, modified.text

    polled = client.get(
        "/api/agents/local-agent/bridge/tool-requests/claude-v6-modify-shell/decision",
        headers=bridge_headers,
    )
    assert polled.status_code == 200, polled.text
    assert polled.json()["input_json"]["command"] == "printf sanitized"
    assert polled.json()["decision_json"]["input_json"]["command"] == "printf sanitized"

    original_start = client.post(
        "/api/agents/local-agent/bridge/commands/claude-v6-modify-shell-original/events",
        headers=bridge_headers,
        json={
            "event_id": "claude-v6-modify-shell-original-start",
            "tool_request_id": "claude-v6-modify-shell",
            "event_type": "started",
            "tool_name": "run_shell",
            "command": "printf original",
        },
    )
    assert original_start.status_code == 409
    assert "approved executable input" in original_start.text

    _start_and_finish_command(
        client,
        bridge_headers=bridge_headers,
        tool_request_id="claude-v6-modify-shell",
        command_id="claude-v6-modify-shell-command",
        command="printf sanitized",
    )
    result = client.post(
        "/api/agents/local-agent/bridge/tool-requests/claude-v6-modify-shell/result",
        headers=bridge_headers,
        json={
            "event_id": "claude-v6-modify-shell-result",
            "status": "SUCCESS",
            "output_json": {"stdout": "sanitized"},
            "duration_ms": 1,
            "command_id": "claude-v6-modify-shell-command",
        },
    )
    assert result.status_code == 202, result.text

    db_session.expire_all()
    request_row = db_session.execute(
        select(LocalAgentToolRequest).where(
            LocalAgentToolRequest.tool_request_id == "claude-v6-modify-shell"
        )
    ).scalar_one()
    tool_call = db_session.get(ToolCall, decision["tool_call_id"])
    assert request_row.decision_json["input_json"]["command"] == "printf sanitized"
    assert tool_call is not None
    assert tool_call.input_json["command"] == "printf sanitized"
    assert request_row.status == "succeeded"


def test_local_agent_v6_modify_write_file_rejects_stale_original_pending_change_result(
    db_session: Session,
) -> None:
    client = TestClient(app)
    connection, device_token = _registered_claude_v6_connection(client, db_session)
    sent, task = _leased_bridge_task(
        client,
        connection["id"],
        device_token,
        client_message_id="claude-v6-modify-write-stale",
    )
    bridge_headers = {"X-Local-Agent-Device-Token": device_token}
    tool_request = client.post(
        "/api/agents/local-agent/bridge/tool-requests",
        headers=bridge_headers,
        json={
            "tool_request_id": "claude-v6-modify-write-stale",
            "bridge_task_id": task["id"],
            "tool_name": "write_file",
            "input_json": {"path": "notes.md", "content": "original\n"},
            "execution_target": "host",
            "risk_level": "low",
            "permission_mode": "confirm",
            "target_paths": ["notes.md"],
            "pending_change_preview": {
                "change_id": "change-original",
                "target_paths": ["notes.md"],
                "diff_sha256": "a" * 64,
            },
        },
    )
    assert tool_request.status_code == 201, tool_request.text
    decision = tool_request.json()
    modified = client.post(
        f"/api/tasks/{sent['run_id']}/tool-approvals/{decision['approval_id']}/modify",
        headers=ADMIN_HEADERS,
        json={
            "modified_input_json": {
                "path": "safe.md",
                "content": "sanitized\n",
            },
            "reason": "sanitize write target",
        },
    )
    assert modified.status_code == 202, modified.text

    stale_result = client.post(
        "/api/agents/local-agent/bridge/tool-requests/claude-v6-modify-write-stale/result",
        headers=bridge_headers,
        json={
            "event_id": "claude-v6-modify-write-result-stale",
            "status": "SUCCESS",
            "output_json": {"path": "notes.md"},
            "duration_ms": 1,
            "change_id": "change-original",
            "diff_sha256": "a" * 64,
        },
    )
    assert stale_result.status_code == 409
    assert "diff hash is required" in stale_result.text

    db_session.expire_all()
    request_row = db_session.execute(
        select(LocalAgentToolRequest).where(
            LocalAgentToolRequest.tool_request_id == "claude-v6-modify-write-stale"
        )
    ).scalar_one()
    pending_change = db_session.execute(
        select(LocalAgentPendingChange).where(
            LocalAgentPendingChange.local_agent_tool_request_id == request_row.id
        )
    ).scalar_one()
    assert request_row.status == "failed"
    assert pending_change.status == "failed"


def test_local_agent_v6_modify_write_file_refreshes_pending_change_to_modified_hash(
    db_session: Session,
) -> None:
    client = TestClient(app)
    connection, device_token = _registered_claude_v6_connection(client, db_session)
    sent, task = _leased_bridge_task(
        client,
        connection["id"],
        device_token,
        client_message_id="claude-v6-modify-write",
    )
    bridge_headers = {"X-Local-Agent-Device-Token": device_token}
    tool_request = client.post(
        "/api/agents/local-agent/bridge/tool-requests",
        headers=bridge_headers,
        json={
            "tool_request_id": "claude-v6-modify-write",
            "bridge_task_id": task["id"],
            "tool_name": "write_file",
            "input_json": {"path": "notes.md", "content": "original\n"},
            "execution_target": "host",
            "risk_level": "low",
            "permission_mode": "confirm",
            "target_paths": ["notes.md"],
            "pending_change_preview": {
                "change_id": "change-original",
                "target_paths": ["notes.md"],
                "diff_sha256": "a" * 64,
            },
        },
    )
    assert tool_request.status_code == 201, tool_request.text
    decision = tool_request.json()

    modified = client.post(
        f"/api/tasks/{sent['run_id']}/tool-approvals/{decision['approval_id']}/modify",
        headers=ADMIN_HEADERS,
        json={
            "modified_input_json": {
                "path": "safe.md",
                "content": "sanitized\n",
            },
            "reason": "sanitize write target",
        },
    )
    assert modified.status_code == 202, modified.text

    polled = client.get(
        "/api/agents/local-agent/bridge/tool-requests/claude-v6-modify-write/decision",
        headers=bridge_headers,
    )
    assert polled.status_code == 200, polled.text
    assert polled.json()["input_json"] == {"path": "safe.md", "content": "sanitized\n"}

    refreshed = client.post(
        "/api/agents/local-agent/bridge/tool-requests/claude-v6-modify-write/pending-change-refresh",
        headers=bridge_headers,
        json={
            "input_json": {"path": "safe.md", "content": "sanitized\n"},
            "target_paths": ["safe.md"],
            "pending_change_preview": {
                "change_id": "change-sanitized",
                "target_paths": ["safe.md"],
                "diff_sha256": "b" * 64,
            },
        },
    )
    assert refreshed.status_code == 202, refreshed.text
    assert refreshed.json()["decision_json"]["pending_change_preview"]["change_id"] == (
        "change-sanitized"
    )

    result = client.post(
        "/api/agents/local-agent/bridge/tool-requests/claude-v6-modify-write/result",
        headers=bridge_headers,
        json={
            "event_id": "claude-v6-modify-write-result",
            "status": "SUCCESS",
            "output_json": {"path": "safe.md"},
            "duration_ms": 1,
            "change_id": "change-sanitized",
            "diff_sha256": "b" * 64,
        },
    )
    assert result.status_code == 202, result.text

    db_session.expire_all()
    request_row = db_session.execute(
        select(LocalAgentToolRequest).where(
            LocalAgentToolRequest.tool_request_id == "claude-v6-modify-write"
        )
    ).scalar_one()
    pending_change = db_session.execute(
        select(LocalAgentPendingChange).where(
            LocalAgentPendingChange.local_agent_tool_request_id == request_row.id
        )
    ).scalar_one()
    assert pending_change.change_id == "change-sanitized"
    assert pending_change.target_paths_json == ["safe.md"]
    assert pending_change.diff_sha256 == "b" * 64
    assert pending_change.status == "committed"
    assert request_row.decision_json["pending_change_preview"]["change_id"] == "change-sanitized"
    assert request_row.decision_json["input_json"] == {"path": "safe.md", "content": "sanitized\n"}


def test_local_agent_v6_task_cancel_terminalizes_pending_tool_state(
    db_session: Session,
) -> None:
    client = TestClient(app)
    connection, device_token = _registered_claude_v6_connection(client, db_session)
    bridge_headers = {"X-Local-Agent-Device-Token": device_token}
    sent_payload, task = _leased_bridge_task(
        client,
        connection["id"],
        device_token,
        client_message_id="claude-v6-cancel-pending-tool",
    )
    tool_request = client.post(
        "/api/agents/local-agent/bridge/tool-requests",
        headers=bridge_headers,
        json={
            "tool_request_id": "claude-v6-cancel-tool",
            "bridge_task_id": task["id"],
            "tool_name": "write_file",
            "input_json": {"path": "notes.md", "content": "new\n"},
            "execution_target": "host",
            "risk_level": "low",
            "permission_mode": "confirm",
            "target_paths": ["notes.md"],
            "pending_change_preview": {
                "change_id": "claude-v6-cancel-change",
                "target_paths": ["notes.md"],
                "diff_sha256": "c" * 64,
            },
        },
    )
    assert tool_request.status_code == 201, tool_request.text
    decision = tool_request.json()
    local_request_id = db_session.execute(
        select(LocalAgentToolRequest.id).where(
            LocalAgentToolRequest.tool_request_id == "claude-v6-cancel-tool"
        )
    ).scalar_one()
    command = LocalAgentCommand(
        organization_id=connection.get("organization_id"),
        connection_id=connection["id"],
        binding_id=task["binding_id"],
        bridge_task_id=task["id"],
        task_id=sent_payload["run_id"],
        local_agent_tool_request_id=local_request_id,
        tool_request_id="claude-v6-cancel-tool",
        command_id="claude-v6-cancel-command",
        tool_name="write_file",
        command="write notes.md",
        status="pending",
        output_summary_json={},
        event_receipts_json={},
    )
    db_session.add(command)
    db_session.commit()

    cancelled = client.post(f"/api/tasks/{sent_payload['run_id']}/cancel", headers=AUTH_HEADERS)
    assert cancelled.status_code == 202, cancelled.text

    db_session.expire_all()
    request_row = db_session.execute(
        select(LocalAgentToolRequest).where(
            LocalAgentToolRequest.tool_request_id == "claude-v6-cancel-tool"
        )
    ).scalar_one()
    approval = db_session.get(ToolApproval, decision["approval_id"])
    tool_call = db_session.get(ToolCall, decision["tool_call_id"])
    change = db_session.execute(select(LocalAgentPendingChange)).scalar_one()
    command = db_session.execute(
        select(LocalAgentCommand).where(LocalAgentCommand.command_id == "claude-v6-cancel-command")
    ).scalar_one()
    bridge_task = db_session.get(LocalAgentBridgeTask, task["id"])
    run = db_session.get(Task, sent_payload["run_id"])
    assert request_row.status == "cancelled"
    assert request_row.decision_json["terminal_status"] == "cancelled"
    assert approval is not None
    assert approval.status == "DENIED"
    assert tool_call is not None
    assert tool_call.status == "CANCELLED"
    assert change.status == "denied"
    assert command.status == "cancelled"
    assert bridge_task is not None
    assert bridge_task.status == "cancelled"
    assert run is not None
    assert run.status == "CANCELLED"

    late_approval = client.post(
        f"/api/tasks/{sent_payload['run_id']}/tool-approvals/{decision['approval_id']}/approve",
        headers=ADMIN_HEADERS,
        json={"reason": "too late"},
    )
    assert late_approval.status_code == 409, late_approval.text
    polled = client.get(
        "/api/agents/local-agent/bridge/tool-requests/claude-v6-cancel-tool/decision",
        headers=bridge_headers,
    )
    assert polled.status_code == 200, polled.text
    assert polled.json()["decision"] == "cancelled"
    assert polled.json()["executable"] is False


def test_local_agent_v6_claude_legacy_tool_result_is_rejected(
    db_session: Session,
) -> None:
    client = TestClient(app)
    connection, device_token = _registered_claude_v6_connection(client, db_session)
    _sent, task = _leased_bridge_task(
        client,
        connection["id"],
        device_token,
        client_message_id="claude-v6-legacy-tool-result",
    )
    bridge_headers = {"X-Local-Agent-Device-Token": device_token}

    rejected = client.post(
        "/api/agents/local-agent/bridge/events",
        headers=bridge_headers,
        json={
            "event_id": "claude-v6-legacy-tool-result",
            "bridge_task_id": task["id"],
            "event_type": "tool_result",
            "tool_name": "read_metadata",
            "input_json": {"path": "README.md"},
            "output_json": {"content": "legacy"},
            "status": "SUCCESS",
            "risk_level": "low",
        },
    )

    assert rejected.status_code == 409, rejected.text
    assert "cannot report legacy tool_result" in rejected.text
    assert db_session.execute(select(ToolCall)).scalars().all() == []


def test_local_agent_v4_codex_resume_is_always_context_replay(
    db_session: Session,
) -> None:
    client = TestClient(app)
    _ensure_agent(db_session)
    created = client.post(
        "/api/agents/local-agent/pairing-tokens",
        headers=AUTH_HEADERS,
        json={"agent_id": "default", "scope": {"executable": True, "adapters": ["codex"]}},
    )
    assert created.status_code == 201, created.text
    pairing = created.json()
    registered = client.post(
        "/api/agents/local-agent/connections/register",
        json={
            "pair_token": pairing["pair_token"],
            "pair_code": pairing["pair_code"],
            "adapter_kind": "codex",
            "protocol_version": "local-agent-v1",
            "capabilities": {
                "supports_resume": True,
                "supports_cancel": True,
                "host_tools_authorized": True,
                "deterministic_session_id": True,
                "resume_sandbox_read_only": True,
            },
            "metadata": {"workspace_identity_hash": "hash-codex"},
        },
    )
    assert registered.status_code == 201, registered.text
    connection = registered.json()["connection"]
    device_token = registered.json()["device_token"]
    assert connection["capabilities_json"]["supports_resume"] is False
    assert connection["capabilities_json"]["resume_mode"] == "context_replay_new_session"

    binding = client.post(
        f"/api/agents/local-agent/connections/{connection['id']}/bindings",
        headers=AUTH_HEADERS,
        json={
            "title": "Codex context replay",
            "adapter_session_id": "untrusted-codex-session",
            "resume_mode": "native_resume",
        },
    )
    assert binding.status_code == 201, binding.text
    assert binding.json()["resume_mode"] == "context_replay_new_session"

    sent = client.post(
        f"/api/agents/local-agent/bindings/{binding.json()['id']}/messages",
        headers=AUTH_HEADERS,
        json={"content": "continue safely", "client_message_id": "codex-resume-test"},
    )
    assert sent.status_code == 202, sent.text
    pulled = client.get(
        "/api/agents/local-agent/bridge/tasks",
        headers={"X-Local-Agent-Device-Token": device_token},
    )
    assert pulled.status_code == 200, pulled.text
    task_payload = pulled.json()["items"][0]["payload"]
    assert task_payload["resume_mode"] == "context_replay_new_session"
    assert task_payload["capabilities"]["supports_resume"] is False
    assert task_payload["workspace_identity_hash"] == "hash-codex"


def test_local_agent_v4_codex_second_turn_replays_redacted_harness_context(
    db_session: Session,
) -> None:
    client = TestClient(app)
    _ensure_agent(db_session)
    created = client.post(
        "/api/agents/local-agent/pairing-tokens",
        headers=AUTH_HEADERS,
        json={"agent_id": "default", "scope": {"executable": True, "adapters": ["codex"]}},
    )
    assert created.status_code == 201, created.text
    pairing = created.json()
    registered = client.post(
        "/api/agents/local-agent/connections/register",
        json={
            "pair_token": pairing["pair_token"],
            "pair_code": pairing["pair_code"],
            "adapter_kind": "codex",
            "protocol_version": "local-agent-v1",
            "capabilities": {"supports_streaming": True},
            "metadata": {"workspace_identity_hash": "hash-codex"},
        },
    )
    assert registered.status_code == 201, registered.text
    connection = registered.json()["connection"]
    device_token = registered.json()["device_token"]
    bridge_headers = {"X-Local-Agent-Device-Token": device_token}
    binding = client.post(
        f"/api/agents/local-agent/connections/{connection['id']}/bindings",
        headers=AUTH_HEADERS,
        json={"title": "Codex replay", "resume_mode": "native_resume"},
    )
    assert binding.status_code == 201, binding.text
    binding_id = binding.json()["id"]

    first = client.post(
        f"/api/agents/local-agent/bindings/{binding_id}/messages",
        headers=AUTH_HEADERS,
        json={
            "content": "remember TOKEN=raw-token /Users/luohao/private/file.txt",
            "client_message_id": "codex-context-1",
        },
    )
    assert first.status_code == 202, first.text
    first_pull = client.get("/api/agents/local-agent/bridge/tasks", headers=bridge_headers)
    assert first_pull.status_code == 200, first_pull.text
    first_task = first_pull.json()["items"][0]
    first_done = client.post(
        "/api/agents/local-agent/bridge/events",
        headers=bridge_headers,
        json={
            "event_id": "codex-context-1-done",
            "bridge_task_id": first_task["id"],
            "event_type": "assistant_done",
            "content": "stored sk-proj-1234567890abcdef",
            "sequence": 1,
        },
    )
    assert first_done.status_code == 201, first_done.text

    second = client.post(
        f"/api/agents/local-agent/bindings/{binding_id}/messages",
        headers=AUTH_HEADERS,
        json={"content": "continue from prior turn", "client_message_id": "codex-context-2"},
    )
    assert second.status_code == 202, second.text
    second_pull = client.get("/api/agents/local-agent/bridge/tasks", headers=bridge_headers)
    assert second_pull.status_code == 200, second_pull.text
    payload = second_pull.json()["items"][0]["payload"]
    context = payload["conversation_context"]

    assert payload["resume_mode"] == "context_replay_new_session"
    assert [item["role"] for item in context] == ["user", "assistant"]
    context_text = json.dumps(context, ensure_ascii=False)
    assert "remember TOKEN=[REDACTED] .../private/file.txt" in context_text
    assert "stored [REDACTED]" in context_text
    assert "raw-token" not in context_text
    assert "sk-proj-1234567890abcdef" not in context_text
    assert "/Users/luohao" not in context_text
    assert "continue from prior turn" not in context_text


def test_local_agent_v4_codex_legacy_tool_result_is_rejected_without_tool_call(
    db_session: Session,
) -> None:
    client = TestClient(app)
    _ensure_agent(db_session)
    created = client.post(
        "/api/agents/local-agent/pairing-tokens",
        headers=AUTH_HEADERS,
        json={"agent_id": "default", "scope": {"executable": True, "adapters": ["codex"]}},
    )
    assert created.status_code == 201, created.text
    pairing = created.json()
    registered = client.post(
        "/api/agents/local-agent/connections/register",
        json={
            "pair_token": pairing["pair_token"],
            "pair_code": pairing["pair_code"],
            "adapter_kind": "codex",
            "protocol_version": "local-agent-v1",
            "capabilities": {"supports_streaming": True},
        },
    )
    assert registered.status_code == 201, registered.text
    connection = registered.json()["connection"]
    device_token = registered.json()["device_token"]
    sent, task = _leased_bridge_task(
        client,
        connection["id"],
        device_token,
        client_message_id="codex-tool-result-test",
    )
    assert sent["run_id"]
    bridge_headers = {"X-Local-Agent-Device-Token": device_token}

    rejected = client.post(
        "/api/agents/local-agent/bridge/events",
        headers=bridge_headers,
        json={
            "event_id": "codex-legacy-tool-result",
            "bridge_task_id": task["id"],
            "event_type": "tool_result",
            "tool_name": "read_metadata",
            "input_json": {"path": "README.md"},
            "output_json": {"content": "safe-looking but not authorized"},
            "status": "SUCCESS",
            "risk_level": "low",
        },
    )

    assert rejected.status_code == 409, rejected.text
    assert "cannot report legacy tool_result" in rejected.text
    assert db_session.execute(select(ToolCall)).scalars().all() == []
    assert (
        db_session.execute(
            select(LocalAgentBridgeEventReceipt).where(
                LocalAgentBridgeEventReceipt.event_id == "codex-legacy-tool-result"
            )
        ).scalar_one_or_none()
        is None
    )


def test_local_agent_v4_codex_host_tool_protocol_is_hard_denied(
    db_session: Session,
) -> None:
    client = TestClient(app)
    _ensure_agent(db_session)
    created = client.post(
        "/api/agents/local-agent/pairing-tokens",
        headers=AUTH_HEADERS,
        json={"agent_id": "default", "scope": {"executable": True, "adapters": ["codex"]}},
    )
    assert created.status_code == 201, created.text
    pairing = created.json()
    registered = client.post(
        "/api/agents/local-agent/connections/register",
        json={
            "pair_token": pairing["pair_token"],
            "pair_code": pairing["pair_code"],
            "adapter_kind": "codex",
            "protocol_version": "local-agent-v1",
            "capabilities": {"supports_streaming": True},
        },
    )
    assert registered.status_code == 201, registered.text
    connection = registered.json()["connection"]
    device_token = registered.json()["device_token"]
    _sent, task = _leased_bridge_task(
        client,
        connection["id"],
        device_token,
        client_message_id="codex-host-tool-denied",
    )
    bridge_headers = {"X-Local-Agent-Device-Token": device_token}

    tool_request = client.post(
        "/api/agents/local-agent/bridge/tool-requests",
        headers=bridge_headers,
        json={
            "tool_request_id": "codex-tool-req",
            "bridge_task_id": task["id"],
            "tool_name": "run_shell",
            "input_json": {"command": "printf denied"},
            "execution_target": "host",
            "risk_level": "low",
            "permission_mode": "full-auto",
        },
    )
    assert tool_request.status_code == 409, tool_request.text
    assert "cannot use local host tool protocol" in tool_request.text

    result = client.post(
        "/api/agents/local-agent/bridge/tool-requests/codex-tool-req/result",
        headers=bridge_headers,
        json={"event_id": "codex-tool-result", "status": "SUCCESS"},
    )
    assert result.status_code == 409, result.text
    command_event = client.post(
        "/api/agents/local-agent/bridge/commands/codex-cmd/events",
        headers=bridge_headers,
        json={
            "event_id": "codex-cmd-start",
            "tool_request_id": "codex-tool-req",
            "event_type": "started",
            "tool_name": "run_shell",
            "command": "printf denied",
        },
    )
    assert command_event.status_code == 409, command_event.text
    command_status = client.get(
        "/api/agents/local-agent/bridge/commands/codex-cmd",
        headers=bridge_headers,
    )
    assert command_status.status_code == 409, command_status.text
    cancel_ack = client.post(
        "/api/agents/local-agent/bridge/commands/codex-cmd/cancel-ack",
        headers=bridge_headers,
        json={"status": "cancelled", "error_message": "cancelled"},
    )
    assert cancel_ack.status_code == 409, cancel_ack.text
    cancel = client.post(
        f"/api/agents/local-agent/bindings/{task['binding_id']}/commands/codex-cmd/cancel",
        headers=AUTH_HEADERS,
    )
    assert cancel.status_code == 409, cancel.text
    retry = client.post(
        f"/api/agents/local-agent/bindings/{task['binding_id']}/commands/codex-cmd/retry",
        headers=AUTH_HEADERS,
    )
    assert retry.status_code == 409, retry.text

    assert db_session.execute(select(LocalAgentToolRequest)).scalars().all() == []
    assert db_session.execute(select(ToolCall)).scalars().all() == []
    assert db_session.execute(select(ToolApproval)).scalars().all() == []
    assert db_session.execute(select(LocalAgentCommand)).scalars().all() == []
    assert db_session.execute(select(LocalAgentPendingChange)).scalars().all() == []
    assert db_session.execute(select(LocalAgentBridgeEventReceipt)).scalars().all() == []


def test_local_agent_pairing_registration_replay_cannot_create_second_connection(
    db_session: Session,
) -> None:
    client = TestClient(app)
    _ensure_agent(db_session)
    created = client.post(
        "/api/agents/local-agent/pairing-tokens",
        headers=AUTH_HEADERS,
        json={"agent_id": "default", "ttl_minutes": 5},
    )
    assert created.status_code == 201, created.text
    pairing = created.json()

    first = client.post(
        "/api/agents/local-agent/connections/register",
        json={
            "pair_token": pairing["pair_token"],
            "pair_code": pairing["pair_code"],
            "adapter_kind": "hao",
            "protocol_version": "local-agent-v1",
        },
    )
    assert first.status_code == 201, first.text

    second = client.post(
        "/api/agents/local-agent/connections/register",
        json={
            "pair_token": pairing["pair_token"],
            "pair_code": pairing["pair_code"],
            "adapter_kind": "hao",
            "protocol_version": "local-agent-v1",
        },
    )
    assert second.status_code == 410
    assert (
        db_session.execute(select(LocalAgentConnection)).scalars().all()[0].pairing_token_id
        == pairing["id"]
    )
    assert len(db_session.execute(select(LocalAgentConnection)).scalars().all()) == 1


def test_local_agent_owner_can_send_and_bridge_events_are_idempotent(
    db_session: Session,
) -> None:
    client = TestClient(app)
    connection, device_token = _registered_connection(client, db_session)
    bridge_headers = {"X-Local-Agent-Device-Token": device_token}

    binding = client.post(
        f"/api/agents/local-agent/connections/{connection['id']}/bindings",
        headers=AUTH_HEADERS,
        json={"title": "Local coding session", "resume_mode": "native_resume"},
    )
    assert binding.status_code == 201, binding.text
    binding_id = binding.json()["id"]

    sent = client.post(
        f"/api/agents/local-agent/bindings/{binding_id}/messages",
        headers=AUTH_HEADERS,
        json={"content": "请检查本地项目", "client_message_id": "msg-1"},
    )
    assert sent.status_code == 202, sent.text
    sent_payload = sent.json()
    assert sent_payload["run_id"]

    pull = client.get("/api/agents/local-agent/bridge/tasks", headers=bridge_headers)
    assert pull.status_code == 200, pull.text
    tasks = pull.json()["items"]
    assert len(tasks) == 1
    assert tasks[0]["status"] == "leased"
    assert tasks[0]["payload"]["adapter_kind"] == "hao"

    ack = client.post(
        f"/api/agents/local-agent/bridge/tasks/{tasks[0]['id']}/ack",
        headers=bridge_headers,
        json={"status": "running"},
    )
    assert ack.status_code == 200, ack.text

    delta = client.post(
        "/api/agents/local-agent/bridge/events",
        headers=bridge_headers,
        json={
            "event_id": "evt-1",
            "bridge_task_id": tasks[0]["id"],
            "event_type": "assistant_delta",
            "content": "我开始检查。",
            "sequence": 1,
        },
    )
    assert delta.status_code == 201, delta.text
    repeated_delta = client.post(
        "/api/agents/local-agent/bridge/events",
        headers=bridge_headers,
        json={
            "event_id": "evt-1",
            "bridge_task_id": tasks[0]["id"],
            "event_type": "assistant_delta",
            "content": "duplicate",
        },
    )
    assert repeated_delta.status_code == 201, repeated_delta.text
    assert repeated_delta.json()["duplicate"] is True

    unauthorized_tool = client.post(
        "/api/agents/local-agent/bridge/events",
        headers=bridge_headers,
        json={
            "event_id": "evt-tool",
            "bridge_task_id": tasks[0]["id"],
            "event_type": "tool_result",
            "tool_name": "run_shell",
            "input_json": {
                "command": "echo sk-proj-1234567890abcdef",
                "api_key": "sk-secret-value",
            },
            "output_json": {"stdout": "sk-proj-1234567890abcdef", "token": "sat-secret-value"},
            "status": "SUCCESS",
            "risk_level": "high",
            "duration_ms": 12,
        },
    )
    assert unauthorized_tool.status_code == 409, unauthorized_tool.text

    tool_request = client.post(
        "/api/agents/local-agent/bridge/tool-requests",
        headers=bridge_headers,
        json={
            "tool_request_id": "tool-req-1",
            "bridge_task_id": tasks[0]["id"],
            "tool_name": "run_shell",
            "input_json": {
                "command": "echo sk-proj-1234567890abcdef",
                "api_key": "sk-secret-value",
            },
            "execution_target": "host",
            "risk_level": "low",
            "permission_mode": "full-auto",
        },
    )
    assert tool_request.status_code == 201, tool_request.text
    tool_decision = tool_request.json()
    assert tool_decision["decision"] == "approval_required"
    assert tool_decision["executable"] is False
    assert tool_decision["server_execution"] is False
    assert tool_decision["approval_id"]

    early_done = client.post(
        "/api/agents/local-agent/bridge/events",
        headers=bridge_headers,
        json={
            "event_id": "evt-done-before-tool",
            "bridge_task_id": tasks[0]["id"],
            "event_type": "assistant_done",
            "content": "too early",
            "sequence": 2,
        },
    )
    assert early_done.status_code == 409

    approved = client.post(
        f"/api/tasks/{sent_payload['run_id']}/tool-approvals/{tool_decision['approval_id']}/approve",
        headers=ADMIN_HEADERS,
        json={"reason": "allow deterministic local test command"},
    )
    assert approved.status_code == 202, approved.text
    approval_rows = approved.json()["items"]
    assert approval_rows[0]["decision_json"]["server_execution"] is False

    polled = client.get(
        "/api/agents/local-agent/bridge/tool-requests/tool-req-1/decision",
        headers=bridge_headers,
    )
    assert polled.status_code == 200, polled.text
    assert polled.json()["decision"] == "approved"
    assert polled.json()["executable"] is True
    assert polled.json()["input_json"]["api_key"] == "[REDACTED]"

    command_started = client.post(
        "/api/agents/local-agent/bridge/commands/cmd-1/events",
        headers=bridge_headers,
        json={
            "event_id": "cmd-1-start",
            "tool_request_id": "tool-req-1",
            "event_type": "started",
            "tool_name": "run_shell",
            "command": "echo [REDACTED]",
        },
    )
    assert command_started.status_code == 202, command_started.text

    command_output = client.post(
        "/api/agents/local-agent/bridge/commands/cmd-1/events",
        headers=bridge_headers,
        json={
            "event_id": "cmd-1-output",
            "tool_request_id": "tool-req-1",
            "event_type": "output",
            "stdout": "sk-proj-1234567890abcdef",
        },
    )
    assert command_output.status_code == 202, command_output.text

    command_finished = client.post(
        "/api/agents/local-agent/bridge/commands/cmd-1/events",
        headers=bridge_headers,
        json={
            "event_id": "cmd-1-finished",
            "tool_request_id": "tool-req-1",
            "event_type": "finished",
            "status": "success",
            "exit_code": 0,
            "duration_ms": 12,
        },
    )
    assert command_finished.status_code == 202, command_finished.text

    result = client.post(
        "/api/agents/local-agent/bridge/tool-requests/tool-req-1/result",
        headers=bridge_headers,
        json={
            "event_id": "tool-req-1-result",
            "status": "SUCCESS",
            "output_json": {"stdout": "sk-proj-1234567890abcdef", "token": "sat-secret-value"},
            "duration_ms": 12,
            "command_id": "cmd-1",
        },
    )
    assert result.status_code == 202, result.text
    assert result.json()["decision"] == "succeeded"

    done = client.post(
        "/api/agents/local-agent/bridge/events",
        headers=bridge_headers,
        json={
            "event_id": "evt-done",
            "bridge_task_id": tasks[0]["id"],
            "event_type": "assistant_done",
            "content": "检查完成。",
            "sequence": 2,
        },
    )
    assert done.status_code == 201, done.text

    bridge_task = db_session.get(LocalAgentBridgeTask, tasks[0]["id"])
    assert bridge_task is not None
    assert bridge_task.status == "completed"
    run = db_session.get(Task, sent_payload["run_id"])
    assert run is not None
    assert run.status == "COMPLETED"
    assert db_session.execute(select(LocalAgentBridgeEventReceipt)).scalars().all()
    assert db_session.execute(select(AgentEvent)).scalars().all()
    tool_call = db_session.execute(select(ToolCall)).scalar_one()
    assert tool_call.input_json["api_key"] == "[REDACTED]"
    assert tool_call.output_json["token"] == "[REDACTED]"
    assert tool_call.input_json["command"] == "echo [REDACTED]"
    assert tool_call.output_json["stdout"] == "[REDACTED]"
    assert tool_call.status == "SUCCESS"
    assert tool_call.capability_snapshot_json["server_execution"] is False
    assert db_session.execute(select(ToolApproval)).scalar_one().status == "APPROVED"
    assert db_session.execute(select(LocalAgentToolRequest)).scalar_one().status == "succeeded"
    assert db_session.execute(select(LocalAgentCommand)).scalar_one().status == "success"
    messages = list(
        db_session.execute(
            select(AgentMessage).where(AgentMessage.session_id == sent_payload["agent_session_id"])
        ).scalars()
    )
    assert [message.role for message in messages] == ["user", "assistant"]


def test_local_agent_v3_rejects_results_before_or_after_denial(
    db_session: Session,
) -> None:
    client = TestClient(app)
    connection, device_token = _registered_connection(client, db_session)
    bridge_headers = {"X-Local-Agent-Device-Token": device_token}
    sent_payload, task = _leased_bridge_task(
        client,
        connection["id"],
        device_token,
        client_message_id="v3-denial",
    )

    tool_request = client.post(
        "/api/agents/local-agent/bridge/tool-requests",
        headers=bridge_headers,
        json={
            "tool_request_id": "tool-req-deny",
            "bridge_task_id": task["id"],
            "tool_name": "run_shell",
            "input_json": {"command": "printf ok"},
            "execution_target": "host",
            "risk_level": "low",
            "permission_mode": "full-auto",
        },
    )
    assert tool_request.status_code == 201, tool_request.text
    decision = tool_request.json()
    assert decision["decision"] == "approval_required"

    early_result = client.post(
        "/api/agents/local-agent/bridge/tool-requests/tool-req-deny/result",
        headers=bridge_headers,
        json={
            "event_id": "tool-req-deny-result-early",
            "status": "SUCCESS",
            "output_json": {"stdout": "ok"},
        },
    )
    assert early_result.status_code == 409

    rejected = client.post(
        f"/api/tasks/{sent_payload['run_id']}/tool-approvals/{decision['approval_id']}/reject",
        headers=ADMIN_HEADERS,
        json={"reason": "reject local shell"},
    )
    assert rejected.status_code == 202, rejected.text

    polled = client.get(
        "/api/agents/local-agent/bridge/tool-requests/tool-req-deny/decision",
        headers=bridge_headers,
    )
    assert polled.status_code == 200, polled.text
    assert polled.json()["decision"] == "denied"
    assert polled.json()["executable"] is False

    late_result = client.post(
        "/api/agents/local-agent/bridge/tool-requests/tool-req-deny/result",
        headers=bridge_headers,
        json={
            "event_id": "tool-req-deny-result-late",
            "status": "SUCCESS",
            "output_json": {"stdout": "should not land"},
        },
    )
    assert late_result.status_code == 409
    db_session.expire_all()
    tool_call = db_session.get(ToolCall, decision["tool_call_id"])
    request_row = db_session.execute(select(LocalAgentToolRequest)).scalar_one()
    assert tool_call is not None
    assert tool_call.status == "DENIED"
    assert request_row.status == "denied"


def test_local_agent_v3_modify_cannot_change_protected_execution_fields(
    db_session: Session,
) -> None:
    client = TestClient(app)
    connection, device_token = _registered_connection(client, db_session)
    bridge_headers = {"X-Local-Agent-Device-Token": device_token}
    sent_payload, task = _leased_bridge_task(
        client,
        connection["id"],
        device_token,
        client_message_id="v3-modify",
    )
    tool_request = client.post(
        "/api/agents/local-agent/bridge/tool-requests",
        headers=bridge_headers,
        json={
            "tool_request_id": "tool-req-modify",
            "bridge_task_id": task["id"],
            "tool_name": "run_shell",
            "input_json": {"command": "printf safe", "api_key": "sk-secret-value"},
            "execution_target": "host",
            "risk_level": "low",
            "permission_mode": "full-auto",
        },
    )
    assert tool_request.status_code == 201, tool_request.text
    decision = tool_request.json()

    modified = client.post(
        f"/api/tasks/{sent_payload['run_id']}/tool-approvals/{decision['approval_id']}/modify",
        headers=ADMIN_HEADERS,
        json={
            "modified_input_json": {
                "command": "printf changed",
                "api_key": "[REDACTED]",
            },
            "reason": "attempt to change execution",
        },
    )
    assert modified.status_code == 409
    assert "protected field" in modified.text
    db_session.expire_all()
    approval = db_session.get(ToolApproval, decision["approval_id"])
    tool_call = db_session.get(ToolCall, decision["tool_call_id"])
    assert approval is not None
    assert approval.status == "PENDING"
    assert tool_call is not None
    assert tool_call.status == "PENDING_APPROVAL"


def test_local_agent_v3_modify_cannot_expand_unprotected_input(
    db_session: Session,
) -> None:
    client = TestClient(app)
    connection, device_token = _registered_connection(client, db_session)
    bridge_headers = {"X-Local-Agent-Device-Token": device_token}
    sent_payload, task = _leased_bridge_task(
        client,
        connection["id"],
        device_token,
        client_message_id="v3-modify-expand",
    )
    tool_request = client.post(
        "/api/agents/local-agent/bridge/tool-requests",
        headers=bridge_headers,
        json={
            "tool_request_id": "tool-req-modify-expand",
            "bridge_task_id": task["id"],
            "tool_name": "run_shell",
            "input_json": {
                "command": "printf safe",
                "timeout_seconds": 5,
                "label": "safe",
                "nested": {"mode": "safe"},
            },
            "execution_target": "host",
            "risk_level": "low",
            "permission_mode": "full-auto",
        },
    )
    assert tool_request.status_code == 201, tool_request.text
    decision = tool_request.json()

    modified = client.post(
        f"/api/tasks/{sent_payload['run_id']}/tool-approvals/{decision['approval_id']}/modify",
        headers=ADMIN_HEADERS,
        json={
            "modified_input_json": {
                "command": "printf safe",
                "timeout_seconds": 600,
                "label": "safe",
                "nested": {"mode": "expanded"},
            },
            "reason": "attempt broad modify",
        },
    )
    assert modified.status_code == 409
    assert "redact or preserve" in modified.text


def test_local_agent_v3_detached_capability_denies_local_execution(
    db_session: Session,
) -> None:
    client = TestClient(app)
    _create_limited_agent(db_session)
    connection, device_token = _registered_connection_for_agent(client, "limited-local-agent")
    bridge_headers = {"X-Local-Agent-Device-Token": device_token}
    _sent_payload, task = _leased_bridge_task(
        client,
        connection["id"],
        device_token,
        client_message_id="v3-detached-capability",
    )

    tool_request = client.post(
        "/api/agents/local-agent/bridge/tool-requests",
        headers=bridge_headers,
        json={
            "tool_request_id": "tool-req-detached",
            "bridge_task_id": task["id"],
            "tool_name": "run_shell",
            "input_json": {"command": "printf denied"},
            "execution_target": "host",
            "risk_level": "low",
            "permission_mode": "full-auto",
        },
    )

    assert tool_request.status_code == 201, tool_request.text
    decision = tool_request.json()
    assert decision["decision"] == "denied"
    assert decision["executable"] is False
    assert decision["approval_id"] is None
    assert "capability is not attached" in decision["reason"]
    db_session.expire_all()
    request_row = db_session.execute(select(LocalAgentToolRequest)).scalar_one()
    tool_call = db_session.execute(select(ToolCall)).scalar_one()
    assert request_row.status == "denied"
    assert tool_call.status == "DENIED"


def test_local_agent_v3_command_start_rejects_safe_tool_injection_and_command_substitution(
    db_session: Session,
) -> None:
    client = TestClient(app)
    connection, device_token = _registered_connection(client, db_session)
    bridge_headers = {"X-Local-Agent-Device-Token": device_token}
    sent_payload, task = _leased_bridge_task(
        client,
        connection["id"],
        device_token,
        client_message_id="v3-command-substitution",
    )
    safe_request = client.post(
        "/api/agents/local-agent/bridge/tool-requests",
        headers=bridge_headers,
        json={
            "tool_request_id": "tool-req-safe-noop",
            "bridge_task_id": task["id"],
            "tool_name": "fake.noop",
            "input_json": {"message": "safe"},
            "execution_target": "host",
            "risk_level": "low",
            "permission_mode": "full-auto",
        },
    )
    assert safe_request.status_code == 201, safe_request.text
    assert safe_request.json()["decision"] == "allowed"

    injected_start = client.post(
        "/api/agents/local-agent/bridge/commands/cmd-injected/events",
        headers=bridge_headers,
        json={
            "event_id": "cmd-injected-start",
            "tool_request_id": "tool-req-safe-noop",
            "event_type": "started",
            "tool_name": "run_shell",
            "command": "printf injected",
        },
    )
    assert injected_start.status_code == 409
    assert "command events are only valid" in injected_start.text

    approved = _approved_local_tool_request(
        client,
        bridge_headers=bridge_headers,
        task=task,
        run_id=sent_payload["run_id"],
        tool_request_id="tool-req-safe-command",
        input_json={"command": "printf safe"},
    )
    assert approved["decision"] == "approval_required"

    substituted_start = client.post(
        "/api/agents/local-agent/bridge/commands/cmd-substituted/events",
        headers=bridge_headers,
        json={
            "event_id": "cmd-substituted-start",
            "tool_request_id": "tool-req-safe-command",
            "event_type": "started",
            "tool_name": "run_shell",
            "command": "printf unsafe",
        },
    )
    assert substituted_start.status_code == 409
    assert "approved executable input" in substituted_start.text
    db_session.expire_all()
    assert db_session.execute(select(LocalAgentCommand)).scalars().all() == []


def test_local_agent_v3_command_start_accepts_hao_python_normalization(
    db_session: Session,
) -> None:
    client = TestClient(app)
    connection, device_token = _registered_connection(client, db_session)
    bridge_headers = {"X-Local-Agent-Device-Token": device_token}
    sent_payload, task = _leased_bridge_task(
        client,
        connection["id"],
        device_token,
        client_message_id="v3-command-python-normalization",
    )
    _approved_local_tool_request(
        client,
        bridge_headers=bridge_headers,
        task=task,
        run_id=sent_payload["run_id"],
        tool_request_id="tool-req-python-normalized",
        input_json={"command": "python -c 'print(1)'"},
    )

    _start_and_finish_command(
        client,
        bridge_headers=bridge_headers,
        tool_request_id="tool-req-python-normalized",
        command_id="cmd-python-normalized",
        command=f"{sys.executable} -c 'print(1)'",
    )
    result = client.post(
        "/api/agents/local-agent/bridge/tool-requests/tool-req-python-normalized/result",
        headers=bridge_headers,
        json={
            "event_id": "tool-req-python-normalized-result",
            "status": "SUCCESS",
            "output_json": {"stdout": "1\n"},
            "command_id": "cmd-python-normalized",
        },
    )
    assert result.status_code == 202, result.text
    assert result.json()["decision"] == "succeeded"


def test_local_agent_v3_command_start_enforces_expired_approval_before_execution(
    db_session: Session,
) -> None:
    client = TestClient(app)
    connection, device_token = _registered_connection(client, db_session)
    bridge_headers = {"X-Local-Agent-Device-Token": device_token}
    sent_payload, task = _leased_bridge_task(
        client,
        connection["id"],
        device_token,
        client_message_id="v3-command-expired",
    )
    decision = _approved_local_tool_request(
        client,
        bridge_headers=bridge_headers,
        task=task,
        run_id=sent_payload["run_id"],
        tool_request_id="tool-req-expired",
        input_json={"command": "printf safe"},
    )
    request_row = db_session.execute(select(LocalAgentToolRequest)).scalar_one()
    request_row.decision_expires_at = utc_now() - timedelta(minutes=1)
    db_session.commit()

    started = client.post(
        "/api/agents/local-agent/bridge/commands/cmd-expired/events",
        headers=bridge_headers,
        json={
            "event_id": "cmd-expired-start",
            "tool_request_id": "tool-req-expired",
            "event_type": "started",
            "tool_name": "run_shell",
            "command": "printf safe",
        },
    )
    assert started.status_code == 409
    db_session.expire_all()
    request_row = db_session.execute(select(LocalAgentToolRequest)).scalar_one()
    tool_call = db_session.get(ToolCall, decision["tool_call_id"])
    assert request_row.status == "expired"
    assert tool_call is not None
    assert tool_call.status == "DENIED"
    assert db_session.execute(select(LocalAgentCommand)).scalars().all() == []


def test_local_agent_v3_approval_after_ttl_expires_fail_closed(
    db_session: Session,
) -> None:
    client = TestClient(app)
    connection, device_token = _registered_connection(client, db_session)
    bridge_headers = {"X-Local-Agent-Device-Token": device_token}
    sent_payload, task = _leased_bridge_task(
        client,
        connection["id"],
        device_token,
        client_message_id="v3-approval-expired",
    )
    tool_request = client.post(
        "/api/agents/local-agent/bridge/tool-requests",
        headers=bridge_headers,
        json={
            "tool_request_id": "tool-req-approval-expired",
            "bridge_task_id": task["id"],
            "tool_name": "write_file",
            "input_json": {"path": "notes.md", "content": "new\n"},
            "execution_target": "host",
            "risk_level": "low",
            "permission_mode": "full-auto",
            "target_paths": ["notes.md"],
            "pending_change_preview": {
                "change_id": "change-expired-approval",
                "target_paths": ["notes.md"],
                "diff_sha256": "c" * 64,
            },
        },
    )
    assert tool_request.status_code == 201, tool_request.text
    decision = tool_request.json()
    request_row = db_session.execute(select(LocalAgentToolRequest)).scalar_one()
    request_row.decision_expires_at = utc_now() - timedelta(minutes=1)
    db_session.commit()

    approved = client.post(
        f"/api/tasks/{sent_payload['run_id']}/tool-approvals/{decision['approval_id']}/approve",
        headers=ADMIN_HEADERS,
        json={"reason": "too late"},
    )

    assert approved.status_code == 409
    assert "expired" in approved.text
    db_session.expire_all()
    request_row = db_session.execute(select(LocalAgentToolRequest)).scalar_one()
    approval = db_session.get(ToolApproval, decision["approval_id"])
    tool_call = db_session.get(ToolCall, decision["tool_call_id"])
    change = db_session.execute(select(LocalAgentPendingChange)).scalar_one()
    assert request_row.status == "expired"
    assert approval is not None
    assert approval.status == "EXPIRED"
    assert tool_call is not None
    assert tool_call.status == "DENIED"
    assert change.status == "denied"

    done = client.post(
        "/api/agents/local-agent/bridge/events",
        headers=bridge_headers,
        json={
            "event_id": "evt-expired-cleanup-done",
            "bridge_task_id": task["id"],
            "event_type": "assistant_done",
            "content": "expired tool skipped",
        },
    )
    assert done.status_code == 201, done.text


def test_local_agent_v3_command_lifecycle_and_result_fail_closed(
    db_session: Session,
) -> None:
    client = TestClient(app)
    connection, device_token = _registered_connection(client, db_session)
    bridge_headers = {"X-Local-Agent-Device-Token": device_token}
    sent_payload, task = _leased_bridge_task(
        client,
        connection["id"],
        device_token,
        client_message_id="v3-command-guards",
    )
    _approved_local_tool_request(
        client,
        bridge_headers=bridge_headers,
        task=task,
        run_id=sent_payload["run_id"],
        tool_request_id="tool-req-command-guards",
    )

    output_before_start = client.post(
        "/api/agents/local-agent/bridge/commands/cmd-guard/events",
        headers=bridge_headers,
        json={
            "event_id": "cmd-guard-output-first",
            "tool_request_id": "tool-req-command-guards",
            "event_type": "output",
            "stdout": "too early",
        },
    )
    assert output_before_start.status_code == 409

    missing_command = client.post(
        "/api/agents/local-agent/bridge/tool-requests/tool-req-command-guards/result",
        headers=bridge_headers,
        json={
            "event_id": "tool-req-command-guards-result-missing-command",
            "status": "SUCCESS",
            "output_json": {"stdout": "ok"},
        },
    )
    assert missing_command.status_code == 409

    started = client.post(
        "/api/agents/local-agent/bridge/commands/cmd-guard/events",
        headers=bridge_headers,
        json={
            "event_id": "cmd-guard-start",
            "tool_request_id": "tool-req-command-guards",
            "event_type": "started",
            "tool_name": "run_shell",
            "command": "printf ok",
        },
    )
    assert started.status_code == 202, started.text

    nonterminal_command = client.post(
        "/api/agents/local-agent/bridge/tool-requests/tool-req-command-guards/result",
        headers=bridge_headers,
        json={
            "event_id": "tool-req-command-guards-result-nonterminal-command",
            "status": "SUCCESS",
            "output_json": {"stdout": "ok"},
            "command_id": "cmd-guard",
        },
    )
    assert nonterminal_command.status_code == 409

    finished = client.post(
        "/api/agents/local-agent/bridge/commands/cmd-guard/events",
        headers=bridge_headers,
        json={
            "event_id": "cmd-guard-finish",
            "tool_request_id": "tool-req-command-guards",
            "event_type": "finished",
            "status": "failed",
            "exit_code": 1,
            "duration_ms": 1,
        },
    )
    assert finished.status_code == 202, finished.text

    success_for_failed_command = client.post(
        "/api/agents/local-agent/bridge/tool-requests/tool-req-command-guards/result",
        headers=bridge_headers,
        json={
            "event_id": "tool-req-command-guards-result-failed-command",
            "status": "SUCCESS",
            "output_json": {"stdout": "ok"},
            "command_id": "cmd-guard",
        },
    )
    assert success_for_failed_command.status_code == 409


def test_local_agent_v3_result_command_must_belong_to_request(
    db_session: Session,
) -> None:
    client = TestClient(app)
    connection, device_token = _registered_connection(client, db_session)
    bridge_headers = {"X-Local-Agent-Device-Token": device_token}
    sent_payload, task = _leased_bridge_task(
        client,
        connection["id"],
        device_token,
        client_message_id="v3-command-ownership",
    )
    _approved_local_tool_request(
        client,
        bridge_headers=bridge_headers,
        task=task,
        run_id=sent_payload["run_id"],
        tool_request_id="tool-req-a",
    )
    _approved_local_tool_request(
        client,
        bridge_headers=bridge_headers,
        task=task,
        run_id=sent_payload["run_id"],
        tool_request_id="tool-req-b",
    )
    _start_and_finish_command(
        client,
        bridge_headers=bridge_headers,
        tool_request_id="tool-req-a",
        command_id="cmd-owned-by-a",
    )

    wrong_request_result = client.post(
        "/api/agents/local-agent/bridge/tool-requests/tool-req-b/result",
        headers=bridge_headers,
        json={
            "event_id": "tool-req-b-result-wrong-command",
            "status": "SUCCESS",
            "output_json": {"stdout": "ok"},
            "command_id": "cmd-owned-by-a",
        },
    )

    assert wrong_request_result.status_code == 409
    assert "does not belong" in wrong_request_result.text


def test_local_agent_v3_retry_creates_fresh_request_and_command(
    db_session: Session,
) -> None:
    client = TestClient(app)
    connection, device_token = _registered_connection(client, db_session)
    bridge_headers = {"X-Local-Agent-Device-Token": device_token}
    sent_payload, task = _leased_bridge_task(
        client,
        connection["id"],
        device_token,
        client_message_id="v3-command-retry",
    )
    _approved_local_tool_request(
        client,
        bridge_headers=bridge_headers,
        task=task,
        run_id=sent_payload["run_id"],
        tool_request_id="tool-req-retry-original",
    )
    _start_and_finish_command(
        client,
        bridge_headers=bridge_headers,
        tool_request_id="tool-req-retry-original",
        command_id="cmd-retry-original",
        status_value="failed",
    )

    retried = client.post(
        (
            f"/api/agents/local-agent/bindings/{task['binding_id']}"
            "/commands/cmd-retry-original/retry"
        ),
        headers=AUTH_HEADERS,
    )

    assert retried.status_code == 202, retried.text
    retry_payload = retried.json()
    assert retry_payload["command_id"] != "cmd-retry-original"
    assert retry_payload["tool_request_id"] != "tool-req-retry-original"
    assert retry_payload["status"] == "pending"
    db_session.expire_all()
    requests = {
        row.tool_request_id: row
        for row in db_session.execute(
            select(LocalAgentToolRequest).order_by(LocalAgentToolRequest.created_at.asc())
        ).scalars()
    }
    assert requests["tool-req-retry-original"].status == "failed"
    assert requests[retry_payload["tool_request_id"]].status == "approved"
    commands = {
        row.command_id: row
        for row in db_session.execute(
            select(LocalAgentCommand).order_by(LocalAgentCommand.created_at.asc())
        ).scalars()
    }
    assert commands["cmd-retry-original"].status == "failed"
    assert commands[retry_payload["command_id"]].retry_of_command_id == "cmd-retry-original"

    mismatched_retry_source = client.post(
        f"/api/agents/local-agent/bridge/commands/{retry_payload['command_id']}/events",
        headers=bridge_headers,
        json={
            "event_id": "cmd-retry-mismatch-start",
            "tool_request_id": retry_payload["tool_request_id"],
            "event_type": "started",
            "tool_name": "run_shell",
            "command": "printf ok",
            "retry_of_command_id": "cmd-other",
        },
    )
    assert mismatched_retry_source.status_code == 409
    assert "retry source" in mismatched_retry_source.text

    _start_and_finish_command(
        client,
        bridge_headers=bridge_headers,
        tool_request_id=retry_payload["tool_request_id"],
        command_id=retry_payload["command_id"],
        retry_of_command_id="cmd-retry-original",
    )
    result = client.post(
        f"/api/agents/local-agent/bridge/tool-requests/{retry_payload['tool_request_id']}/result",
        headers=bridge_headers,
        json={
            "event_id": "tool-req-retry-result",
            "status": "SUCCESS",
            "output_json": {"stdout": "ok"},
            "command_id": retry_payload["command_id"],
        },
    )
    assert result.status_code == 202, result.text
    assert result.json()["decision"] == "succeeded"
    db_session.expire_all()
    original_request = db_session.execute(
        select(LocalAgentToolRequest).where(
            LocalAgentToolRequest.tool_request_id == "tool-req-retry-original"
        )
    ).scalar_one()
    assert original_request.status == "failed"
    retry_request = db_session.execute(
        select(LocalAgentToolRequest).where(
            LocalAgentToolRequest.tool_request_id == retry_payload["tool_request_id"]
        )
    ).scalar_one()
    retry_tool_call = db_session.get(ToolCall, retry_request.tool_call_id)
    assert retry_request.status == "succeeded"
    assert retry_tool_call is not None
    assert retry_tool_call.status == "SUCCESS"


def test_local_agent_v3_retry_rejects_non_retryable_commands(
    db_session: Session,
) -> None:
    client = TestClient(app)
    connection, device_token = _registered_connection(client, db_session)
    bridge_headers = {"X-Local-Agent-Device-Token": device_token}
    sent_payload, task = _leased_bridge_task(
        client,
        connection["id"],
        device_token,
        client_message_id="v3-command-retry-reject",
    )
    _approved_local_tool_request(
        client,
        bridge_headers=bridge_headers,
        task=task,
        run_id=sent_payload["run_id"],
        tool_request_id="tool-req-retry-success",
    )
    _start_and_finish_command(
        client,
        bridge_headers=bridge_headers,
        tool_request_id="tool-req-retry-success",
        command_id="cmd-retry-success",
    )
    success_retry = client.post(
        (
            f"/api/agents/local-agent/bindings/{task['binding_id']}"
            "/commands/cmd-retry-success/retry"
        ),
        headers=AUTH_HEADERS,
    )
    assert success_retry.status_code == 409

    _approved_local_tool_request(
        client,
        bridge_headers=bridge_headers,
        task=task,
        run_id=sent_payload["run_id"],
        tool_request_id="tool-req-retry-pending",
    )
    started = client.post(
        "/api/agents/local-agent/bridge/commands/cmd-retry-pending/events",
        headers=bridge_headers,
        json={
            "event_id": "cmd-retry-pending-start",
            "tool_request_id": "tool-req-retry-pending",
            "event_type": "started",
            "tool_name": "run_shell",
            "command": "printf ok",
        },
    )
    assert started.status_code == 202, started.text
    pending_retry = client.post(
        (
            f"/api/agents/local-agent/bindings/{task['binding_id']}"
            "/commands/cmd-retry-pending/retry"
        ),
        headers=AUTH_HEADERS,
    )
    assert pending_retry.status_code == 409

    denied_request = client.post(
        "/api/agents/local-agent/bridge/tool-requests",
        headers=bridge_headers,
        json={
            "tool_request_id": "tool-req-retry-denied",
            "bridge_task_id": task["id"],
            "tool_name": "run_shell",
            "input_json": {"command": "printf denied"},
            "execution_target": "host",
            "risk_level": "low",
            "permission_mode": "full-auto",
        },
    )
    assert denied_request.status_code == 201, denied_request.text
    rejected = client.post(
        (
            f"/api/tasks/{sent_payload['run_id']}/tool-approvals/"
            f"{denied_request.json()['approval_id']}/reject"
        ),
        headers=ADMIN_HEADERS,
        json={"reason": "reject retry parent"},
    )
    assert rejected.status_code == 202, rejected.text
    denied_command = LocalAgentCommand(
        organization_id=connection.get("organization_id"),
        connection_id=connection["id"],
        binding_id=task["binding_id"],
        bridge_task_id=task["id"],
        task_id=sent_payload["run_id"],
        local_agent_tool_request_id=db_session.execute(
            select(LocalAgentToolRequest.id).where(
                LocalAgentToolRequest.tool_request_id == "tool-req-retry-denied"
            )
        ).scalar_one(),
        tool_request_id="tool-req-retry-denied",
        command_id="cmd-retry-denied",
        tool_name="run_shell",
        command="printf denied",
        status="failed",
        finished_at=utc_now(),
        output_summary_json={},
        event_receipts_json={},
    )
    db_session.add(denied_command)
    db_session.commit()
    denied_retry = client.post(
        (
            f"/api/agents/local-agent/bindings/{task['binding_id']}"
            "/commands/cmd-retry-denied/retry"
        ),
        headers=AUTH_HEADERS,
    )
    assert denied_retry.status_code == 409
    assert "not retryable" in denied_retry.text


def test_local_agent_v3_pending_change_hash_guard_and_unknown_change_fail_closed(
    db_session: Session,
) -> None:
    client = TestClient(app)
    connection, device_token = _registered_connection(client, db_session)
    bridge_headers = {"X-Local-Agent-Device-Token": device_token}
    sent_payload, task = _leased_bridge_task(
        client,
        connection["id"],
        device_token,
        client_message_id="v3-pending-change",
    )
    decision = _approved_local_tool_request(
        client,
        bridge_headers=bridge_headers,
        task=task,
        run_id=sent_payload["run_id"],
        tool_request_id="tool-req-write",
        tool_name="write_file",
        input_json={"path": "notes.md", "content": "new\n"},
        target_paths=["notes.md"],
        pending_change_preview={
            "change_id": "change-write-1",
            "operation": "write_file",
            "target_paths": ["notes.md"],
            "diff_sha256": "a" * 64,
            "preview_bytes": 12,
        },
    )
    polled = client.get(
        "/api/agents/local-agent/bridge/tool-requests/tool-req-write/decision",
        headers=bridge_headers,
    )
    assert polled.status_code == 200, polled.text
    assert polled.json()["decision"] == "approved"
    assert polled.json()["decision_json"]["metadata"]["run_id"] == sent_payload["run_id"]
    assert polled.json()["decision_json"]["pending_change_preview"]["change_id"] == (
        "change-write-1"
    )
    assert polled.json()["approval_id"] == decision["approval_id"]

    missing_change_result = client.post(
        "/api/agents/local-agent/bridge/tool-requests/tool-req-write/result",
        headers=bridge_headers,
        json={
            "event_id": "tool-req-write-result-unknown-change",
            "status": "SUCCESS",
            "output_json": {"changed": True},
            "change_id": "missing-change",
            "diff_sha256": "a" * 64,
        },
    )
    assert missing_change_result.status_code == 409

    mismatched_hash = client.post(
        "/api/agents/local-agent/bridge/tool-requests/tool-req-write/result",
        headers=bridge_headers,
        json={
            "event_id": "tool-req-write-result-bad-hash",
            "status": "SUCCESS",
            "output_json": {"changed": True},
            "change_id": "change-write-1",
            "diff_sha256": "b" * 64,
        },
    )
    assert mismatched_hash.status_code == 409
    db_session.expire_all()
    change = db_session.execute(select(LocalAgentPendingChange)).scalar_one()
    request_row = db_session.execute(select(LocalAgentToolRequest)).scalar_one()
    assert change.status == "failed"
    assert "mismatch" in (change.error_message or "")
    assert request_row.status == "failed"
    tool_call = db_session.get(ToolCall, decision["tool_call_id"])
    assert tool_call is not None
    assert tool_call.status == "FAILED"

    late_success = client.post(
        "/api/agents/local-agent/bridge/tool-requests/tool-req-write/result",
        headers=bridge_headers,
        json={
            "event_id": "tool-req-write-result-late-success",
            "status": "SUCCESS",
            "output_json": {"changed": True},
            "change_id": "change-write-1",
            "diff_sha256": "a" * 64,
        },
    )
    assert late_success.status_code == 409
    db_session.expire_all()
    change = db_session.execute(select(LocalAgentPendingChange)).scalar_one()
    request_row = db_session.execute(select(LocalAgentToolRequest)).scalar_one()
    tool_call = db_session.get(ToolCall, decision["tool_call_id"])
    assert change.status == "failed"
    assert request_row.status == "failed"
    assert tool_call is not None
    assert tool_call.status == "FAILED"


def test_local_agent_v3_pending_discovery_and_recursive_redaction(
    db_session: Session,
) -> None:
    client = TestClient(app)
    connection, device_token = _registered_connection(client, db_session)
    bridge_headers = {"X-Local-Agent-Device-Token": device_token}
    _sent_payload, task = _leased_bridge_task(
        client,
        connection["id"],
        device_token,
        client_message_id="v3-pending-discovery",
    )
    tool_request = client.post(
        "/api/agents/local-agent/bridge/tool-requests",
        headers=bridge_headers,
        json={
            "tool_request_id": "tool-req-pending-list",
            "bridge_task_id": task["id"],
            "tool_name": "run_shell",
            "input_json": {
                "command": "echo safe",
                "items": [
                    "sk-proj-1234567890abcdef",
                    {"Authorization": "Bearer sat-secret-value"},
                ],
            },
            "execution_target": "host",
            "risk_level": "low",
            "permission_mode": "full-auto",
            "metadata": {"nested": ["token=sat-secret-value"]},
        },
    )
    assert tool_request.status_code == 201, tool_request.text
    page = client.get(
        "/api/agents/local-agent/bridge/tool-requests/pending",
        headers=bridge_headers,
    )

    assert page.status_code == 200, page.text
    items = page.json()["items"]
    assert [item["tool_request_id"] for item in items] == ["tool-req-pending-list"]
    assert items[0]["decision"] == "approval_required"
    assert items[0]["input_json"]["items"][0] == "[REDACTED]"
    assert items[0]["input_json"]["items"][1]["Authorization"] == "[REDACTED]"
    assert items[0]["decision_json"]["metadata"]["nested"][0] == "token=[REDACTED]"


def test_local_agent_v3_command_string_redaction_reaches_persisted_audit_rows(
    db_session: Session,
) -> None:
    client = TestClient(app)
    connection, device_token = _registered_connection(client, db_session)
    bridge_headers = {"X-Local-Agent-Device-Token": device_token}
    _sent_payload, task = _leased_bridge_task(
        client,
        connection["id"],
        device_token,
        client_message_id="v3-command-redaction",
    )
    raw_command = (
        "export AWS_SECRET_ACCESS_KEY=supersecret123; "
        "ls /Users/luohao/private-project; "
        "printf 'Authorization: Bearer sat-secret-value'"
    )

    tool_request = client.post(
        "/api/agents/local-agent/bridge/tool-requests",
        headers=bridge_headers,
        json={
            "tool_request_id": "tool-req-command-redaction",
            "bridge_task_id": task["id"],
            "tool_name": "run_shell",
            "input_json": {
                "command": raw_command,
                "target_paths": ["/Users/luohao/private-project/secrets.env"],
            },
            "execution_target": "host",
            "risk_level": "low",
            "permission_mode": "full-auto",
            "cwd": "/Users/luohao/private-project",
            "metadata": {
                "Authorization": "Bearer sat-secret-value",
                "workspace_root": "/Users/luohao/private-project",
            },
        },
    )
    assert tool_request.status_code == 201, tool_request.text

    db_session.expire_all()
    tool_call = db_session.execute(select(ToolCall)).scalar_one()
    approval = db_session.execute(select(ToolApproval)).scalar_one()
    local_request = db_session.execute(select(LocalAgentToolRequest)).scalar_one()
    events = list(db_session.execute(select(AgentEvent)).scalars())
    persisted_payload = json.dumps(
        {
            "tool_call_input": tool_call.input_json,
            "tool_call_snapshot": tool_call.capability_snapshot_json,
            "approval_request": approval.request_json,
            "local_input": local_request.input_json,
            "local_decision": local_request.decision_json,
            "events": [event.payload_json for event in events],
        },
        ensure_ascii=False,
        sort_keys=True,
    )

    assert "supersecret123" not in persisted_payload
    assert "sat-secret-value" not in persisted_payload
    assert "/Users/luohao" not in persisted_payload
    assert "AWS_SECRET_ACCESS_KEY=[REDACTED]" in persisted_payload
    assert "Authorization: Bearer [REDACTED]" in persisted_payload
    assert ".../private-project" in persisted_payload


def test_local_agent_pending_task_is_api_projected_and_not_released_twice(
    db_session: Session,
) -> None:
    client = TestClient(app)
    connection, device_token = _registered_connection(client, db_session)
    bridge_headers = {"X-Local-Agent-Device-Token": device_token}
    binding = client.post(
        f"/api/agents/local-agent/connections/{connection['id']}/bindings",
        headers=AUTH_HEADERS,
        json={"title": "Pending local session"},
    )
    assert binding.status_code == 201, binding.text
    binding_id = binding.json()["id"]
    sent = client.post(
        f"/api/agents/local-agent/bindings/{binding_id}/messages",
        headers=AUTH_HEADERS,
        json={"content": "queue me", "client_message_id": "pending-1"},
    )
    assert sent.status_code == 202, sent.text

    pending_page = client.get(
        f"/api/agents/local-agent/bindings/{binding_id}/tasks",
        headers=AUTH_HEADERS,
    )
    assert pending_page.status_code == 200, pending_page.text
    assert pending_page.json()["items"][0]["id"] == sent.json()["bridge_task_id"]
    assert "payload" not in pending_page.json()["items"][0]

    first_pull = client.get("/api/agents/local-agent/bridge/tasks", headers=bridge_headers)
    assert first_pull.status_code == 200, first_pull.text
    assert [item["id"] for item in first_pull.json()["items"]] == [sent.json()["bridge_task_id"]]
    second_pull = client.get("/api/agents/local-agent/bridge/tasks", headers=bridge_headers)
    assert second_pull.status_code == 200, second_pull.text
    assert second_pull.json()["items"] == []


def test_local_agent_terminal_task_rejects_new_bridge_event_ids(
    db_session: Session,
) -> None:
    client = TestClient(app)
    connection, device_token = _registered_connection(client, db_session)
    bridge_headers = {"X-Local-Agent-Device-Token": device_token}
    binding = client.post(
        f"/api/agents/local-agent/connections/{connection['id']}/bindings",
        headers=AUTH_HEADERS,
        json={"title": "Terminal local session"},
    )
    assert binding.status_code == 201, binding.text
    sent = client.post(
        f"/api/agents/local-agent/bindings/{binding.json()['id']}/messages",
        headers=AUTH_HEADERS,
        json={"content": "finish me", "client_message_id": "terminal-1"},
    )
    assert sent.status_code == 202, sent.text
    task_id = sent.json()["bridge_task_id"]
    done = client.post(
        "/api/agents/local-agent/bridge/events",
        headers=bridge_headers,
        json={
            "event_id": "terminal-done",
            "bridge_task_id": task_id,
            "event_type": "assistant_done",
            "content": "done",
        },
    )
    assert done.status_code == 201, done.text
    replay = client.post(
        "/api/agents/local-agent/bridge/events",
        headers=bridge_headers,
        json={
            "event_id": "terminal-done",
            "bridge_task_id": task_id,
            "event_type": "assistant_done",
            "content": "duplicate",
        },
    )
    assert replay.status_code == 201, replay.text
    assert replay.json()["duplicate"] is True
    late_ack = client.post(
        f"/api/agents/local-agent/bridge/tasks/{task_id}/ack",
        headers=bridge_headers,
        json={"status": "running"},
    )
    assert late_ack.status_code == 409
    db_session.expire_all()
    bridge_task = db_session.get(LocalAgentBridgeTask, task_id)
    assert bridge_task is not None
    assert bridge_task.status == "completed"
    new_event = client.post(
        "/api/agents/local-agent/bridge/events",
        headers=bridge_headers,
        json={
            "event_id": "terminal-error-new",
            "bridge_task_id": task_id,
            "event_type": "assistant_error",
            "error_message": "should not flip",
        },
    )
    assert new_event.status_code == 409
    messages = list(db_session.execute(select(AgentMessage)).scalars())
    assert [message.role for message in messages] == ["user", "assistant"]


def test_local_agent_client_message_id_is_scoped_to_binding(
    db_session: Session,
) -> None:
    client = TestClient(app)
    connection, _device_token = _registered_connection(client, db_session)
    first_binding = client.post(
        f"/api/agents/local-agent/connections/{connection['id']}/bindings",
        headers=AUTH_HEADERS,
        json={"title": "First local coding session"},
    )
    assert first_binding.status_code == 201, first_binding.text
    second_binding = client.post(
        f"/api/agents/local-agent/connections/{connection['id']}/bindings",
        headers=AUTH_HEADERS,
        json={"title": "Second local coding session"},
    )
    assert second_binding.status_code == 201, second_binding.text

    first_sent = client.post(
        f"/api/agents/local-agent/bindings/{first_binding.json()['id']}/messages",
        headers=AUTH_HEADERS,
        json={"content": "first", "client_message_id": "same-client-id"},
    )
    assert first_sent.status_code == 202, first_sent.text
    repeated_first = client.post(
        f"/api/agents/local-agent/bindings/{first_binding.json()['id']}/messages",
        headers=AUTH_HEADERS,
        json={"content": "first again", "client_message_id": "same-client-id"},
    )
    assert repeated_first.status_code == 202, repeated_first.text
    assert repeated_first.json()["bridge_task_id"] == first_sent.json()["bridge_task_id"]

    second_sent = client.post(
        f"/api/agents/local-agent/bindings/{second_binding.json()['id']}/messages",
        headers=AUTH_HEADERS,
        json={"content": "second", "client_message_id": "same-client-id"},
    )
    assert second_sent.status_code == 202, second_sent.text
    assert second_sent.json()["bridge_task_id"] != first_sent.json()["bridge_task_id"]


def test_local_agent_non_owner_and_operator_cannot_execute(
    db_session: Session,
) -> None:
    client = TestClient(app)
    connection, _device_token = _registered_connection(client, db_session)
    binding = client.post(
        f"/api/agents/local-agent/connections/{connection['id']}/bindings",
        headers=AUTH_HEADERS,
        json={"title": "Local coding session"},
    )
    assert binding.status_code == 201

    other_org = client.post(
        f"/api/agents/local-agent/bindings/{binding.json()['id']}/messages",
        headers=OTHER_ORG_HEADERS,
        json={"content": "try", "client_message_id": "other"},
    )
    assert other_org.status_code in {403, 404}

    operator = client.post(
        f"/api/agents/local-agent/bindings/{binding.json()['id']}/messages",
        headers=OPERATOR_HEADERS,
        json={"content": "try", "client_message_id": "operator"},
    )
    assert operator.status_code == 403


def test_local_agent_lists_bindings_for_owner_and_admin_only(
    db_session: Session,
) -> None:
    client = TestClient(app)
    connection, _device_token = _registered_connection(client, db_session)
    binding = client.post(
        f"/api/agents/local-agent/connections/{connection['id']}/bindings",
        headers=AUTH_HEADERS,
        json={"title": "Workspace local session"},
    )
    assert binding.status_code == 201, binding.text

    owner_list = client.get(
        f"/api/agents/local-agent/connections/{connection['id']}/bindings",
        headers=AUTH_HEADERS,
    )
    assert owner_list.status_code == 200, owner_list.text
    assert [item["id"] for item in owner_list.json()["items"]] == [binding.json()["id"]]

    admin_list = client.get(
        f"/api/agents/local-agent/connections/{connection['id']}/bindings",
        headers=ADMIN_HEADERS,
    )
    assert admin_list.status_code == 200, admin_list.text
    assert [item["id"] for item in admin_list.json()["items"]] == [binding.json()["id"]]

    operator_list = client.get(
        f"/api/agents/local-agent/connections/{connection['id']}/bindings",
        headers=OPERATOR_HEADERS,
    )
    assert operator_list.status_code == 403


def test_local_agent_connection_list_projects_stale_heartbeat_offline(
    db_session: Session,
) -> None:
    client = TestClient(app)
    connection, _device_token = _registered_connection(client, db_session)
    row = db_session.get(LocalAgentConnection, connection["id"])
    assert row is not None
    row.status = "online"
    row.last_seen_at = utc_now() - timedelta(seconds=90)
    db_session.commit()

    listed = client.get("/api/agents/local-agent/connections", headers=AUTH_HEADERS)
    assert listed.status_code == 200, listed.text
    projected = next(item for item in listed.json()["items"] if item["id"] == connection["id"])
    assert projected["status"] == "offline"


def test_local_agent_revoke_blocks_bridge_pull(db_session: Session) -> None:
    client = TestClient(app)
    connection, device_token = _registered_connection(client, db_session)

    revoked = client.post(
        f"/api/agents/local-agent/connections/{connection['id']}/revoke",
        headers=ADMIN_HEADERS,
    )
    assert revoked.status_code == 200, revoked.text
    assert revoked.json()["status"] == "revoked"

    pull = client.get(
        "/api/agents/local-agent/bridge/tasks",
        headers={"X-Local-Agent-Device-Token": device_token},
    )
    assert pull.status_code == 403
    audit_actions = {
        event.action
        for event in db_session.execute(
            select(AdminAuditEvent).where(AdminAuditEvent.event_type == "LOCAL_AGENT_LIFECYCLE")
        ).scalars()
    }
    assert "local_agent.connection.revoke" in audit_actions


def test_local_agent_v3_revoke_terminalizes_pending_tool_state(
    db_session: Session,
) -> None:
    client = TestClient(app)
    connection, device_token = _registered_connection(client, db_session)
    bridge_headers = {"X-Local-Agent-Device-Token": device_token}
    sent_payload, task = _leased_bridge_task(
        client,
        connection["id"],
        device_token,
        client_message_id="v3-revoke-pending-tool",
    )
    tool_request = client.post(
        "/api/agents/local-agent/bridge/tool-requests",
        headers=bridge_headers,
        json={
            "tool_request_id": "tool-req-revoke-pending",
            "bridge_task_id": task["id"],
            "tool_name": "write_file",
            "input_json": {"path": "notes.md", "content": "new\n"},
            "execution_target": "host",
            "risk_level": "low",
            "permission_mode": "full-auto",
            "target_paths": ["notes.md"],
            "pending_change_preview": {
                "change_id": "change-revoke-pending",
                "target_paths": ["notes.md"],
                "diff_sha256": "d" * 64,
            },
        },
    )
    assert tool_request.status_code == 201, tool_request.text
    decision = tool_request.json()
    command = LocalAgentCommand(
        organization_id=connection.get("organization_id"),
        connection_id=connection["id"],
        binding_id=task["binding_id"],
        bridge_task_id=task["id"],
        task_id=sent_payload["run_id"],
        local_agent_tool_request_id=db_session.execute(
            select(LocalAgentToolRequest.id).where(
                LocalAgentToolRequest.tool_request_id == "tool-req-revoke-pending"
            )
        ).scalar_one(),
        tool_request_id="tool-req-revoke-pending",
        command_id="cmd-revoke-pending",
        tool_name="write_file",
        command="write notes.md",
        status="pending",
        output_summary_json={},
        event_receipts_json={},
    )
    db_session.add(command)
    db_session.commit()

    revoked = client.post(
        f"/api/agents/local-agent/connections/{connection['id']}/revoke",
        headers=AUTH_HEADERS,
    )

    assert revoked.status_code == 200, revoked.text
    db_session.expire_all()
    request_row = db_session.execute(select(LocalAgentToolRequest)).scalar_one()
    approval = db_session.get(ToolApproval, decision["approval_id"])
    tool_call = db_session.get(ToolCall, decision["tool_call_id"])
    change = db_session.execute(select(LocalAgentPendingChange)).scalar_one()
    command = db_session.execute(select(LocalAgentCommand)).scalar_one()
    bridge_task = db_session.get(LocalAgentBridgeTask, task["id"])
    run = db_session.get(Task, sent_payload["run_id"])
    assert request_row.status == "cancelled"
    assert approval is not None
    assert approval.status == "DENIED"
    assert tool_call is not None
    assert tool_call.status == "CANCELLED"
    assert change.status == "denied"
    assert command.status == "cancelled"
    assert bridge_task is not None
    assert bridge_task.status == "cancelled"
    assert run is not None
    assert run.status == "CANCELLED"

    late_result = client.post(
        "/api/agents/local-agent/bridge/tool-requests/tool-req-revoke-pending/result",
        headers=bridge_headers,
        json={
            "event_id": "tool-req-revoke-late-result",
            "status": "SUCCESS",
            "output_json": {"changed": True},
            "change_id": "change-revoke-pending",
            "diff_sha256": "d" * 64,
        },
    )
    assert late_result.status_code == 403
