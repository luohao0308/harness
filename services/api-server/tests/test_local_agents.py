import json
import shlex
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.model_gateway import AuditedModelGateway, ModelStreamChunk
from app.core.config import get_settings
from app.db.models import (
    AdminAuditEvent,
    Agent,
    AgentEvent,
    AgentMessage,
    AgentSession,
    LocalAgentBridgeEventReceipt,
    LocalAgentBridgeTask,
    LocalAgentCommand,
    LocalAgentConnection,
    LocalAgentConversationBinding,
    LocalAgentPairingToken,
    LocalAgentPendingChange,
    LocalAgentToolRequest,
    ModelCall,
    OrganizationMember,
    SystemSetting,
    Task,
    ToolApproval,
    ToolCall,
    User,
    utc_now,
)
from app.main import app
from app.security.jwt_utils import decode_jwt, issue_access_token
from app.tools.capabilities import CapabilityRegistry
from tests.conftest import AUTH_HEADERS

ADMIN_HEADERS = {"Authorization": "Bearer dev-admin-token"}
OPERATOR_HEADERS = {"Authorization": "Bearer dev-operator-token"}
OTHER_ORG_HEADERS = {"Authorization": "Bearer dev-other-org-token"}
LOCAL_AGENT_NPX_COMMAND_PREFIX = (
    f"npx -y {shlex.quote(str(Path(__file__).resolve().parents[1]))} bridge pair"
)


def _ensure_agent(session: Session, agent_id: str = "default") -> Agent:
    local_tools = [
        "read_file",
        "list_files",
        "write_file",
        "run_shell",
        "run_tests",
        "git_command",
        "network_request",
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


def _ensure_dev_engineer_member(session: Session) -> None:
    user = session.get(User, "dev-engineer")
    if user is None:
        session.add(
            User(
                id="dev-engineer",
                email="dev-engineer@example.com",
                name="Dev Engineer",
                password_hash="dev",
                email_verified=True,
                status="active",
                created_at=utc_now(),
                updated_at=utc_now(),
            )
        )
    membership = session.execute(
        select(OrganizationMember).where(
            OrganizationMember.organization_id == "dev-org",
            OrganizationMember.user_id == "dev-engineer",
        )
    ).scalar_one_or_none()
    if membership is None:
        session.add(
            OrganizationMember(
                organization_id="dev-org",
                user_id="dev-engineer",
                role="member",
                invited_at=utc_now(),
                accepted_at=utc_now(),
            )
        )
    session.commit()


def _confirm_connection(
    client: TestClient,
    connection: dict | str,
    *,
    display_name: str = "Confirmed Local Agent",
) -> dict:
    connection_id = connection if isinstance(connection, str) else connection["id"]
    current_display_name = (
        display_name
        if isinstance(connection, str)
        else str(connection.get("display_name") or display_name)
    )
    confirmed = client.patch(
        f"/api/agents/local-agent/connections/{connection_id}",
        headers=AUTH_HEADERS,
        json={"display_name": current_display_name},
    )
    assert confirmed.status_code == 200, confirmed.text
    return confirmed.json()


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
            "capabilities": {
                "supports_resume": True,
                "supports_streaming": True,
                "supports_cancel": True,
                "host_tools_authorized": True,
                "permission_defer_supported": True,
                "tool_execution_authority": "harness_approved_local_bridge",
            },
            "risk_capabilities": ["host_read", "host_write", "shell", "git", "network"],
        },
    )
    assert registered.status_code == 201, registered.text
    payload = registered.json()
    return _confirm_connection(client, payload["connection"]), payload["device_token"]


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
    return _confirm_connection(client, payload["connection"]), payload["device_token"]


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
    return _confirm_connection(client, payload["connection"]), payload["device_token"]


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
    _confirm_connection(client, connection_id)
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


def _sse_events(response_text: str) -> list[dict]:
    events: list[dict] = []
    current_event = "message"
    data_lines: list[str] = []
    for raw_line in response_text.splitlines():
        line = raw_line.rstrip("\r")
        if not line:
            if data_lines:
                payload = json.loads("\n".join(data_lines))
                events.append({"event": current_event, "data": payload})
                current_event = "message"
                data_lines = []
            continue
        if line.startswith(":"):
            continue
        if line.startswith("event:"):
            current_event = line.split(":", 1)[1].strip()
        elif line.startswith("data:"):
            data_lines.append(line.split(":", 1)[1].strip())
    if data_lines:
        events.append({"event": current_event, "data": json.loads("\n".join(data_lines))})
    return events


def test_local_agent_pairing_registers_with_hashed_token_and_multi_adapter_default(
    db_session: Session,
    monkeypatch,
    request,
) -> None:
    monkeypatch.setenv("API_BASE_URL", "http://harness.internal:18000")
    get_settings.cache_clear()
    request.addfinalizer(get_settings.cache_clear)
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
    assert payload["pair_code"] in payload["command"]
    assert payload["command"].startswith(LOCAL_AGENT_NPX_COMMAND_PREFIX)
    assert "--api http://harness.internal:18000" in payload["command"]
    assert "--pair-code" in payload["command"]
    assert payload["command"].endswith(" --daemon")
    assert "@harness/hao@latest" not in payload["command"]
    assert "--registry=" not in payload["command"]

    token = db_session.get(LocalAgentPairingToken, payload["id"])
    assert token is not None
    assert token.token_hash != payload["pair_token"]
    assert len(token.token_hash) == 64

    assert "--adapter" not in payload["command"]

    registered_hao = client.post(
        "/api/agents/local-agent/connections/register",
        json={
            "pair_token": payload["pair_token"],
            "pair_code": payload["pair_code"],
            "adapter_kind": "hao",
            "display_name": "hao Local",
            "protocol_version": "local-agent-v1",
        },
    )
    assert registered_hao.status_code == 201, registered_hao.text
    assert registered_hao.json()["device_token"]
    assert registered_hao.json()["connection"]["workspace_root"] is None
    assert registered_hao.json()["connection"]["pairing_token_id"] == payload["id"]
    assert registered_hao.json()["connection"]["onboarding_confirmed"] is False
    assert registered_hao.json()["connection"]["status"] == "pending_confirmation"

    registered_codex = client.post(
        "/api/agents/local-agent/connections/register",
        json={
            "pair_token": payload["pair_token"],
            "pair_code": payload["pair_code"],
            "adapter_kind": "codex",
            "display_name": "Codex CLI",
            "protocol_version": "local-agent-v1",
            "workspace_root": "/Users/luohao/private-demo",
            "metadata": {"workspace_identity_hash": "hash-codex"},
        },
    )
    assert registered_codex.status_code == 201, registered_codex.text
    assert registered_codex.json()["connection"]["pairing_token_id"] == payload["id"]
    assert registered_codex.json()["connection"]["onboarding_confirmed"] is False
    assert registered_codex.json()["connection"]["status"] == "pending_confirmation"

    registered_claude = client.post(
        "/api/agents/local-agent/connections/register",
        json={
            "pair_token": payload["pair_token"],
            "pair_code": payload["pair_code"],
            "adapter_kind": "claude_code",
            "display_name": "Claude Code",
            "protocol_version": "local-agent-v1",
            "workspace_root": "/Users/luohao/private-demo",
            "metadata": {"workspace_identity_hash": "hash-claude"},
        },
    )
    assert registered_claude.status_code == 201, registered_claude.text
    assert registered_claude.json()["connection"]["pairing_token_id"] == payload["id"]
    assert registered_claude.json()["connection"]["onboarding_confirmed"] is False
    assert registered_claude.json()["connection"]["status"] == "pending_confirmation"

    confirmed_codex = client.patch(
        f"/api/agents/local-agent/connections/{registered_codex.json()['connection']['id']}",
        headers=AUTH_HEADERS,
        json={"display_name": "Codex CLI confirmed"},
    )
    assert confirmed_codex.status_code == 200, confirmed_codex.text
    assert confirmed_codex.json()["display_name"] == "Codex CLI confirmed"
    assert confirmed_codex.json()["onboarding_confirmed"] is True
    assert confirmed_codex.json()["status"] == "online"

    reused = client.post(
        "/api/agents/local-agent/connections/register",
        json={
            "pair_token": payload["pair_token"],
            "pair_code": payload["pair_code"],
            "adapter_kind": "hao",
            "protocol_version": "local-agent-v1",
        },
    )
    assert reused.status_code == 410
    db_session.refresh(token)
    assert token.status == "active"
    assert token.consumed_at is not None
    connections = db_session.execute(
        select(LocalAgentConnection).order_by(LocalAgentConnection.adapter_kind.asc())
    ).scalars().all()
    assert [connection.adapter_kind for connection in connections] == [
        "claude_code",
        "codex",
        "hao",
    ]
    connection_by_adapter = {connection.adapter_kind: connection for connection in connections}
    for adapter_kind in ("claude_code", "codex", "hao"):
        assert (
            connection_by_adapter[adapter_kind].metadata_json["local_tool_policy"]
            == "harness_approved_local_bridge"
        )
    assert (
        connection_by_adapter["codex"].device_token_hash
        != registered_codex.json()["device_token"]
    )
    assert (
        connection_by_adapter["claude_code"].device_token_hash
        != registered_claude.json()["device_token"]
    )
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
    get_settings.cache_clear()


def test_local_agent_unconfirmed_connection_cannot_execute_until_confirmed(
    db_session: Session,
) -> None:
    _ensure_agent(db_session)
    client = TestClient(app)
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
            "adapter_kind": "codex",
            "display_name": "Codex CLI",
            "protocol_version": "local-agent-v1",
            "bridge_version": "0.1.0",
            "workspace_root": "/Users/luohao/projects/demo",
            "capabilities": {
                "supports_resume": True,
                "supports_streaming": True,
                "host_tools_authorized": True,
                "permission_defer_supported": True,
                "tool_execution_authority": "harness_approved_local_bridge",
            },
            "risk_capabilities": ["host_read", "host_write", "shell", "git", "network"],
        },
    )
    assert registered.status_code == 201, registered.text
    connection = registered.json()["connection"]
    bridge_headers = {"X-Local-Agent-Device-Token": registered.json()["device_token"]}
    assert connection["onboarding_confirmed"] is False
    assert connection["status"] == "pending_confirmation"

    heartbeat = client.post(
        f"/api/agents/local-agent/connections/{connection['id']}/heartbeat",
        headers=bridge_headers,
        json={
            "status": "online",
            "protocol_version": "local-agent-v1",
            "bridge_version": "0.1.1",
        },
    )
    assert heartbeat.status_code == 200, heartbeat.text
    assert heartbeat.json()["connection"]["onboarding_confirmed"] is False
    assert heartbeat.json()["connection"]["status"] == "pending_confirmation"
    listed = client.get("/api/agents/local-agent/connections", headers=AUTH_HEADERS)
    assert listed.status_code == 200, listed.text
    listed_connection = next(
        item for item in listed.json()["items"] if item["id"] == connection["id"]
    )
    assert listed_connection["onboarding_confirmed"] is False
    assert listed_connection["status"] == "pending_confirmation"

    rejected_binding = client.post(
        f"/api/agents/local-agent/connections/{connection['id']}/bindings",
        headers=AUTH_HEADERS,
        json={"title": "Unconfirmed Codex", "resume_mode": "native_resume"},
    )
    assert rejected_binding.status_code == 409
    assert "not been confirmed" in rejected_binding.text

    agent_session = AgentSession(
        organization_id="dev-org",
        agent_id="default",
        created_by="dev-engineer",
        title="Manual bypass session",
        status="ACTIVE",
        created_at=utc_now(),
        updated_at=utc_now(),
    )
    db_session.add(agent_session)
    db_session.flush()
    binding = LocalAgentConversationBinding(
        organization_id="dev-org",
        owner_user_id="dev-engineer",
        connection_id=connection["id"],
        agent_id="default",
        agent_session_id=agent_session.id,
        resume_mode="native_resume",
        status="active",
        metadata_json={},
        created_at=utc_now(),
        updated_at=utc_now(),
    )
    db_session.add(binding)
    task = Task(
        organization_id="dev-org",
        agent_id="default",
        created_by="dev-engineer",
        title="Unconfirmed command bypass",
        goal="Do not run",
        status="WAITING_APPROVAL",
        model_provider="default",
        model_name="default",
        created_at=utc_now(),
        updated_at=utc_now(),
    )
    db_session.add(task)
    db_session.flush()
    user_message = AgentMessage(
        session_id=agent_session.id,
        agent_id="default",
        role="user",
        content="Do not run",
        metadata_json={},
        created_at=utc_now(),
    )
    db_session.add(user_message)
    db_session.flush()
    bridge_task = LocalAgentBridgeTask(
        organization_id="dev-org",
        owner_user_id="dev-engineer",
        connection_id=connection["id"],
        binding_id=binding.id,
        agent_session_id=agent_session.id,
        task_id=task.id,
        user_message_id=user_message.id,
        client_message_id="unconfirmed-command-task",
        status="running",
        payload_json={},
        created_at=utc_now(),
        updated_at=utc_now(),
    )
    db_session.add(bridge_task)
    db_session.flush()
    tool_call = ToolCall(
        task_id=task.id,
        tool_name="run_shell",
        status="FAILED",
        risk_level="medium",
        requires_sandbox=False,
        input_json={"command": "printf nope"},
        output_json={},
        created_at=utc_now(),
    )
    db_session.add(tool_call)
    db_session.flush()
    local_request = LocalAgentToolRequest(
        organization_id="dev-org",
        connection_id=connection["id"],
        binding_id=binding.id,
        bridge_task_id=bridge_task.id,
        task_id=task.id,
        tool_request_id="unconfirmed-command-request",
        tool_call_id=tool_call.id,
        tool_name="run_shell",
        execution_target="host",
        risk_level="medium",
        permission_mode="full-auto",
        status="failed",
        input_json={"command": "printf nope"},
        policy_decision_json={"decision": "approval_required"},
        decision_json={
            "decision": "approved",
            "input_json": {"command": "printf nope"},
            "executable_input_sha256": "x",
        },
        result_json={},
        created_at=utc_now(),
        updated_at=utc_now(),
    )
    db_session.add(local_request)
    db_session.flush()
    command = LocalAgentCommand(
        organization_id="dev-org",
        connection_id=connection["id"],
        binding_id=binding.id,
        bridge_task_id=bridge_task.id,
        task_id=task.id,
        local_agent_tool_request_id=local_request.id,
        tool_request_id=local_request.tool_request_id,
        command_id="unconfirmed-command",
        tool_name="run_shell",
        command="printf nope",
        status="failed",
        output_summary_json={},
        event_receipts_json={},
        created_at=utc_now(),
        updated_at=utc_now(),
    )
    db_session.add(command)
    db_session.commit()
    rejected_send = client.post(
        f"/api/agents/local-agent/bindings/{binding.id}/messages",
        headers=AUTH_HEADERS,
        json={"content": "should not execute", "client_message_id": "unconfirmed-send"},
    )
    assert rejected_send.status_code == 409
    assert "not been confirmed" in rejected_send.text

    rejected_pull = client.get("/api/agents/local-agent/bridge/tasks", headers=bridge_headers)
    assert rejected_pull.status_code == 409
    assert "not been confirmed" in rejected_pull.text

    rejected_event = client.post(
        "/api/agents/local-agent/bridge/events",
        headers=bridge_headers,
        json={
            "event_id": "unconfirmed-event",
            "bridge_task_id": "missing-task",
            "event_type": "assistant_done",
            "content": "nope",
        },
    )
    assert rejected_event.status_code == 409
    assert "not been confirmed" in rejected_event.text

    rejected_tool = client.post(
        "/api/agents/local-agent/bridge/tool-requests",
        headers=bridge_headers,
        json={
            "tool_request_id": "unconfirmed-tool",
            "bridge_task_id": "missing-task",
            "tool_name": "read_file",
            "input_json": {"path": "README.md"},
            "execution_target": "host",
        },
    )
    assert rejected_tool.status_code == 409
    assert "not been confirmed" in rejected_tool.text

    rejected_cancel = client.post(
        f"/api/agents/local-agent/bindings/{binding.id}/commands/{command.command_id}/cancel",
        headers=AUTH_HEADERS,
    )
    assert rejected_cancel.status_code == 409
    assert "not been confirmed" in rejected_cancel.text

    rejected_retry = client.post(
        f"/api/agents/local-agent/bindings/{binding.id}/commands/{command.command_id}/retry",
        headers=AUTH_HEADERS,
    )
    assert rejected_retry.status_code == 409
    assert "not been confirmed" in rejected_retry.text

    confirmed = client.patch(
        f"/api/agents/local-agent/connections/{connection['id']}",
        headers=AUTH_HEADERS,
        json={"display_name": "Codex CLI confirmed"},
    )
    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json()["onboarding_confirmed"] is True
    assert confirmed.json()["status"] == "online"

    allowed_binding = client.post(
        f"/api/agents/local-agent/connections/{connection['id']}/bindings",
        headers=AUTH_HEADERS,
        json={"title": "Confirmed Codex", "resume_mode": "native_resume"},
    )
    assert allowed_binding.status_code == 201, allowed_binding.text


