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
    Base,
    LocalAgentCommand,
    LocalAgentConnection,
    LocalAgentPendingChange,
    LocalAgentToolRequest,
    ToolApproval,
    ToolCall,
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
            attached_by="smoke",
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
        attached_by="smoke",
    )
    session.commit()


def _pair(client: TestClient, session: Session) -> tuple[dict[str, Any], str]:
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
            "adapter_kind": "hao",
            "display_name": "hao smoke",
            "protocol_version": "local-agent-v1",
            "bridge_version": "smoke-v3",
            "workspace_root": str(ROOT),
            "capabilities": {"supports_resume": True, "supports_streaming": True},
            "risk_capabilities": ["host_read", "host_write", "shell"],
        },
    )
    assert registered.status_code == 201, registered.text
    payload = registered.json()
    return payload["connection"], payload["device_token"]


def _lease_task(
    client: TestClient,
    connection_id: str,
    device_token: str,
    *,
    message: str,
    client_message_id: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    bridge_headers = {"X-Local-Agent-Device-Token": device_token}
    binding = client.post(
        f"/api/agents/local-agent/connections/{connection_id}/bindings",
        headers=AUTH_HEADERS,
        json={"title": "V3 smoke", "resume_mode": "native_resume"},
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
    ack = client.post(
        f"/api/agents/local-agent/bridge/tasks/{task['id']}/ack",
        headers=bridge_headers,
        json={"status": "running"},
    )
    assert ack.status_code == 200, ack.text
    return sent.json(), task


def approve_shell() -> dict[str, Any]:
    client, session = _new_session()
    connection, device_token = _pair(client, session)
    bridge_headers = {"X-Local-Agent-Device-Token": device_token}
    sent, task = _lease_task(
        client,
        connection["id"],
        device_token,
        message="run benign shell",
        client_message_id="smoke-approve-shell",
    )
    request = client.post(
        "/api/agents/local-agent/bridge/tool-requests",
        headers=bridge_headers,
        json={
            "tool_request_id": "smoke-shell-1",
            "bridge_task_id": task["id"],
            "tool_name": "run_shell",
            "input_json": {"command": "printf ok"},
            "execution_target": "host",
            "risk_level": "low",
            "permission_mode": "full-auto",
        },
    )
    assert request.status_code == 201, request.text
    decision = request.json()
    assert decision["decision"] == "approval_required"
    approved = client.post(
        f"/api/tasks/{sent['run_id']}/tool-approvals/{decision['approval_id']}/approve",
        headers=ADMIN_HEADERS,
        json={"reason": "smoke approve"},
    )
    assert approved.status_code == 202, approved.text
    polled = client.get(
        "/api/agents/local-agent/bridge/tool-requests/smoke-shell-1/decision",
        headers=bridge_headers,
    )
    assert polled.status_code == 200, polled.text
    assert polled.json()["executable"] is True
    for event_type, payload in (
        ("started", {"command": "printf ok"}),
        ("output", {"stdout": "ok"}),
        ("finished", {"status": "success", "exit_code": 0, "duration_ms": 1}),
    ):
        event = client.post(
            "/api/agents/local-agent/bridge/commands/smoke-cmd-1/events",
            headers=bridge_headers,
            json={
                "event_id": f"smoke-cmd-1-{event_type}",
                "tool_request_id": "smoke-shell-1",
                "event_type": event_type,
                **payload,
            },
        )
        assert event.status_code == 202, event.text
    result = client.post(
        "/api/agents/local-agent/bridge/tool-requests/smoke-shell-1/result",
        headers=bridge_headers,
        json={
            "event_id": "smoke-shell-1-result",
            "status": "SUCCESS",
            "output_json": {"stdout": "ok", "exit_code": 0},
            "command_id": "smoke-cmd-1",
            "duration_ms": 1,
        },
    )
    assert result.status_code == 202, result.text
    done = client.post(
        "/api/agents/local-agent/bridge/events",
        headers=bridge_headers,
        json={
            "event_id": "smoke-shell-1-done",
            "bridge_task_id": task["id"],
            "event_type": "assistant_done",
            "content": "done",
        },
    )
    assert done.status_code == 201, done.text
    return _evidence(session, scenario="approve-shell")


def reject_write() -> dict[str, Any]:
    client, session = _new_session()
    connection, device_token = _pair(client, session)
    bridge_headers = {"X-Local-Agent-Device-Token": device_token}
    sent, task = _lease_task(
        client,
        connection["id"],
        device_token,
        message="write preview",
        client_message_id="smoke-reject-write",
    )
    request = client.post(
        "/api/agents/local-agent/bridge/tool-requests",
        headers=bridge_headers,
        json={
            "tool_request_id": "smoke-write-1",
            "bridge_task_id": task["id"],
            "tool_name": "write_file",
            "input_json": {"path": "notes.md", "content": "new\n"},
            "execution_target": "host",
            "risk_level": "high",
            "permission_mode": "full-auto",
            "target_paths": ["notes.md"],
            "pending_change_preview": {
                "change_id": "change-smoke-write",
                "target_paths": ["notes.md"],
                "diff_sha256": "0" * 64,
            },
        },
    )
    assert request.status_code == 201, request.text
    decision = request.json()
    rejected = client.post(
        f"/api/tasks/{sent['run_id']}/tool-approvals/{decision['approval_id']}/reject",
        headers=ADMIN_HEADERS,
        json={"reason": "smoke reject"},
    )
    assert rejected.status_code == 202, rejected.text
    late = client.post(
        "/api/agents/local-agent/bridge/tool-requests/smoke-write-1/result",
        headers=bridge_headers,
        json={
            "event_id": "smoke-write-1-result",
            "status": "SUCCESS",
            "output_json": {"path": "notes.md"},
            "change_id": "change-smoke-write",
            "diff_sha256": "0" * 64,
        },
    )
    assert late.status_code == 409, late.text
    return _evidence(session, scenario="reject-write")


def revoke_pending() -> dict[str, Any]:
    client, session = _new_session()
    connection, device_token = _pair(client, session)
    bridge_headers = {"X-Local-Agent-Device-Token": device_token}
    _sent, task = _lease_task(
        client,
        connection["id"],
        device_token,
        message="pending then revoke",
        client_message_id="smoke-revoke-pending",
    )
    request = client.post(
        "/api/agents/local-agent/bridge/tool-requests",
        headers=bridge_headers,
        json={
            "tool_request_id": "smoke-revoke-1",
            "bridge_task_id": task["id"],
            "tool_name": "run_shell",
            "input_json": {"command": "printf no"},
            "execution_target": "host",
            "risk_level": "high",
            "permission_mode": "full-auto",
        },
    )
    assert request.status_code == 201, request.text
    revoked = client.post(
        f"/api/agents/local-agent/connections/{connection['id']}/revoke",
        headers=ADMIN_HEADERS,
    )
    assert revoked.status_code == 200, revoked.text
    polled = client.get(
        "/api/agents/local-agent/bridge/tool-requests/smoke-revoke-1/decision",
        headers=bridge_headers,
    )
    assert polled.status_code == 403, polled.text
    return _evidence(session, scenario="revoke-pending")


def _evidence(session: Session, *, scenario: str) -> dict[str, Any]:
    return {
        "scenario": scenario,
        "connections": len(session.execute(select(LocalAgentConnection)).scalars().all()),
        "tool_calls": len(session.execute(select(ToolCall)).scalars().all()),
        "approvals": len(session.execute(select(ToolApproval)).scalars().all()),
        "tool_requests": len(session.execute(select(LocalAgentToolRequest)).scalars().all()),
        "commands": len(session.execute(select(LocalAgentCommand)).scalars().all()),
        "pending_changes": len(
            session.execute(select(LocalAgentPendingChange)).scalars().all()
        ),
        "events": len(session.execute(select(AgentEvent)).scalars().all()),
    }


SCENARIOS = {
    "approve-shell": approve_shell,
    "reject-write": reject_write,
    "revoke-pending": revoke_pending,
}


def main() -> int:
    parser = argparse.ArgumentParser(description="Deterministic Local Agent V3 smoke scenarios.")
    parser.add_argument("--scenario", choices=sorted(SCENARIOS), required=True)
    args = parser.parse_args()
    evidence = SCENARIOS[args.scenario]()
    print(f"PASS local-agent-v3 {evidence}")
    app.dependency_overrides.clear()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
