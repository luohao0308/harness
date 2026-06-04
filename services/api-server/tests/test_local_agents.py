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
    LocalAgentConnection,
    LocalAgentPairingToken,
    Task,
    ToolCall,
    utc_now,
)
from app.main import app
from tests.conftest import AUTH_HEADERS

ADMIN_HEADERS = {"Authorization": "Bearer dev-admin-token"}
OPERATOR_HEADERS = {"Authorization": "Bearer dev-operator-token"}
OTHER_ORG_HEADERS = {"Authorization": "Bearer dev-other-org-token"}


def _ensure_agent(session: Session, agent_id: str = "default") -> Agent:
    agent = session.get(Agent, agent_id)
    if agent is not None:
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
        tools_json=[],
        routing_tags=["workspace"],
        max_parallel_assignments=1,
    )
    session.add(agent)
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


def test_local_agent_v1_rejects_disabled_adapters(db_session: Session) -> None:
    client = TestClient(app)
    _ensure_agent(db_session)
    created = client.post(
        "/api/agents/local-agent/pairing-tokens",
        headers=AUTH_HEADERS,
        json={"agent_id": "default"},
    ).json()

    response = client.post(
        "/api/agents/local-agent/connections/register",
        json={
            "pair_token": created["pair_token"],
            "pair_code": created["pair_code"],
            "adapter_kind": "codex",
            "protocol_version": "local-agent-v1",
        },
    )

    assert response.status_code == 400
    assert "not enabled" in response.text


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

    tool = client.post(
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
    assert tool.status_code == 201, tool.text

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
    messages = list(
        db_session.execute(
            select(AgentMessage).where(AgentMessage.session_id == sent_payload["agent_session_id"])
        ).scalars()
    )
    assert [message.role for message in messages] == ["user", "assistant"]


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