def test_local_agent_pending_confirmation_status_is_not_executable_even_if_metadata_is_dirty(
    db_session: Session,
) -> None:
    client = TestClient(app)
    connection, device_token = _registered_connection(client, db_session)
    row = db_session.get(LocalAgentConnection, connection["id"])
    assert row is not None
    row.status = "pending_confirmation"
    row.metadata_json = {
        **(row.metadata_json if isinstance(row.metadata_json, dict) else {}),
        "onboarding_confirmed": True,
    }
    db_session.commit()

    bridge_headers = {"X-Local-Agent-Device-Token": device_token}
    heartbeat = client.post(
        f"/api/agents/local-agent/connections/{connection['id']}/heartbeat",
        headers=bridge_headers,
        json={
            "status": "online",
            "protocol_version": "local-agent-v1",
            "bridge_version": "0.1.2",
        },
    )
    assert heartbeat.status_code == 200, heartbeat.text
    assert heartbeat.json()["connection"]["onboarding_confirmed"] is True
    assert heartbeat.json()["connection"]["status"] == "pending_confirmation"

    rejected_binding = client.post(
        f"/api/agents/local-agent/connections/{connection['id']}/bindings",
        headers=AUTH_HEADERS,
        json={"title": "Dirty pending state", "resume_mode": "native_resume"},
    )
    assert rejected_binding.status_code == 409
    assert "not been confirmed" in rejected_binding.text

    rejected_pull = client.get("/api/agents/local-agent/bridge/tasks", headers=bridge_headers)
    assert rejected_pull.status_code == 409
    assert "not been confirmed" in rejected_pull.text

    confirmed = client.patch(
        f"/api/agents/local-agent/connections/{connection['id']}",
        headers=AUTH_HEADERS,
        json={"display_name": "Dirty pending confirmed"},
    )
    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json()["onboarding_confirmed"] is True
    assert confirmed.json()["status"] == "online"

    allowed_binding = client.post(
        f"/api/agents/local-agent/connections/{connection['id']}/bindings",
        headers=AUTH_HEADERS,
        json={"title": "Dirty pending confirmed", "resume_mode": "native_resume"},
    )
    assert allowed_binding.status_code == 201, allowed_binding.text


def test_local_agent_revoked_pairing_token_blocks_late_codex_registration(
    db_session: Session,
) -> None:
    _ensure_agent(db_session)
    client = TestClient(app)
    created = client.post(
        "/api/agents/local-agent/pairing-tokens",
        headers=AUTH_HEADERS,
        json={"agent_id": "default", "ttl_minutes": 5},
    )
    assert created.status_code == 201, created.text
    pairing = created.json()

    registered_hao = client.post(
        "/api/agents/local-agent/connections/register",
        json={
            "pair_token": pairing["pair_token"],
            "pair_code": pairing["pair_code"],
            "adapter_kind": "hao",
            "display_name": "hao Local Agent",
            "protocol_version": "local-agent-v1",
        },
    )
    assert registered_hao.status_code == 201, registered_hao.text
    assert registered_hao.json()["connection"]["onboarding_confirmed"] is False

    revoked = client.post(
        f"/api/agents/local-agent/pairing-tokens/{pairing['id']}/revoke",
        headers=AUTH_HEADERS,
    )
    assert revoked.status_code == 200, revoked.text
    assert revoked.json()["status"] == "revoked"
    assert revoked.json()["pair_token"] is None
    assert revoked.json()["command"] is None

    late_codex = client.post(
        "/api/agents/local-agent/connections/register",
        json={
            "pair_token": pairing["pair_token"],
            "pair_code": pairing["pair_code"],
            "adapter_kind": "codex",
            "display_name": "Codex CLI",
            "protocol_version": "local-agent-v1",
            "capabilities": {
                "supports_resume": False,
                "supports_streaming": True,
                "supports_cancel": True,
                "host_tools_authorized": True,
                "permission_defer_supported": True,
                "tool_execution_authority": "harness_approved_local_bridge",
            },
            "risk_capabilities": ["host_read", "host_write", "shell", "git", "network"],
        },
    )
    assert late_codex.status_code == 410, late_codex.text
    assert "already used or revoked" in late_codex.text

    connections = db_session.execute(
        select(LocalAgentConnection).order_by(LocalAgentConnection.adapter_kind.asc())
    ).scalars().all()
    assert [connection.adapter_kind for connection in connections] == ["hao"]


