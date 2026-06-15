#!/usr/bin/env python3
from __future__ import annotations

# ruff: noqa: E402,I001

import argparse
import os
import sys
from collections.abc import Generator
from pathlib import Path
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
    LocalAgentConnection,
    LocalAgentPairingToken,
    ToolCall,
)
from app.db.session import get_db_session  # noqa: E402
from app.events.event_types import EventType  # noqa: E402
from app.main import app  # noqa: E402
from app.tools.capabilities import CapabilityRegistry  # noqa: E402


AUTH_HEADERS = {"Authorization": "Bearer dev-engineer-token"}


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
            attached_by="smoke-v4",
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
        attached_by="smoke-v4",
    )
    session.commit()


def _pair_codex(
    client: TestClient,
    session: Session,
    *,
    supports_resume: bool = False,
    deterministic_session_id: bool = False,
    resume_sandbox_read_only: bool = False,
) -> tuple[dict[str, Any], str]:
    _ensure_agent(session)
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
            "display_name": "Codex CLI smoke",
            "protocol_version": "local-agent-v1",
            "bridge_version": "smoke-v4",
            "workspace_root": "/Users/luohao/private/codex-v4",
            "capabilities": {
                "supports_streaming": True,
                "supports_resume": supports_resume,
                "supports_cancel": True,
                "host_tools_authorized": True,
                "deterministic_session_id": deterministic_session_id,
                "resume_sandbox_read_only": resume_sandbox_read_only,
            },
            "risk_capabilities": [
                "workspace_read_constrained",
                "host_write",
                "shell",
                "git",
                "network",
                "secret_read",
            ],
            "metadata": {
                "workspace_identity_hash": "workspace-hash-v4",
                "workspace_root_ref": "bridge.workspace-root",
            },
        },
    )
    assert registered.status_code == 201, registered.text
    payload = registered.json()
    connection = payload["connection"]
    assert connection["adapter_kind"] == "codex"
    assert connection["workspace_root"] == ".../private/codex-v4"
    assert connection["capabilities_json"]["host_tools_authorized"] is False
    assert connection["capabilities_json"]["supports_resume"] is False
    assert connection["capabilities_json"]["supports_cancel"] is False
    assert connection["capabilities_json"]["resume_mode"] == "context_replay_new_session"
    assert "host_write" not in connection["risk_capabilities_json"]
    assert "shell" not in connection["risk_capabilities_json"]
    return connection, payload["device_token"]