def test_local_agent_recovery_command_restarts_confirmed_connection(
    db_session: Session,
) -> None:
    client = TestClient(app)
    connection, device_token = _registered_connection(client, db_session)
    row = db_session.get(LocalAgentConnection, connection["id"])
    assert row is not None
    row.status = "online"
    row.last_seen_at = utc_now() - timedelta(minutes=10)
    db_session.commit()

    response = client.get(
        f"/api/agents/local-agent/connections/{connection['id']}/recovery-command",
        headers=AUTH_HEADERS,
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    command = payload["command"]
    package_spec = shlex.quote(str(Path(__file__).resolve().parents[1]))
    assert payload["connection_id"] == connection["id"]
    assert payload["adapter_kind"] == "hao"
    assert payload["state_home"] == "$HOME/.hao/bridges/hao"
    assert payload["status"] == "offline"
    assert command.startswith(
        f'HAO_HOME="${{HAO_HOME:-$HOME/.hao/bridges/hao}}" '
        f"npx -y {package_spec} bridge run"
    )
    assert f"--connection-id {connection['id']}" in command
    assert "--adapter hao" in command
    assert command.endswith(" --daemon")
    assert "bridge pair" not in command
    assert "--device-token" not in command
    assert device_token not in command


def test_local_agent_pairing_command_can_use_published_npm_package_override(
    db_session: Session,
    monkeypatch,
    request,
) -> None:
    monkeypatch.setenv("LOCAL_AGENT_NPX_PACKAGE", "@harness/hao@latest")
    monkeypatch.setenv("LOCAL_AGENT_NPX_REGISTRY", "https://registry.npmmirror.com")
    get_settings.cache_clear()
    request.addfinalizer(get_settings.cache_clear)
    client = TestClient(app)
    _ensure_agent(db_session)

    created = client.post(
        "/api/agents/local-agent/pairing-tokens",
        headers=AUTH_HEADERS,
        json={"agent_id": "default", "ttl_minutes": 5},
    )

    assert created.status_code == 201, created.text
    command = created.json()["command"]
    assert command.startswith(
        "npx -y --registry=https://registry.npmmirror.com @harness/hao@latest bridge pair"
    )
    assert f"--pair-token {created.json()['pair_token']}" in command
    assert f"--pair-code {created.json()['pair_code']}" in command
    assert command.endswith(" --daemon")
    assert "--adapter" not in command


def test_local_agent_pairing_command_does_not_add_registry_for_git_package_override(
    db_session: Session,
    monkeypatch,
    request,
) -> None:
    monkeypatch.setenv("LOCAL_AGENT_NPX_PACKAGE", "github:harness/hao")
    monkeypatch.setenv("LOCAL_AGENT_NPX_REGISTRY", "https://registry.npmmirror.com")
    get_settings.cache_clear()
    request.addfinalizer(get_settings.cache_clear)
    client = TestClient(app)
    _ensure_agent(db_session)

    created = client.post(
        "/api/agents/local-agent/pairing-tokens",
        headers=AUTH_HEADERS,
        json={"agent_id": "default", "ttl_minutes": 5},
    )

    assert created.status_code == 201, created.text
    command = created.json()["command"]
    assert command.startswith("npx -y github:harness/hao bridge pair")
    assert "--registry=" not in command


def test_local_agent_explicit_single_adapter_pairing_is_single_use(
    db_session: Session,
) -> None:
    client = TestClient(app)
    _ensure_agent(db_session)

    created = client.post(
        "/api/agents/local-agent/pairing-tokens",
        headers=AUTH_HEADERS,
        json={
            "agent_id": "default",
            "ttl_minutes": 5,
            "scope": {"executable": True, "adapters": ["fake"]},
        },
    )
    assert created.status_code == 201, created.text
    payload = created.json()

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
    token = db_session.get(LocalAgentPairingToken, payload["id"])
    assert token is not None
    assert token.status == "consumed"


def test_local_agent_host_tool_protocol_requires_server_policy(
    db_session: Session,
) -> None:
    client = TestClient(app)
    _ensure_agent(db_session)
    created = client.post(
        "/api/agents/local-agent/pairing-tokens",
        headers=AUTH_HEADERS,
        json={
            "agent_id": "default",
            "ttl_minutes": 5,
            "scope": {"executable": True, "adapters": ["fake"]},
        },
    )
    assert created.status_code == 201, created.text
    pairing = created.json()
    registered = client.post(
        "/api/agents/local-agent/connections/register",
        json={
            "pair_token": pairing["pair_token"],
            "pair_code": pairing["pair_code"],
            "adapter_kind": "fake",
            "display_name": "Untrusted Fake",
            "protocol_version": "local-agent-v1",
            "capabilities": {"host_tools_authorized": True},
            "metadata": {"local_tool_policy": "harness_approved_local_bridge"},
        },
    )
    assert registered.status_code == 201, registered.text
    connection = registered.json()["connection"]
    assert connection["capabilities_json"]["host_tools_authorized"] is True
    row = db_session.get(LocalAgentConnection, connection["id"])
    assert row is not None
    assert "local_tool_policy" not in row.metadata_json
    device_token = registered.json()["device_token"]
    _sent, task = _leased_bridge_task(
        client,
        connection["id"],
        device_token,
        client_message_id="fake-host-tool-policy",
    )

    rejected = client.post(
        "/api/agents/local-agent/bridge/tool-requests",
        headers={"X-Local-Agent-Device-Token": device_token},
        json={
            "tool_request_id": "fake-tool-req",
            "bridge_task_id": task["id"],
            "tool_name": "run_shell",
            "input_json": {"command": "printf bypass"},
            "execution_target": "host",
            "risk_level": "low",
            "permission_mode": "full-auto",
        },
    )

    assert rejected.status_code == 409, rejected.text
    assert "fake adapter cannot use local host tool protocol" in rejected.text


def test_local_agent_connection_display_name_can_be_updated(
    db_session: Session,
) -> None:
    client = TestClient(app)
    connection, _device_token = _registered_connection(client, db_session)

    updated = client.patch(
        f"/api/agents/local-agent/connections/{connection['id']}",
        headers=AUTH_HEADERS,
        json={"display_name": "本机 Claude"},
    )

    assert updated.status_code == 200, updated.text
    assert updated.json()["display_name"] == "本机 Claude"
    row = db_session.get(LocalAgentConnection, connection["id"])
    assert row is not None
    assert row.display_name == "本机 Claude"


def test_local_agent_v5_supports_full_permission_assistant_adapters(
    db_session: Session,
) -> None:
    client = TestClient(app)
    _ensure_agent(db_session)

    expected = {
        "codex": {
            "display_name": "Codex CLI",
            "workspace_identity_hash": "hash-codex",
            "enabled_flag": "enabled_in_v4",
            "risk_capabilities": ["host_read", "host_write", "shell", "git", "network"],
        },
        "claude_code": {
            "display_name": "Claude Code",
            "workspace_identity_hash": "hash-claude",
            "enabled_flag": "enabled_in_v5",
            "risk_capabilities": ["host_read", "host_write", "shell", "git", "network"],
        },
    }
    full_risk_capabilities = ["host_read", "host_write", "shell", "git", "network"]

    for adapter_kind, config in expected.items():
        created = client.post(
            "/api/agents/local-agent/pairing-tokens",
            headers=AUTH_HEADERS,
            json={
                "agent_id": "default",
                "scope": {"executable": True, "adapters": [adapter_kind]},
            }
            if adapter_kind == "claude_code"
            else {"agent_id": "default"},
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
        assert connection["capabilities_json"]["supports_cancel"] is True
        assert connection["capabilities_json"]["host_tools_authorized"] is True
        assert connection["capabilities_json"]["resume_mode"] == "context_replay_new_session"
        if adapter_kind == "claude_code":
            assert (
                connection["capabilities_json"]["execution_mode"]
                == "headless_harness_tool_bridge"
            )
        assert connection["risk_capabilities_json"] == full_risk_capabilities
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
    assert default_pairing.json()["command"].startswith(LOCAL_AGENT_NPX_COMMAND_PREFIX)
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
    assert codex_pairing.json()["command"].startswith(LOCAL_AGENT_NPX_COMMAND_PREFIX)
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
    assert claude_pairing.json()["command"].startswith(LOCAL_AGENT_NPX_COMMAND_PREFIX)
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
    assert command.startswith(LOCAL_AGENT_NPX_COMMAND_PREFIX)
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
        "host_read",
        "host_write",
        "shell",
        "git",
        "network",
    ]


def test_local_agent_claude_host_tool_protocol_uses_harness_approval(
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
        client_message_id="claude-v5-host-tool-allowed",
    )
    bridge_headers = {"X-Local-Agent-Device-Token": device_token}

    allowed_v5 = client.post(
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
    assert allowed_v5.status_code == 201, allowed_v5.text
    assert allowed_v5.json()["decision"] == "approval_required"
    assert allowed_v5.json()["approval_id"]
    assert allowed_v5.json()["decision_json"]["metadata"]["harness_stream_token"]

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
    assert capabilities["host_tools_authorized"] is True
    assert capabilities["permission_bridge"] is None
    assert capabilities["execution_mode"] == "headless_harness_tool_bridge"

    _sent, task = _leased_bridge_task(
        client,
        connection["id"],
        device_token,
        client_message_id="claude-v5-heartbeat-upgrade-denied",
    )
    allowed = client.post(
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
    assert allowed.status_code == 201, allowed.text
    assert allowed.json()["decision"] == "approval_required"


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
    connection = _confirm_connection(client, connection)

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
    connection = _confirm_connection(client, connection)
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
    agent_session_id = binding.json()["agent_session_id"]
    db_session.add(
        AgentMessage(
            session_id=agent_session_id,
            agent_id="default",
            role="user",
            content="STALE_SOURCE_ONLY_CONTEXT",
            metadata_json={"source": "local_agent"},
            created_at=utc_now(),
        )
    )
    db_session.add(
        AgentMessage(
            session_id=agent_session_id,
            agent_id="default",
            role="assistant",
            content="OTHER_BINDING_CONTEXT",
            metadata_json={
                "source": "local_agent",
                "connection_id": "other-connection",
                "binding_id": "other-binding",
                "agent_session_id": agent_session_id,
            },
            created_at=utc_now(),
        )
    )
    db_session.commit()

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
    assert "STALE_SOURCE_ONLY_CONTEXT" not in context_text
    assert "OTHER_BINDING_CONTEXT" not in context_text
    assert "raw-token" not in context_text
    assert "sk-proj-1234567890abcdef" not in context_text
    assert "/Users/luohao" not in context_text
    assert "continue from prior turn" not in context_text


def test_local_agent_explicit_empty_workspace_context_does_not_replay_session(
    db_session: Session,
) -> None:
    client = TestClient(app)
    connection, device_token = _registered_connection(client, db_session)
    bridge_headers = {"X-Local-Agent-Device-Token": device_token}
    binding = client.post(
        f"/api/agents/local-agent/connections/{connection['id']}/bindings",
        headers=AUTH_HEADERS,
        json={"title": "Local no replay", "resume_mode": "native_resume"},
    )
    assert binding.status_code == 201, binding.text
    binding_id = binding.json()["id"]

    first = client.post(
        f"/api/agents/local-agent/bindings/{binding_id}/messages",
        headers=AUTH_HEADERS,
        json={
            "content": "OLD_LOCAL_CONTEXT",
            "client_message_id": "explicit-empty-context-1",
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
            "event_id": "explicit-empty-context-1-done",
            "bridge_task_id": first_task["id"],
            "event_type": "assistant_done",
            "content": "OLD_LOCAL_REPLY",
            "sequence": 1,
        },
    )
    assert first_done.status_code == 201, first_done.text

    second = client.post(
        f"/api/agents/local-agent/bindings/{binding_id}/messages",
        headers=AUTH_HEADERS,
        json={
            "content": "fresh visible blank chat",
            "client_message_id": "explicit-empty-context-2",
            "workspace_context_provided": True,
            "messages": [],
        },
    )
    assert second.status_code == 202, second.text
    second_pull = client.get("/api/agents/local-agent/bridge/tasks", headers=bridge_headers)
    assert second_pull.status_code == 200, second_pull.text
    payload = second_pull.json()["items"][0]["payload"]

    assert payload["workspace_request"]["workspace_context_provided"] is True
    assert "conversation_context" not in payload
    assert "OLD_LOCAL_CONTEXT" not in json.dumps(payload, ensure_ascii=False)
    assert "OLD_LOCAL_REPLY" not in json.dumps(payload, ensure_ascii=False)


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


def test_local_agent_v4_codex_host_tool_protocol_uses_harness_approval(
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
        client_message_id="codex-host-tool-allowed",
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
    assert tool_request.status_code == 201, tool_request.text
    assert tool_request.json()["decision"] == "approval_required"
    assert tool_request.json()["approval_id"]
    assert tool_request.json()["decision_json"]["metadata"]["harness_stream_token"]

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
    assert command_status.status_code == 404, command_status.text
    cancel_ack = client.post(
        "/api/agents/local-agent/bridge/commands/codex-cmd/cancel-ack",
        headers=bridge_headers,
        json={"status": "cancelled", "error_message": "cancelled"},
    )
    assert cancel_ack.status_code == 404, cancel_ack.text
    cancel = client.post(
        f"/api/agents/local-agent/bindings/{task['binding_id']}/commands/codex-cmd/cancel",
        headers=AUTH_HEADERS,
    )
    assert cancel.status_code == 404, cancel.text
    retry = client.post(
        f"/api/agents/local-agent/bindings/{task['binding_id']}/commands/codex-cmd/retry",
        headers=AUTH_HEADERS,
    )
    assert retry.status_code == 404, retry.text

    assert len(db_session.execute(select(LocalAgentToolRequest)).scalars().all()) == 1
    assert len(db_session.execute(select(ToolCall)).scalars().all()) == 1
    assert len(db_session.execute(select(ToolApproval)).scalars().all()) == 1
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


def test_hao_local_agent_send_falls_back_from_mock_provider_to_real_default(
    db_session: Session,
) -> None:
    client = TestClient(app)
    connection, device_token = _registered_connection(client, db_session)
    bridge_headers = {"X-Local-Agent-Device-Token": device_token}
    setting = db_session.execute(
        select(SystemSetting).where(
            SystemSetting.organization_id == "dev-org",
            SystemSetting.key == "settings.models",
        )
    ).scalar_one_or_none()
    settings_value = {
        "default_provider": "custom-real",
        "default_model": "real-model",
        "providers": [
            {
                "name": "custom-mock",
                "label": "Unconfigured compatible provider",
                "api_format": "openai",
                "base_url": "https://mock.example.test/v1",
                "api_key": "",
                "model": "mock-model",
            },
            {
                "name": "custom-real",
                "base_url": "https://models.example.test/v1",
                "model": "real-model",
                "api_key": "test-real-key",
            },
        ],
    }
    if setting is None:
        db_session.add(
            SystemSetting(
                organization_id="dev-org",
                key="settings.models",
                value_json=settings_value,
                updated_by="test",
            )
        )
    else:
        setting.value_json = settings_value
        setting.updated_by = "test"
    db_session.commit()

    binding = client.post(
        f"/api/agents/local-agent/connections/{connection['id']}/bindings",
        headers=AUTH_HEADERS,
        json={"title": "Local coding session", "resume_mode": "native_resume"},
    )
    assert binding.status_code == 201, binding.text

    sent = client.post(
        f"/api/agents/local-agent/bindings/{binding.json()['id']}/messages",
        headers=AUTH_HEADERS,
        json={
            "content": "你好",
            "client_message_id": "msg-mock-provider-fallback",
            "model_provider": "custom-mock",
            "model_name": "mock-model",
        },
    )
    assert sent.status_code == 202, sent.text
    sent_payload = sent.json()

    run = db_session.get(Task, sent_payload["run_id"])
    assert run is not None
    assert run.model_provider == "custom-real"
    assert run.model_name == "real-model"

    pull = client.get("/api/agents/local-agent/bridge/tasks", headers=bridge_headers)
    assert pull.status_code == 200, pull.text
    [task] = pull.json()["items"]
    assert task["payload"]["model_provider"] == "custom-real"
    assert task["payload"]["model_name"] == "real-model"
    assert task["payload"]["workspace_request"]["model_provider"] == "custom-real"
    assert task["payload"]["workspace_request"]["model_name"] == "real-model"
    assert task["payload"]["model_fallback"] == {
        "requested_model_provider": "custom-mock",
        "requested_model_name": "mock-model",
        "fallback_model_provider": "custom-real",
        "fallback_model_name": "real-model",
        "fallback_reason": "selected_provider_would_use_local_mock",
    }
    assert task["payload"]["workspace_request"]["model_fallback"] == task["payload"][
        "model_fallback"
    ]

    [message] = list(
        db_session.execute(
            select(AgentMessage).where(
                AgentMessage.session_id == sent_payload["agent_session_id"],
                AgentMessage.role == "user",
            )
        ).scalars()
    )
    local_io = message.metadata_json["local_agent_io"]
    assert local_io["input"]["model_provider"] == "custom-real"
    assert local_io["input"]["model_name"] == "real-model"
    assert local_io["input"]["model_fallback"]["requested_model_provider"] == (
        "custom-mock"
    )


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
    unsafe_attachment_name = "/Users/luohao/private/sat_secret_README.md"
    safe_attachment_name = ".../private/[REDACTED].md"
    long_assistant_output = "\n".join(
        [
            "检查完成。",
            "1. 已读取 README.md，并确认本地项目说明存在。",
            "2. 已比对私有附件摘要，敏感路径和 token 样式名称不会进入审计快照。",
            "3. 已保留模型、上下文、工具、附件和压缩摘要输入，供观测面板完整展示。",
        ]
    )

    sent = client.post(
        f"/api/agents/local-agent/bindings/{binding_id}/messages",
        headers=AUTH_HEADERS,
        json={
            "content": "请检查本地项目",
            "client_message_id": "msg-1",
            "model_provider": "deepseek",
            "model_name": "deepseek-v4",
            "messages": [
                {
                    "id": "node-context-user",
                    "role": "user",
                    "content": "此前用户上下文",
                    "state": "done",
                    "metadata": {
                        "orchestration": {
                            "source": "local_agent",
                            "connection_id": connection["id"],
                            "binding_id": binding_id,
                            "agent_session_id": binding.json()["agent_session_id"],
                        }
                    },
                },
                {
                    "id": "node-context-assistant",
                    "role": "assistant",
                    "content": "此前助手回复",
                    "state": "done",
                    "metadata": {
                        "orchestration": {
                            "source": "local_agent",
                            "connection_id": connection["id"],
                            "binding_id": binding_id,
                            "agent_session_id": binding.json()["agent_session_id"],
                        }
                    },
                },
            ],
            "pinned_node_ids": ["node-context-user"],
            "context_window_turns": 8,
            "tool_mentions": [
                {"name": "read_file", "source": "local", "payload": {"path": "README.md"}},
                {
                    "name": "list_files",
                    "source": "local",
                    "payload": {"path": "/Users/luohao/private"},
                },
            ],
            "attachment_names": ["README.md", unsafe_attachment_name],
            "attachments": [
                {
                    "name": "README.md",
                    "mime_type": "text/markdown",
                    "size_bytes": 12,
                    "content_text": "local notes",
                    "content_status": "ready",
                },
                {
                    "name": unsafe_attachment_name,
                    "mime_type": "text/markdown",
                    "size_bytes": 128,
                    "content_text": "private attachment notes",
                    "content_status": "ready",
                },
            ],
            "compressed_context": {
                "summary": "压缩后的历史摘要",
                "branch_id": "node-context-assistant",
                "coverage_node_ids": ["node-context-user"],
                "coverage_path_hash": "hash",
                "summary_schema_version": "v1",
                "compression_prompt_version": "v1",
                "compressor_provider": "default",
                "compressor_model": "default",
            },
        },
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
    assert tasks[0]["payload"]["model_provider"] == "deepseek"
    assert tasks[0]["payload"]["model_name"] == "deepseek-v4"
    assert tasks[0]["payload"]["tool_mentions"][0]["name"] == "read_file"
    assert tasks[0]["payload"]["tool_mentions"][1]["name"] == "list_files"
    assert tasks[0]["payload"]["attachment_names"] == ["README.md", unsafe_attachment_name]
    assert tasks[0]["payload"]["compressed_context"]["summary"] == "压缩后的历史摘要"
    assert tasks[0]["payload"]["conversation_context"] == [
        {"role": "user", "content": "此前用户上下文"},
        {"role": "assistant", "content": "Compressed prior workspace context: 压缩后的历史摘要"},
        {"role": "assistant", "content": "此前助手回复"},
    ]

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
    fresh_stream_token = tool_decision["decision_json"]["metadata"]["harness_stream_token"]
    fresh_token_payload = decode_jwt(fresh_stream_token, expected_type="access")
    assert fresh_token_payload["scope"] == "local_agent_bridge_stream"
    assert fresh_token_payload["bridge_task_id"] == tasks[0]["id"]
    fresh_token_seconds = int(fresh_token_payload["exp"]) - int(datetime.now(UTC).timestamp())
    assert fresh_token_seconds >= 29 * 60

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
            "content": long_assistant_output,
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
    user_io = messages[0].metadata_json["local_agent_io"]
    assert user_io["input"]["adapter_kind"] == "hao"
    assert user_io["input"]["connection_id"] == connection["id"]
    assert user_io["input"]["binding_id"] == binding_id
    assert user_io["input"]["agent_session_id"] == sent_payload["agent_session_id"]
    assert user_io["input"]["model_provider"] == "deepseek"
    assert user_io["input"]["model_name"] == "deepseek-v4"
    assert user_io["input"]["message"] == "请检查本地项目"
    assert user_io["input"]["conversation_context_count"] == 3
    assert user_io["input"]["conversation_context_preview"][0] == {
        "role": "user",
        "content": "此前用户上下文",
    }
    assert user_io["input"]["tool_mentions"][0]["name"] == "read_file"
    assert user_io["input"]["tool_mentions"][1]["name"] == "list_files"
    assert user_io["input"]["attachment_names"] == ["README.md", safe_attachment_name]
    assert user_io["input"]["attachments"][0]["name"] == "README.md"
    assert user_io["input"]["attachments"][0]["content_preview"] == "local notes"
    assert user_io["input"]["attachments"][1]["name"] == safe_attachment_name
    assert user_io["input"]["attachments"][1]["content_preview"] == "private attachment notes"
    assert user_io["input"]["workspace_request"]["attachment_names"] == [
        "README.md",
        safe_attachment_name,
    ]
    assert user_io["input"]["workspace_request"]["attachments"][1]["name"] == safe_attachment_name
    assert user_io["input"]["compressed_context"]["summary"] == "压缩后的历史摘要"
    assert "/Users/luohao" not in json.dumps(user_io, ensure_ascii=False)
    assert "sat_secret_README" not in json.dumps(user_io, ensure_ascii=False)
    assert user_io["output"] is None
    user_metadata_json = json.dumps(messages[0].metadata_json, ensure_ascii=False)
    assert safe_attachment_name in user_metadata_json
    assert "/Users/luohao" not in user_metadata_json
    assert "sat_secret_README" not in user_metadata_json
    model_call = db_session.execute(
        select(ModelCall).where(ModelCall.task_id == sent_payload["run_id"])
    ).scalar_one()
    assert model_call.model_provider == "deepseek"
    assert model_call.model_name == "deepseek-v4"
    assert model_call.status == "SUCCESS"
    assert model_call.terminal_status == "success"
    assert model_call.prompt_tokens > 0
    assert model_call.completion_tokens > 0
    assert model_call.duration_ms >= 0
    assert model_call.model_request_sha256
    assert model_call.hash_recomputability_status == "local_bridge_safe_snapshot"
    assert model_call.request_json["source"] == "local_agent_bridge"
    assert model_call.request_json["message"] == "请检查本地项目"
    assert model_call.request_json["model_provider"] == "deepseek"
    assert model_call.request_json["model_name"] == "deepseek-v4"
    assert model_call.request_json["workspace_request"]["model_provider"] == "deepseek"
    assert model_call.request_json["workspace_request"]["model_name"] == "deepseek-v4"
    assert model_call.request_json["workspace_request"]["attachment_names"] == [
        "README.md",
        safe_attachment_name,
    ]
    assert model_call.request_json["conversation_context"][0] == {
        "role": "user",
        "content": "此前用户上下文",
    }
    assert model_call.request_json["attachments"][0]["name"] == "README.md"
    assert model_call.request_json["attachments"][0]["content_preview"] == "local notes"
    assert model_call.request_json["attachments"][1]["name"] == safe_attachment_name
    assert model_call.request_json["attachments"][1]["content_preview"] == (
        "private attachment notes"
    )
    assert "/Users/luohao" not in json.dumps(model_call.request_json, ensure_ascii=False)
    assert "sat_secret_README" not in json.dumps(model_call.request_json, ensure_ascii=False)
    assert model_call.response_json["source"] == "local_agent_bridge"
    assert model_call.response_json["content_preview"] == long_assistant_output
    assert model_call.response_json["usage"]["prompt_tokens"] == model_call.prompt_tokens
    assert model_call.response_json["usage"]["completion_tokens"] == model_call.completion_tokens
    assert model_call.capability_snapshot_json["source"] == "local_agent_bridge"
    assert model_call.capability_snapshot_json["server_execution"] is False
    assert model_call.capability_snapshot_json["connection_id"] == connection["id"]
    assert messages[1].metadata_json["model_call_id"] == model_call.id
    assert messages[1].metadata_json["model_provider"] == "deepseek"
    assert messages[1].metadata_json["model_name"] == "deepseek-v4"
    assert messages[1].metadata_json["connection_id"] == connection["id"]
    assert messages[1].metadata_json["binding_id"] == binding_id
    assert messages[1].metadata_json["agent_session_id"] == sent_payload["agent_session_id"]
    assistant_io = messages[1].metadata_json["local_agent_io"]
    assert assistant_io["input"]["adapter_kind"] == "hao"
    assert assistant_io["input"]["connection_id"] == connection["id"]
    assert assistant_io["input"]["binding_id"] == binding_id
    assert assistant_io["input"]["agent_session_id"] == sent_payload["agent_session_id"]
    assert assistant_io["input"]["model_provider"] == "deepseek"
    assert assistant_io["input"]["model_name"] == "deepseek-v4"
    assert assistant_io["input"]["message"] == "请检查本地项目"
    assert assistant_io["input"]["conversation_context_count"] == 3
    assert assistant_io["input"]["tool_mentions"][0]["name"] == "read_file"
    assert assistant_io["input"]["tool_mentions"][1]["name"] == "list_files"
    assert assistant_io["input"]["attachment_names"] == ["README.md", safe_attachment_name]
    assert assistant_io["input"]["attachments"][0]["name"] == "README.md"
    assert assistant_io["input"]["attachments"][1]["name"] == safe_attachment_name
    assert "/Users/luohao" not in json.dumps(assistant_io, ensure_ascii=False)
    assert "sat_secret_README" not in json.dumps(assistant_io, ensure_ascii=False)
    assert messages[1].metadata_json["attachment_names"] == ["README.md", safe_attachment_name]
    assistant_metadata_json = json.dumps(messages[1].metadata_json, ensure_ascii=False)
    assert safe_attachment_name in assistant_metadata_json
    assert "/Users/luohao" not in assistant_metadata_json
    assert "sat_secret_README" not in assistant_metadata_json
    assert assistant_io["output"]["adapter_kind"] == "hao"
    assert assistant_io["output"]["connection_id"] == connection["id"]
    assert assistant_io["output"]["binding_id"] == binding_id
    assert assistant_io["output"]["agent_session_id"] == sent_payload["agent_session_id"]
    assert assistant_io["output"]["bridge_task_id"] == tasks[0]["id"]
    assert assistant_io["output"]["model_call_id"] == model_call.id
    assert assistant_io["output"]["content_preview"] == long_assistant_output
    assert assistant_io["output"]["prompt_tokens"] == model_call.prompt_tokens
    assert assistant_io["output"]["completion_tokens"] == model_call.completion_tokens
    assert assistant_io["output"]["total_tokens"] == (
        model_call.prompt_tokens + model_call.completion_tokens
    )
    assert assistant_io["output"]["duration_ms"] == model_call.duration_ms

    events = list(
        db_session.execute(
            select(AgentEvent).where(AgentEvent.task_id == sent_payload["run_id"])
        ).scalars()
    )
    model_event_types = [
        event.event_type for event in events if event.event_type.startswith("MODEL_")
    ]
    assert model_event_types == ["MODEL_CALLED", "MODEL_RESPONSE_RECEIVED"]
    assert [
        event.payload_json["model_call_id"]
        for event in events
        if event.event_type in {"MODEL_CALLED", "MODEL_RESPONSE_RECEIVED"}
    ] == [model_call.id, model_call.id]
    completed_event = next(
        event for event in events if event.event_type == "LOCAL_AGENT_MESSAGE_COMPLETED"
    )
    assert completed_event.payload_json["model_call_id"] == model_call.id

    model_calls_response = client.get(
        f"/api/tasks/{sent_payload['run_id']}/model-calls",
        headers=AUTH_HEADERS,
    )
    assert model_calls_response.status_code == 200, model_calls_response.text
    model_call_payload = model_calls_response.json()["items"][0]
    assert model_call_payload["id"] == model_call.id
    assert model_call_payload["model_provider"] == "deepseek"
    assert model_call_payload["model_name"] == "deepseek-v4"
    assert model_call_payload["request_json"]["source"] == "local_agent_bridge"
    assert model_call_payload["request_json"]["workspace_request"]["model_name"] == "deepseek-v4"
    assert model_call_payload["response_json"]["content_preview"] == long_assistant_output


def test_local_agent_rejects_cross_binding_compressed_context_from_bridge_payload(
    db_session: Session,
) -> None:
    client = TestClient(app)
    connection, device_token = _registered_connection(client, db_session)
    bridge_headers = {"X-Local-Agent-Device-Token": device_token}
    binding = client.post(
        f"/api/agents/local-agent/connections/{connection['id']}/bindings",
        headers=AUTH_HEADERS,
        json={"title": "Compressed context guard"},
    )
    assert binding.status_code == 201, binding.text
    binding_id = binding.json()["id"]

    sent = client.post(
        f"/api/agents/local-agent/bindings/{binding_id}/messages",
        headers=AUTH_HEADERS,
        json={
            "content": "当前 hao 问题",
            "client_message_id": "compressed-context-guard",
            "messages": [
                {
                    "id": "hao-node",
                    "role": "user",
                    "content": "HAO_ONLY_CONTEXT",
                    "state": "done",
                    "metadata": {
                        "orchestration": {
                            "source": "local_agent",
                            "connection_id": connection["id"],
                            "binding_id": binding_id,
                            "agent_session_id": binding.json()["agent_session_id"],
                        }
                    },
                },
                {
                    "id": "claude-node",
                    "role": "assistant",
                    "content": "CLAUDE_SECRET_CONTEXT",
                    "state": "done",
                    "metadata": {
                        "orchestration": {
                            "source": "local_agent",
                            "connection_id": "conn-claude",
                            "binding_id": "binding-claude",
                            "agent_session_id": "session-claude",
                        }
                    },
                },
            ],
            "compressed_context": {
                "summary": "CLAUDE_COMPRESSED_SECRET",
                "branch_id": "claude-node",
                "coverage_node_ids": ["claude-node"],
                "coverage_path_hash": "hash",
            },
        },
    )
    assert sent.status_code == 202, sent.text

    pull = client.get("/api/agents/local-agent/bridge/tasks", headers=bridge_headers)
    assert pull.status_code == 200, pull.text
    payload = pull.json()["items"][0]["payload"]
    assert payload.get("compressed_context") is None
    assert payload["workspace_request"].get("compressed_context") is None
    payload_json = json.dumps(payload, ensure_ascii=False)
    assert "CLAUDE_COMPRESSED_SECRET" not in payload_json
    assert "CLAUDE_SECRET_CONTEXT" not in payload_json
    assert payload["conversation_context"] == [{"role": "user", "content": "HAO_ONLY_CONTEXT"}]

    db_session.expire_all()
    user_message = db_session.execute(
        select(AgentMessage).where(AgentMessage.session_id == sent.json()["agent_session_id"])
    ).scalar_one()
    io_json = json.dumps(user_message.metadata_json["local_agent_io"], ensure_ascii=False)
    assert "CLAUDE_COMPRESSED_SECRET" not in io_json
    assert "CLAUDE_SECRET_CONTEXT" not in io_json
    assert user_message.metadata_json["local_agent_io"]["input"]["compressed_context"] is None


def test_local_agent_full_flow_streams_tools_and_observability_like_platform_model(
    db_session: Session,
    monkeypatch,
) -> None:
    client = TestClient(app)
    _ensure_agent(db_session)
    pairing_response = client.post(
        "/api/agents/local-agent/pairing-tokens",
        headers=AUTH_HEADERS,
        json={"agent_id": "default", "ttl_minutes": 5},
    )
    assert pairing_response.status_code == 201, pairing_response.text
    pairing = pairing_response.json()
    assert pairing["command"].startswith(LOCAL_AGENT_NPX_COMMAND_PREFIX)
    assert pairing["pair_token"] in pairing["command"]
    assert pairing["pair_code"] in pairing["command"]
    assert "--adapter" not in pairing["command"]

    token_row = db_session.get(LocalAgentPairingToken, pairing["id"])
    assert token_row is not None
    assert token_row.token_hash != pairing["pair_token"]

    registered = client.post(
        "/api/agents/local-agent/connections/register",
        json={
            "pair_token": pairing["pair_token"],
            "pair_code": pairing["pair_code"],
            "adapter_kind": "hao",
            "display_name": "hao Full Flow Local",
            "protocol_version": "local-agent-v1",
            "bridge_version": "0.1.0",
            "workspace_root": "/Users/luohao/projects/full-flow",
            "capabilities": {
                "supports_resume": True,
                "supports_streaming": True,
                "supports_cancel": True,
                "host_tools_authorized": True,
                "permission_defer_supported": True,
                "tool_execution_authority": "harness_approved_local_bridge",
            },
            "risk_capabilities": ["host_read", "host_write", "shell", "git", "network"],
        },
    )
    assert registered.status_code == 201, registered.text
    registered_payload = registered.json()
    connection = registered_payload["connection"]
    device_token = registered_payload["device_token"]
    assert connection["pairing_token_id"] == pairing["id"]
    assert connection["onboarding_confirmed"] is False

    rejected_binding = client.post(
        f"/api/agents/local-agent/connections/{connection['id']}/bindings",
        headers=AUTH_HEADERS,
        json={"title": "Unconfirmed full flow", "resume_mode": "native_resume"},
    )
    assert rejected_binding.status_code == 409
    assert "not been confirmed" in rejected_binding.text

    confirmed = client.patch(
        f"/api/agents/local-agent/connections/{connection['id']}",
        headers=AUTH_HEADERS,
        json={"display_name": "hao Full Flow Local"},
    )
    assert confirmed.status_code == 200, confirmed.text
    connection = confirmed.json()
    assert connection["onboarding_confirmed"] is True
    bridge_headers = {"X-Local-Agent-Device-Token": device_token}

    connections = client.get("/api/agents/local-agent/connections", headers=AUTH_HEADERS)
    assert connections.status_code == 200, connections.text
    connection_payload = connections.json()["items"][0]
    assert connection_payload["risk_capabilities_json"] == [
        "host_read",
        "host_write",
        "shell",
        "git",
        "network",
    ]
    assert connection_payload["capabilities_json"]["host_tools_authorized"] is True
    assert (
        connection_payload["capabilities_json"]["tool_execution_authority"]
        == "harness_approved_local_bridge"
    )

    binding = client.post(
        f"/api/agents/local-agent/connections/{connection['id']}/bindings",
        headers=AUTH_HEADERS,
        json={"title": "Full local parity session", "resume_mode": "native_resume"},
    )
    assert binding.status_code == 201, binding.text
    binding_id = binding.json()["id"]

    sent = client.post(
        f"/api/agents/local-agent/bindings/{binding_id}/messages",
        headers=AUTH_HEADERS,
        json={
            "content": "完整本地 Agent 链路验收",
            "client_message_id": "full-local-flow",
            "workspace_mode": "chat",
            "model_provider": "deepseek",
            "model_name": "deepseek-v4",
            "messages": [
                {
                    "id": "full-flow-context-user",
                    "role": "user",
                    "content": "已有上下文",
                    "state": "done",
                    "metadata": {
                        "orchestration": {
                            "source": "local_agent",
                            "connection_id": connection["id"],
                            "binding_id": binding_id,
                            "agent_session_id": binding.json()["agent_session_id"],
                        }
                    },
                }
            ],
            "tool_mentions": [
                {"name": "read_file", "source": "local", "payload": {"path": "README.md"}},
                {"name": "run_tests", "source": "local", "payload": {"command": "pytest -q"}},
            ],
            "attachment_names": ["README.md"],
            "attachments": [
                {
                    "name": "README.md",
                    "mime_type": "text/markdown",
                    "size_bytes": 18,
                    "content_text": "full flow notes",
                    "content_status": "ready",
                }
            ],
        },
    )
    assert sent.status_code == 202, sent.text
    sent_payload = sent.json()

    pull = client.get("/api/agents/local-agent/bridge/tasks", headers=bridge_headers)
    assert pull.status_code == 200, pull.text
    [task] = pull.json()["items"]
    assert task["payload"]["workspace_request"]["mode"] == "chat"
    assert task["payload"]["model_provider"] == "deepseek"
    assert task["payload"]["model_name"] == "deepseek-v4"
    assert task["payload"]["attachments"][0]["content_text"] == "full flow notes"
    assert task["payload"]["tool_mentions"][0]["name"] == "read_file"
    stream_token = task["payload"]["harness_stream_token"]
    assert stream_token
    token_payload = decode_jwt(stream_token, expected_type="access")
    assert token_payload["scope"] == "local_agent_bridge_stream"
    assert token_payload["bridge_task_id"] == task["id"]

    ack = client.post(
        f"/api/agents/local-agent/bridge/tasks/{task['id']}/ack",
        headers=bridge_headers,
        json={"status": "running"},
    )
    assert ack.status_code == 200, ack.text

    gateway_requests: list[dict] = []

    class FakeUpstreamGateway:
        def stream(self, request):
            gateway_requests[-1]["model_provider"] = request.model_provider
            gateway_requests[-1]["model_name"] = request.model_name
            gateway_requests[-1]["messages"] = [
                {"role": message.role, "content": message.content}
                for message in request.messages
            ]
            metadata = gateway_requests[-1].get("request_metadata") or {}
            is_local_bridge_stream = metadata.get("source") == "local_agent_bridge_stream"
            first_delta = "本地 " if is_local_bridge_stream else "平台 "
            yield ModelStreamChunk(text=first_delta)
            yield ModelStreamChunk(text="SSE 回复")
            yield ModelStreamChunk(
                text="",
                usage={
                    "prompt_tokens": 11 if is_local_bridge_stream else 13,
                    "completion_tokens": 7 if is_local_bridge_stream else 5,
                },
                done=True,
            )

    class FakeAuditedGateway:
        def __init__(self, *args, **kwargs) -> None:
            del args
            gateway_requests.append(kwargs)
            self.gateway = AuditedModelGateway(gateway=FakeUpstreamGateway(), **kwargs)

        def stream(self, request):
            yield from self.gateway.stream(request)

    monkeypatch.setattr(
        "app.api.agents.agent_chat.streaming.AuditedModelGateway",
        FakeAuditedGateway,
    )
    monkeypatch.setattr(
        "app.api.agents._session_helpers.ensure_default_agents",
        lambda *args, **kwargs: None,
    )

    scoped_stream = client.post(
        "/api/agents/default/runs/chat/stream",
        headers={"Authorization": f"Bearer {stream_token}"},
        json={
            "mode": "cli_agent",
            "goal": "完整本地 Agent 链路验收",
            "run_id": sent_payload["run_id"],
            "local_bridge_task_id": task["id"],
            "model_provider": "deepseek",
            "model_name": "deepseek-v4",
            "messages": [
                {
                    "id": "full-flow-user",
                    "role": "user",
                    "content": "完整本地 Agent 链路验收",
                    "state": "done",
                    "children_ids": [],
                    "metadata": {},
                    "tool_calls": [],
                    "artifacts": [],
                }
            ],
        },
    )
    assert scoped_stream.status_code == 200, scoped_stream.text
    sse_events = _sse_events(scoped_stream.text)
    stream_event_names = [
        event["event"]
        for event in sse_events
        if event["event"] in {"delta", "usage", "done"}
    ]
    assert stream_event_names == [
        "delta",
        "delta",
        "usage",
        "done",
    ]
    assert "".join(
        event["data"]["content"] for event in sse_events if event["event"] == "delta"
    ) == "本地 SSE 回复"
    usage_event = next(event for event in sse_events if event["event"] == "usage")
    platform_model_call_id = usage_event["data"]["model_call_id"]
    assert platform_model_call_id
    assert gateway_requests[0]["request_metadata"] == {
        "source": "local_agent_bridge_stream",
        "local_bridge_task_id": task["id"],
    }
    assert gateway_requests[0]["model_provider"] == "deepseek"
    assert gateway_requests[0]["model_name"] == "deepseek-v4"

    direct_platform_stream = client.post(
        "/api/agents/default/runs/chat/stream",
        headers=AUTH_HEADERS,
        json={
            "mode": "cli_agent",
            "goal": "完整平台模型链路验收",
            "model_provider": "deepseek",
            "model_name": "deepseek-v4",
            "messages": [
                {
                    "id": "full-flow-platform-user",
                    "role": "user",
                    "content": "完整平台模型链路验收",
                    "state": "done",
                    "children_ids": [],
                    "metadata": {},
                    "tool_calls": [],
                    "artifacts": [],
                }
            ],
        },
    )
    assert direct_platform_stream.status_code == 200, direct_platform_stream.text
    platform_sse_events = _sse_events(direct_platform_stream.text)
    platform_stream_event_names = [
        event["event"]
        for event in platform_sse_events
        if event["event"] in {"delta", "usage", "done"}
    ]
    assert platform_stream_event_names == stream_event_names
    assert "".join(
        event["data"]["content"]
        for event in platform_sse_events
        if event["event"] == "delta"
    ) == "平台 SSE 回复"
    platform_usage_event = next(
        event for event in platform_sse_events if event["event"] == "usage"
    )
    direct_platform_model_call_id = platform_usage_event["data"]["model_call_id"]
    platform_done = next(event for event in platform_sse_events if event["event"] == "done")
    direct_platform_run_id = platform_done["data"]["run_id"]
    assert direct_platform_run_id != sent_payload["run_id"]
    assert direct_platform_model_call_id
    assert gateway_requests[1]["request_metadata"] is None
    assert gateway_requests[1]["model_provider"] == "deepseek"
    assert gateway_requests[1]["model_name"] == "deepseek-v4"

    direct_model_calls_response = client.get(
        f"/api/tasks/{direct_platform_run_id}/model-calls",
        headers=AUTH_HEADERS,
    )
    assert direct_model_calls_response.status_code == 200, direct_model_calls_response.text
    direct_model_call_payload = direct_model_calls_response.json()["items"][0]
    assert direct_model_call_payload["id"] == direct_platform_model_call_id
    assert direct_model_call_payload["model_provider"] == "deepseek"
    assert direct_model_call_payload["model_name"] == "deepseek-v4"
    assert "source" not in direct_model_call_payload["request_json"]
    assert direct_model_call_payload["response_json"]["content_preview"] == "平台 SSE 回复"

    for index, content in enumerate(["本地 ", "SSE 回复"], start=1):
        delta = client.post(
            "/api/agents/local-agent/bridge/events",
            headers=bridge_headers,
            json={
                "event_id": f"full-flow-delta-{index}",
                "bridge_task_id": task["id"],
                "event_type": "assistant_delta",
                "content": content,
                "sequence": index,
                "metadata": {"platform_model_call_id": platform_model_call_id},
            },
        )
        assert delta.status_code == 201, delta.text

    tool_specs = [
        {
            "tool_request_id": "full-flow-read-file",
            "tool_name": "read_file",
            "input_json": {"path": "README.md"},
            "output_json": {"content": "read ok", "size_bytes": 7},
        },
        {
            "tool_request_id": "full-flow-list-files",
            "tool_name": "list_files",
            "input_json": {"root": ".", "glob": "*.md"},
            "output_json": {"files": ["README.md"]},
        },
        {
            "tool_request_id": "full-flow-write-file",
            "tool_name": "write_file",
            "input_json": {"path": "notes/full-flow.md", "content": "ok"},
            "output_json": {"path": "notes/full-flow.md", "bytes_written": 2},
            "pending_change_preview": {
                "change_id": "change-full-flow-write",
                "target_paths": ["notes/full-flow.md"],
                "diff": "--- a/notes/full-flow.md\n+++ b/notes/full-flow.md\n@@\n+ok\n",
            },
            "target_paths": ["notes/full-flow.md"],
            "change_id": "change-full-flow-write",
        },
        {
            "tool_request_id": "full-flow-run-shell",
            "tool_name": "run_shell",
            "input_json": {"command": "printf full-flow"},
            "output_json": {"stdout": "full-flow"},
            "command_id": "cmd-full-flow-shell",
            "command": "printf full-flow",
        },
        {
            "tool_request_id": "full-flow-run-tests",
            "tool_name": "run_tests",
            "input_json": {"command": "pytest -q"},
            "output_json": {"stdout": "1 passed"},
            "command_id": "cmd-full-flow-tests",
            "command": "pytest -q",
        },
        {
            "tool_request_id": "full-flow-git",
            "tool_name": "git",
            "input_json": {"args": ["status", "--short"]},
            "output_json": {"stdout": ""},
            "command_id": "cmd-full-flow-git",
            "command": "git status --short",
        },
        {
            "tool_request_id": "full-flow-network",
            "tool_name": "network",
            "input_json": {"command": "curl https://example.com/health"},
            "output_json": {"status_code": 200, "body": "ok"},
            "requires_network": True,
        },
    ]
    decisions_by_tool_request: dict[str, dict] = {}

    for spec in tool_specs:
        payload = {
            "tool_request_id": spec["tool_request_id"],
            "bridge_task_id": task["id"],
            "tool_name": spec["tool_name"],
            "input_json": spec["input_json"],
            "execution_target": "host",
            "risk_level": "medium",
            "permission_mode": "full-auto",
            "metadata": {
                "run_id": sent_payload["run_id"],
                "agent_id": "default",
                "local_session_id": task.get("agent_session_id"),
            },
            "requires_network": spec.get("requires_network", False),
        }
        if spec.get("pending_change_preview"):
            payload["pending_change_preview"] = spec["pending_change_preview"]
        if spec.get("target_paths"):
            payload["target_paths"] = spec["target_paths"]
        tool_request = client.post(
            "/api/agents/local-agent/bridge/tool-requests",
            headers=bridge_headers,
            json=payload,
        )
        assert tool_request.status_code == 201, tool_request.text
        decision = tool_request.json()
        decisions_by_tool_request[spec["tool_request_id"]] = decision
        assert decision["decision"] == "approval_required"
        assert decision["server_execution"] is False
        assert decision["approval_id"]
        assert decision["decision_json"]["metadata"]["harness_stream_token"]

        approved = client.post(
            f"/api/tasks/{sent_payload['run_id']}/tool-approvals/{decision['approval_id']}/approve",
            headers=ADMIN_HEADERS,
            json={"reason": f"approve {spec['tool_name']} full-flow test"},
        )
        assert approved.status_code == 202, approved.text
        polled = client.get(
            f"/api/agents/local-agent/bridge/tool-requests/{spec['tool_request_id']}/decision",
            headers=bridge_headers,
        )
        assert polled.status_code == 200, polled.text
        assert polled.json()["decision"] == "approved"
        assert polled.json()["executable"] is True

        command_id = spec.get("command_id")
        if command_id:
            _start_and_finish_command(
                client,
                bridge_headers=bridge_headers,
                tool_request_id=spec["tool_request_id"],
                command_id=command_id,
                command=spec["command"],
                tool_name=spec["tool_name"],
            )

        result_payload = {
            "event_id": f"{spec['tool_request_id']}-result",
            "status": "SUCCESS",
            "output_json": spec["output_json"],
            "duration_ms": 5,
            "command_id": command_id,
            "metadata": {"tool_name": spec["tool_name"], "full_flow": True},
        }
        if spec.get("change_id"):
            result_payload["change_id"] = spec["change_id"]
            result_payload["diff_sha256"] = decision["decision_json"]["pending_change_preview"][
                "diff_sha256"
            ]
        result = client.post(
            f"/api/agents/local-agent/bridge/tool-requests/{spec['tool_request_id']}/result",
            headers=bridge_headers,
            json=result_payload,
        )
        assert result.status_code == 202, result.text
        assert result.json()["decision"] == "succeeded"

    done = client.post(
        "/api/agents/local-agent/bridge/events",
        headers=bridge_headers,
        json={
            "event_id": "full-flow-done",
            "bridge_task_id": task["id"],
            "event_type": "assistant_done",
            "content": "本地 SSE 回复",
            "sequence": 3,
            "metadata": {"model_call_id": platform_model_call_id},
        },
    )
    assert done.status_code == 201, done.text

    run = db_session.get(Task, sent_payload["run_id"])
    assert run is not None
    assert run.status == "COMPLETED"
    bridge_task = db_session.get(LocalAgentBridgeTask, task["id"])
    assert bridge_task is not None
    assert bridge_task.status == "completed"

    tool_calls = list(
        db_session.execute(
            select(ToolCall).where(ToolCall.task_id == sent_payload["run_id"])
        ).scalars()
    )
    assert {call.tool_name for call in tool_calls} == {
        "read_file",
        "list_files",
        "write_file",
        "run_shell",
        "run_tests",
        "git",
        "network",
    }
    assert all(call.status == "SUCCESS" for call in tool_calls)
    assert all(call.capability_snapshot_json["server_execution"] is False for call in tool_calls)
    assert all(
        call.capability_snapshot_json["source"] == "local_agent_bridge"
        for call in tool_calls
    )
    assert all(call.capability_snapshot_json["capability_attached"] is True for call in tool_calls)
    assert all(
        call.capability_snapshot_json["connection_id"] == connection["id"]
        for call in tool_calls
    )
    assert all(call.capability_snapshot_json["bridge_task_id"] == task["id"] for call in tool_calls)
    assert len(db_session.execute(select(ToolApproval)).scalars().all()) == len(tool_specs)
    assert len(db_session.execute(select(LocalAgentToolRequest)).scalars().all()) == len(tool_specs)
    assert {
        request.status for request in db_session.execute(select(LocalAgentToolRequest)).scalars()
    } == {"succeeded"}
    assert len(db_session.execute(select(LocalAgentCommand)).scalars().all()) == 3
    pending_change = db_session.execute(
        select(LocalAgentPendingChange).where(
            LocalAgentPendingChange.change_id == "change-full-flow-write"
        )
    ).scalar_one()
    write_file_request = db_session.execute(
        select(LocalAgentToolRequest).where(
            LocalAgentToolRequest.tool_request_id == "full-flow-write-file"
        )
    ).scalar_one()
    write_file_decision = decisions_by_tool_request["full-flow-write-file"]
    assert pending_change.status == "committed"
    assert pending_change.committed_at is not None
    assert pending_change.target_paths_json == ["notes/full-flow.md"]
    assert pending_change.diff_sha256 == write_file_decision["decision_json"][
        "pending_change_preview"
    ]["diff_sha256"]
    assert pending_change.preview_json["diff_sha256"] == pending_change.diff_sha256
    assert pending_change.local_agent_tool_request_id == write_file_request.id
    assert write_file_request.result_json["change_id"] == "change-full-flow-write"
    assert write_file_request.result_json["diff_sha256"] == pending_change.diff_sha256

    model_calls = list(
        db_session.execute(
            select(ModelCall).where(ModelCall.task_id == sent_payload["run_id"])
        ).scalars()
    )
    assert [call.id for call in model_calls] == [platform_model_call_id]
    model_call = model_calls[0]
    assert model_call.model_provider == "deepseek"
    assert model_call.model_name == "deepseek-v4"
    assert model_call.request_json["source"] == "local_agent_bridge_stream"
    assert model_call.request_json["local_bridge_task_id"] == task["id"]
    assert model_call.prompt_tokens == 11
    assert model_call.completion_tokens == 7

    assistant = db_session.execute(
        select(AgentMessage)
        .where(
            AgentMessage.session_id == sent_payload["agent_session_id"],
            AgentMessage.role == "assistant",
        )
    ).scalar_one()
    assert assistant.content == "本地 SSE 回复"
    assert assistant.metadata_json["model_call_id"] == platform_model_call_id
    assert assistant.metadata_json["model_provider"] == "deepseek"
    assert assistant.metadata_json["model_name"] == "deepseek-v4"

    event_page = client.get(
        f"/api/tasks/{sent_payload['run_id']}/events",
        headers=AUTH_HEADERS,
    )
    assert event_page.status_code == 200, event_page.text
    event_types = [event["event_type"] for event in event_page.json()["items"]]
    assert "LOCAL_AGENT_DELTA_RECEIVED" in event_types
    assert "LOCAL_AGENT_MESSAGE_COMPLETED" in event_types
    assert event_types.count("TOOL_CALLED") == len(tool_specs)
    assert event_types.count("TOOL_APPROVAL_REQUESTED") == len(tool_specs)
    assert event_types.count("TOOL_RESULT_RECEIVED") == len(tool_specs)
    assert event_types.count("MODEL_CALLED") == 1
    assert event_types.count("MODEL_RESPONSE_RECEIVED") == 1

    event_stream = client.get(
        f"/api/tasks/{sent_payload['run_id']}/events/stream?once=true",
        headers=AUTH_HEADERS,
    )
    assert event_stream.status_code == 200, event_stream.text
    assert "LOCAL_AGENT_DELTA_RECEIVED" in event_stream.text
    assert "TOOL_RESULT_RECEIVED" in event_stream.text
    assert "LOCAL_AGENT_MESSAGE_COMPLETED" in event_stream.text

    model_calls_response = client.get(
        f"/api/tasks/{sent_payload['run_id']}/model-calls",
        headers=AUTH_HEADERS,
    )
    assert model_calls_response.status_code == 200, model_calls_response.text
    assert model_calls_response.json()["items"][0]["id"] == platform_model_call_id
    summary = client.get("/api/observability/summary", headers=AUTH_HEADERS)
    assert summary.status_code == 200, summary.text
    summary_payload = summary.json()
    assert summary_payload["model_call_total"] >= 2
    assert summary_payload["tool_call_total"] >= len(tool_specs)
    model_calls_by_status = {
        item["name"]: item["count"] for item in summary_payload["model_calls_by_status"]
    }
    tool_calls_by_status = {
        item["name"]: item["count"] for item in summary_payload["tool_calls_by_status"]
    }
    assert model_calls_by_status["SUCCESS"] >= 1
    assert tool_calls_by_status["SUCCESS"] >= len(tool_specs)
    assert summary_payload["event_total"] >= len(event_types)


def test_local_agent_assistant_done_reuses_existing_model_call(
    db_session: Session,
) -> None:
    client = TestClient(app)
    connection, device_token = _registered_connection(client, db_session)
    bridge_headers = {"X-Local-Agent-Device-Token": device_token}

    binding = client.post(
        f"/api/agents/local-agent/connections/{connection['id']}/bindings",
        headers=AUTH_HEADERS,
        json={"title": "Local streaming session", "resume_mode": "native_resume"},
    )
    assert binding.status_code == 201, binding.text

    sent = client.post(
        f"/api/agents/local-agent/bindings/{binding.json()['id']}/messages",
        headers=AUTH_HEADERS,
        json={
            "content": "本地流式回复",
            "client_message_id": "msg-existing-model-call",
            "model_provider": "deepseek",
            "model_name": "deepseek-v4",
        },
    )
    assert sent.status_code == 202, sent.text
    sent_payload = sent.json()

    pull = client.get("/api/agents/local-agent/bridge/tasks", headers=bridge_headers)
    assert pull.status_code == 200, pull.text
    [task] = pull.json()["items"]
    ack = client.post(
        f"/api/agents/local-agent/bridge/tasks/{task['id']}/ack",
        headers=bridge_headers,
        json={"status": "running"},
    )
    assert ack.status_code == 200, ack.text

    existing_call = ModelCall(
        id="platform-model-call-1",
        task_id=sent_payload["run_id"],
        agent_run_id=None,
        model_provider="deepseek",
        model_name="deepseek-v4",
        status="SUCCESS",
        prompt_tokens=7,
        completion_tokens=0,
        duration_ms=42,
        capability_snapshot_json={"source": "platform_stream"},
        request_json={
            "source": "local_agent_bridge_stream",
            "local_bridge_task_id": task["id"],
            "message": "本地流式回复",
        },
        response_json={"content_preview": "平台流式输出"},
        terminal_status="success",
    )
    db_session.add(existing_call)
    db_session.commit()

    done = client.post(
        "/api/agents/local-agent/bridge/events",
        headers=bridge_headers,
        json={
            "event_id": "evt-done-existing-call",
            "bridge_task_id": task["id"],
            "event_type": "assistant_done",
            "content": "平台流式输出",
            "sequence": 2,
            "metadata": {"model_call_id": existing_call.id},
        },
    )
    assert done.status_code == 201, done.text

    model_calls = list(
        db_session.execute(
            select(ModelCall).where(ModelCall.task_id == sent_payload["run_id"])
        ).scalars()
    )
    assert [call.id for call in model_calls] == [existing_call.id]
    assistant = db_session.execute(
        select(AgentMessage)
        .where(
            AgentMessage.session_id == sent_payload["agent_session_id"],
            AgentMessage.role == "assistant",
        )
    ).scalar_one()
    assert assistant.metadata_json["model_call_id"] == existing_call.id
    assert assistant.metadata_json["input_tokens"] == 7
    assert assistant.metadata_json["output_tokens"] == 0
    assistant_io = assistant.metadata_json["local_agent_io"]
    assert assistant_io["output"]["model_call_id"] == existing_call.id
    assert assistant_io["output"]["prompt_tokens"] == 7
    assert assistant_io["output"]["completion_tokens"] == 0
    assert assistant_io["output"]["total_tokens"] == 7
    completed_event = db_session.execute(
        select(AgentEvent).where(AgentEvent.event_type == "LOCAL_AGENT_MESSAGE_COMPLETED")
    ).scalar_one()
    assert completed_event.payload_json["model_call_id"] == existing_call.id


def test_hao_local_agent_plan_mode_queues_markdown_plan_run_with_stream_token(
    db_session: Session,
    monkeypatch,
) -> None:
    _ensure_dev_engineer_member(db_session)
    client = TestClient(app)
    connection, device_token = _registered_connection(client, db_session)
    bridge_headers = {"X-Local-Agent-Device-Token": device_token}

    binding = client.post(
        f"/api/agents/local-agent/connections/{connection['id']}/bindings",
        headers=AUTH_HEADERS,
        json={"title": "Local plan session", "resume_mode": "native_resume"},
    )
    assert binding.status_code == 201, binding.text
    binding_id = binding.json()["id"]

    sent = client.post(
        f"/api/agents/local-agent/bindings/{binding_id}/messages",
        headers=AUTH_HEADERS,
        json={
            "content": "先规划，不执行本地工具",
            "client_message_id": "local-plan-mode",
            "workspace_mode": "plan",
            "model_provider": "anthropic",
            "model_name": "claude-sonnet-4",
        },
    )

    assert sent.status_code == 202, sent.text
    sent_payload = sent.json()
    pull = client.get("/api/agents/local-agent/bridge/tasks", headers=bridge_headers)
    assert pull.status_code == 200, pull.text
    [task] = pull.json()["items"]
    assert task["payload"]["workspace_request"]["mode"] == "plan"
    assert task["payload"]["model_provider"] == "anthropic"
    assert task["payload"]["model_name"] == "claude-sonnet-4"
    stream_token = task["payload"]["harness_stream_token"]
    assert stream_token
    token_payload = decode_jwt(stream_token, expected_type="access")
    assert token_payload["scope"] == "local_agent_bridge_stream"
    assert token_payload["bridge_task_id"] == task["id"]
    stream_token_seconds = int(token_payload["exp"]) - int(datetime.now(UTC).timestamp())
    assert stream_token_seconds >= 29 * 60

    scoped_headers = {"Authorization": f"Bearer {stream_token}"}
    rejected_list = client.get("/api/agents", headers=scoped_headers)
    assert rejected_list.status_code == 401

    class FakeGateway:
        def __init__(self, *args, **kwargs) -> None:
            del args, kwargs

        def stream(self, request):
            del request
            yield ModelStreamChunk(text="本地桥接流式输出")
            yield ModelStreamChunk(
                text="",
                usage={"prompt_tokens": 1, "completion_tokens": 1},
                done=True,
            )

    monkeypatch.setattr(
        "app.api.agents.agent_chat.streaming.AuditedModelGateway",
        FakeGateway,
    )
    monkeypatch.setattr(
        "app.api.agents._session_helpers.ensure_default_agents",
        lambda *args, **kwargs: None,
    )
    scoped_stream = client.post(
        "/api/agents/default/runs/chat/stream",
        headers=scoped_headers,
        json={
            "mode": "cli_agent",
            "goal": "stream local output",
            "run_id": sent_payload["run_id"],
            "local_bridge_task_id": task["id"],
            "messages": [
                {
                    "id": "user-local-stream",
                    "role": "user",
                    "content": "stream local output",
                    "state": "done",
                    "children_ids": [],
                    "metadata": {},
                    "tool_calls": [],
                    "artifacts": [],
                }
            ],
        },
    )
    assert scoped_stream.status_code == 200, scoped_stream.text
    assert "本地桥接流式输出" in scoped_stream.text

    created_event = db_session.execute(
        select(AgentEvent).where(
            AgentEvent.task_id == sent_payload["run_id"],
            AgentEvent.event_type == "TASK_CREATED",
        )
    ).scalar_one()
    assert created_event.payload_json["mode"] == "markdown_plan"


def test_normal_token_cannot_mark_local_bridge_stream_model_call_metadata(
    db_session: Session,
    monkeypatch,
) -> None:
    client = TestClient(app)
    connection, device_token = _registered_connection(client, db_session)
    bridge_headers = {"X-Local-Agent-Device-Token": device_token}

    binding = client.post(
        f"/api/agents/local-agent/connections/{connection['id']}/bindings",
        headers=AUTH_HEADERS,
        json={"title": "Normal auth stream session", "resume_mode": "native_resume"},
    )
    assert binding.status_code == 201, binding.text
    sent = client.post(
        f"/api/agents/local-agent/bindings/{binding.json()['id']}/messages",
        headers=AUTH_HEADERS,
        json={"content": "普通 token 不应伪造本地流", "client_message_id": "normal-token-stream"},
    )
    assert sent.status_code == 202, sent.text
    sent_payload = sent.json()
    pull = client.get("/api/agents/local-agent/bridge/tasks", headers=bridge_headers)
    assert pull.status_code == 200, pull.text
    [task] = pull.json()["items"]

    gateway_kwargs: dict = {}

    class FakeGateway:
        def __init__(self, *args, **kwargs) -> None:
            del args
            gateway_kwargs.update(kwargs)

        def stream(self, request):
            del request
            yield ModelStreamChunk(text="普通登录流式输出")
            yield ModelStreamChunk(
                text="",
                usage={"prompt_tokens": 1, "completion_tokens": 1},
                done=True,
            )

    monkeypatch.setattr(
        "app.api.agents.agent_chat.streaming.AuditedModelGateway",
        FakeGateway,
    )
    monkeypatch.setattr(
        "app.api.agents._session_helpers.ensure_default_agents",
        lambda *args, **kwargs: None,
    )

    response = client.post(
        "/api/agents/default/runs/chat/stream",
        headers=AUTH_HEADERS,
        json={
            "mode": "cli_agent",
            "goal": "normal auth stream",
            "run_id": sent_payload["run_id"],
            "local_bridge_task_id": task["id"],
            "messages": [
                {
                    "id": "user-normal-stream",
                    "role": "user",
                    "content": "normal auth stream",
                    "state": "done",
                    "children_ids": [],
                    "metadata": {},
                    "tool_calls": [],
                    "artifacts": [],
                }
            ],
        },
    )

    assert response.status_code == 200, response.text
    assert "普通登录流式输出" in response.text
    assert gateway_kwargs.get("request_metadata") is None


def test_local_agent_scoped_stream_token_rejects_terminal_bridge_task_replay(
    db_session: Session,
    monkeypatch,
) -> None:
    _ensure_dev_engineer_member(db_session)
    client = TestClient(app)
    connection, device_token = _registered_connection(client, db_session)
    bridge_headers = {"X-Local-Agent-Device-Token": device_token}

    binding = client.post(
        f"/api/agents/local-agent/connections/{connection['id']}/bindings",
        headers=AUTH_HEADERS,
        json={"title": "Terminal replay session", "resume_mode": "native_resume"},
    )
    assert binding.status_code == 201, binding.text
    sent = client.post(
        f"/api/agents/local-agent/bindings/{binding.json()['id']}/messages",
        headers=AUTH_HEADERS,
        json={"content": "不要重放", "client_message_id": "stream-replay"},
    )
    assert sent.status_code == 202, sent.text
    sent_payload = sent.json()
    pull = client.get("/api/agents/local-agent/bridge/tasks", headers=bridge_headers)
    assert pull.status_code == 200, pull.text
    [task] = pull.json()["items"]
    stream_token = task["payload"]["harness_stream_token"]

    done = client.post(
        "/api/agents/local-agent/bridge/events",
        headers=bridge_headers,
        json={
            "event_id": "evt-terminal-replay-done",
            "bridge_task_id": task["id"],
            "event_type": "assistant_done",
            "content": "完成",
            "sequence": 1,
        },
    )
    assert done.status_code == 201, done.text
    run = db_session.get(Task, sent_payload["run_id"])
    assert run is not None
    assert run.status == "COMPLETED"
    existing_model_call_ids = [
        call.id
        for call in db_session.execute(
        select(ModelCall).where(ModelCall.task_id == sent_payload["run_id"])
        ).scalars()
    ]

    class ExplodingGateway:
        def __init__(self, *args, **kwargs) -> None:
            del args, kwargs

        def stream(self, request):
            del request
            raise AssertionError("terminal scoped token replay must not reach model gateway")

    monkeypatch.setattr(
        "app.api.agents.agent_chat.streaming.AuditedModelGateway",
        ExplodingGateway,
    )
    replay = client.post(
        "/api/agents/default/runs/chat/stream",
        headers={"Authorization": f"Bearer {stream_token}"},
        json={
            "mode": "cli_agent",
            "goal": "replay",
            "run_id": sent_payload["run_id"],
            "local_bridge_task_id": task["id"],
            "messages": [],
        },
    )

    assert replay.status_code == 401
    db_session.refresh(run)
    assert run.status == "COMPLETED"
    assert [
        call.id
        for call in db_session.execute(
            select(ModelCall).where(ModelCall.task_id == sent_payload["run_id"])
        ).scalars()
    ] == existing_model_call_ids


def test_local_agent_scoped_stream_token_is_single_use_before_terminal_state(
    db_session: Session,
    monkeypatch,
) -> None:
    _ensure_dev_engineer_member(db_session)
    client = TestClient(app)
    connection, device_token = _registered_connection(client, db_session)
    bridge_headers = {"X-Local-Agent-Device-Token": device_token}

    binding = client.post(
        f"/api/agents/local-agent/connections/{connection['id']}/bindings",
        headers=AUTH_HEADERS,
        json={"title": "Active replay session", "resume_mode": "native_resume"},
    )
    assert binding.status_code == 201, binding.text
    sent = client.post(
        f"/api/agents/local-agent/bindings/{binding.json()['id']}/messages",
        headers=AUTH_HEADERS,
        json={"content": "只允许一次流", "client_message_id": "stream-single-use"},
    )
    assert sent.status_code == 202, sent.text
    sent_payload = sent.json()
    pull = client.get("/api/agents/local-agent/bridge/tasks", headers=bridge_headers)
    assert pull.status_code == 200, pull.text
    [task] = pull.json()["items"]
    stream_token = task["payload"]["harness_stream_token"]

    stream_count = 0

    class FakeGateway:
        def __init__(self, *args, **kwargs) -> None:
            del args, kwargs

        def stream(self, request):
            nonlocal stream_count
            del request
            stream_count += 1
            yield ModelStreamChunk(text="第一次流式输出")
            yield ModelStreamChunk(
                text="",
                usage={"prompt_tokens": 1, "completion_tokens": 1},
                done=True,
            )

    monkeypatch.setattr(
        "app.api.agents.agent_chat.streaming.AuditedModelGateway",
        FakeGateway,
    )
    monkeypatch.setattr(
        "app.api.agents._session_helpers.ensure_default_agents",
        lambda *args, **kwargs: None,
    )
    stream_body = {
        "mode": "cli_agent",
        "goal": "first stream",
        "run_id": sent_payload["run_id"],
        "local_bridge_task_id": task["id"],
        "messages": [],
    }
    headers = {"Authorization": f"Bearer {stream_token}"}
    first = client.post(
        "/api/agents/default/runs/chat/stream",
        headers=headers,
        json=stream_body,
    )
    assert first.status_code == 200, first.text
    assert "第一次流式输出" in first.text

    bridge_task = db_session.get(LocalAgentBridgeTask, task["id"])
    assert bridge_task is not None
    assert bridge_task.status in {"leased", "running"}
    assert bridge_task.payload_json["harness_stream_token_consumed_at"]
    token_payload = decode_jwt(stream_token, expected_type="access")
    consumed_jti = bridge_task.payload_json["harness_stream_token_consumed_jti"]
    assert consumed_jti == token_payload["jti"]
    assert bridge_task.payload_json["harness_stream_token_consumed_jtis"] == [
        token_payload["jti"]
    ]

    second = client.post(
        "/api/agents/default/runs/chat/stream",
        headers=headers,
        json=stream_body,
    )

    assert second.status_code == 401
    assert stream_count == 1

    fresh_stream_token = issue_access_token(
        user_id=token_payload["sub"],
        organization_id=token_payload["org"],
        role=token_payload["role"],
        roles=token_payload.get("roles") or [token_payload["role"]],
        extra={
            "scope": token_payload["scope"],
            "agent_id": token_payload["agent_id"],
            "run_id": token_payload["run_id"],
            "bridge_task_id": token_payload["bridge_task_id"],
            "exp": token_payload["exp"],
        },
    )
    fresh_token_payload = decode_jwt(fresh_stream_token, expected_type="access")
    assert fresh_token_payload["jti"] != token_payload["jti"]

    fresh_headers = {"Authorization": f"Bearer {fresh_stream_token}"}
    third = client.post(
        "/api/agents/default/runs/chat/stream",
        headers=fresh_headers,
        json=stream_body,
    )
    assert third.status_code == 200, third.text
    assert stream_count == 2

    db_session.refresh(bridge_task)
    assert bridge_task.payload_json["harness_stream_token_consumed_jti"] == (
        fresh_token_payload["jti"]
    )
    assert bridge_task.payload_json["harness_stream_token_consumed_jtis"] == [
        token_payload["jti"],
        fresh_token_payload["jti"],
    ]

    fourth = client.post(
        "/api/agents/default/runs/chat/stream",
        headers=fresh_headers,
        json=stream_body,
    )
    assert fourth.status_code == 401
    assert stream_count == 2


def test_local_agent_assistant_done_rejects_unbound_or_failed_model_call_id(
    db_session: Session,
) -> None:
    client = TestClient(app)
    connection, device_token = _registered_connection(client, db_session)
    bridge_headers = {"X-Local-Agent-Device-Token": device_token}
    binding = client.post(
        f"/api/agents/local-agent/connections/{connection['id']}/bindings",
        headers=AUTH_HEADERS,
        json={"title": "ModelCall binding session", "resume_mode": "native_resume"},
    )
    assert binding.status_code == 201, binding.text
    sent = client.post(
        f"/api/agents/local-agent/bindings/{binding.json()['id']}/messages",
        headers=AUTH_HEADERS,
        json={"content": "检查绑定", "client_message_id": "model-call-binding"},
    )
    assert sent.status_code == 202, sent.text
    sent_payload = sent.json()
    pull = client.get("/api/agents/local-agent/bridge/tasks", headers=bridge_headers)
    assert pull.status_code == 200, pull.text
    [task] = pull.json()["items"]

    stale_same_run_call = ModelCall(
        id="platform-stale-same-run",
        task_id=sent_payload["run_id"],
        agent_run_id=None,
        model_provider="deepseek",
        model_name="deepseek-v4",
        status="SUCCESS",
        prompt_tokens=7,
        completion_tokens=5,
        duration_ms=42,
        capability_snapshot_json={"source": "platform_stream"},
        request_json={"source": "platform_stream", "message": "检查绑定"},
        response_json={"content_preview": "stale"},
        terminal_status="success",
    )
    failed_bridge_call = ModelCall(
        id="platform-failed-bridge-stream",
        task_id=sent_payload["run_id"],
        agent_run_id=None,
        model_provider="deepseek",
        model_name="deepseek-v4",
        status="FAILED",
        prompt_tokens=7,
        completion_tokens=0,
        duration_ms=42,
        capability_snapshot_json={"source": "platform_stream"},
        request_json={
            "source": "local_agent_bridge_stream",
            "local_bridge_task_id": task["id"],
        },
        response_json={},
        terminal_status="failed",
    )
    wrong_task_call = ModelCall(
        id="platform-wrong-bridge-stream",
        task_id=sent_payload["run_id"],
        agent_run_id=None,
        model_provider="deepseek",
        model_name="deepseek-v4",
        status="SUCCESS",
        prompt_tokens=7,
        completion_tokens=5,
        duration_ms=42,
        capability_snapshot_json={"source": "platform_stream"},
        request_json={
            "source": "local_agent_bridge_stream",
            "local_bridge_task_id": "different-bridge-task",
        },
        response_json={"content_preview": "wrong"},
        terminal_status="success",
    )
    db_session.add_all([stale_same_run_call, failed_bridge_call, wrong_task_call])
    db_session.commit()

    for model_call_id in [
        stale_same_run_call.id,
        failed_bridge_call.id,
        wrong_task_call.id,
    ]:
        done = client.post(
            "/api/agents/local-agent/bridge/events",
            headers=bridge_headers,
            json={
                "event_id": f"evt-done-{model_call_id}",
                "bridge_task_id": task["id"],
                "event_type": "assistant_done",
                "content": "错误复用",
                "sequence": 2,
                "metadata": {"model_call_id": model_call_id},
            },
        )
        assert done.status_code == 409, done.text

    db_session.refresh(db_session.get(LocalAgentBridgeTask, task["id"]))
    bridge_task = db_session.get(LocalAgentBridgeTask, task["id"])
    assert bridge_task is not None
    assert bridge_task.status in {"pending", "leased"}


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


def test_local_agent_v3_retry_rejects_revoked_connection(
    db_session: Session,
) -> None:
    client = TestClient(app)
    connection, device_token = _registered_connection(client, db_session)
    bridge_headers = {"X-Local-Agent-Device-Token": device_token}
    sent_payload, task = _leased_bridge_task(
        client,
        connection["id"],
        device_token,
        client_message_id="v3-command-retry-revoked",
    )
    _approved_local_tool_request(
        client,
        bridge_headers=bridge_headers,
        task=task,
        run_id=sent_payload["run_id"],
        tool_request_id="tool-req-retry-revoked",
    )
    _start_and_finish_command(
        client,
        bridge_headers=bridge_headers,
        tool_request_id="tool-req-retry-revoked",
        command_id="cmd-retry-revoked",
        status_value="failed",
    )
    db_session.expire_all()
    request_ids_before = {
        row.tool_request_id
        for row in db_session.execute(select(LocalAgentToolRequest)).scalars()
    }
    command_ids_before = {
        row.command_id
        for row in db_session.execute(select(LocalAgentCommand)).scalars()
    }

    revoked = client.post(
        f"/api/agents/local-agent/connections/{connection['id']}/revoke",
        headers=AUTH_HEADERS,
    )
    assert revoked.status_code == 200, revoked.text

    retried = client.post(
        (
            f"/api/agents/local-agent/bindings/{task['binding_id']}"
            "/commands/cmd-retry-revoked/retry"
        ),
        headers=AUTH_HEADERS,
    )

    assert retried.status_code == 403, retried.text
    assert "connection revoked" in retried.text
    db_session.expire_all()
    request_ids_after = {
        row.tool_request_id
        for row in db_session.execute(select(LocalAgentToolRequest)).scalars()
    }
    command_ids_after = {
        row.command_id
        for row in db_session.execute(select(LocalAgentCommand)).scalars()
    }
    assert request_ids_after == request_ids_before
    assert command_ids_after == command_ids_before


def test_local_agent_v3_retry_and_cancel_reject_conflict_binding_without_new_work(
    db_session: Session,
) -> None:
    client = TestClient(app)
    connection, device_token = _registered_connection(client, db_session)
    bridge_headers = {"X-Local-Agent-Device-Token": device_token}
    sent_payload, task = _leased_bridge_task(
        client,
        connection["id"],
        device_token,
        client_message_id="v3-command-conflict-binding",
    )
    _approved_local_tool_request(
        client,
        bridge_headers=bridge_headers,
        task=task,
        run_id=sent_payload["run_id"],
        tool_request_id="tool-req-conflict-retry",
    )
    _start_and_finish_command(
        client,
        bridge_headers=bridge_headers,
        tool_request_id="tool-req-conflict-retry",
        command_id="cmd-conflict-retry",
        status_value="failed",
    )
    _approved_local_tool_request(
        client,
        bridge_headers=bridge_headers,
        task=task,
        run_id=sent_payload["run_id"],
        tool_request_id="tool-req-conflict-cancel",
    )
    started = client.post(
        "/api/agents/local-agent/bridge/commands/cmd-conflict-cancel/events",
        headers=bridge_headers,
        json={
            "event_id": "cmd-conflict-cancel-start",
            "tool_request_id": "tool-req-conflict-cancel",
            "event_type": "started",
            "tool_name": "run_shell",
            "command": "printf ok",
        },
    )
    assert started.status_code == 202, started.text
    binding = db_session.get(LocalAgentConversationBinding, task["binding_id"])
    assert binding is not None
    binding.status = "conflict"
    binding.updated_at = utc_now()
    db_session.commit()
    db_session.expire_all()
    request_ids_before = {
        row.tool_request_id
        for row in db_session.execute(select(LocalAgentToolRequest)).scalars()
    }
    command_ids_before = {
        row.command_id
        for row in db_session.execute(select(LocalAgentCommand)).scalars()
    }

    cancelled = client.post(
        (
            f"/api/agents/local-agent/bindings/{task['binding_id']}"
            "/commands/cmd-conflict-cancel/cancel"
        ),
        headers=AUTH_HEADERS,
    )
    retried = client.post(
        (
            f"/api/agents/local-agent/bindings/{task['binding_id']}"
            "/commands/cmd-conflict-retry/retry"
        ),
        headers=AUTH_HEADERS,
    )

    assert cancelled.status_code == 409, cancelled.text
    assert "not active" in cancelled.text
    assert retried.status_code == 409, retried.text
    assert "not active" in retried.text
    db_session.expire_all()
    request_ids_after = {
        row.tool_request_id
        for row in db_session.execute(select(LocalAgentToolRequest)).scalars()
    }
    command_ids_after = {
        row.command_id
        for row in db_session.execute(select(LocalAgentCommand)).scalars()
    }
    cancel_command = db_session.execute(
        select(LocalAgentCommand).where(LocalAgentCommand.command_id == "cmd-conflict-cancel")
    ).scalar_one()
    assert request_ids_after == request_ids_before
    assert command_ids_after == command_ids_before
    assert cancel_command.cancel_requested_at is None


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


def test_local_agent_v3_pending_discovery_hides_conflict_binding_requests(
    db_session: Session,
) -> None:
    client = TestClient(app)
    connection, device_token = _registered_connection(client, db_session)
    bridge_headers = {"X-Local-Agent-Device-Token": device_token}
    _sent_payload, task = _leased_bridge_task(
        client,
        connection["id"],
        device_token,
        client_message_id="v3-pending-conflict-hidden",
    )
    tool_request = client.post(
        "/api/agents/local-agent/bridge/tool-requests",
        headers=bridge_headers,
        json={
            "tool_request_id": "tool-req-conflict-hidden",
            "bridge_task_id": task["id"],
            "tool_name": "run_shell",
            "input_json": {"command": "echo safe"},
            "execution_target": "host",
            "risk_level": "low",
            "permission_mode": "full-auto",
        },
    )
    assert tool_request.status_code == 201, tool_request.text
    binding = db_session.get(LocalAgentConversationBinding, task["binding_id"])
    assert binding is not None
    binding.status = "conflict"
    binding.updated_at = utc_now()
    db_session.commit()

    page = client.get(
        "/api/agents/local-agent/bridge/tool-requests/pending",
        headers=bridge_headers,
    )

    assert page.status_code == 200, page.text
    assert page.json()["items"] == []


def test_local_agent_v3_duplicate_tool_request_rechecks_bridge_task_binding(
    db_session: Session,
) -> None:
    client = TestClient(app)
    connection, device_token = _registered_connection(client, db_session)
    bridge_headers = {"X-Local-Agent-Device-Token": device_token}
    first_payload, first_task = _leased_bridge_task(
        client,
        connection["id"],
        device_token,
        client_message_id="v3-duplicate-tool-first",
    )
    decision = _approved_local_tool_request(
        client,
        bridge_headers=bridge_headers,
        task=first_task,
        run_id=first_payload["run_id"],
        tool_request_id="tool-req-duplicate-guard",
    )
    duplicate_same_task = client.post(
        "/api/agents/local-agent/bridge/tool-requests",
        headers=bridge_headers,
        json={
            "tool_request_id": "tool-req-duplicate-guard",
            "bridge_task_id": first_task["id"],
            "tool_name": "run_shell",
            "input_json": {"command": "printf ok"},
            "execution_target": "host",
            "risk_level": "low",
            "permission_mode": "full-auto",
        },
    )
    assert duplicate_same_task.status_code == 201, duplicate_same_task.text
    assert duplicate_same_task.json()["approval_id"] == decision["approval_id"]

    _second_payload, second_task = _leased_bridge_task(
        client,
        connection["id"],
        device_token,
        client_message_id="v3-duplicate-tool-second",
    )
    duplicate_wrong_task = client.post(
        "/api/agents/local-agent/bridge/tool-requests",
        headers=bridge_headers,
        json={
            "tool_request_id": "tool-req-duplicate-guard",
            "bridge_task_id": second_task["id"],
            "tool_name": "run_shell",
            "input_json": {"command": "printf ok"},
            "execution_target": "host",
            "risk_level": "low",
            "permission_mode": "full-auto",
        },
    )
    assert duplicate_wrong_task.status_code == 409, duplicate_wrong_task.text
    assert "different bridge task" in duplicate_wrong_task.text

    binding = db_session.get(LocalAgentConversationBinding, first_task["binding_id"])
    assert binding is not None
    binding.status = "conflict"
    binding.updated_at = utc_now()
    db_session.commit()
    duplicate_conflict_binding = client.post(
        "/api/agents/local-agent/bridge/tool-requests",
        headers=bridge_headers,
        json={
            "tool_request_id": "tool-req-duplicate-guard",
            "bridge_task_id": first_task["id"],
            "tool_name": "run_shell",
            "input_json": {"command": "printf ok"},
            "execution_target": "host",
            "risk_level": "low",
            "permission_mode": "full-auto",
        },
    )
    assert duplicate_conflict_binding.status_code == 409, duplicate_conflict_binding.text
    assert "binding is not active" in duplicate_conflict_binding.text


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


def test_local_agent_stale_active_task_auto_fails_on_binding_poll(
    db_session: Session,
) -> None:
    client = TestClient(app)
    connection, device_token = _registered_connection(client, db_session)
    sent_payload, task = _leased_bridge_task(
        client,
        connection["id"],
        device_token,
        client_message_id="stale-active-task",
    )
    bridge_task = db_session.get(LocalAgentBridgeTask, task["id"])
    assert bridge_task is not None
    stale_at = utc_now() - timedelta(minutes=10)
    bridge_task.created_at = stale_at
    bridge_task.leased_at = stale_at
    bridge_task.acked_at = stale_at
    bridge_task.updated_at = stale_at
    db_session.commit()

    page = client.get(
        f"/api/agents/local-agent/bindings/{task['binding_id']}/tasks",
        headers=AUTH_HEADERS,
    )

    assert page.status_code == 200, page.text
    assert page.json()["items"][0]["status"] == "failed"
    assert "没有返回" in page.json()["items"][0]["error_message"]
    db_session.expire_all()
    bridge_task = db_session.get(LocalAgentBridgeTask, task["id"])
    run = db_session.get(Task, sent_payload["run_id"])
    assert bridge_task is not None
    assert bridge_task.status == "failed"
    assert bridge_task.completed_at is not None
    assert bridge_task.payload_json["timeout"] is True
    assert run is not None
    assert run.status == "FAILED"
    failed_event = db_session.execute(
        select(AgentEvent).where(
            AgentEvent.task_id == sent_payload["run_id"],
            AgentEvent.event_type == "LOCAL_AGENT_MESSAGE_FAILED",
        )
    ).scalar_one()
    assert failed_event.payload_json["bridge_task_id"] == task["id"]
    assert failed_event.payload_json["timeout"] is True


def test_local_agent_stale_task_waiting_on_local_tool_does_not_timeout(
    db_session: Session,
) -> None:
    client = TestClient(app)
    connection, device_token = _registered_connection(client, db_session)
    bridge_headers = {"X-Local-Agent-Device-Token": device_token}
    sent_payload, task = _leased_bridge_task(
        client,
        connection["id"],
        device_token,
        client_message_id="stale-tool-wait",
    )
    tool_request = client.post(
        "/api/agents/local-agent/bridge/tool-requests",
        headers=bridge_headers,
        json={
            "tool_request_id": "tool-req-stale-wait",
            "bridge_task_id": task["id"],
            "tool_name": "write_file",
            "input_json": {"path": "notes.md", "content": "new\n"},
            "execution_target": "host",
            "risk_level": "low",
            "permission_mode": "full-auto",
            "target_paths": ["notes.md"],
            "pending_change_preview": {
                "change_id": "change-stale-wait",
                "target_paths": ["notes.md"],
                "diff_sha256": "d" * 64,
            },
        },
    )
    assert tool_request.status_code == 201, tool_request.text
    bridge_task = db_session.get(LocalAgentBridgeTask, task["id"])
    assert bridge_task is not None
    stale_at = utc_now() - timedelta(minutes=10)
    bridge_task.created_at = stale_at
    bridge_task.leased_at = stale_at
    bridge_task.acked_at = stale_at
    bridge_task.updated_at = stale_at
    db_session.commit()

    page = client.get(
        f"/api/agents/local-agent/bindings/{task['binding_id']}/tasks",
        headers=AUTH_HEADERS,
    )

    assert page.status_code == 200, page.text
    assert page.json()["items"][0]["status"] == "running"
    db_session.expire_all()
    bridge_task = db_session.get(LocalAgentBridgeTask, task["id"])
    run = db_session.get(Task, sent_payload["run_id"])
    assert bridge_task is not None
    assert bridge_task.status == "running"
    assert bridge_task.completed_at is None
    assert run is not None
    assert run.status != "FAILED"


def test_local_agent_adapter_heartbeat_keeps_active_task_alive(
    db_session: Session,
) -> None:
    client = TestClient(app)
    connection, device_token = _registered_connection(client, db_session)
    bridge_headers = {"X-Local-Agent-Device-Token": device_token}
    sent_payload, task = _leased_bridge_task(
        client,
        connection["id"],
        device_token,
        client_message_id="stale-heartbeat",
    )
    bridge_task = db_session.get(LocalAgentBridgeTask, task["id"])
    assert bridge_task is not None
    stale_at = utc_now() - timedelta(minutes=10)
    bridge_task.created_at = stale_at
    bridge_task.leased_at = stale_at
    bridge_task.acked_at = stale_at
    bridge_task.updated_at = stale_at
    db_session.commit()

    heartbeat = client.post(
        "/api/agents/local-agent/bridge/events",
        headers=bridge_headers,
        json={
            "event_id": f"{task['id']}:heartbeat:test",
            "bridge_task_id": task["id"],
            "event_type": "adapter_heartbeat",
            "sequence": 10000,
            "metadata": {"adapter_kind": "hao", "heartbeat": True},
        },
    )
    assert heartbeat.status_code == 201, heartbeat.text

    page = client.get(
        f"/api/agents/local-agent/bindings/{task['binding_id']}/tasks",
        headers=AUTH_HEADERS,
    )

    assert page.status_code == 200, page.text
    assert page.json()["items"][0]["status"] == "running"
    db_session.expire_all()
    bridge_task = db_session.get(LocalAgentBridgeTask, task["id"])
    run = db_session.get(Task, sent_payload["run_id"])
    assert bridge_task is not None
    assert bridge_task.status == "running"
    assert bridge_task.completed_at is None
    assert run is not None
    assert run.status != "FAILED"


def test_local_agent_pending_task_with_mismatched_session_is_not_leased_or_acked(
    db_session: Session,
) -> None:
    client = TestClient(app)
    connection, device_token = _registered_connection(client, db_session)
    bridge_headers = {"X-Local-Agent-Device-Token": device_token}
    binding = client.post(
        f"/api/agents/local-agent/connections/{connection['id']}/bindings",
        headers=AUTH_HEADERS,
        json={"title": "Mismatched local session"},
    )
    assert binding.status_code == 201, binding.text
    sent = client.post(
        f"/api/agents/local-agent/bindings/{binding.json()['id']}/messages",
        headers=AUTH_HEADERS,
        json={"content": "queue me", "client_message_id": "mismatch-session-task"},
    )
    assert sent.status_code == 202, sent.text
    other_session = AgentSession(
        organization_id="dev-org",
        agent_id="default",
        created_by="dev-engineer",
        title="Wrong session fixture",
        status="ACTIVE",
        created_at=utc_now(),
        updated_at=utc_now(),
    )
    db_session.add(other_session)
    db_session.flush()
    bridge_task = db_session.get(LocalAgentBridgeTask, sent.json()["bridge_task_id"])
    assert bridge_task is not None
    bridge_task.agent_session_id = other_session.id
    bridge_task.updated_at = utc_now()
    db_session.commit()

    pull = client.get("/api/agents/local-agent/bridge/tasks", headers=bridge_headers)
    assert pull.status_code == 200, pull.text
    assert pull.json()["items"] == []

    ack = client.post(
        f"/api/agents/local-agent/bridge/tasks/{sent.json()['bridge_task_id']}/ack",
        headers=bridge_headers,
        json={"status": "running"},
    )
    assert ack.status_code == 409, ack.text
    assert "binding is not active" in ack.text
    db_session.expire_all()
    bridge_task = db_session.get(LocalAgentBridgeTask, sent.json()["bridge_task_id"])
    assert bridge_task is not None
    assert bridge_task.status == "pending"
    assert bridge_task.leased_at is None
    assert bridge_task.acked_at is None


def test_local_agent_failed_task_is_projected_with_error_message(
    db_session: Session,
) -> None:
    client = TestClient(app)
    connection, device_token = _registered_connection(client, db_session)
    bridge_headers = {"X-Local-Agent-Device-Token": device_token}
    sent, task = _leased_bridge_task(
        client,
        connection["id"],
        device_token,
        client_message_id="failed-visible-1",
    )

    failed = client.post(
        "/api/agents/local-agent/bridge/events",
        headers=bridge_headers,
        json={
            "event_id": "failed-visible-error",
            "bridge_task_id": task["id"],
            "event_type": "assistant_error",
            "error_message": "codex unavailable",
            "sequence": 2,
        },
    )
    assert failed.status_code == 201, failed.text

    page = client.get(
        f"/api/agents/local-agent/bindings/{task['binding_id']}/tasks",
        headers=AUTH_HEADERS,
    )
    assert page.status_code == 200, page.text
    assert page.json()["items"] == [
        {
            "id": task["id"],
            "connection_id": connection["id"],
            "binding_id": task["binding_id"],
            "agent_session_id": sent["agent_session_id"],
            "run_id": sent["run_id"],
            "user_message_id": sent["user_message_id"],
            "client_message_id": "failed-visible-1",
            "status": "failed",
            "error_message": "codex unavailable",
            "created_at": page.json()["items"][0]["created_at"],
            "updated_at": page.json()["items"][0]["updated_at"],
        }
    ]


def test_local_agent_failed_ack_closes_run_and_projects_error_message(
    db_session: Session,
) -> None:
    client = TestClient(app)
    connection, device_token = _registered_connection(client, db_session)
    bridge_headers = {"X-Local-Agent-Device-Token": device_token}
    binding = client.post(
        f"/api/agents/local-agent/connections/{connection['id']}/bindings",
        headers=AUTH_HEADERS,
        json={"title": "Failed ack local session"},
    )
    assert binding.status_code == 201, binding.text
    sent = client.post(
        f"/api/agents/local-agent/bindings/{binding.json()['id']}/messages",
        headers=AUTH_HEADERS,
        json={"content": "queue me", "client_message_id": "failed-ack-1"},
    )
    assert sent.status_code == 202, sent.text
    pull = client.get("/api/agents/local-agent/bridge/tasks", headers=bridge_headers)
    assert pull.status_code == 200, pull.text
    task = pull.json()["items"][0]

    failed_ack = client.post(
        f"/api/agents/local-agent/bridge/tasks/{task['id']}/ack",
        headers=bridge_headers,
        json={"status": "failed", "error_message": "adapter unavailable"},
    )

    assert failed_ack.status_code == 200, failed_ack.text
    page = client.get(
        f"/api/agents/local-agent/bindings/{task['binding_id']}/tasks",
        headers=AUTH_HEADERS,
    )
    assert page.status_code == 200, page.text
    assert page.json()["items"][0]["status"] == "failed"
    assert page.json()["items"][0]["error_message"] == "adapter unavailable"

    bridge_task = db_session.get(LocalAgentBridgeTask, task["id"])
    run = db_session.get(Task, sent.json()["run_id"])
    assert bridge_task is not None
    assert bridge_task.completed_at is not None
    assert bridge_task.payload_json["terminal_error_message"] == "adapter unavailable"
    assert run is not None
    assert run.status == "FAILED"
    assert run.completed_at is not None


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


def test_local_agent_session_cannot_be_rebound_to_another_connection(
    db_session: Session,
) -> None:
    client = TestClient(app)
    hao_connection, _hao_device_token = _registered_connection(client, db_session)
    claude_connection, _claude_device_token = _registered_claude_v6_connection(client, db_session)
    first_binding = client.post(
        f"/api/agents/local-agent/connections/{hao_connection['id']}/bindings",
        headers=AUTH_HEADERS,
        json={"title": "hao local session"},
    )
    assert first_binding.status_code == 201, first_binding.text

    rebound = client.post(
        f"/api/agents/local-agent/connections/{claude_connection['id']}/bindings",
        headers=AUTH_HEADERS,
        json={
            "agent_session_id": first_binding.json()["agent_session_id"],
            "title": "claude should not reuse hao session",
        },
    )

    assert rebound.status_code == 409, rebound.text
    assert "different local Agent connection" in rebound.text


def test_local_agent_conflict_session_binding_cannot_send(
    db_session: Session,
) -> None:
    client = TestClient(app)
    hao_connection, _hao_device_token = _registered_connection(client, db_session)
    claude_connection, _claude_device_token = _registered_claude_v6_connection(client, db_session)
    binding = client.post(
        f"/api/agents/local-agent/connections/{hao_connection['id']}/bindings",
        headers=AUTH_HEADERS,
        json={"title": "hao local session"},
    )
    assert binding.status_code == 201, binding.text
    stale_binding = LocalAgentConversationBinding(
        organization_id="dev-org",
        owner_user_id="dev-engineer",
        connection_id=claude_connection["id"],
        agent_id="default",
        agent_session_id=binding.json()["agent_session_id"],
        adapter_session_id=None,
        resume_mode="context_replay_new_session",
        status="conflict",
        metadata_json={"test_fixture": "historical_cross_connection_session"},
        created_at=utc_now(),
        updated_at=utc_now(),
    )
    db_session.add(stale_binding)
    db_session.flush()

    rejected = client.post(
        f"/api/agents/local-agent/bindings/{stale_binding.id}/messages",
        headers=AUTH_HEADERS,
        json={"content": "must not continue shared session", "client_message_id": "shared-1"},
    )

    assert rejected.status_code == 409, rejected.text
    assert "not active" in rejected.text


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


def test_local_agent_connection_list_order_is_not_heartbeat_driven(
    db_session: Session,
) -> None:
    client = TestClient(app)
    hao_connection, _hao_device_token = _registered_connection(client, db_session)
    created = client.post(
        "/api/agents/local-agent/pairing-tokens",
        headers=AUTH_HEADERS,
        json={"agent_id": "default", "ttl_minutes": 5},
    )
    assert created.status_code == 201, created.text
    pairing = created.json()
    registered_codex = client.post(
        "/api/agents/local-agent/connections/register",
        json={
            "pair_token": pairing["pair_token"],
            "pair_code": pairing["pair_code"],
            "adapter_kind": "codex",
            "display_name": "Codex CLI",
            "protocol_version": "local-agent-v1",
            "bridge_version": "0.1.0",
            "workspace_root": "/Users/luohao/projects/demo",
            "capabilities": {"supports_resume": False, "supports_streaming": True},
            "risk_capabilities": ["host_read", "host_write", "shell", "git", "network"],
        },
    )
    assert registered_codex.status_code == 201, registered_codex.text
    codex_payload = registered_codex.json()

    first_list = client.get("/api/agents/local-agent/connections", headers=AUTH_HEADERS)
    assert first_list.status_code == 200, first_list.text
    first_ids = [
        item["id"]
        for item in first_list.json()["items"]
        if item["id"] in {hao_connection["id"], codex_payload["connection"]["id"]}
    ]
    assert first_ids == [codex_payload["connection"]["id"], hao_connection["id"]]

    heartbeat = client.post(
        f"/api/agents/local-agent/connections/{hao_connection['id']}/heartbeat",
        headers={"X-Local-Agent-Device-Token": _hao_device_token},
        json={
            "status": "busy",
            "protocol_version": "local-agent-v1",
            "bridge_version": "0.1.1",
            "capabilities": {"supports_resume": True, "supports_streaming": True},
        },
    )
    assert heartbeat.status_code == 200, heartbeat.text

    second_list = client.get("/api/agents/local-agent/connections", headers=AUTH_HEADERS)
    assert second_list.status_code == 200, second_list.text
    second_ids = [
        item["id"]
        for item in second_list.json()["items"]
        if item["id"] in {hao_connection["id"], codex_payload["connection"]["id"]}
    ]
    assert second_ids == first_ids


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