def _bind_and_lease(
    client: TestClient,
    *,
    connection_id: str,
    device_token: str,
    message: str = "reply read-only",
    client_message_id: str = "smoke-v4-message",
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    bridge_headers = {"X-Local-Agent-Device-Token": device_token}
    binding = client.post(
        f"/api/agents/local-agent/connections/{connection_id}/bindings",
        headers=AUTH_HEADERS,
        json={"title": "Codex V4 smoke", "resume_mode": "native_resume"},
    )
    assert binding.status_code == 201, binding.text
    sent = client.post(
        f"/api/agents/local-agent/bindings/{binding.json()['id']}/messages",
        headers=AUTH_HEADERS,
        json={"content": message, "client_message_id": client_message_id},
    )
    assert sent.status_code == 202, sent.text
    pulled = client.get("/api/agents/local-agent/bridge/tasks", headers=bridge_headers)
    assert pulled.status_code == 200, pulled.text
    task = pulled.json()["items"][0]
    assert task["payload"]["adapter_kind"] == "codex"
    ack = client.post(
        f"/api/agents/local-agent/bridge/tasks/{task['id']}/ack",
        headers=bridge_headers,
        json={"status": "running"},
    )
    assert ack.status_code == 200, ack.text
    return binding.json(), sent.json(), task


def codex_unavailable() -> dict[str, Any]:
    client, session = _new_session()
    _ensure_agent(session)
    created = client.post(
        "/api/agents/local-agent/pairing-tokens",
        headers=AUTH_HEADERS,
        json={"agent_id": "default", "scope": {"executable": True, "adapters": ["hao"]}},
    )
    assert created.status_code == 201, created.text
    pairing = created.json()
    rejected = client.post(
        "/api/agents/local-agent/connections/register",
        json={
            "pair_token": pairing["pair_token"],
            "pair_code": pairing["pair_code"],
            "adapter_kind": "codex",
            "protocol_version": "local-agent-v1",
        },
    )
    assert rejected.status_code == 403, rejected.text
    token = session.get(LocalAgentPairingToken, pairing["id"])
    assert token is not None
    assert token.status == "active"
    assert token.consumed_at is None

    connection, device_token = _pair_codex(client, session)
    _binding, sent, task = _bind_and_lease(
        client,
        connection_id=connection["id"],
        device_token=device_token,
        message="codex is unavailable at runtime",
        client_message_id="smoke-v4-unavailable",
    )
    bridge_headers = {"X-Local-Agent-Device-Token": device_token}
    failed = client.post(
        "/api/agents/local-agent/bridge/events",
        headers=bridge_headers,
        json={
            "event_id": f"{task['id']}:codex:error",
            "bridge_task_id": task["id"],
            "event_type": "assistant_error",
            "error_message": "codex executable not found",
            "sequence": 2,
            "metadata": {
                "adapter_kind": "codex",
                "stderr": "/Users/luohao/private/token=sk-proj-1234567890abcdef",
            },
        },
    )
    assert failed.status_code == 201, failed.text
    duplicate = client.post(
        "/api/agents/local-agent/bridge/events",
        headers=bridge_headers,
        json={
            "event_id": f"{task['id']}:codex:error",
            "bridge_task_id": task["id"],
            "event_type": "assistant_error",
            "error_message": "duplicate",
        },
    )
    assert duplicate.status_code == 201, duplicate.text
    assert duplicate.json()["duplicate"] is True
    session.expire_all()
    bridge_task = session.get(LocalAgentBridgeTask, task["id"])
    assert bridge_task is not None
    assert bridge_task.status == "failed"
    receipt = session.execute(
        select(LocalAgentBridgeEventReceipt).where(
            LocalAgentBridgeEventReceipt.event_id == f"{task['id']}:codex:error"
        )
    ).scalar_one()
    receipt_text = str(receipt.payload_json)
    assert "sk-proj" not in receipt_text
    assert "/Users/luohao" not in receipt_text
    return _evidence(session, scenario="codex-unavailable", run_id=sent["run_id"])


def codex_readonly_reply() -> dict[str, Any]:
    client, session = _new_session()
    connection, device_token = _pair_codex(client, session)
    _binding, sent, task = _bind_and_lease(
        client,
        connection_id=connection["id"],
        device_token=device_token,
        message="summarize this repo without side effects",
        client_message_id="smoke-v4-readonly",
    )
    bridge_headers = {"X-Local-Agent-Device-Token": device_token}
    started = client.post(
        "/api/agents/local-agent/bridge/events",
        headers=bridge_headers,
        json={
            "event_id": f"{task['id']}:codex:started",
            "bridge_task_id": task["id"],
            "event_type": "adapter_started",
            "sequence": 1,
            "metadata": {
                "adapter_kind": "codex",
                "command_mode": "exec_json_read_only_stdin",
                "workspace_identity_hash": "workspace-hash-v4",
                "argv": "codex exec -C /Users/luohao/private/codex-v4",
            },
        },
    )
    assert started.status_code == 201, started.text
    delta = client.post(
        "/api/agents/local-agent/bridge/events",
        headers=bridge_headers,
        json={
            "event_id": f"{task['id']}:codex:delta:1",
            "bridge_task_id": task["id"],
            "event_type": "assistant_delta",
            "content": "Codex read-only reply",
            "sequence": 2,
            "metadata": {"adapter_kind": "codex"},
        },
    )
    assert delta.status_code == 201, delta.text
    done = client.post(
        "/api/agents/local-agent/bridge/events",
        headers=bridge_headers,
        json={
            "event_id": f"{task['id']}:codex:done",
            "bridge_task_id": task["id"],
            "event_type": "assistant_done",
            "content": "Codex read-only reply",
            "sequence": 3,
            "metadata": {
                "adapter_kind": "codex",
                "resume_mode": "context_replay_new_session",
                "adapter_session_id": "codex-session-fixture",
            },
        },
    )
    assert done.status_code == 201, done.text
    repeated_done = client.post(
        "/api/agents/local-agent/bridge/events",
        headers=bridge_headers,
        json={
            "event_id": f"{task['id']}:codex:done",
            "bridge_task_id": task["id"],
            "event_type": "assistant_done",
            "content": "duplicate should not append",
        },
    )
    assert repeated_done.status_code == 201, repeated_done.text
    assert repeated_done.json()["duplicate"] is True
    session.expire_all()
    messages = list(
        session.execute(
            select(AgentMessage).where(AgentMessage.session_id == sent["agent_session_id"])
        ).scalars()
    )
    assert [message.role for message in messages] == ["user", "assistant"]
    assert messages[-1].metadata_json["adapter_kind"] == "codex"
    assert messages[-1].content == "Codex read-only reply"
    assert session.execute(select(ToolCall)).scalars().all() == []
    event_types = {
        event.event_type
        for event in session.execute(select(AgentEvent).where(AgentEvent.task_id == sent["run_id"]))
        .scalars()
        .all()
    }
    assert EventType.LOCAL_AGENT_ADAPTER_STARTED in event_types
    assert EventType.LOCAL_AGENT_MESSAGE_COMPLETED in event_types
    return _evidence(session, scenario="codex-readonly-reply", run_id=sent["run_id"])


def codex_resume_mode() -> dict[str, Any]:
    client, session = _new_session()
    context_connection, context_token = _pair_codex(
        client,
        session,
        supports_resume=True,
        deterministic_session_id=False,
        resume_sandbox_read_only=True,
    )
    context_binding = client.post(
        f"/api/agents/local-agent/connections/{context_connection['id']}/bindings",
        headers=AUTH_HEADERS,
        json={
            "title": "Context replay",
            "adapter_session_id": "untrusted-session",
            "resume_mode": "native_resume",
        },
    )
    assert context_binding.status_code == 201, context_binding.text
    assert context_binding.json()["resume_mode"] == "context_replay_new_session"
    context_sent = client.post(
        f"/api/agents/local-agent/bindings/{context_binding.json()['id']}/messages",
        headers=AUTH_HEADERS,
        json={"content": "resume safely", "client_message_id": "smoke-v4-resume-context"},
    )
    assert context_sent.status_code == 202, context_sent.text
    context_task = client.get(
        "/api/agents/local-agent/bridge/tasks",
        headers={"X-Local-Agent-Device-Token": context_token},
    )
    assert context_task.status_code == 200, context_task.text
    assert (
        context_task.json()["items"][0]["payload"]["resume_mode"]
        == "context_replay_new_session"
    )

    native_connection, native_token = _pair_codex(
        client,
        session,
        supports_resume=True,
        deterministic_session_id=True,
        resume_sandbox_read_only=True,
    )
    assert native_connection["capabilities_json"]["supports_resume"] is False
    native_binding = client.post(
        f"/api/agents/local-agent/connections/{native_connection['id']}/bindings",
        headers=AUTH_HEADERS,
        json={
            "title": "Native resume",
            "adapter_session_id": "codex-session-deterministic",
            "resume_mode": "native_resume",
        },
    )
    assert native_binding.status_code == 201, native_binding.text
    assert native_binding.json()["resume_mode"] == "context_replay_new_session"
    native_sent = client.post(
        f"/api/agents/local-agent/bindings/{native_binding.json()['id']}/messages",
        headers=AUTH_HEADERS,
        json={"content": "do not native resume", "client_message_id": "smoke-v4-resume-native"},
    )
    assert native_sent.status_code == 202, native_sent.text
    native_task = client.get(
        "/api/agents/local-agent/bridge/tasks",
        headers={"X-Local-Agent-Device-Token": native_token},
    )
    assert native_task.status_code == 200, native_task.text
    assert (
        native_task.json()["items"][0]["payload"]["resume_mode"]
        == "context_replay_new_session"
    )
    return _evidence(session, scenario="codex-resume-mode")


def codex_side_effect_rejected() -> dict[str, Any]:
    client, session = _new_session()
    connection, device_token = _pair_codex(client, session)
    _binding, sent, task = _bind_and_lease(
        client,
        connection_id=connection["id"],
        device_token=device_token,
        message="attempt side effect",
        client_message_id="smoke-v4-side-effect",
    )
    bridge_headers = {"X-Local-Agent-Device-Token": device_token}
    unauthorized_tool = client.post(
        "/api/agents/local-agent/bridge/events",
        headers=bridge_headers,
        json={
            "event_id": "smoke-v4-codex-tool-result",
            "bridge_task_id": task["id"],
            "event_type": "tool_result",
            "tool_name": "run_shell",
            "input_json": {"command": "touch should-not-exist"},
            "output_json": {"stdout": "created"},
            "status": "SUCCESS",
            "risk_level": "high",
        },
    )
    assert unauthorized_tool.status_code == 409, unauthorized_tool.text
    assert session.execute(select(ToolCall)).scalars().all() == []
    done = client.post(
        "/api/agents/local-agent/bridge/events",
        headers=bridge_headers,
        json={
            "event_id": f"{task['id']}:codex:done",
            "bridge_task_id": task["id"],
            "event_type": "assistant_done",
            "content": "I need host-tool approval before changing files.",
            "sequence": 3,
            "metadata": {"adapter_kind": "codex"},
        },
    )
    assert done.status_code == 201, done.text
    session.expire_all()
    assert session.execute(select(ToolCall)).scalars().all() == []
    return _evidence(session, scenario="codex-side-effect-rejected", run_id=sent["run_id"])


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
    "codex-unavailable": codex_unavailable,
    "codex-readonly-reply": codex_readonly_reply,
    "codex-resume-mode": codex_resume_mode,
    "codex-side-effect-rejected": codex_side_effect_rejected,
}


def main() -> int:
    parser = argparse.ArgumentParser(description="Deterministic Local Agent V4 smoke scenarios.")
    parser.add_argument("--scenario", choices=sorted(SCENARIOS), required=True)
    args = parser.parse_args()
    evidence = SCENARIOS[args.scenario]()
    print(f"PASS local-agent-v4 {evidence}")
    app.dependency_overrides.clear()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
