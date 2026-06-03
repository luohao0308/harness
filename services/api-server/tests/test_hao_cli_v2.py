from __future__ import annotations

import importlib
import io
import json
import sqlite3
from collections.abc import Callable
from hashlib import sha256
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.registry import ensure_default_agents
from app.api.schemas import AgentChatStreamRequest, AgentLocalToolEventRequest
from app.cli.hao import local_tools as hao_local_tools
from app.cli.hao.api_client import SSEEvent
from app.cli.hao.config import load_persisted_config
from app.cli.hao.local_tools import ToolExecutionResult, execute_local_tool
from app.cli.hao.sandbox_tools import SandboxToolResult
from app.cli.hao.session_store import SessionStore
from app.cli.hao.tui import HaoApp
from app.db.models import AgentEvent, Task, ToolCall, utc_now
from app.main import app as fastapi_app
from tests.conftest import AUTH_HEADERS

TERMINAL_COMMAND_STATUSES = {"success", "failed", "timeout", "cancelled"}
hao_main = importlib.import_module("app.cli.hao.main")


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def _make_hao_app(
    tmp_path: Path,
    monkeypatch,
    *,
    permission_mode: str = "confirm",
    target: str = "host",
    resume_session_id: str | None = None,
) -> HaoApp:
    home = tmp_path / "hao-home"
    monkeypatch.setenv("HAO_HOME", str(home))
    app = HaoApp(
        api_url="http://127.0.0.1:8000",
        token="token",
        agent_id="default",
        cwd=tmp_path,
        model_provider="default",
        model_name="default",
        permission_mode=permission_mode,
        target=target,
        resume_session_id=resume_session_id,
    )
    monkeypatch.setattr(app, "_status", lambda: None)
    monkeypatch.setattr(app, "_chat", lambda message: None)
    monkeypatch.setattr(app, "_render_side_panel", lambda: None)
    monkeypatch.setattr(app, "_tool_log", lambda message: None)
    return app


def test_session_store_persists_tree_and_reconstructs_active_path(tmp_path: Path) -> None:
    store = SessionStore(tmp_path / "hao.db", tmp_path / "sessions")
    session = store.create_session(
        cwd="/tmp/work",
        agent_id="default",
        mode="confirm",
        target="host",
    )

    root = store.append_message(session.id, role="user", content="start")
    assistant = store.append_message(session.id, role="assistant", content="ok")
    original_followup = store.append_message(session.id, role="user", content="old ask")
    edited_followup = store.append_message(
        session.id,
        role="user",
        content="edited ask",
        parent_id=assistant["id"],
        source_message_id=original_followup["id"],
    )

    loaded = store.get_session(session.id)
    assert loaded is not None
    assert loaded.active_leaf_id == edited_followup["id"]

    messages = {message["id"]: message for message in store.list_messages(session.id)}
    assert messages[root["id"]]["parent_id"] is None
    assert messages[assistant["id"]]["parent_id"] == root["id"]
    assert messages[original_followup["id"]]["parent_id"] == assistant["id"]
    assert set(messages[assistant["id"]]["children_ids"]) == {
        original_followup["id"],
        edited_followup["id"],
    }
    assert messages[assistant["id"]]["branch_id"] == messages[root["id"]]["branch_id"]
    assert messages[original_followup["id"]]["branch_id"] == messages[root["id"]]["branch_id"]
    assert messages[edited_followup["id"]]["branch_id"] != messages[root["id"]]["branch_id"]
    assert messages[edited_followup["id"]]["source_message_id"] == original_followup["id"]

    active_path = store.list_active_path(session.id)
    assert [message["id"] for message in active_path] == [
        root["id"],
        assistant["id"],
        edited_followup["id"],
    ]
    assert original_followup["id"] not in [message["id"] for message in active_path]


def test_session_store_reopen_preserves_tree_fields(tmp_path: Path) -> None:
    db_path = tmp_path / "hao.db"
    sessions_dir = tmp_path / "sessions"
    store = SessionStore(db_path, sessions_dir)
    session = store.create_session(
        cwd="/tmp/work",
        agent_id="default",
        mode="auto-edit",
        target="host",
    )
    root = store.append_message(session.id, role="user", content="inspect")
    tool_event_id = store.record_tool_event(
        session.id,
        run_id="run-1",
        tool_call_id="tool-1",
        tool_name="read_file",
        status="SUCCESS",
        input_json={"path": "README.md"},
        output_json={"content": "ok"},
        duration_ms=1,
    )
    tool_message = store.append_message(
        session.id,
        role="tool",
        content="tool result",
        state="paused",
        run_id="run-1",
        source_message_id=root["id"],
        tool_event_id=tool_event_id,
        metadata={"tool_name": "read_file"},
    )

    reopened = SessionStore(db_path, sessions_dir)
    loaded = reopened.get_session(session.id)
    assert loaded is not None
    assert loaded.active_leaf_id == tool_message["id"]

    messages = {message["id"]: message for message in reopened.list_messages(session.id)}
    assert messages[tool_message["id"]]["parent_id"] == root["id"]
    assert messages[tool_message["id"]]["branch_id"] == messages[root["id"]]["branch_id"]
    assert messages[tool_message["id"]]["state"] == "paused"
    assert messages[tool_message["id"]]["source_message_id"] == root["id"]
    assert messages[tool_message["id"]]["tool_event_id"] == tool_event_id
    assert messages[tool_message["id"]]["metadata"]["tool_name"] == "read_file"
    assert reopened.list_tool_events(session.id)[0]["id"] == tool_event_id


def test_hao_resume_restores_session_metadata_and_active_path(
    tmp_path: Path,
    monkeypatch,
) -> None:
    home = tmp_path / "hao-home"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    monkeypatch.setenv("HAO_HOME", str(home))
    store = SessionStore(home / "hao.db", home / "sessions")
    session = store.create_session(
        cwd=str(workspace),
        agent_id="custom-agent",
        mode="full-auto",
        cli_mode="act",
        target="sandbox",
    )
    root = store.append_message(session.id, role="user", content="start")
    stale = store.append_message(session.id, role="assistant", content="old path")
    active = store.append_message(
        session.id,
        role="assistant",
        content="active path",
        parent_id=root["id"],
        source_message_id=stale["id"],
    )
    store.update_run_id(session.id, "run-1")

    app = HaoApp(
        api_url="http://127.0.0.1:8000",
        token="token",
        agent_id="wrong-agent",
        cwd=tmp_path,
        model_provider="default",
        model_name="default",
        permission_mode="confirm",
        target="host",
        resume_session_id=session.id,
    )
    monkeypatch.setattr(app, "_status", lambda: None)
    monkeypatch.setattr(app, "_chat", lambda message: None)
    monkeypatch.setattr(app, "_render_side_panel", lambda: None)

    app.on_mount()

    assert app.agent_id == "custom-agent"
    assert app.cwd == workspace.resolve()
    assert app.permission_mode == "full-auto"
    assert app.interaction_mode == "act"
    assert app.target == "sandbox"
    assert app.run_id == "run-1"
    assert [message["id"] for message in app.messages] == [root["id"], active["id"]]
    assert stale["id"] not in [message["id"] for message in app.messages]


def test_hao_workflow_payloads_distinguish_chat_plan_and_act(
    tmp_path: Path,
    monkeypatch,
) -> None:
    app = _make_hao_app(tmp_path, monkeypatch)

    chat = app._build_stream_payload("inspect", "chat")
    plan = app._build_stream_payload("draft a plan", "plan")
    act = app._build_stream_payload("edit the file", "act")

    assert chat["mode"] == "cli_agent"
    assert chat["interaction_mode"] == "chat"
    assert chat["act_intent"] is None
    assert plan["mode"] == "markdown_plan"
    assert plan["interaction_mode"] == "plan"
    assert plan["act_intent"] is None
    assert act["mode"] == "cli_agent"
    assert act["interaction_mode"] == "act"
    assert act["act_intent"] == {
        "source": "slash_command",
        "allow_local_tools": True,
    }


def test_hao_backend_schemas_accept_workflow_metadata() -> None:
    act_intent = {"source": "slash_command", "allow_local_tools": True}

    stream_request = AgentChatStreamRequest(
        mode="cli_agent",
        goal="edit the file",
        interaction_mode="act",
        act_intent=act_intent,
    )
    local_tool_request = AgentLocalToolEventRequest(
        tool_name="run_shell",
        input_json={"command": "pytest"},
        output_json={"stdout": "ok", "exit_code": 0},
        interaction_mode="act",
        act_intent=act_intent,
    )

    assert stream_request.interaction_mode == "act"
    assert stream_request.act_intent == act_intent
    assert local_tool_request.interaction_mode == "act"
    assert local_tool_request.act_intent == act_intent


def test_hao_backend_schema_normalizes_legacy_markdown_plan_mode() -> None:
    stream_request = AgentChatStreamRequest(
        mode="co" + "dex_plan",
        goal="draft a plan",
    )

    assert stream_request.mode == "markdown_plan"


def test_hao_plan_mode_suppresses_tool_requests_for_host_and_sandbox(
    tmp_path: Path,
    monkeypatch,
) -> None:
    class FakeClient:
        def stream_chat(self, agent_id: str, payload: dict):
            del agent_id, payload
            yield SSEEvent(
                event="run_created",
                data={"run_id": "run-1"},
                raw='event: run_created\ndata: {"run_id": "run-1"}',
            )
            yield SSEEvent(
                event="tool_call_requested",
                data={
                    "tool_call_id": "tool-1",
                    "tool_name": "write_file",
                    "input_json": {"path": "README.md", "content": "changed"},
                },
                raw='event: tool_call_requested\ndata: {"tool_call_id": "tool-1"}',
            )
            yield SSEEvent(event="done", data={}, raw="event: done\ndata: {}")

    def make_spy(calls: list[dict]) -> Callable[[SSEEvent], str | None]:
        def spy_on_tool_request(event: SSEEvent) -> str | None:
            calls.append(event.data)
            return None

        return spy_on_tool_request

    for target in ("host", "sandbox"):
        app = _make_hao_app(tmp_path / target, monkeypatch, target=target)
        app.session = app.store.create_session(
            cwd=str(tmp_path / target),
            agent_id="default",
            mode="confirm",
            cli_mode="plan",
            target=target,
        )
        app.api_client = FakeClient()  # type: ignore[assignment]
        tool_request_calls: list[dict] = []
        monkeypatch.setattr(app, "_handle_tool_request", make_spy(tool_request_calls))

        app._run_turn_sync("draft a plan", 0, "plan")

        assert app.pending_tools == {}
        assert tool_request_calls == []
        assert app.store.list_tool_events(app.session.id) == []
        assert [message["role"] for message in app.messages] == []


@pytest.mark.parametrize("interaction_mode", ["chat", "act"])
@pytest.mark.parametrize("target", ["host", "sandbox"])
def test_hao_non_plan_tool_requests_route_by_target(
    tmp_path: Path,
    monkeypatch,
    interaction_mode: str,
    target: str,
) -> None:
    app = _make_hao_app(tmp_path / target, monkeypatch, target=target)
    app.session = app.store.create_session(
        cwd=str(tmp_path / target),
        agent_id="default",
        mode="confirm",
        cli_mode=interaction_mode,
        target=target,
    )
    app.run_id = "run-1"
    app.interaction_mode = interaction_mode
    calls = {"local": 0, "sandbox": 0}

    class FakeClient:
        def record_local_tool_event(self, run_id: str, payload: dict) -> dict:
            del run_id, payload
            return {"tool_call": {"id": "tool-call-1"}}

    app.api_client = FakeClient()  # type: ignore[assignment]

    def fake_local_tool(
        tool_name: str,
        input_json: dict,
        workspace_root: Path,
    ) -> ToolExecutionResult:
        del workspace_root
        calls["local"] += 1
        return ToolExecutionResult(
            tool_name=tool_name,
            status="SUCCESS",
            input_json=input_json,
            output_json={"content": "host"},
            duration_ms=1,
        )

    def fake_sandbox_tool(api_client, *, run_id: str, tool_name: str, input_json: dict):
        del api_client, run_id
        calls["sandbox"] += 1
        return SandboxToolResult(
            status="SUCCESS",
            tool_call_id="sandbox-tool-1",
            output_json={"content": "sandbox"},
            duration_ms=1,
        )

    monkeypatch.setattr("app.cli.hao.tui.execute_local_tool", fake_local_tool)
    monkeypatch.setattr("app.cli.hao.tui.execute_sandbox_tool", fake_sandbox_tool)
    event = SSEEvent(
        event="tool_call_requested",
        data={
            "tool_call_id": "tool-1",
            "tool_name": "read_file",
            "input_json": {"path": "README.md"},
        },
        raw="event: tool_call_requested\ndata: {}",
    )

    result_message = app._handle_tool_request(event, interaction_mode)

    assert result_message is not None
    assert calls == (
        {"local": 1, "sandbox": 0}
        if target == "host"
        else {"local": 0, "sandbox": 1}
    )


@pytest.mark.parametrize(
    ("tool_name", "input_json"),
    [
        ("run_shell", {"command": "pytest"}),
        ("write_file", {"path": "notes.md", "content": "new\n"}),
        (
            "apply_patch",
            {
                "patch": "--- a/notes.md\n+++ b/notes.md\n@@ -1 +1 @@\n-old\n+new\n",
            },
        ),
    ],
)
def test_hao_sandbox_write_and_shell_requests_never_call_local_runner(
    tmp_path: Path,
    monkeypatch,
    tool_name: str,
    input_json: dict,
) -> None:
    app = _make_hao_app(tmp_path, monkeypatch, permission_mode="full-auto", target="sandbox")
    app.session = app.store.create_session(
        cwd=str(tmp_path),
        agent_id="default",
        mode="full-auto",
        cli_mode="act",
        target="sandbox",
    )
    app.run_id = "run-1"
    sandbox_calls: list[tuple[str, dict]] = []

    def fail_local_tool(*args, **kwargs):
        del args, kwargs
        raise AssertionError("sandbox target must not call execute_local_tool")

    def fake_sandbox_tool(api_client, *, run_id: str, tool_name: str, input_json: dict):
        del api_client, run_id
        sandbox_calls.append((tool_name, input_json))
        return SandboxToolResult(
            status="SUCCESS",
            tool_call_id="sandbox-tool-1",
            output_json={"sandbox": True, "tool_name": tool_name},
            duration_ms=1,
        )

    monkeypatch.setattr("app.cli.hao.tui.execute_local_tool", fail_local_tool)
    monkeypatch.setattr("app.cli.hao.tui.execute_sandbox_tool", fake_sandbox_tool)
    event = SSEEvent(
        event="tool_call_requested",
        data={
            "tool_call_id": "tool-1",
            "tool_name": tool_name,
            "input_json": input_json,
        },
        raw="event: tool_call_requested\ndata: {}",
    )

    result_message = app._handle_tool_request(event, "act")

    assert result_message is not None
    assert sandbox_calls == [(tool_name, input_json)]
    assert app.store.list_pending_changes(app.session.id) == []
    assert app.store.list_tool_events(app.session.id)[-1]["output_json"]["sandbox"] is True


def test_hao_act_tool_result_message_metadata_keeps_act_intent(
    tmp_path: Path,
    monkeypatch,
) -> None:
    app = _make_hao_app(tmp_path, monkeypatch)
    app.session = app.store.create_session(
        cwd=str(tmp_path),
        agent_id="default",
        mode="confirm",
        cli_mode="act",
        target="host",
    )
    app.interaction_mode = "act"
    result = ToolExecutionResult(
        tool_name="read_file",
        status="SUCCESS",
        input_json={"path": "README.md"},
        output_json={"content": "ok"},
        duration_ms=1,
    )

    app._record_tool_result(result, "low", audit_host=False)

    metadata = app.messages[-1]["metadata"]
    assert metadata["interaction_mode"] == "act"
    assert metadata["backend_mode"] == "cli_agent"
    assert metadata["act_intent"] == {
        "source": "slash_command",
        "allow_local_tools": True,
    }


def test_hao_pending_change_preserves_workflow_metadata_through_approval(
    tmp_path: Path,
    monkeypatch,
) -> None:
    app = _make_hao_app(tmp_path, monkeypatch, target="host")
    app.session = app.store.create_session(
        cwd=str(tmp_path),
        agent_id="default",
        mode="confirm",
        cli_mode="act",
        target="host",
    )
    app.run_id = "run-1"
    app.interaction_mode = "act"
    recorded_payloads: list[dict] = []

    class FakeClient:
        def record_local_tool_event(self, run_id: str, payload: dict) -> dict:
            if str(payload["tool_name"]).startswith("commit_"):
                raise AssertionError("commit must not be audited after approval")
            recorded_payloads.append({"run_id": run_id, **payload})
            return {"tool_call": {"id": "tool-call-1"}}

    app.api_client = FakeClient()  # type: ignore[assignment]
    continue_calls: list[tuple[str, int, str]] = []
    monkeypatch.setattr(
        app,
        "_run_turn_sync",
        lambda goal, depth, interaction_mode: continue_calls.append(
            (goal, depth, interaction_mode)
        ),
    )
    target = tmp_path / "README.md"
    target.write_text("before\n", encoding="utf-8")
    event = SSEEvent(
        event="tool_call_requested",
        data={
            "tool_call_id": "tool-1",
            "tool_name": "write_file",
            "input_json": {"path": "README.md", "content": "changed"},
        },
        raw="event: tool_call_requested\ndata: {}",
    )

    result_message = app._handle_tool_request(event, "act")

    assert result_message is None
    assert app.pending_tools == {}
    assert target.read_text(encoding="utf-8") == "before\n"
    changes = app.store.list_pending_changes(app.session.id)
    assert len(changes) == 1
    assert changes[0]["metadata"]["workflow_metadata"]["interaction_mode"] == "act"
    assert changes[0]["metadata"]["execution_target"] == "host"
    assert changes[0]["metadata"]["permission_mode"] == "confirm"
    app.target = "sandbox"
    app.permission_mode = "full-auto"
    app.interaction_mode = "chat"
    HaoApp.approve_change_worker.__wrapped__(app, changes[0]["id"])

    expected_act_intent = {"source": "slash_command", "allow_local_tools": True}
    assert target.read_text(encoding="utf-8") == "changed"
    assert [payload["tool_name"] for payload in recorded_payloads] == ["write_file"]
    assert recorded_payloads[-1]["interaction_mode"] == "act"
    assert recorded_payloads[-1]["act_intent"] == expected_act_intent
    assert recorded_payloads[-1]["execution_target"] == "host"
    assert recorded_payloads[-1]["permission_mode"] == "confirm"
    metadata = app.messages[-1]["metadata"]
    assert metadata["interaction_mode"] == "act"
    assert metadata["backend_mode"] == "cli_agent"
    assert metadata["act_intent"] == expected_act_intent
    assert metadata["execution_target"] == "host"
    assert metadata["permission_mode"] == "confirm"
    assert continue_calls == [
        ("Continue using the approved local tool result.", 1, "act")
    ]


def test_hao_approve_command_executes_pending_tool_with_frozen_metadata(
    tmp_path: Path,
    monkeypatch,
) -> None:
    app = _make_hao_app(tmp_path, monkeypatch, target="host")
    app.session = app.store.create_session(
        cwd=str(tmp_path),
        agent_id="default",
        mode="confirm",
        cli_mode="act",
        target="host",
    )
    app.run_id = "run-1"
    app.interaction_mode = "act"
    recorded_payloads: list[dict] = []

    class FakeClient:
        def record_local_tool_event(self, run_id: str, payload: dict) -> dict:
            recorded_payloads.append({"run_id": run_id, **payload})
            return {"tool_call": {"id": "tool-call-1"}}

    def fake_execute_local_tool(
        tool_name: str,
        input_json: dict,
        workspace_root: Path,
        **kwargs,
    ) -> ToolExecutionResult:
        del workspace_root, kwargs
        return ToolExecutionResult(
            tool_name=tool_name,
            status="SUCCESS",
            input_json=input_json,
            output_json={
                "command": input_json["command"],
                "exit_code": 0,
                "stdout": "ok",
            },
            duration_ms=1,
        )

    app.api_client = FakeClient()  # type: ignore[assignment]
    monkeypatch.setattr("app.cli.hao.tui.execute_local_tool", fake_execute_local_tool)
    continue_calls: list[tuple[str, int, str]] = []
    monkeypatch.setattr(
        app,
        "_run_turn_sync",
        lambda goal, depth, interaction_mode: continue_calls.append(
            (goal, depth, interaction_mode)
        ),
    )
    monkeypatch.setattr(
        app,
        "approve_tool_worker",
        lambda pending_id: HaoApp.approve_tool_worker.__wrapped__(app, pending_id),
    )
    event = SSEEvent(
        event="tool_call_requested",
        data={
            "tool_call_id": "shell-1",
            "tool_name": "run_shell",
            "input_json": {"command": "pytest"},
        },
        raw="event: tool_call_requested\ndata: {}",
    )

    result_message = app._handle_tool_request(event, "act")
    app.target = "sandbox"
    app.permission_mode = "full-auto"
    app.interaction_mode = "chat"
    app._handle_command("/approve tool-shell-1")

    assert result_message is None
    assert "tool-shell-1" not in app.pending_tools
    assert recorded_payloads[-1]["interaction_mode"] == "act"
    assert recorded_payloads[-1]["execution_target"] == "host"
    assert recorded_payloads[-1]["permission_mode"] == "confirm"
    assert app.messages[-1]["metadata"]["interaction_mode"] == "act"
    assert app.messages[-1]["metadata"]["execution_target"] == "host"
    assert continue_calls == [
        ("Continue using the approved local tool result.", 1, "act")
    ]


def test_hao_approve_command_commits_pending_change_through_handler(
    tmp_path: Path,
    monkeypatch,
) -> None:
    app = _make_hao_app(tmp_path, monkeypatch, permission_mode="confirm", target="host")
    app.session = app.store.create_session(
        cwd=str(tmp_path),
        agent_id="default",
        mode="confirm",
        target="host",
    )
    target = tmp_path / "notes.md"
    target.write_text("old\n", encoding="utf-8")
    preview = execute_local_tool(
        "preview_write_file",
        {"path": "notes.md", "content": "new\n"},
        tmp_path,
        session_store=app.store,
        session_id=app.session.id,
    )
    monkeypatch.setattr(
        app,
        "approve_change_worker",
        lambda change_id: HaoApp.approve_change_worker.__wrapped__(app, change_id),
    )

    app._handle_command(f"/approve {preview.output_json['change_id']}")

    assert target.read_text(encoding="utf-8") == "new\n"
    change = app.store.get_pending_change(preview.output_json["change_id"])
    assert change is not None
    assert change["status"] == "committed"


def test_hao_cancel_command_routes_through_tui_helper(
    tmp_path: Path,
    monkeypatch,
) -> None:
    app = _make_hao_app(tmp_path, monkeypatch)
    app.session = app.store.create_session(
        cwd=str(tmp_path),
        agent_id="default",
        mode="confirm",
        target="host",
    )
    cancel_calls: list[str] = []
    tool_logs: list[str] = []

    monkeypatch.setattr(
        app,
        "_tool_log",
        lambda message: tool_logs.append(message),
    )
    monkeypatch.setattr(
        "app.cli.hao.tui.cancel_local_command",
        lambda command_id: cancel_calls.append(command_id) or True,
    )

    app._handle_command("/cancel command-1")

    assert cancel_calls == ["command-1"]
    assert tool_logs == ["[yellow]cancel requested[/yellow] command-1"]


def test_hao_retry_command_routes_to_worker(
    tmp_path: Path,
    monkeypatch,
) -> None:
    app = _make_hao_app(tmp_path, monkeypatch)
    app.session = app.store.create_session(
        cwd=str(tmp_path),
        agent_id="default",
        mode="confirm",
        target="host",
    )
    retry_calls: list[str] = []

    monkeypatch.setattr(
        app,
        "retry_command_worker",
        lambda command_id: retry_calls.append(command_id),
    )

    app._handle_command("/retry command-2")

    assert retry_calls == ["command-2"]


def test_hao_retry_command_worker_creates_retry_row_and_links_tool_event(
    tmp_path: Path,
    monkeypatch,
) -> None:
    app = _make_hao_app(tmp_path, monkeypatch, target="host")
    app.session = app.store.create_session(
        cwd=str(tmp_path),
        agent_id="default",
        mode="confirm",
        cli_mode="act",
        target="host",
    )
    app.interaction_mode = "act"
    original = app.store.create_command(
        app.session.id,
        tool_name="run_shell",
        command="printf ok",
        command_json={"command": "printf ok"},
        timeout_seconds=30,
    )
    app.store.start_command(original["id"])
    app.store.finish_command(
        original["id"],
        status="success",
        exit_code=0,
        stdout_truncated=False,
        stderr_truncated=False,
    )

    def fake_retry_local_command_tool(
        command_id: str,
        workspace_root: Path,
        *,
        session_store: SessionStore,
        cancel_check=None,
    ) -> ToolExecutionResult:
        del workspace_root, cancel_check
        retry = session_store.retry_command(command_id)
        started = session_store.start_command(retry["id"])
        session_store.record_command_output(
            retry["id"],
            stream="stdout",
            chunk="retry ok",
        )
        finished = session_store.finish_command(
            retry["id"],
            status="success",
            exit_code=0,
            stdout_truncated=False,
            stderr_truncated=False,
        )
        return ToolExecutionResult(
            tool_name=retry["tool_name"],
            status="SUCCESS",
            input_json=retry["command_json"],
            output_json={
                "command_id": retry["id"],
                "command": retry["command"],
                "command_status": "success",
                "started_at": started["started_at"],
                "finished_at": finished["finished_at"],
                "exit_code": 0,
                "stdout": "retry ok",
                "stderr": "",
                "stdout_truncated": False,
                "stderr_truncated": False,
            },
            duration_ms=1,
        )

    monkeypatch.setattr(
        "app.cli.hao.tui.retry_local_command_tool",
        fake_retry_local_command_tool,
    )

    HaoApp.retry_command_worker.__wrapped__(app, original["id"])

    commands = app.store.list_commands(app.session.id)
    assert len(commands) == 2
    retry = commands[-1]
    assert retry["retry_of_id"] == original["id"]
    assert retry["status"] == "success"
    assert retry["tool_event_id"] is not None
    assert app.messages[-1]["metadata"]["interaction_mode"] == "act"


def test_hao_audit_failure_records_local_failure_without_tool_message(
    tmp_path: Path,
    monkeypatch,
) -> None:
    app = _make_hao_app(tmp_path, monkeypatch, target="host")
    app.session = app.store.create_session(
        cwd=str(tmp_path),
        agent_id="default",
        mode="confirm",
        target="host",
    )
    app.run_id = "run-1"
    tool_logs: list[str] = []
    monkeypatch.setattr(app, "_tool_log", lambda message: tool_logs.append(message))

    class FakeClient:
        def record_local_tool_event(self, run_id: str, payload: dict) -> dict:
            del run_id, payload
            raise RuntimeError("audit service unavailable")

    app.api_client = FakeClient()  # type: ignore[assignment]
    result = ToolExecutionResult(
        tool_name="read_file",
        status="SUCCESS",
        input_json={"path": "README.md"},
        output_json={"content": "ok"},
        duration_ms=1,
    )

    message = app._record_tool_result(result, "low")

    assert message is None
    assert app.store.list_messages(app.session.id) == []
    events = app.store.list_tool_events(app.session.id)
    assert len(events) == 1
    assert events[0]["status"] == "AUDIT_FAILED"
    assert events[0]["output_json"]["audit_failed"] is True
    assert events[0]["output_json"]["original_status"] == "SUCCESS"
    assert "local tool result not continued" in tool_logs[-1]


def test_hao_write_preview_audit_failure_fails_pending_change_without_tool_message(
    tmp_path: Path,
    monkeypatch,
) -> None:
    app = _make_hao_app(tmp_path, monkeypatch, permission_mode="confirm", target="host")
    app.session = app.store.create_session(
        cwd=str(tmp_path),
        agent_id="default",
        mode="confirm",
        target="host",
    )
    app.run_id = "run-1"
    target = tmp_path / "notes.md"
    target.write_text("old\n", encoding="utf-8")

    class FakeClient:
        def record_local_tool_event(self, run_id: str, payload: dict) -> dict:
            del run_id, payload
            raise RuntimeError("audit service unavailable")

    app.api_client = FakeClient()  # type: ignore[assignment]
    event = SSEEvent(
        event="tool_call_requested",
        data={
            "tool_call_id": "write-1",
            "tool_name": "write_file",
            "input_json": {"path": "notes.md", "content": "new\n"},
        },
        raw="event: tool_call_requested\ndata: {}",
    )

    result_message = app._handle_tool_request(event, "act")

    changes = app.store.list_pending_changes(app.session.id)
    events = app.store.list_tool_events(app.session.id)
    assert result_message is None
    assert target.read_text(encoding="utf-8") == "old\n"
    assert changes[0]["status"] == "failed"
    assert "audit failed" in changes[0]["error_message"]
    assert app.store.list_messages(app.session.id) == []
    assert events[0]["status"] == "AUDIT_FAILED"


def test_hao_workbench_status_snapshot_counts_branch_pending_and_commands(
    tmp_path: Path,
    monkeypatch,
) -> None:
    app = _make_hao_app(tmp_path, monkeypatch)
    app.session = app.store.create_session(
        cwd=str(tmp_path),
        agent_id="default",
        mode="confirm",
        target="host",
    )
    root = app.store.append_message(app.session.id, role="user", content="start")
    active = app.store.append_message(app.session.id, role="assistant", content="active")
    app.messages = app.store.list_active_path(app.session.id)
    app.pending_tools["tool-shell"] = object()  # type: ignore[assignment]
    preview = execute_local_tool(
        "preview_write_file",
        {"path": "notes.md", "content": "new\n"},
        tmp_path,
        session_store=app.store,
        session_id=app.session.id,
    )
    command = app.store.create_command(
        app.session.id,
        tool_name="run_shell",
        command="pytest",
        command_json={"command": "pytest"},
        timeout_seconds=30,
    )
    app.store.start_command(command["id"])

    status = app._workbench_status()
    status_text = app._status_text(status)

    assert status["active_leaf_id"] == active["id"]
    assert status["active_branch_id"] == root["id"]
    assert status["pending_tool_count"] == 1
    assert status["pending_change_count"] == 1
    assert status["pending_approval_count"] == 2
    assert status["running_command_count"] == 1
    assert status["side_view"] == "tools"
    assert status["output_style"] == "default"
    assert status["compact_active"] is False
    assert preview.output_json["change_id"].startswith("change-")
    for fragment in (
        f"leaf={active['id']}",
        f"branch={root['id']}",
        "approvals=2",
        "commands=1/1",
        "view=tools",
        "style=default",
        "compact=off",
    ):
        assert fragment in status_text


def test_hao_v3_approvals_view_lists_current_pending_tools_and_changes(
    tmp_path: Path,
    monkeypatch,
) -> None:
    app = _make_hao_app(tmp_path, monkeypatch)
    app.session = app.store.create_session(
        cwd=str(tmp_path),
        agent_id="default",
        mode="confirm",
        target="host",
    )
    app.pending_tools["tool-shell"] = object()  # type: ignore[assignment]
    preview = execute_local_tool(
        "preview_write_file",
        {"path": "notes.md", "content": "new\n"},
        tmp_path,
        session_store=app.store,
        session_id=app.session.id,
    )

    entries = app._approval_entries()

    assert any("tool tool-shell" in entry for entry in entries)
    assert any(preview.output_json["change_id"] in entry for entry in entries)
    assert any("notes.md" in entry for entry in entries)


def test_hao_view_command_accepts_plan_and_outputs_and_rejects_unknown(
    tmp_path: Path,
    monkeypatch,
) -> None:
    app = _make_hao_app(tmp_path, monkeypatch)
    app.session = app.store.create_session(
        cwd=str(tmp_path),
        agent_id="default",
        mode="confirm",
        target="host",
    )
    render_calls: list[str] = []
    monkeypatch.setattr(app, "_render_side_panel", lambda: render_calls.append(app.side_view))

    for view in ("tools", "diff", "files", "approvals", "commands", "plan", "outputs"):
        app._handle_command(f"/view {view}")
        assert app.side_view == view

    app._handle_command("/view invalid")

    assert app.side_view == "outputs"
    assert render_calls[-2:] == ["plan", "outputs"]


def test_hao_v4_slash_menu_filters_and_hints_look_local_agent_like(
    tmp_path: Path,
    monkeypatch,
) -> None:
    app = _make_hao_app(tmp_path, monkeypatch)

    menu = app._format_command_menu("perm")
    hint = app._slash_hint_text("/mo")
    output_hint = app._slash_hint_text("/out")

    assert "hao commands" in menu
    assert "/permissions" in menu
    assert "/mode" in menu
    assert "/allowed-tools" in menu
    assert "/model" in hint
    assert "provider/model" in hint
    assert "/output-style" in output_hint
    assert "/chat" not in hint
    assert app._format_transcript_line("user", "hello") == "[bold cyan]›[/bold cyan] hello"
    assert app._format_transcript_line("assistant", "ok") == "[bold green]hao[/bold green] ok"


def test_hao_v42_welcome_card_and_workbench_start_local_agent_like(
    tmp_path: Path,
    monkeypatch,
) -> None:
    app = _make_hao_app(tmp_path, monkeypatch)
    app.session = app.store.create_session(
        cwd=str(tmp_path),
        agent_id="default",
        mode="confirm",
        target="host",
    )

    welcome = app._welcome_card()
    status = app._workbench_status()
    footer = app._footer_status_block()
    header, entries = app._side_panel_entries()

    assert "hao Code" in welcome
    assert "Welcome back!" in welcome
    assert "Tips for getting started" in welcome
    assert "/init" in welcome
    assert "What's new" in welcome
    assert "Single-column terminal UI" in welcome
    assert "/release-notes" in welcome
    assert "strength" in welcome
    assert "compact" in footer
    assert status["model_strength"] in footer
    assert app.workbench_open is False
    assert header == "tools"
    assert entries == []


def test_hao_v42_startup_tip_commands_are_real(
    tmp_path: Path,
    monkeypatch,
) -> None:
    app = _make_hao_app(tmp_path, monkeypatch)
    app.session = app.store.create_session(
        cwd=str(tmp_path),
        agent_id="default",
        mode="confirm",
        target="host",
    )
    chat_logs: list[str] = []
    tool_logs: list[str] = []
    monkeypatch.setattr(app, "_chat", lambda message: chat_logs.append(message))
    monkeypatch.setattr(app, "_tool_log", lambda message: tool_logs.append(message))

    menu = app._format_command_menu("init")
    app._handle_command("/init")
    app._handle_command("/init")
    app._handle_command("/release-notes")

    init_file = tmp_path / "HAO.md"
    assert "/init" in menu
    assert init_file.read_text(encoding="utf-8").startswith("# HAO.md")
    assert tool_logs[0].startswith("[green]created[/green]")
    assert tool_logs[1].startswith("[yellow]exists[/yellow]")
    assert chat_logs[-1].startswith("[bold]hao release notes[/bold]")
    assert "v4.2" in chat_logs[-1]


def test_hao_v42_stream_auth_failure_is_cli_friendly(
    tmp_path: Path,
    monkeypatch,
) -> None:
    app = _make_hao_app(tmp_path, monkeypatch)

    class FakeStatusError(Exception):
        response = SimpleNamespace(status_code=401)

    message = app._format_stream_failure(FakeStatusError("raw httpx 401 text"))

    assert "authentication failed (401)" in message
    assert "hao login" in message
    assert "raw httpx" not in message


def test_hao_v42_terminal_input_decodes_utf8_and_replaces_bad_sequences() -> None:
    assert hao_main._decode_terminal_input(bytes.fromhex("e4bda0e5a5bd0a")) == "\u4f60\u597d"
    assert hao_main._decode_terminal_input(b"hello \xc2\n") == "hello \ufffd"


def test_hao_v42_terminal_tui_records_utf8_input_once_without_user_echo(
    tmp_path: Path,
    monkeypatch,
) -> None:
    import rich.console

    class FakeConsole:
        instances: list[FakeConsole] = []

        def __init__(self) -> None:
            self.printed: list[tuple[str, str]] = []
            FakeConsole.instances.append(self)

        def print(self, *objects: Any, end: str = "\n", **kwargs: Any) -> None:
            del kwargs
            self.printed.append(("".join(str(item) for item in objects), end))

        def clear(self) -> None:
            self.printed.append(("<clear>", "\n"))

    class FakeStdin:
        def __init__(self, raw: bytes) -> None:
            self.buffer = io.BytesIO(raw)

    class FakeApp:
        def __init__(self) -> None:
            self.resume_session_id = None
            self.store = SimpleNamespace(get_session=lambda session_id: None)
            self.messages: list[dict[str, Any]] = []
            self.interaction_mode = "chat"
            self.workbench_open = False
            self.tool_entries: list[str] = []
            self.diff_entries: list[str] = []
            self.approval_entries: list[str] = []
            self.recorded_messages: list[tuple[str, str, dict[str, Any] | None]] = []
            self.turns: list[tuple[str, int, str]] = []
            self.transcript_calls: list[tuple[str, str]] = []

        def _side_panel_entries(self) -> tuple[str, list[str]]:
            return "tools", []

        def _welcome_card(self) -> str:
            return "hao Code"

        def _new_session(self) -> SimpleNamespace:
            return SimpleNamespace(id="session-1")

        def _load_session_state(self, session: SimpleNamespace) -> None:
            self.session = session

        def _format_transcript_line(self, role: str, content: str) -> str:
            self.transcript_calls.append((role, content))
            return f"{role}: {content}"

        def _workflow_metadata(self, interaction_mode: str) -> dict[str, Any]:
            return {"interaction_mode": interaction_mode}

        def _record_message_ui(
            self,
            role: str,
            content: str,
            *,
            metadata: dict[str, Any] | None = None,
        ) -> None:
            self.recorded_messages.append((role, content, metadata))

        def _run_turn_sync(self, goal: str, depth: int, interaction_mode: str) -> None:
            self.turns.append((goal, depth, interaction_mode))

        def _handle_command(self, value: str) -> None:
            raise AssertionError(f"unexpected command: {value}")

    monkeypatch.setattr(rich.console, "Console", FakeConsole)
    monkeypatch.setattr(
        hao_main.sys,
        "stdin",
        FakeStdin(bytes.fromhex("e4bda0e5a5bd0a2f717569740a")),
    )

    app = FakeApp()

    assert hao_main._run_terminal_tui(app) == 0

    assert app.recorded_messages == [
        ("user", "\u4f60\u597d", {"interaction_mode": "chat"})
    ]
    assert app.turns == [("\u4f60\u597d", 0, "chat")]
    assert app.transcript_calls == []
    prompt_prints = [
        item for item in FakeConsole.instances[0].printed if item[1] == ""
    ]
    assert prompt_prints == [
        ("[bold #d97757]›[/bold #d97757] ", ""),
        ("[bold #d97757]›[/bold #d97757] ", ""),
    ]


def test_hao_v4_streaming_assistant_block_starts_once_and_appends_content(
    tmp_path: Path,
    monkeypatch,
) -> None:
    app = _make_hao_app(tmp_path, monkeypatch)
    app.session = app.store.create_session(
        cwd=str(tmp_path),
        agent_id="default",
        mode="confirm",
        target="host",
    )
    begin_calls: list[str] = []
    append_calls: list[str] = []
    monkeypatch.setattr(app, "_stream_assistant_begin", lambda: begin_calls.append("begin"))
    monkeypatch.setattr(
        app,
        "_stream_assistant_append",
        lambda content: append_calls.append(content),
    )

    class FakeClient:
        def stream_chat(self, agent_id: str, payload: dict):
            del agent_id, payload
            yield SSEEvent(
                event="run_created",
                data={"run_id": "run-1"},
                raw='event: run_created\ndata: {"run_id": "run-1"}',
            )
            yield SSEEvent(
                event="delta",
                data={"content": "你好"},
                raw='event: delta\ndata: {"content": "你好"}',
            )
            yield SSEEvent(
                event="delta",
                data={"content": "！有什么我可以帮你的？"},
                raw='event: delta\ndata: {"content": "！有什么我可以帮你的？"}',
            )
            yield SSEEvent(event="done", data={}, raw="event: done\ndata: {}")

    app.api_client = FakeClient()  # type: ignore[assignment]

    app._run_turn_sync("你好", 0, "chat")

    assert begin_calls == ["begin"]
    assert append_calls == ["你好", "！有什么我可以帮你的？"]


def test_hao_v4_alias_commands_route_to_model_permissions_usage_and_context(
    tmp_path: Path,
    monkeypatch,
) -> None:
    app = _make_hao_app(tmp_path, monkeypatch)
    app.session = app.store.create_session(
        cwd=str(tmp_path),
        agent_id="default",
        mode="confirm",
        target="host",
    )
    chat_logs: list[str] = []
    tool_logs: list[str] = []
    render_calls: list[str] = []
    monkeypatch.setattr(app, "_chat", lambda message: chat_logs.append(message))
    monkeypatch.setattr(app, "_tool_log", lambda message: tool_logs.append(message))
    monkeypatch.setattr(app, "_render_side_panel", lambda: render_calls.append(app.side_view))

    app._handle_command("/permissions full-auto")
    app._handle_command("/mode auto-edit")
    app._handle_command("/allowed-tools")
    app._handle_command("/model vendor/message-model")
    app._handle_command("/model openai gpt-5.5")
    app._handle_command("/output-style concise")
    app._handle_command("/diff")
    app._handle_command("/tasks")
    app._handle_command("/bashes")
    app._handle_command("/usage")
    app._handle_command("/cost")
    app._handle_command("/settings")
    app._handle_command("/context")

    loaded = app.store.get_session(app.session.id)
    assert loaded is not None
    assert loaded.mode == "auto-edit"
    assert app.permission_mode == "auto-edit"
    assert app.model_provider == "openai"
    assert app.model_name == "gpt-5.5"
    assert app.output_style == "concise"
    assert app.side_view == "commands"
    assert render_calls[-1] == "commands"
    assert any("usage" in message for message in chat_logs)
    assert any("hao config" in message for message in chat_logs)
    assert any("output_style=concise" in message for message in chat_logs)
    assert any("hao local context:" in message for message in chat_logs)
    assert not tool_logs


def test_hao_v4_compact_replaces_older_context_in_next_payload(
    tmp_path: Path,
    monkeypatch,
) -> None:
    app = _make_hao_app(tmp_path, monkeypatch)
    app.session = app.store.create_session(
        cwd=str(tmp_path),
        agent_id="default",
        mode="confirm",
        target="host",
    )
    for index in range(10):
        role = "user" if index % 2 == 0 else "assistant"
        app.store.append_message(app.session.id, role=role, content=f"turn-{index}")
    app.messages = app.store.list_active_path(app.session.id)
    chat_logs: list[str] = []
    monkeypatch.setattr(app, "_chat", lambda message: chat_logs.append(message))

    app._handle_command("/compact preserve decisions")
    payload = app._build_stream_payload("continue", "chat")

    assert any("summarized 4 messages" in message for message in chat_logs)
    assert app._compact_summary is not None
    assert payload["messages"][0]["content"].startswith("hao local context:")
    assert payload["messages"][0]["id"] == "hao-local-context"
    assert "compact=on" in payload["messages"][0]["content"]
    assert payload["messages"][1]["metadata"]["source"] == "hao_compact_context"
    assert payload["messages"][1]["id"] == "hao-compact-context"
    assert "summarized_messages=4" in payload["messages"][1]["content"]
    assert "user_compact_instructions=preserve decisions" in payload["messages"][1]["content"]
    parsed = AgentChatStreamRequest(**payload)
    assert [message.id for message in parsed.messages[:2]] == [
        "hao-local-context",
        "hao-compact-context",
    ]
    assert [message["content"] for message in payload["messages"][2:]] == [
        "turn-4",
        "turn-5",
        "turn-6",
        "turn-7",
        "turn-8",
        "turn-9",
    ]


def test_hao_compress_alias_updates_compact_state_and_status_text(
    tmp_path: Path,
    monkeypatch,
) -> None:
    app = _make_hao_app(tmp_path, monkeypatch)
    app.session = app.store.create_session(
        cwd=str(tmp_path),
        agent_id="default",
        mode="confirm",
        target="host",
    )
    for index in range(8):
        role = "user" if index % 2 == 0 else "assistant"
        app.store.append_message(app.session.id, role=role, content=f"turn-{index}")
    app.messages = app.store.list_active_path(app.session.id)
    chat_logs: list[str] = []
    monkeypatch.setattr(app, "_chat", lambda message: chat_logs.append(message))

    app._handle_command("/compress preserve older turns")

    status = app._workbench_status()
    status_text = app._status_text(status)

    assert app._compact_summary is not None
    assert app._compact_keep_from_index == 2
    assert status["compact_active"] is True
    assert status["compact_ring"] != "○"
    assert status["compact_percent"] > 0
    assert any("summarized 2 messages" in message for message in chat_logs)
    assert "compact_ring=" in status_text
    assert "strength=" in status_text


def test_hao_v4_resume_command_switches_session_and_reloads_active_path(
    tmp_path: Path,
    monkeypatch,
) -> None:
    app = _make_hao_app(tmp_path, monkeypatch)
    first = app.store.create_session(
        cwd=str(tmp_path),
        agent_id="default",
        mode="confirm",
        cli_mode="chat",
        target="host",
    )
    second = app.store.create_session(
        cwd=str(tmp_path / "other"),
        agent_id="research",
        mode="auto-edit",
        cli_mode="plan",
        target="sandbox",
    )
    app.store.append_message(first.id, role="user", content="first")
    app.store.append_message(first.id, role="assistant", content="first reply")
    app.store.append_message(second.id, role="user", content="second")
    second_leaf = app.store.append_message(second.id, role="assistant", content="second reply")
    app.messages = app.store.list_active_path(first.id)
    app.session = first
    chat_logs: list[str] = []
    monkeypatch.setattr(app, "_chat", lambda message: chat_logs.append(message))
    monkeypatch.setattr(app, "_render_side_panel", lambda: None)

    app._handle_command(f"/resume {second.id}")

    assert app.session is not None
    assert app.session.id == second.id
    assert app.agent_id == "research"
    assert app.permission_mode == "auto-edit"
    assert app.interaction_mode == "plan"
    assert app.target == "sandbox"
    assert app.cwd == (tmp_path / "other").resolve()
    assert app.messages[-1]["id"] == second_leaf["id"]
    assert any("resumed" in message for message in chat_logs)


def test_hao_workflow_and_sessions_commands_persist_and_render(
    tmp_path: Path,
    monkeypatch,
) -> None:
    app = _make_hao_app(tmp_path, monkeypatch)
    app.session = app.store.create_session(
        cwd=str(tmp_path),
        agent_id="default",
        mode="confirm",
        target="host",
    )
    chat_logs: list[str] = []
    monkeypatch.setattr(app, "_chat", lambda message: chat_logs.append(message))

    for mode in ("plan", "act", "chat"):
        app._handle_command(f"/{mode}")
        loaded = app.store.get_session(app.session.id)
        assert loaded is not None
        assert app.interaction_mode == mode
        assert loaded.cli_mode == mode
        assert chat_logs[-1] == app._format_transcript_line("system", f"workflow {mode}")

    app._handle_command("/sessions")

    assert any(app.session.id in message for message in chat_logs)
    assert any("workflow=chat" in message for message in chat_logs)


def test_hao_plan_mode_assistant_content_enters_plan_view_only(
    tmp_path: Path,
    monkeypatch,
) -> None:
    class FakeClient:
        def stream_chat(self, agent_id: str, payload: dict):
            interaction_mode = str(payload.get("interaction_mode") or "")
            content = {
                "plan": "1. inspect\n",
                "chat": "chat response\n",
                "act": "act response\n",
            }.get(interaction_mode, "response\n")
            yield SSEEvent(
                event="run_created",
                data={"run_id": "run-1"},
                raw='event: run_created\ndata: {"run_id": "run-1"}',
            )
            yield SSEEvent(
                event="delta",
                data={"content": content},
                raw=f'event: delta\ndata: {{"content": {json.dumps(content)}}}',
            )
            yield SSEEvent(event="done", data={}, raw="event: done\ndata: {}")

    app = _make_hao_app(tmp_path, monkeypatch)
    app.session = app.store.create_session(
        cwd=str(tmp_path),
        agent_id="default",
        mode="confirm",
        cli_mode="plan",
        target="host",
    )
    app.api_client = FakeClient()  # type: ignore[assignment]

    app._run_turn_sync("draft a plan", 0, "plan")

    assert app.plan_entries[-1] == "1. inspect"
    assert app.messages[-1]["metadata"]["interaction_mode"] == "plan"

    app._run_turn_sync("normal chat", 0, "chat")
    app._run_turn_sync("normal act", 0, "act")

    assert app.plan_entries == ["1. inspect"]


def test_hao_outputs_view_uses_persisted_tool_output_summaries(
    tmp_path: Path,
    monkeypatch,
) -> None:
    app = _make_hao_app(tmp_path, monkeypatch)
    app.session = app.store.create_session(
        cwd=str(tmp_path),
        agent_id="default",
        mode="confirm",
        target="host",
    )
    app.store.record_tool_event(
        app.session.id,
        run_id="run-1",
        tool_call_id="tool-1",
        tool_name="run_shell",
        status="SUCCESS",
        input_json={"command": "pytest"},
        output_json={
            "command": "pytest",
            "exit_code": 0,
            "stdout": "ok\n",
            "stderr": "",
            "stdout_truncated": False,
            "stderr_truncated": False,
        },
        duration_ms=10,
    )
    command = app.store.create_command(
        app.session.id,
        tool_name="run_shell",
        command="printf ok",
        command_json={"command": "printf ok"},
        timeout_seconds=30,
    )
    app.store.start_command(command["id"])
    app.store.finish_command(
        command["id"],
        status="success",
        exit_code=0,
        stdout_truncated=False,
        stderr_truncated=False,
    )

    entries = app._output_entries()

    assert "> run_shell SUCCESS\nexit=0\n$ pytest\nstdout: ok" in entries
    assert "> run_shell success\nexit=0\n$ printf ok" in entries
    output_artifacts = list((app.store.session_dir(app.session.id) / "outputs").glob("*.json"))
    assert output_artifacts
    artifact = json.loads(output_artifacts[0].read_text(encoding="utf-8"))
    assert artifact["tool_name"] == "run_shell"
    assert artifact["output_json"]["stdout"] == "ok\n"


@pytest.mark.parametrize("interaction_mode", ["chat", "plan", "act"])
def test_hao_continue_command_resumes_active_path_without_user_message(
    tmp_path: Path,
    monkeypatch,
    interaction_mode: str,
) -> None:
    app = _make_hao_app(tmp_path, monkeypatch)
    app.session = app.store.create_session(
        cwd=str(tmp_path),
        agent_id="default",
        mode="confirm",
        cli_mode=interaction_mode,
        target="host",
    )
    app.interaction_mode = interaction_mode
    app.messages = [app.store.append_message(app.session.id, role="user", content="start")]
    run_calls: list[tuple[str, bool, int, str]] = []
    monkeypatch.setattr(
        app,
        "run_turn_worker",
        lambda goal, append_user, depth, mode: run_calls.append(
            (goal, append_user, depth, mode)
        ),
    )

    app._handle_command("/continue")

    assert [message["role"] for message in app.messages] == ["user"]
    assert run_calls == [
        ("Continue from the active path.", False, 0, interaction_mode)
    ]


def test_hao_continue_after_branch_switch_sends_only_active_path_messages(
    tmp_path: Path,
    monkeypatch,
) -> None:
    app = _make_hao_app(tmp_path, monkeypatch)
    app.session = app.store.create_session(
        cwd=str(tmp_path),
        agent_id="default",
        mode="confirm",
        cli_mode="act",
        target="host",
    )
    app.interaction_mode = "act"
    root = app.store.append_message(app.session.id, role="user", content="start")
    assistant = app.store.append_message(app.session.id, role="assistant", content="ok")
    old_leaf = app.store.append_message(app.session.id, role="user", content="old")
    new_leaf = app.store.append_message(
        app.session.id,
        role="user",
        content="new",
        parent_id=assistant["id"],
        source_message_id=old_leaf["id"],
    )
    app.messages = app.store.list_active_path(app.session.id)
    assert app.messages[-1]["id"] == new_leaf["id"]
    payloads: list[dict] = []
    monkeypatch.setattr(
        app,
        "run_turn_worker",
        lambda goal, append_user, depth, mode: payloads.append(
            app._build_stream_payload(goal, mode)
        ),
    )

    app._handle_command(f"/branch {old_leaf['id']}")
    app._handle_command("/continue")

    messages = payloads[-1]["messages"]
    assert messages[0]["role"] == "system"
    assert messages[0]["metadata"]["source"] == "hao_local_context"
    assert [message["id"] for message in messages[1:]] == [
        root["id"],
        assistant["id"],
        old_leaf["id"],
    ]


def test_hao_branch_command_switches_to_existing_leaf_and_reloads_active_path(
    tmp_path: Path,
    monkeypatch,
) -> None:
    app = _make_hao_app(tmp_path, monkeypatch)
    app.session = app.store.create_session(
        cwd=str(tmp_path),
        agent_id="default",
        mode="confirm",
        target="host",
    )
    root = app.store.append_message(app.session.id, role="user", content="start")
    assistant = app.store.append_message(app.session.id, role="assistant", content="ok")
    old_leaf = app.store.append_message(app.session.id, role="user", content="old")
    new_leaf = app.store.append_message(
        app.session.id,
        role="user",
        content="new",
        parent_id=assistant["id"],
        source_message_id=old_leaf["id"],
    )
    app.messages = app.store.list_active_path(app.session.id)
    assert app.messages[-1]["id"] == new_leaf["id"]
    message_count = len(app.store.list_messages(app.session.id))

    app._handle_command(f"/branch {old_leaf['id']}")

    loaded = app.store.get_session(app.session.id)
    assert loaded is not None
    assert loaded.active_leaf_id == old_leaf["id"]
    assert len(app.store.list_messages(app.session.id)) == message_count
    assert [message["id"] for message in app.messages] == [
        root["id"],
        assistant["id"],
        old_leaf["id"],
    ]


def test_hao_branch_command_rejects_unknown_leaf_without_mutating_active_path(
    tmp_path: Path,
    monkeypatch,
) -> None:
    app = _make_hao_app(tmp_path, monkeypatch)
    app.session = app.store.create_session(
        cwd=str(tmp_path),
        agent_id="default",
        mode="confirm",
        target="host",
    )
    root = app.store.append_message(app.session.id, role="user", content="start")
    app.messages = app.store.list_active_path(app.session.id)
    tool_logs: list[str] = []
    monkeypatch.setattr(app, "_tool_log", lambda message: tool_logs.append(message))

    app._handle_command("/branch missing-message")

    loaded = app.store.get_session(app.session.id)
    assert loaded is not None
    assert loaded.active_leaf_id == root["id"]
    assert [message["id"] for message in app.messages] == [root["id"]]
    assert tool_logs == ["[red]unknown branch leaf[/red] missing-message"]


def test_hao_v3_store_contract_persists_branch_scoped_todos_and_verifications(
    tmp_path: Path,
) -> None:
    store = SessionStore(tmp_path / "hao.db", tmp_path / "sessions")
    session = store.create_session(
        cwd=str(tmp_path),
        agent_id="default",
        mode="confirm",
        target="host",
    )
    root = store.append_message(session.id, role="user", content="implement v3")
    assistant = store.append_message(session.id, role="assistant", content="plan")
    old_leaf = store.append_message(session.id, role="user", content="old branch")
    active_leaf = store.append_message(
        session.id,
        role="user",
        content="active branch",
        parent_id=assistant["id"],
        source_message_id=old_leaf["id"],
    )
    command = store.create_command(
        session.id,
        tool_name="run_tests",
        command="pytest tests/test_hao_cli_v2.py -q",
        command_json={"command": "pytest tests/test_hao_cli_v2.py -q"},
        timeout_seconds=120,
    )
    store.start_command(command["id"])
    finished = store.finish_command(
        command["id"],
        status="success",
        exit_code=0,
        stdout_truncated=False,
        stderr_truncated=False,
    )
    tool_event_id = store.record_tool_event(
        session.id,
        run_id="run-1",
        tool_call_id="tool-test",
        tool_name="run_tests",
        status="SUCCESS",
        input_json={"command": finished["command"]},
        output_json={"command_id": command["id"], "exit_code": 0, "stdout": "ok"},
        duration_ms=3,
    )

    todo = store.create_todo(
        session.id,
        title="Lock v3 workflow contract",
        source="model",
        branch_id=active_leaf["branch_id"],
        leaf_id=active_leaf["id"],
        status="in_progress",
        message_id=root["id"],
    )
    verification = store.create_verification(
        session.id,
        label="targeted hao CLI regression",
        status="passed",
        branch_id=active_leaf["branch_id"],
        leaf_id=active_leaf["id"],
        command_id=command["id"],
        tool_event_id=tool_event_id,
        evidence_summary="pytest tests/test_hao_cli_v2.py -q -> passed",
    )
    store.update_todo(
        todo["id"],
        status="done",
        command_id=command["id"],
        tool_event_id=tool_event_id,
        verification_id=verification["id"],
    )

    reopened = SessionStore(tmp_path / "hao.db", tmp_path / "sessions")
    todos = reopened.list_todos(session.id, branch_id=active_leaf["branch_id"])
    verifications = reopened.list_verifications(
        session.id,
        branch_id=active_leaf["branch_id"],
    )
    sibling_todos = reopened.list_todos(session.id, branch_id=old_leaf["branch_id"])
    sibling_verifications = reopened.list_verifications(
        session.id,
        branch_id=old_leaf["branch_id"],
    )

    assert todos == [
        {
            **todo,
            "status": "done",
            "command_id": command["id"],
            "tool_event_id": tool_event_id,
            "verification_id": verification["id"],
            "updated_at": todos[0]["updated_at"],
        }
    ]
    assert todos[0]["updated_at"] >= todo["updated_at"]
    assert verifications == [verification]
    assert verifications[0]["created_at"]
    assert verifications[0]["updated_at"]
    assert sibling_todos == []
    assert sibling_verifications == []


def test_hao_v3_headless_argv_contract_dispatches_user_visible_commands(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    calls: list[dict[str, Any]] = []

    def fake_run_headless(args) -> int:
        calls.append(
            {
                "command": args.command,
                "prompt": args.prompt,
                "cwd": args.cwd,
                "mode": args.mode,
                "target": args.target,
                "max_auto_turns": args.max_auto_turns,
                "resume_session_id": args.resume_session_id,
            }
        )
        print(f"hao {args.command}: completed")
        return 0

    monkeypatch.setattr(hao_main, "_run_headless", fake_run_headless, raising=False)

    for command in ("chat", "plan", "act"):
        result = hao_main.main(
            [
                "--cwd",
                str(tmp_path),
                "--mode",
                "confirm",
                "--target",
                "host",
                "--max-auto-turns",
                "5",
                command,
                "finish the local task",
            ]
        )
        assert result == 0

    output = capsys.readouterr().out
    assert [call["command"] for call in calls] == ["chat", "plan", "act"]
    assert all(call["prompt"] == "finish the local task" for call in calls)
    assert all(call["cwd"] == str(tmp_path) for call in calls)
    assert all(call["mode"] == "confirm" for call in calls)
    assert all(call["target"] == "host" for call in calls)
    assert all(call["max_auto_turns"] == 5 for call in calls)
    assert "hao chat: completed" in output
    assert "hao plan: completed" in output
    assert "hao act: completed" in output


def test_hao_v3_headless_argv_contract_passes_defaults_and_resume(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    calls: list[dict[str, Any]] = []

    def fake_run_headless(args) -> int:
        calls.append(
            {
                "command": args.command,
                "prompt": args.prompt,
                "cwd": args.cwd,
                "mode": args.mode,
                "target": args.target,
                "max_auto_turns": args.max_auto_turns,
                "resume_session_id": args.resume_session_id,
            }
        )
        print(
            json.dumps(
                {
                    "status": "pending_approval",
                    "change_id": "change-1",
                    "session_id": args.resume_session_id,
                },
                sort_keys=True,
            )
        )
        return 2

    monkeypatch.setattr(hao_main, "_run_headless", fake_run_headless, raising=False)

    result = hao_main.main(
        [
            "--cwd",
            str(tmp_path),
            "act",
            "--resume",
            "session-1",
            "write safely",
        ]
    )

    output = capsys.readouterr().out
    assert result == 2
    assert calls == [
        {
            "command": "act",
            "prompt": "write safely",
            "cwd": str(tmp_path),
            "mode": "confirm",
            "target": "host",
            "max_auto_turns": 3,
            "resume_session_id": "session-1",
        }
    ]
    assert '"status": "pending_approval"' in output
    assert '"change_id": "change-1"' in output
    assert '"session_id": "session-1"' in output


def test_hao_v3_headless_argv_rejects_invalid_max_auto_turns(capsys) -> None:
    parser = hao_main.build_parser()
    assert "--max-auto-turns" in parser.format_help()

    with pytest.raises(SystemExit) as exc_info:
        parser.parse_args(["--max-auto-turns", "0", "act", "do work"])

    stderr = capsys.readouterr().err
    assert exc_info.value.code != 0
    assert "--max-auto-turns" in stderr
    assert "positive" in stderr or ">= 1" in stderr


def test_hao_version_flag_prints_package_version(capsys) -> None:
    parser = hao_main.build_parser()
    help_text = parser.format_help()
    assert "-V" in help_text
    assert "-v" in help_text
    assert "--version" in help_text
    assert "login" in help_text
    assert "logout" in help_text
    assert "status" in help_text
    assert "version" in help_text

    with pytest.raises(SystemExit) as exc_info:
        parser.parse_args(["--version"])

    stdout = capsys.readouterr().out
    assert exc_info.value.code == 0
    assert stdout == f"hao {hao_main._hao_version()}\n"


@pytest.mark.parametrize("argv", [["-V"], ["-v"]])
def test_hao_version_short_flags_print_package_version(argv, capsys) -> None:
    parser = hao_main.build_parser()

    with pytest.raises(SystemExit) as exc_info:
        parser.parse_args(argv)

    stdout = capsys.readouterr().out
    assert exc_info.value.code == 0
    assert stdout == f"hao {hao_main._hao_version()}\n"


def test_hao_version_subcommand_prints_package_version(capsys) -> None:
    result = hao_main.main(["version"])

    stdout = capsys.readouterr().out
    assert result == 0
    assert stdout == f"hao {hao_main._hao_version()}\n"


def test_hao_login_status_and_logout_aliases(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.setenv("HAO_HOME", str(tmp_path))

    login_result = hao_main.main(
        [
            "login",
            "--api-url",
            "http://stored.example",
            "--token",
            "stored-token",
        ]
    )
    login_output = capsys.readouterr().out
    assert login_result == 0
    assert "saved auth config" in login_output

    status_result = hao_main.main(["status"])
    status_output = capsys.readouterr().out
    assert status_result == 0
    assert "api_url=http://stored.example" in status_output
    assert "token=set" in status_output

    logout_result = hao_main.main(["logout"])
    logout_output = capsys.readouterr().out
    assert logout_result == 0
    assert "cleared persisted token" in logout_output

    persisted = load_persisted_config({"HAO_HOME": str(tmp_path)})
    assert persisted.api_url == "http://stored.example"
    assert persisted.token == ""


@pytest.mark.parametrize("command", ["chat", "plan", "act"])
def test_hao_headless_commands_accept_shared_flags_after_subcommand(
    command: str,
    tmp_path: Path,
    monkeypatch,
) -> None:
    calls: list[dict[str, Any]] = []

    def fake_run_headless(args) -> int:
        calls.append(
            {
                "command": args.command,
                "cwd": args.cwd,
                "mode": args.mode,
                "target": args.target,
                "prompt": args.prompt,
            }
        )
        return 0

    monkeypatch.setattr(hao_main, "_run_headless", fake_run_headless, raising=False)

    result = hao_main.main(
        [
            command,
            "--cwd",
            str(tmp_path),
            "--mode",
            "full-auto",
            "--target",
            "host",
            "draft",
            "a",
            "plan",
        ]
    )

    assert result == 0
    assert calls == [
        {
            "command": command,
            "cwd": str(tmp_path),
            "mode": "full-auto",
            "target": "host",
            "prompt": "draft a plan",
        }
    ]


def test_hao_v3_tui_receives_default_and_overridden_max_auto_turns(
    tmp_path: Path,
    monkeypatch,
) -> None:
    created_apps: list[dict[str, Any]] = []
    terminal_runs: list[dict[str, Any]] = []

    class FakeHaoApp:
        def __init__(self, **kwargs) -> None:
            created_apps.append(kwargs)

    def fake_run_terminal_tui(app) -> int:
        terminal_runs.append(app.__dict__)
        return 0

    monkeypatch.setattr("app.cli.hao.tui.HaoApp", FakeHaoApp)
    monkeypatch.setattr(hao_main, "_run_terminal_tui", fake_run_terminal_tui)

    assert hao_main.main(["--cwd", str(tmp_path)]) == 0
    assert hao_main.main(["--cwd", str(tmp_path), "--max-auto-turns", "7"]) == 0

    assert created_apps[0]["max_auto_turns"] == 3
    assert created_apps[1]["max_auto_turns"] == 7
    assert len(terminal_runs) == 2


def test_hao_v3_headless_missing_resume_fails_without_new_session(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    monkeypatch.setenv("HAO_HOME", str(tmp_path / "hao-home"))

    class FailClient:
        def __init__(self, api_url: str, token: str) -> None:
            del api_url, token

        def stream_chat(self, agent_id: str, payload: dict):
            del agent_id, payload
            raise AssertionError("missing resume must fail before streaming")

    monkeypatch.setattr(hao_main, "HarnessApiClient", FailClient)

    result = hao_main.main(
        ["--cwd", str(tmp_path), "act", "--resume", "missing-session", "do work"]
    )

    captured = capsys.readouterr()
    error = json.loads(captured.err)
    config = hao_main.load_config()
    store = SessionStore(config.session_db_path, config.sessions_dir)
    assert result == 1
    assert captured.out == ""
    assert error["status"] == "failed"
    assert error["resume_session_id"] == "missing-session"
    assert "session not found" in error["error"]
    assert store.list_sessions() == []


def test_hao_v3_local_context_is_ephemeral_and_carries_loop_state(
    tmp_path: Path,
    monkeypatch,
) -> None:
    app = _make_hao_app(tmp_path, monkeypatch, permission_mode="confirm", target="host")
    app.session = app.store.create_session(
        cwd=str(tmp_path),
        agent_id="default",
        mode="confirm",
        cli_mode="act",
        target="host",
    )
    user = app.store.append_message(app.session.id, role="user", content="start")
    app.messages = app.store.list_active_path(app.session.id)
    app.pending_tools["tool-shell"] = object()  # type: ignore[assignment]
    command = app.store.create_command(
        app.session.id,
        tool_name="run_tests",
        command="pytest",
        command_json={"command": "pytest"},
        timeout_seconds=120,
    )
    app.store.start_command(command["id"])
    todo = app.store.create_todo(
        app.session.id,
        title="Run targeted tests",
        source="user",
        branch_id=user["branch_id"],
        leaf_id=user["id"],
        status="in_progress",
    )
    verification = app.store.create_verification(
        app.session.id,
        label="pytest",
        status="pending",
        branch_id=user["branch_id"],
        leaf_id=user["id"],
        evidence_summary="waiting for command",
    )

    payload = app._build_stream_payload("continue", "act")
    messages = payload["messages"]
    persisted = app.store.list_messages(app.session.id)

    assert messages[0]["role"] == "system"
    assert messages[0]["metadata"]["source"] == "hao_local_context"
    assert "cwd=" in messages[0]["content"]
    assert "target=host" in messages[0]["content"]
    assert "permission=confirm" in messages[0]["content"]
    assert "workflow=act" in messages[0]["content"]
    assert f"session={app.session.id}" in messages[0]["content"]
    assert f"branch={user['branch_id']}" in messages[0]["content"]
    assert "approvals=1" in messages[0]["content"]
    assert "commands=1/1" in messages[0]["content"]
    assert "max_auto_turns=3" in messages[0]["content"]
    assert todo["title"] in messages[0]["content"]
    assert verification["label"] in messages[0]["content"]
    assert [message["id"] for message in messages[1:]] == [message["id"] for message in persisted]
    assert all(message["role"] != "system" for message in persisted)


def test_hao_v3_headless_local_context_counts_pending_changes(
    tmp_path: Path,
) -> None:
    store = SessionStore(tmp_path / "hao.db", tmp_path / "sessions")
    session = store.create_session(
        cwd=str(tmp_path),
        agent_id="default",
        mode="confirm",
        cli_mode="act",
        target="host",
    )
    store.append_message(session.id, role="user", content="start")
    execute_local_tool(
        "preview_write_file",
        {"path": "notes.md", "content": "new\n"},
        tmp_path,
        session_store=store,
        session_id=session.id,
    )

    context = hao_main._local_context_message(
        store=store,
        session_id=session.id,
        cwd=tmp_path,
        permission_mode="confirm",
        target="host",
        interaction_mode="act",
        max_auto_turns=3,
    )

    assert "approvals=1" in context["content"]


def test_hao_v3_search_files_prefers_rg_and_uses_fallback_safe_glob(
    tmp_path: Path,
    monkeypatch,
) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.py").write_text("print('hello world')\n", encoding="utf-8")

    monkeypatch.setattr(
        hao_local_tools.shutil,
        "which",
        lambda name: "/usr/bin/rg" if name == "rg" else None,
    )
    seen_commands: list[list[str]] = []

    def fake_run(command, **kwargs):  # type: ignore[no-untyped-def]
        del kwargs
        seen_commands.append(command)
        return SimpleNamespace(
            returncode=0,
            stdout=(
                '{"type":"match","data":{"path":{"text":"src/app.py"},'
                '"lines":{"text":"print(\'hello world\')\\n"},"line_number":1}}\n'
            ),
        )

    monkeypatch.setattr(hao_local_tools.subprocess, "run", fake_run)

    result = hao_local_tools.execute_local_tool(
        "search_files",
        {"query": "world", "limit": 5},
        tmp_path,
    )

    assert result.output_json["engine"] == "rg"
    assert seen_commands and seen_commands[0][0] == "/usr/bin/rg"
    assert "--json" in seen_commands[0]
    assert result.output_json["matches"] == [
        {"path": "src/app.py", "line": 1, "text": "print('hello world')"}
    ]


def test_hao_v3_search_files_python_fallback_prunes_ignored_and_binary_dirs(
    tmp_path: Path,
    monkeypatch,
) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "one.txt").write_text("needle one\n", encoding="utf-8")
    (tmp_path / "src" / "two.txt").write_text("needle two\n", encoding="utf-8")
    (tmp_path / "src" / "three.txt").write_text("needle three\n", encoding="utf-8")
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "ignored.txt").write_text("needle ignored\n", encoding="utf-8")
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "hidden.txt").write_text("needle hidden\n", encoding="utf-8")
    (tmp_path / "src" / "binary.bin").write_bytes(b"\x00needle\n")

    monkeypatch.setattr(hao_local_tools.shutil, "which", lambda name: None)

    result = hao_local_tools.execute_local_tool(
        "search_files",
        {"query": "needle", "limit": 2},
        tmp_path,
    )

    assert result.output_json["engine"] == "python"
    assert [match["path"] for match in result.output_json["matches"]] == [
        "src/one.txt",
        "src/three.txt",
    ]
    assert result.output_json["truncated"] is True


def test_hao_v3_search_files_rg_path_excludes_oversized_files(
    tmp_path: Path,
    monkeypatch,
) -> None:
    large = tmp_path / "large.txt"
    large.write_text("needle\n" * 200_000, encoding="utf-8")
    monkeypatch.setattr(
        hao_local_tools.shutil,
        "which",
        lambda name: "/usr/bin/rg" if name == "rg" else None,
    )
    seen_commands: list[list[str]] = []

    def fake_run(command, **kwargs):  # type: ignore[no-untyped-def]
        del kwargs
        seen_commands.append(command)
        if "--max-filesize" not in command:
            return SimpleNamespace(
                returncode=0,
                stdout=(
                    '{"type":"match","data":{"path":{"text":"large.txt"},'
                    '"lines":{"text":"needle\\n"},"line_number":1}}\n'
                ),
            )
        return SimpleNamespace(returncode=1, stdout="")

    monkeypatch.setattr(hao_local_tools.subprocess, "run", fake_run)

    result = hao_local_tools.execute_local_tool(
        "search_files",
        {"query": "needle"},
        tmp_path,
    )

    assert result.output_json["engine"] == "rg"
    assert result.output_json["matches"] == []
    assert "--max-filesize" in seen_commands[0]
    size_index = seen_commands[0].index("--max-filesize") + 1
    assert seen_commands[0][size_index] == str(hao_local_tools.MAX_SEARCH_FILE_BYTES)


def test_hao_v3_tui_commands_manage_todos_verifications_max_turns_and_status(
    tmp_path: Path,
    monkeypatch,
) -> None:
    app = _make_hao_app(tmp_path, monkeypatch, permission_mode="confirm", target="host")
    app.session = app.store.create_session(
        cwd=str(tmp_path),
        agent_id="default",
        mode="confirm",
        cli_mode="act",
        target="host",
    )
    app.store.append_message(app.session.id, role="user", content="start")
    assistant = app.store.append_message(app.session.id, role="assistant", content="ok")
    old_leaf = app.store.append_message(app.session.id, role="user", content="old branch")
    active_leaf = app.store.append_message(
        app.session.id,
        role="user",
        content="active branch",
        parent_id=assistant["id"],
        source_message_id=old_leaf["id"],
    )
    app.messages = app.store.list_active_path(app.session.id)
    tool_logs: list[str] = []
    chat_logs: list[str] = []
    monkeypatch.setattr(app, "_tool_log", lambda message: tool_logs.append(message))
    monkeypatch.setattr(app, "_chat", lambda message: chat_logs.append(message))

    app._handle_command("/todo add Run targeted tests")
    todo = app.store.list_todos(app.session.id, branch_id=active_leaf["branch_id"])[0]
    app._handle_command(f"/todo done {todo['id']}")
    app._handle_command(f"/todo fail {todo['id']}")
    app._handle_command("/verify pass pytest")
    app._handle_command("/verify fail lint")
    app._handle_command("/max-turns nope")
    app._handle_command("/max-turns 0")
    app._handle_command("/max-turns 6")
    app._handle_command("/status")
    app._handle_command(f"/branch {old_leaf['id']}")

    reopened = SessionStore(app.store.db_path, app.store.sessions_dir)
    active_todos = reopened.list_todos(app.session.id, branch_id=active_leaf["branch_id"])
    active_verifications = reopened.list_verifications(
        app.session.id,
        branch_id=active_leaf["branch_id"],
    )
    sibling_todos = reopened.list_todos(app.session.id, branch_id=old_leaf["branch_id"])
    sibling_verifications = reopened.list_verifications(
        app.session.id,
        branch_id=old_leaf["branch_id"],
    )

    assert active_todos[0]["title"] == "Run targeted tests"
    assert active_todos[0]["status"] == "failed"
    assert [verification["status"] for verification in active_verifications] == [
        "passed",
        "failed",
    ]
    assert [verification["label"] for verification in active_verifications] == [
        "pytest",
        "lint",
    ]
    assert sibling_todos == []
    assert sibling_verifications == []
    assert app.max_auto_turns == 6
    assert any("invalid max turns" in message for message in tool_logs)
    assert any("max turns must be >= 1" in message for message in tool_logs)
    assert chat_logs[-1]
    assert f"session={app.session.id}" in chat_logs[-1]
    assert "max_turns=6" in chat_logs[-1]
    assert app.store.get_session(app.session.id).active_leaf_id == old_leaf["id"]  # type: ignore[union-attr]


def test_hao_v3_local_context_and_file_tree_surface_repo_and_test_hints(
    tmp_path: Path,
    monkeypatch,
) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "example.txt").write_text("example\n", encoding="utf-8")
    app = _make_hao_app(tmp_path, monkeypatch, permission_mode="confirm", target="host")
    app.session = app.store.create_session(
        cwd=str(tmp_path),
        agent_id="default",
        mode="confirm",
        cli_mode="act",
        target="host",
    )
    root = app.store.append_message(app.session.id, role="user", content="start")
    app.messages = app.store.list_active_path(app.session.id)
    command = app.store.create_command(
        app.session.id,
        tool_name="run_tests",
        command="pytest tests/test_hao_cli.py",
        command_json={"command": "pytest tests/test_hao_cli.py"},
        timeout_seconds=120,
    )
    app.store.start_command(command["id"])
    app.store.finish_command(
        command["id"],
        status="success",
        exit_code=0,
        stdout_truncated=False,
        stderr_truncated=False,
    )
    monkeypatch.setattr(
        app,
        "_git_output",
        lambda args: (
            "main"
            if args == ["branch", "--show-current"]
            else " M src/example.txt\n?? scratch.txt"
        ),
    )

    context = app._local_context_message("act")
    file_entries = app._file_tree_entries()

    assert f"branch={root['branch_id']}" in context["content"]
    assert (
        "repo: branch=main dirty=2 sample=M src/example.txt; ?? scratch.txt"
        in context["content"]
    )
    assert "recent_diff: M src/example.txt; ?? scratch.txt" in context["content"]
    assert "recent_test: success exit=0 pytest tests/test_hao_cli.py" in context["content"]
    assert file_entries[0].startswith(
        "git branch=main dirty=2 sample=M src/example.txt; ?? scratch.txt"
    )
    assert any(entry.endswith("src/example.txt") for entry in file_entries)


def test_hao_v3_auto_continue_respects_configured_turn_budget(
    tmp_path: Path,
    monkeypatch,
) -> None:
    app = _make_hao_app(tmp_path, monkeypatch, permission_mode="full-auto", target="host")
    app.session = app.store.create_session(
        cwd=str(tmp_path),
        agent_id="default",
        mode="full-auto",
        cli_mode="act",
        target="host",
    )
    app.max_auto_turns = 1
    calls: list[str] = []

    class FakeClient:
        def stream_chat(self, agent_id: str, payload: dict):
            del agent_id
            calls.append(str(payload["goal"]))
            yield SSEEvent(
                event="run_created",
                data={"run_id": "run-budget"},
                raw='event: run_created\ndata: {"run_id": "run-budget"}',
            )
            yield SSEEvent(
                event="tool_call_requested",
                data={
                    "tool_call_id": f"read-{len(calls)}",
                    "tool_name": "read_file",
                    "input_json": {"path": "notes.md"},
                },
                raw="event: tool_call_requested\ndata: {}",
            )
            yield SSEEvent(event="done", data={}, raw="event: done\ndata: {}")

        def record_local_tool_event(self, run_id: str, payload: dict) -> dict:
            del run_id, payload
            return {"tool_call": {"id": f"tool-call-{len(calls)}"}}

    (tmp_path / "notes.md").write_text("ok\n", encoding="utf-8")
    app.api_client = FakeClient()  # type: ignore[assignment]

    app._run_turn_sync("inspect", 0, "act")

    assert calls == ["inspect", "Continue using the local tool results."]


def test_hao_v3_auto_continue_stops_when_pending_change_created(
    tmp_path: Path,
    monkeypatch,
) -> None:
    app = _make_hao_app(tmp_path, monkeypatch, permission_mode="confirm", target="host")
    app.session = app.store.create_session(
        cwd=str(tmp_path),
        agent_id="default",
        mode="confirm",
        cli_mode="act",
        target="host",
    )
    app.max_auto_turns = 3
    target = tmp_path / "notes.md"
    target.write_text("old\n", encoding="utf-8")
    calls: list[str] = []
    audit_payloads: list[dict[str, Any]] = []

    class FakeClient:
        def stream_chat(self, agent_id: str, payload: dict):
            del agent_id
            calls.append(str(payload["goal"]))
            yield SSEEvent(
                event="run_created",
                data={"run_id": "run-pending-stop"},
                raw='event: run_created\ndata: {"run_id": "run-pending-stop"}',
            )
            yield SSEEvent(
                event="tool_call_requested",
                data={
                    "tool_call_id": "read-1",
                    "tool_name": "read_file",
                    "input_json": {"path": "notes.md"},
                },
                raw="event: tool_call_requested\ndata: {}",
            )
            yield SSEEvent(
                event="tool_call_requested",
                data={
                    "tool_call_id": "write-1",
                    "tool_name": "write_file",
                    "input_json": {"path": "notes.md", "content": "new\n"},
                },
                raw="event: tool_call_requested\ndata: {}",
            )
            yield SSEEvent(
                event="tool_call_requested",
                data={
                    "tool_call_id": "read-2",
                    "tool_name": "read_file",
                    "input_json": {"path": "notes.md"},
                },
                raw="event: tool_call_requested\ndata: {}",
            )

        def record_local_tool_event(self, run_id: str, payload: dict) -> dict:
            audit_payloads.append({"run_id": run_id, **payload})
            return {"tool_call": {"id": f"tool-call-{len(audit_payloads)}"}}

    app.api_client = FakeClient()  # type: ignore[assignment]

    app._run_turn_sync("inspect and edit", 0, "act")

    changes = app.store.list_pending_changes(app.session.id)
    assert calls == ["inspect and edit"]
    assert target.read_text(encoding="utf-8") == "old\n"
    assert len(changes) == 1
    assert changes[0]["status"] == "pending"
    assert [payload["tool_name"] for payload in audit_payloads] == ["read_file", "write_file"]


def test_hao_v3_tui_stops_stream_when_tool_needs_approval(
    tmp_path: Path,
    monkeypatch,
) -> None:
    app = _make_hao_app(tmp_path, monkeypatch, permission_mode="confirm", target="host")
    app.session = app.store.create_session(
        cwd=str(tmp_path),
        agent_id="default",
        mode="confirm",
        cli_mode="act",
        target="host",
    )
    (tmp_path / "notes.md").write_text("ok\n", encoding="utf-8")
    calls: list[str] = []
    audit_payloads: list[dict[str, Any]] = []

    class FakeClient:
        def stream_chat(self, agent_id: str, payload: dict):
            del agent_id
            calls.append(str(payload["goal"]))
            yield SSEEvent(
                event="run_created",
                data={"run_id": "run-pending-tool-stop"},
                raw='event: run_created\ndata: {"run_id": "run-pending-tool-stop"}',
            )
            yield SSEEvent(
                event="tool_call_requested",
                data={
                    "tool_call_id": "test-1",
                    "tool_name": "run_tests",
                    "input_json": {"command": "pytest -q"},
                },
                raw="event: tool_call_requested\ndata: {}",
            )
            yield SSEEvent(
                event="tool_call_requested",
                data={
                    "tool_call_id": "read-1",
                    "tool_name": "read_file",
                    "input_json": {"path": "notes.md"},
                },
                raw="event: tool_call_requested\ndata: {}",
            )

        def record_local_tool_event(self, run_id: str, payload: dict) -> dict:
            audit_payloads.append({"run_id": run_id, **payload})
            return {"tool_call": {"id": f"tool-call-{len(audit_payloads)}"}}

    app.api_client = FakeClient()  # type: ignore[assignment]

    app._run_turn_sync("run tests", 0, "act")

    assert calls == ["run tests"]
    assert "tool-test-1" in app.pending_tools
    assert audit_payloads == []
    assert app.store.list_tool_events(app.session.id) == []


def test_hao_v3_tui_stops_stream_on_write_preview_audit_failure(
    tmp_path: Path,
    monkeypatch,
) -> None:
    app = _make_hao_app(tmp_path, monkeypatch, permission_mode="confirm", target="host")
    app.session = app.store.create_session(
        cwd=str(tmp_path),
        agent_id="default",
        mode="confirm",
        cli_mode="act",
        target="host",
    )
    target = tmp_path / "notes.md"
    target.write_text("old\n", encoding="utf-8")
    calls: list[str] = []

    class FakeClient:
        def stream_chat(self, agent_id: str, payload: dict):
            del agent_id
            calls.append(str(payload["goal"]))
            yield SSEEvent(
                event="run_created",
                data={"run_id": "run-audit-stop"},
                raw='event: run_created\ndata: {"run_id": "run-audit-stop"}',
            )
            yield SSEEvent(
                event="tool_call_requested",
                data={
                    "tool_call_id": "write-1",
                    "tool_name": "write_file",
                    "input_json": {"path": "notes.md", "content": "new\n"},
                },
                raw="event: tool_call_requested\ndata: {}",
            )
            yield SSEEvent(
                event="tool_call_requested",
                data={
                    "tool_call_id": "read-1",
                    "tool_name": "read_file",
                    "input_json": {"path": "notes.md"},
                },
                raw="event: tool_call_requested\ndata: {}",
            )

        def record_local_tool_event(self, run_id: str, payload: dict) -> dict:
            del run_id, payload
            raise RuntimeError("audit service unavailable")

    app.api_client = FakeClient()  # type: ignore[assignment]

    app._run_turn_sync("write with failing audit", 0, "act")

    changes = app.store.list_pending_changes(app.session.id)
    events = app.store.list_tool_events(app.session.id)
    assert calls == ["write with failing audit"]
    assert target.read_text(encoding="utf-8") == "old\n"
    assert changes[0]["status"] == "failed"
    assert len(events) == 1
    assert events[0]["tool_name"] == "write_file"
    assert events[0]["status"] == "AUDIT_FAILED"


def test_hao_v3_full_auto_write_commits_without_commit_audit(
    tmp_path: Path,
    monkeypatch,
) -> None:
    app = _make_hao_app(tmp_path, monkeypatch, permission_mode="full-auto", target="host")
    app.session = app.store.create_session(
        cwd=str(tmp_path),
        agent_id="default",
        mode="full-auto",
        cli_mode="act",
        target="host",
    )
    app.run_id = "run-full-auto-write"
    target = tmp_path / "notes.md"
    target.write_text("old\n", encoding="utf-8")
    audit_payloads: list[dict[str, Any]] = []

    class FakeClient:
        def record_local_tool_event(self, run_id: str, payload: dict) -> dict:
            if str(payload["tool_name"]).startswith("commit_"):
                raise AssertionError("commit must not be audited after mutating the workspace")
            audit_payloads.append({"run_id": run_id, **payload})
            return {"tool_call": {"id": f"tool-call-{len(audit_payloads)}"}}

    app.api_client = FakeClient()  # type: ignore[assignment]
    event = SSEEvent(
        event="tool_call_requested",
        data={
            "tool_call_id": "write-1",
            "tool_name": "write_file",
            "input_json": {"path": "notes.md", "content": "new\n"},
        },
        raw="event: tool_call_requested\ndata: {}",
    )

    result_message = app._handle_tool_request(event, "act")

    changes = app.store.list_pending_changes(app.session.id)
    assert result_message is not None
    assert target.read_text(encoding="utf-8") == "new\n"
    assert changes[0]["status"] == "committed"
    assert [payload["tool_name"] for payload in audit_payloads] == ["write_file"]
    assert [event["tool_name"] for event in app.store.list_tool_events(app.session.id)] == [
        "write_file",
        "commit_write_file",
    ]


def test_hao_v3_headless_main_runs_live_stream_and_auto_continues(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    monkeypatch.setenv("HAO_HOME", str(tmp_path / "hao-home"))
    stream_payloads: list[dict[str, Any]] = []
    audit_payloads: list[dict[str, Any]] = []

    class FakeClient:
        def __init__(self, api_url: str, token: str) -> None:
            self.api_url = api_url
            self.token = token

        def stream_chat(self, agent_id: str, payload: dict):
            assert agent_id == "default"
            stream_payloads.append(payload)
            if len(stream_payloads) == 1:
                yield SSEEvent(
                    event="run_created",
                    data={"run_id": "run-headless-live"},
                    raw='event: run_created\ndata: {"run_id": "run-headless-live"}',
                )
                yield SSEEvent(
                    event="tool_call_requested",
                    data={
                        "tool_call_id": "test-1",
                        "tool_name": "run_tests",
                        "input_json": {"command": "pytest -q"},
                    },
                    raw="event: tool_call_requested\ndata: {}",
                )
            else:
                yield SSEEvent(
                    event="run_created",
                    data={"run_id": "run-headless-live"},
                    raw='event: run_created\ndata: {"run_id": "run-headless-live"}',
                )
                yield SSEEvent(
                    event="delta",
                    data={"content": "Tests passed."},
                    raw='event: delta\ndata: {"content": "Tests passed."}',
                )
            yield SSEEvent(event="done", data={}, raw="event: done\ndata: {}")

        def record_local_tool_event(self, run_id: str, payload: dict) -> dict:
            audit_payloads.append({"run_id": run_id, **payload})
            return {"tool_call": {"id": "backend-tool-1"}}

    def fake_local_tool(tool_name, input_json, workspace_root, **kwargs):
        del workspace_root, kwargs
        assert tool_name == "run_tests"
        return ToolExecutionResult(
            tool_name="run_tests",
            status="SUCCESS",
            input_json=input_json,
            output_json={
                "command_id": "cmd-live",
                "command": input_json["command"],
                "exit_code": 0,
                "stdout": "ok\n",
            },
            duration_ms=1,
        )

    monkeypatch.setattr(hao_main, "HarnessApiClient", FakeClient)
    monkeypatch.setattr(hao_main, "execute_local_tool", fake_local_tool)

    result = hao_main.main(
        ["--cwd", str(tmp_path), "--mode", "full-auto", "act", "run tests"]
    )

    output = json.loads(capsys.readouterr().out)
    config = hao_main.load_config()
    store = SessionStore(config.session_db_path, config.sessions_dir)
    session = store.get_session(output["session_id"])
    assert result == 0
    assert output["status"] == "completed"
    assert output["assistant"] == "Tests passed."
    assert output["tool_results"][0]["tool_name"] == "run_tests"
    assert len(stream_payloads) == 2
    assert stream_payloads[0]["messages"][0]["metadata"]["source"] == "hao_local_context"
    assert stream_payloads[1]["goal"] == "Continue using the local tool results."
    assert audit_payloads[0]["run_id"] == "run-headless-live"
    assert audit_payloads[0]["interaction_mode"] == "act"
    assert audit_payloads[0]["local_session_id"] == output["session_id"]
    assert session is not None
    assert [message["role"] for message in store.list_active_path(session.id)] == [
        "user",
        "tool",
        "assistant",
    ]
    assert store.list_verifications(session.id)[0]["status"] == "passed"


def test_hao_v3_headless_confirm_write_contract_leaves_pending_change_for_resume(
    tmp_path: Path,
) -> None:
    store = SessionStore(tmp_path / "hao.db", tmp_path / "sessions")
    session = store.create_session(
        cwd=str(tmp_path),
        agent_id="default",
        mode="confirm",
        cli_mode="act",
        target="host",
    )
    target = tmp_path / "notes.md"
    target.write_text("old\n", encoding="utf-8")

    result = hao_main.run_headless_once(
        command="act",
        prompt="write notes",
        cwd=tmp_path,
        session_store=store,
        session_id=session.id,
        permission_mode="confirm",
        target="host",
        max_auto_turns=3,
        fake_events=[
            SSEEvent(
                event="run_created",
                data={"run_id": "run-headless"},
                raw='event: run_created\ndata: {"run_id": "run-headless"}',
            ),
            SSEEvent(
                event="tool_call_requested",
                data={
                    "tool_call_id": "write-1",
                    "tool_name": "write_file",
                    "input_json": {"path": "notes.md", "content": "new\n"},
                },
                raw="event: tool_call_requested\ndata: {}",
            ),
            SSEEvent(event="done", data={}, raw="event: done\ndata: {}"),
        ],
    )

    changes = store.list_pending_changes(session.id)
    assert result.exit_code == 2
    assert result.status == "pending_approval"
    assert result.stdout_json["change_id"] == changes[0]["id"]
    assert result.stderr == ""
    assert target.read_text(encoding="utf-8") == "old\n"
    assert changes[0]["status"] == "pending"
    resumed = store.get_session(session.id)
    assert resumed is not None
    assert resumed.active_leaf_id is not None


def test_hao_v3_headless_full_auto_write_commits_without_commit_audit(
    tmp_path: Path,
) -> None:
    store = SessionStore(tmp_path / "hao.db", tmp_path / "sessions")
    session = store.create_session(
        cwd=str(tmp_path),
        agent_id="default",
        mode="full-auto",
        cli_mode="act",
        target="host",
    )
    target = tmp_path / "notes.md"
    target.write_text("old\n", encoding="utf-8")
    audit_payloads: list[dict[str, Any]] = []

    class FakeClient:
        def record_local_tool_event(self, run_id: str, payload: dict) -> dict:
            if str(payload["tool_name"]).startswith("commit_"):
                raise AssertionError("commit must not be audited after mutating the workspace")
            audit_payloads.append({"run_id": run_id, **payload})
            return {"tool_call": {"id": f"tool-call-{len(audit_payloads)}"}}

    result = hao_main.run_headless_once(
        command="act",
        prompt="write notes",
        cwd=tmp_path,
        session_store=store,
        session_id=session.id,
        permission_mode="full-auto",
        target="host",
        max_auto_turns=3,
        api_client=FakeClient(),
        fake_events=[
            SSEEvent(
                event="run_created",
                data={"run_id": "run-headless-full-auto-write"},
                raw='event: run_created\ndata: {"run_id": "run-headless-full-auto-write"}',
            ),
            SSEEvent(
                event="tool_call_requested",
                data={
                    "tool_call_id": "write-1",
                    "tool_name": "write_file",
                    "input_json": {"path": "notes.md", "content": "new\n"},
                },
                raw="event: tool_call_requested\ndata: {}",
            ),
            SSEEvent(event="done", data={}, raw="event: done\ndata: {}"),
        ],
    )

    changes = store.list_pending_changes(session.id)
    assert result.exit_code == 0
    assert result.status == "completed"
    assert result.stdout_json["change_status"] == "committed"
    assert target.read_text(encoding="utf-8") == "new\n"
    assert changes[0]["status"] == "committed"
    assert [payload["tool_name"] for payload in audit_payloads] == ["write_file"]
    assert [event["tool_name"] for event in store.list_tool_events(session.id)] == [
        "write_file",
        "commit_write_file",
    ]


def test_hao_v3_headless_audit_failure_records_failure_without_tool_message(
    tmp_path: Path,
) -> None:
    store = SessionStore(tmp_path / "hao.db", tmp_path / "sessions")
    session = store.create_session(
        cwd=str(tmp_path),
        agent_id="default",
        mode="confirm",
        cli_mode="act",
        target="host",
    )
    (tmp_path / "notes.md").write_text("ok\n", encoding="utf-8")

    class FailingAuditClient:
        def record_local_tool_event(self, run_id: str, payload: dict) -> dict:
            del run_id, payload
            raise RuntimeError("audit service unavailable")

    result = hao_main.run_headless_once(
        command="act",
        prompt="read notes",
        cwd=tmp_path,
        session_store=store,
        session_id=session.id,
        permission_mode="confirm",
        target="host",
        max_auto_turns=3,
        api_client=FailingAuditClient(),
        fake_events=[
            SSEEvent(
                event="run_created",
                data={"run_id": "run-audit-fail"},
                raw='event: run_created\ndata: {"run_id": "run-audit-fail"}',
            ),
            SSEEvent(
                event="tool_call_requested",
                data={
                    "tool_call_id": "read-1",
                    "tool_name": "read_file",
                    "input_json": {"path": "notes.md"},
                },
                raw="event: tool_call_requested\ndata: {}",
            ),
            SSEEvent(event="done", data={}, raw="event: done\ndata: {}"),
        ],
    )

    events = store.list_tool_events(session.id)
    assert result.exit_code == 1
    assert result.status == "failed"
    assert "audit service unavailable" in result.stderr
    assert [message["role"] for message in store.list_messages(session.id)] == ["user"]
    assert events[0]["status"] == "AUDIT_FAILED"
    assert events[0]["output_json"]["audit_failed"] is True
    assert events[0]["output_json"]["original_status"] == "SUCCESS"


def test_hao_v3_headless_write_audit_failure_fails_pending_change(
    tmp_path: Path,
) -> None:
    store = SessionStore(tmp_path / "hao.db", tmp_path / "sessions")
    session = store.create_session(
        cwd=str(tmp_path),
        agent_id="default",
        mode="full-auto",
        cli_mode="act",
        target="host",
    )
    target = tmp_path / "notes.md"
    target.write_text("old\n", encoding="utf-8")

    class FailingAuditClient:
        def record_local_tool_event(self, run_id: str, payload: dict) -> dict:
            del run_id, payload
            raise RuntimeError("audit service unavailable")

    result = hao_main.run_headless_once(
        command="act",
        prompt="write notes",
        cwd=tmp_path,
        session_store=store,
        session_id=session.id,
        permission_mode="full-auto",
        target="host",
        max_auto_turns=3,
        api_client=FailingAuditClient(),
        fake_events=[
            SSEEvent(
                event="run_created",
                data={"run_id": "run-write-audit-fail"},
                raw='event: run_created\ndata: {"run_id": "run-write-audit-fail"}',
            ),
            SSEEvent(
                event="tool_call_requested",
                data={
                    "tool_call_id": "write-1",
                    "tool_name": "write_file",
                    "input_json": {"path": "notes.md", "content": "new\n"},
                },
                raw="event: tool_call_requested\ndata: {}",
            ),
            SSEEvent(event="done", data={}, raw="event: done\ndata: {}"),
        ],
    )

    changes = store.list_pending_changes(session.id)
    events = store.list_tool_events(session.id)
    assert result.exit_code == 1
    assert result.status == "failed"
    assert "audit service unavailable" in result.stderr
    assert "change_id" not in result.stdout_json
    assert target.read_text(encoding="utf-8") == "old\n"
    assert changes[0]["status"] == "failed"
    assert changes[0]["tool_event_id"] == events[0]["id"]
    assert "audit failed" in changes[0]["error_message"]
    assert [message["role"] for message in store.list_messages(session.id)] == ["user"]
    assert events[0]["status"] == "AUDIT_FAILED"


def test_hao_v3_headless_plan_mode_suppresses_local_tool_execution(
    tmp_path: Path,
    monkeypatch,
) -> None:
    store = SessionStore(tmp_path / "hao.db", tmp_path / "sessions")
    session = store.create_session(
        cwd=str(tmp_path),
        agent_id="default",
        mode="confirm",
        cli_mode="plan",
        target="host",
    )
    target = tmp_path / "notes.md"
    target.write_text("old\n", encoding="utf-8")

    def fail_local_tool(*args, **kwargs):
        raise AssertionError("plan mode must not execute local tools")

    monkeypatch.setattr(hao_main, "execute_local_tool", fail_local_tool)

    result = hao_main.run_headless_once(
        command="plan",
        prompt="draft only",
        cwd=tmp_path,
        session_store=store,
        session_id=session.id,
        permission_mode="confirm",
        target="host",
        max_auto_turns=3,
        fake_events=[
            SSEEvent(
                event="run_created",
                data={"run_id": "run-plan"},
                raw='event: run_created\ndata: {"run_id": "run-plan"}',
            ),
            SSEEvent(
                event="tool_call_requested",
                data={
                    "tool_call_id": "write-1",
                    "tool_name": "write_file",
                    "input_json": {"path": "notes.md", "content": "new\n"},
                },
                raw="event: tool_call_requested\ndata: {}",
            ),
            SSEEvent(event="done", data={}, raw="event: done\ndata: {}"),
        ],
    )

    assert result.exit_code == 0
    assert result.status == "completed"
    assert target.read_text(encoding="utf-8") == "old\n"
    assert store.list_tool_events(session.id) == []
    assert store.list_pending_changes(session.id) == []


def test_hao_v3_headless_sandbox_target_fails_closed_without_local_execution(
    tmp_path: Path,
    monkeypatch,
) -> None:
    store = SessionStore(tmp_path / "hao.db", tmp_path / "sessions")
    session = store.create_session(
        cwd=str(tmp_path),
        agent_id="default",
        mode="full-auto",
        cli_mode="act",
        target="sandbox",
    )

    def fail_local_tool(*args, **kwargs):
        raise AssertionError("sandbox target must not execute host local tools")

    monkeypatch.setattr(hao_main, "execute_local_tool", fail_local_tool)

    result = hao_main.run_headless_once(
        command="act",
        prompt="inspect",
        cwd=tmp_path,
        session_store=store,
        session_id=session.id,
        permission_mode="full-auto",
        target="sandbox",
        max_auto_turns=3,
        fake_events=[
            SSEEvent(
                event="run_created",
                data={"run_id": "run-sandbox"},
                raw='event: run_created\ndata: {"run_id": "run-sandbox"}',
            ),
            SSEEvent(
                event="tool_call_requested",
                data={
                    "tool_call_id": "read-1",
                    "tool_name": "read_file",
                    "input_json": {"path": "notes.md"},
                },
                raw="event: tool_call_requested\ndata: {}",
            ),
        ],
    )

    assert result.exit_code == 1
    assert result.status == "failed"
    assert "sandbox" in result.stderr
    assert store.list_tool_events(session.id) == []


def test_hao_v3_headless_confirm_shell_leaves_pending_tool_without_execution(
    tmp_path: Path,
    monkeypatch,
) -> None:
    store = SessionStore(tmp_path / "hao.db", tmp_path / "sessions")
    session = store.create_session(
        cwd=str(tmp_path),
        agent_id="default",
        mode="confirm",
        cli_mode="act",
        target="host",
    )

    def fail_local_tool(*args, **kwargs):
        raise AssertionError("confirm shell tool must wait for approval")

    monkeypatch.setattr(hao_main, "execute_local_tool", fail_local_tool)

    result = hao_main.run_headless_once(
        command="act",
        prompt="run tests",
        cwd=tmp_path,
        session_store=store,
        session_id=session.id,
        permission_mode="confirm",
        target="host",
        max_auto_turns=3,
        fake_events=[
            SSEEvent(
                event="run_created",
                data={"run_id": "run-shell"},
                raw='event: run_created\ndata: {"run_id": "run-shell"}',
            ),
            SSEEvent(
                event="tool_call_requested",
                data={
                    "tool_call_id": "test-1",
                    "tool_name": "run_tests",
                    "input_json": {"command": "pytest -q"},
                },
                raw="event: tool_call_requested\ndata: {}",
            ),
        ],
    )

    assert result.exit_code == 2
    assert result.status == "pending_approval"
    assert result.stdout_json["pending_tool"]["tool_name"] == "run_tests"
    assert store.list_tool_events(session.id) == []


def test_hao_v3_headless_denied_tool_records_denial_without_execution(
    tmp_path: Path,
    monkeypatch,
) -> None:
    store = SessionStore(tmp_path / "hao.db", tmp_path / "sessions")
    session = store.create_session(
        cwd=str(tmp_path),
        agent_id="default",
        mode="full-auto",
        cli_mode="act",
        target="host",
    )

    def fail_local_tool(*args, **kwargs):
        raise AssertionError("denied tool must not execute")

    monkeypatch.setattr(hao_main, "execute_local_tool", fail_local_tool)

    result = hao_main.run_headless_once(
        command="act",
        prompt="dangerous",
        cwd=tmp_path,
        session_store=store,
        session_id=session.id,
        permission_mode="full-auto",
        target="host",
        max_auto_turns=3,
        fake_events=[
            SSEEvent(
                event="run_created",
                data={"run_id": "run-denied"},
                raw='event: run_created\ndata: {"run_id": "run-denied"}',
            ),
            SSEEvent(
                event="tool_call_requested",
                data={
                    "tool_call_id": "shell-1",
                    "tool_name": "run_shell",
                    "input_json": {"command": "sudo reboot"},
                },
                raw="event: tool_call_requested\ndata: {}",
            ),
        ],
    )

    events = store.list_tool_events(session.id)
    assert result.exit_code == 1
    assert result.status == "failed"
    assert "dangerous command blocked" in result.stderr
    assert events[0]["tool_name"] == "run_shell"
    assert events[0]["status"] == "DENIED"


def test_hao_v3_headless_run_tests_creates_verification_for_allowed_host_tool(
    tmp_path: Path,
    monkeypatch,
) -> None:
    store = SessionStore(tmp_path / "hao.db", tmp_path / "sessions")
    session = store.create_session(
        cwd=str(tmp_path),
        agent_id="default",
        mode="full-auto",
        cli_mode="act",
        target="host",
    )

    def fake_local_tool(tool_name, input_json, workspace_root, **kwargs):
        del workspace_root, kwargs
        assert tool_name == "run_tests"
        return ToolExecutionResult(
            tool_name="run_tests",
            status="SUCCESS",
            input_json=input_json,
            output_json={
                "command_id": "cmd-1",
                "command": input_json["command"],
                "exit_code": 0,
                "stdout": "ok\n",
            },
            duration_ms=1,
        )

    monkeypatch.setattr(hao_main, "execute_local_tool", fake_local_tool)

    result = hao_main.run_headless_once(
        command="act",
        prompt="run tests",
        cwd=tmp_path,
        session_store=store,
        session_id=session.id,
        permission_mode="full-auto",
        target="host",
        max_auto_turns=3,
        fake_events=[
            SSEEvent(
                event="run_created",
                data={"run_id": "run-tests"},
                raw='event: run_created\ndata: {"run_id": "run-tests"}',
            ),
            SSEEvent(
                event="tool_call_requested",
                data={
                    "tool_call_id": "test-1",
                    "tool_name": "run_tests",
                    "input_json": {"command": "pytest -q"},
                },
                raw="event: tool_call_requested\ndata: {}",
            ),
            SSEEvent(event="done", data={}, raw="event: done\ndata: {}"),
        ],
    )

    verifications = store.list_verifications(session.id)
    assert result.exit_code == 0
    assert result.status == "completed"
    assert verifications[0]["status"] == "passed"
    assert verifications[0]["command_id"] == "cmd-1"
    assert verifications[0]["tool_event_id"] == store.list_tool_events(session.id)[0]["id"]
    assert "pytest -q" in verifications[0]["evidence_summary"]


def test_hao_v3_golden_act_workflow_persists_verification_from_user_commands(
    tmp_path: Path,
    monkeypatch,
) -> None:
    app = _make_hao_app(tmp_path, monkeypatch, permission_mode="confirm", target="host")
    app.session = app.store.create_session(
        cwd=str(tmp_path),
        agent_id="default",
        mode="confirm",
        cli_mode="act",
        target="host",
    )
    app.interaction_mode = "act"
    target = tmp_path / "notes.md"
    target.write_text("old\n", encoding="utf-8")
    recorded_payloads: list[dict[str, Any]] = []
    stream_calls: list[dict[str, Any]] = []

    class FakeClient:
        def stream_chat(self, agent_id: str, payload: dict):
            del agent_id
            stream_calls.append(payload)
            call_index = len(stream_calls)
            run_id = payload.get("run_id") or "run-v3"
            yield SSEEvent(
                event="run_created",
                data={"run_id": run_id},
                raw='event: run_created\ndata: {"run_id": "run-v3"}',
            )
            if call_index == 1:
                yield SSEEvent(
                    event="delta",
                    data={"content": "I will edit notes.md.\n"},
                    raw='event: delta\ndata: {"content": "I will edit notes.md.\\n"}',
                )
                yield SSEEvent(
                    event="tool_call_requested",
                    data={
                        "tool_call_id": "write-1",
                        "tool_name": "write_file",
                        "input_json": {"path": "notes.md", "content": "new\n"},
                    },
                    raw="event: tool_call_requested\ndata: {}",
                )
            elif call_index == 2:
                yield SSEEvent(
                    event="tool_call_requested",
                    data={
                        "tool_call_id": "test-1",
                        "tool_name": "run_tests",
                        "input_json": {"command": "python -c 'print(\"ok\")'"},
                    },
                    raw="event: tool_call_requested\ndata: {}",
                )
            else:
                yield SSEEvent(
                    event="delta",
                    data={"content": "Verification passed.\n"},
                    raw='event: delta\ndata: {"content": "Verification passed.\\n"}',
                )
            yield SSEEvent(event="done", data={}, raw="event: done\ndata: {}")

        def record_local_tool_event(self, run_id: str, payload: dict) -> dict:
            recorded_payloads.append({"run_id": run_id, **payload})
            return {"tool_call": {"id": f"tool-call-{len(recorded_payloads)}"}}

    app.api_client = FakeClient()  # type: ignore[assignment]
    monkeypatch.setattr(
        app,
        "approve_change_worker",
        lambda change_id: HaoApp.approve_change_worker.__wrapped__(app, change_id),
    )
    monkeypatch.setattr(
        app,
        "approve_tool_worker",
        lambda pending_id: HaoApp.approve_tool_worker.__wrapped__(app, pending_id),
    )

    app._handle_command("/act")
    app._record_message_ui(
        "user",
        "update notes and verify",
        metadata=app._workflow_metadata("act"),
    )
    app._run_turn_sync("update notes and verify", 0, "act")

    pending_change = app.store.list_pending_changes(app.session.id)[0]
    assert pending_change["status"] == "pending"
    assert target.read_text(encoding="utf-8") == "old\n"

    app._handle_command(f"/approve {pending_change['id']}")

    assert target.read_text(encoding="utf-8") == "new\n"
    assert "tool-test-1" in app.pending_tools

    app._handle_command("/approve tool-test-1")

    commands = app.store.list_commands(app.session.id)
    tool_events = app.store.list_tool_events(app.session.id)
    verifications = app.store.list_verifications(app.session.id)

    assert len(stream_calls) == 3
    assert any(payload["tool_name"] == "write_file" for payload in recorded_payloads)
    assert not any(
        str(payload["tool_name"]).startswith("commit_") for payload in recorded_payloads
    )
    assert any(payload["tool_name"] == "run_tests" for payload in recorded_payloads)
    assert commands[-1]["tool_name"] == "run_tests"
    assert commands[-1]["status"] == "success"
    assert tool_events[-1]["tool_name"] == "run_tests"
    assert verifications[-1]["status"] == "passed"
    assert verifications[-1]["command_id"] == commands[-1]["id"]
    assert verifications[-1]["tool_event_id"] == tool_events[-1]["id"]
    assert verifications[-1]["created_at"]
    assert verifications[-1]["updated_at"]
    assert "python -c" in verifications[-1]["evidence_summary"]
    assert app.messages[-1]["role"] == "assistant"
    assert "Verification passed" in app.messages[-1]["content"]


@pytest.mark.parametrize(
    ("status", "expected_event_type"),
    [
        ("SUCCESS", "TOOL_RESULT_RECEIVED"),
        ("FAILED", "TOOL_FAILED"),
        ("TIMEOUT", "TOOL_TIMEOUT"),
        ("DENIED", "TOOL_DENIED_BY_POLICY"),
    ],
)
def test_hao_local_tool_audit_persists_workflow_metadata(
    db_session: Session,
    status: str,
    expected_event_type: str,
) -> None:
    ensure_default_agents(db_session, "dev-org")
    run = Task(
        organization_id="dev-org",
        agent_id="default",
        created_by="dev-engineer",
        title="hao act audit",
        goal="record act tool metadata",
        status="RUNNING",
        model_provider="default",
        model_name="default",
        created_at=utc_now(),
        updated_at=utc_now(),
    )
    db_session.add(run)
    db_session.commit()
    act_intent = {"source": "slash_command", "allow_local_tools": True}

    response = TestClient(fastapi_app).post(
        f"/api/agents/runs/{run.id}/local-tool-events",
        headers=AUTH_HEADERS,
        json={
            "tool_name": "run_shell",
            "input_json": {"command": "pytest"},
            "output_json": {"stdout": "ok", "exit_code": 0},
            "status": status,
            "risk_level": "high",
            "duration_ms": 12,
            "execution_target": "host",
            "permission_mode": "confirm",
            "interaction_mode": "act",
            "act_intent": act_intent,
            "local_session_id": "local-1",
            "cwd": "/tmp/work",
        },
    )

    assert response.status_code == 201
    tool_call = db_session.execute(select(ToolCall)).scalar_one()
    assert tool_call.capability_snapshot_json["interaction_mode"] == "act"
    assert tool_call.capability_snapshot_json["act_intent"] == act_intent
    events = list(
        db_session.execute(
            select(AgentEvent).where(AgentEvent.task_id == run.id).order_by(AgentEvent.sequence)
        ).scalars()
    )
    assert expected_event_type in [event.event_type for event in events]
    for event in events:
        if event.event_type in {"POLICY_CHECKED", "TOOL_CALLED", expected_event_type}:
            assert event.payload_json["interaction_mode"] == "act"
            assert event.payload_json["act_intent"] == act_intent


def test_hao_record_tool_result_sends_workflow_metadata_to_audit(
    tmp_path: Path,
    monkeypatch,
) -> None:
    app = _make_hao_app(tmp_path, monkeypatch)
    app.session = app.store.create_session(
        cwd=str(tmp_path),
        agent_id="default",
        mode="confirm",
        cli_mode="act",
        target="host",
    )
    app.run_id = "run-1"
    app.interaction_mode = "act"
    recorded_payloads: list[dict] = []

    class FakeClient:
        def record_local_tool_event(self, run_id: str, payload: dict) -> dict:
            recorded_payloads.append({"run_id": run_id, **payload})
            return {"tool_call": {"id": "tool-call-1"}}

    app.api_client = FakeClient()  # type: ignore[assignment]
    result = ToolExecutionResult(
        tool_name="run_shell",
        status="SUCCESS",
        input_json={"command": "pytest"},
        output_json={"stdout": "ok", "exit_code": 0},
        duration_ms=1,
    )

    app._record_tool_result(result, "high", audit_host=True)

    assert recorded_payloads == [
        {
            "run_id": "run-1",
            "tool_name": "run_shell",
            "input_json": {"command": "pytest"},
            "output_json": {"stdout": "ok", "exit_code": 0},
            "status": "SUCCESS",
            "risk_level": "high",
            "requires_sandbox": False,
            "duration_ms": 1,
            "error_message": None,
            "execution_target": "host",
            "permission_mode": "confirm",
            "interaction_mode": "act",
            "act_intent": {
                "source": "slash_command",
                "allow_local_tools": True,
            },
            "local_session_id": app.session.id,
            "cwd": str(tmp_path),
        }
    ]


def test_session_store_persists_command_record_and_commands_jsonl_event_log(
    tmp_path: Path,
) -> None:
    store = SessionStore(tmp_path / "hao.db", tmp_path / "sessions")
    session = store.create_session(
        cwd="/tmp/work",
        agent_id="default",
        mode="confirm",
        target="host",
    )

    command = store.create_command(
        session.id,
        tool_name="run_shell",
        command="printf ok",
        command_json={"command": "printf ok"},
        timeout_seconds=30,
    )
    store.start_command(command["id"])
    store.record_command_output(command["id"], stream="stdout", chunk="ok")
    store.finish_command(
        command["id"],
        status="success",
        exit_code=0,
        stdout_truncated=False,
        stderr_truncated=False,
    )
    store.link_command_tool_event(command["id"], "tool-event-1")

    loaded = store.get_command(command["id"])
    assert loaded is not None
    assert loaded["session_id"] == session.id
    assert loaded["tool_name"] == "run_shell"
    assert loaded["command"] == "printf ok"
    assert loaded["command_json"] == {"command": "printf ok"}
    assert loaded["timeout_seconds"] == 30
    assert loaded["status"] == "success"
    assert loaded["started_at"] is not None
    assert loaded["finished_at"] is not None
    assert loaded["exit_code"] == 0
    assert loaded["tool_event_id"] == "tool-event-1"
    assert loaded["retry_of_id"] is None

    events = _read_jsonl(tmp_path / "sessions" / session.id / "commands.jsonl")
    assert [event["event"] for event in events] == [
        "pending",
        "running",
        "output",
        "success",
        "linked",
    ]
    assert [event["command_id"] for event in events] == [command["id"]] * len(events)
    assert all(event["created_at"] for event in events)
    assert events[0]["status"] == "pending"
    assert events[1]["status"] == "running"
    assert events[2]["stream"] == "stdout"
    assert events[2]["chunk"] == "ok"
    assert events[3]["status"] == "success"
    assert events[4]["tool_event_id"] == "tool-event-1"


def test_session_store_rejects_duplicate_terminal_transitions(
    tmp_path: Path,
) -> None:
    store = SessionStore(tmp_path / "hao.db", tmp_path / "sessions")
    session = store.create_session(
        cwd="/tmp/work",
        agent_id="default",
        mode="confirm",
        target="host",
    )

    command = store.create_command(
        session.id,
        tool_name="run_shell",
        command="printf ok",
        command_json={"command": "printf ok"},
        timeout_seconds=30,
    )
    store.start_command(command["id"])
    store.finish_command(
        command["id"],
        status="success",
        exit_code=0,
        stdout_truncated=False,
        stderr_truncated=False,
    )

    with pytest.raises(ValueError):
        store.start_command(command["id"])
    with pytest.raises(ValueError):
        store.record_command_output(command["id"], stream="stdout", chunk="late")
    with pytest.raises(ValueError):
        store.finish_command(
            command["id"],
            status="failed",
            exit_code=1,
            stdout_truncated=False,
            stderr_truncated=False,
        )

    events = _read_jsonl(tmp_path / "sessions" / session.id / "commands.jsonl")
    assert [
        event["status"]
        for event in events
        if event["status"] in TERMINAL_COMMAND_STATUSES
    ] == [
        "success",
    ]


def test_command_startup_failure_marks_failed_instead_of_leaving_pending(
    tmp_path: Path,
) -> None:
    from app.cli.hao.local_tools import execute_local_command_tool

    store = SessionStore(tmp_path / "hao.db", tmp_path / "sessions")
    missing_workspace = tmp_path / "missing-workspace"
    session = store.create_session(
        cwd=str(missing_workspace),
        agent_id="default",
        mode="confirm",
        target="host",
    )

    result = execute_local_command_tool(
        "run_shell",
        {"command": "printf ok"},
        missing_workspace,
        session_store=store,
        session_id=session.id,
    )

    assert result.status == "FAILED"
    assert result.output_json["command_status"] == "failed"
    assert result.output_json["started_at"] is not None
    assert result.output_json["finished_at"] is not None
    assert "error" in result.output_json

    commands = store.list_commands(session.id)
    assert len(commands) == 1
    assert commands[0]["status"] == "failed"
    assert commands[0]["started_at"] is not None
    assert commands[0]["finished_at"] is not None

    events = _read_jsonl(tmp_path / "sessions" / session.id / "commands.jsonl")
    assert [
        event["status"]
        for event in events
        if event["status"] in TERMINAL_COMMAND_STATUSES
    ] == [
        "failed",
    ]


def test_command_lifecycle_records_pending_running_then_success(
    tmp_path: Path,
) -> None:
    from app.cli.hao.local_tools import execute_local_command_tool

    store = SessionStore(tmp_path / "hao.db", tmp_path / "sessions")
    session = store.create_session(
        cwd=str(tmp_path),
        agent_id="default",
        mode="confirm",
        target="host",
    )

    result = execute_local_command_tool(
        "run_shell",
        {"command": "printf ok"},
        tmp_path,
        session_store=store,
        session_id=session.id,
    )

    assert result.status == "SUCCESS"
    assert result.output_json["stdout"] == "ok"
    assert result.output_json["command_status"] == "success"
    assert result.output_json["command_id"]
    assert result.output_json["started_at"] is not None
    assert result.output_json["finished_at"] is not None
    assert result.output_json["exit_code"] == 0

    commands = store.list_commands(session.id)
    assert len(commands) == 1
    assert commands[0]["status"] == "success"
    assert commands[0]["started_at"] is not None
    assert commands[0]["finished_at"] is not None
    assert commands[0]["exit_code"] == 0

    events = _read_jsonl(tmp_path / "sessions" / session.id / "commands.jsonl")
    terminal_events = [event for event in events if event["status"] in TERMINAL_COMMAND_STATUSES]
    assert [event["status"] for event in terminal_events] == ["success"]
    assert all(event["command_id"] == result.output_json["command_id"] for event in events)
    assert all(event["created_at"] for event in events)
    assert any(event["event"] == "output" and event["stream"] == "stdout" for event in events)


@pytest.mark.parametrize(
    ("tool_name", "command_json"),
    [
        ("run_shell", {"command": "printf ok"}),
        ("run_tests", {"command": "pytest --version"}),
        ("git", {"command": "--version"}),
    ],
)
def test_command_lifecycle_records_pending_running_then_success_for_shell_tests_and_git(
    tmp_path: Path,
    tool_name: str,
    command_json: dict[str, Any],
) -> None:
    from app.cli.hao.local_tools import execute_local_command_tool

    store = SessionStore(tmp_path / "hao.db", tmp_path / "sessions")
    session = store.create_session(
        cwd=str(tmp_path),
        agent_id="default",
        mode="confirm",
        target="host",
    )

    result = execute_local_command_tool(
        tool_name,
        command_json,
        tmp_path,
        session_store=store,
        session_id=session.id,
    )

    assert result.status == "SUCCESS"
    assert result.output_json["command_status"] == "success"
    assert result.output_json["command_id"]
    assert result.output_json["started_at"] is not None
    assert result.output_json["finished_at"] is not None
    assert result.output_json["exit_code"] == 0

    commands = store.list_commands(session.id)
    assert len(commands) == 1
    assert commands[0]["status"] == "success"
    assert commands[0]["tool_name"] == tool_name
    assert commands[0]["started_at"] is not None
    assert commands[0]["finished_at"] is not None
    assert commands[0]["exit_code"] == 0

    events = _read_jsonl(tmp_path / "sessions" / session.id / "commands.jsonl")
    assert [
        event["status"]
        for event in events
        if event["status"] in TERMINAL_COMMAND_STATUSES
    ] == [
        "success",
    ]
    assert all(event["command_id"] == result.output_json["command_id"] for event in events)
    assert all(event["created_at"] for event in events)
    assert any(event["event"] == "pending" for event in events)
    assert any(event["event"] == "running" for event in events)
    assert any(event["event"] == "output" for event in events)
    assert any(event["event"] == "success" for event in events)


@pytest.mark.parametrize(
    ("command", "timeout_seconds", "expected_command_status", "expected_tool_status"),
    [
        (
            "python -c \"import sys; sys.stderr.write('bad\\\\n'); sys.exit(2)\"",
            20,
            "failed",
            "FAILED",
        ),
        (
            "python -c \"import time; print('started', flush=True); time.sleep(5)\"",
            1,
            "timeout",
            "TIMEOUT",
        ),
        (
            "python -c \"import time; print('started', flush=True); time.sleep(5)\"",
            20,
            "cancelled",
            "FAILED",
        ),
    ],
)
def test_command_lifecycle_records_failed_timeout_and_cancelled_terminals(
    tmp_path: Path,
    command: str,
    timeout_seconds: int,
    expected_command_status: str,
    expected_tool_status: str,
) -> None:
    from app.cli.hao.local_tools import execute_local_command_tool

    store = SessionStore(tmp_path / "hao.db", tmp_path / "sessions")
    session = store.create_session(
        cwd=str(tmp_path),
        agent_id="default",
        mode="confirm",
        target="host",
    )

    cancel_after_started = expected_command_status == "cancelled"

    def cancel_check(command_id: str) -> bool:
        if not cancel_after_started:
            return False
        events_path = tmp_path / "sessions" / session.id / "commands.jsonl"
        if not events_path.exists():
            return False
        return any(
            event["event"] == "output"
            and event["command_id"] == command_id
            and event.get("stream") == "stdout"
            and str(event.get("chunk", "")).startswith("started")
            for event in _read_jsonl(events_path)
        )

    result = execute_local_command_tool(
        "run_shell",
        {"command": command, "timeout_seconds": timeout_seconds},
        tmp_path,
        session_store=store,
        session_id=session.id,
        cancel_check=cancel_check if cancel_after_started else None,
    )

    assert result.status == expected_tool_status
    assert result.output_json["command_status"] == expected_command_status
    assert result.output_json["command_id"]
    assert result.output_json["started_at"] is not None
    assert result.output_json["finished_at"] is not None
    assert "exit_code" in result.output_json
    if expected_command_status == "cancelled":
        assert result.error_message == "cancelled"
        assert result.output_json["error"] == "cancelled"
        assert result.output_json["stdout"].startswith("started")
    elif expected_command_status == "timeout":
        assert result.output_json["stdout"].startswith("started")
    elif expected_command_status == "failed":
        assert result.output_json["exit_code"] == 2
        assert "bad" in result.output_json["stderr"]

    commands = store.list_commands(session.id)
    assert len(commands) == 1
    assert commands[0]["status"] == expected_command_status
    assert commands[0]["started_at"] is not None
    assert commands[0]["finished_at"] is not None
    assert "exit_code" in commands[0]
    if expected_command_status == "failed":
        assert commands[0]["exit_code"] == 2
    terminal_count = sum(
        1
        for event in _read_jsonl(tmp_path / "sessions" / session.id / "commands.jsonl")
        if event["status"] in TERMINAL_COMMAND_STATUSES
    )
    assert terminal_count == 1
    events = _read_jsonl(tmp_path / "sessions" / session.id / "commands.jsonl")
    assert all(
        event["command_id"] == result.output_json["command_id"]
        for event in events
    )
    assert all(event["created_at"] for event in events)
    if expected_command_status == "failed":
        assert any(
            event["event"] == "output"
            and event["stream"] == "stderr"
            and "bad" in str(event["chunk"])
            for event in events
        )
    elif expected_command_status in {"timeout", "cancelled"}:
        assert any(
            event["event"] == "output"
            and event["stream"] == "stdout"
            and str(event["chunk"]).startswith("started")
            for event in events
        )


def test_command_retry_creates_new_command_linked_to_retry_of_id(tmp_path: Path) -> None:
    store = SessionStore(tmp_path / "hao.db", tmp_path / "sessions")
    session = store.create_session(
        cwd="/tmp/work",
        agent_id="default",
        mode="confirm",
        target="host",
    )

    original = store.create_command(
        session.id,
        tool_name="run_tests",
        command="pytest",
        command_json={"command": "pytest"},
        timeout_seconds=120,
    )
    store.start_command(original["id"])
    store.finish_command(
        original["id"],
        status="failed",
        exit_code=1,
        stdout_truncated=False,
        stderr_truncated=False,
    )
    retry = store.retry_command(original["id"])

    assert retry["id"] != original["id"]
    assert retry["retry_of_id"] == original["id"]
    assert retry["tool_name"] == original["tool_name"]
    assert retry["command"] == original["command"]
    assert retry["command_json"] == original["command_json"]
    assert retry["timeout_seconds"] == original["timeout_seconds"]
    assert retry["status"] == "pending"
    assert retry["started_at"] is None
    assert retry["finished_at"] is None
    assert retry["exit_code"] is None


@pytest.mark.parametrize("prepared_status", ["pending", "running"])
def test_command_retry_rejects_non_terminal_commands(
    tmp_path: Path,
    prepared_status: str,
) -> None:
    store = SessionStore(tmp_path / "hao.db", tmp_path / "sessions")
    session = store.create_session(
        cwd="/tmp/work",
        agent_id="default",
        mode="confirm",
        target="host",
    )

    command = store.create_command(
        session.id,
        tool_name="run_tests",
        command="pytest",
        command_json={"command": "pytest"},
        timeout_seconds=120,
    )
    if prepared_status == "running":
        store.start_command(command["id"])

    with pytest.raises(ValueError):
        store.retry_command(command["id"])


def test_hao_records_command_tool_event_link_after_tool_result(
    tmp_path: Path,
    monkeypatch,
) -> None:
    app = _make_hao_app(tmp_path, monkeypatch, target="host")
    app.session = app.store.create_session(
        cwd=str(tmp_path),
        agent_id="default",
        mode="confirm",
        target="host",
    )
    command = app.store.create_command(
        app.session.id,
        tool_name="run_shell",
        command="printf ok",
        command_json={"command": "printf ok"},
        timeout_seconds=30,
    )
    result = ToolExecutionResult(
        tool_name="run_shell",
        status="SUCCESS",
        input_json={"command": "printf ok"},
        output_json={
            "command_id": command["id"],
            "command_status": "success",
            "command": "printf ok",
            "started_at": "2026-05-31T00:00:00+00:00",
            "finished_at": "2026-05-31T00:00:01+00:00",
            "exit_code": 0,
            "stdout": "ok",
            "stderr": "",
            "stdout_truncated": False,
            "stderr_truncated": False,
        },
        duration_ms=1,
    )

    app._record_tool_result(
        result,
        "high",
        workflow_metadata=app._workflow_metadata("chat"),
        execution_target="host",
        permission_mode="confirm",
    )

    loaded = app.store.get_command(command["id"])
    assert loaded is not None
    assert loaded["tool_event_id"] is not None


def test_command_output_truncation_persists_stdout_and_stderr_flags(
    tmp_path: Path,
) -> None:
    from app.cli.hao.local_tools import execute_local_command_tool

    store = SessionStore(tmp_path / "hao.db", tmp_path / "sessions")
    session = store.create_session(
        cwd=str(tmp_path),
        agent_id="default",
        mode="confirm",
        target="host",
    )

    result = execute_local_command_tool(
        "run_shell",
        {
            "command": (
                "python -c \"import sys; "
                "sys.stdout.write('o' * 70000); "
                "sys.stderr.write('e' * 70000)\""
            )
        },
        tmp_path,
        session_store=store,
        session_id=session.id,
    )

    assert result.status == "SUCCESS"
    assert result.output_json["stdout_truncated"] is True
    assert result.output_json["stderr_truncated"] is True
    assert result.output_json["stdout"]
    assert result.output_json["stderr"]
    assert result.output_json["command_status"] == "success"
    assert result.output_json["started_at"] is not None
    assert result.output_json["finished_at"] is not None

    commands = store.list_commands(session.id)
    assert commands[0]["stdout_truncated"] is True
    assert commands[0]["stderr_truncated"] is True
    assert commands[0]["started_at"] is not None
    assert commands[0]["finished_at"] is not None
    assert commands[0]["command_json"]["command"].startswith("python -c")

    events = _read_jsonl(tmp_path / "sessions" / session.id / "commands.jsonl")
    assert sum(1 for event in events if event["event"] == "output") <= 40
    assert any(
        event["event"] == "output_truncated" and event["stream"] == "stdout"
        for event in events
    )
    assert any(
        event["event"] == "output_truncated" and event["stream"] == "stderr"
        for event in events
    )


@pytest.mark.parametrize(
    ("command_status", "expected_tool_status", "expected_error_message"),
    [
        ("success", "SUCCESS", None),
        ("failed", "FAILED", None),
        ("timeout", "TIMEOUT", None),
        ("cancelled", "FAILED", "cancelled"),
    ],
)
def test_local_command_status_maps_to_tool_status_and_cancelled_error_message(
    command_status: str,
    expected_tool_status: str,
    expected_error_message: str | None,
) -> None:
    from app.cli.hao.local_tools import command_status_to_tool_status

    tool_status, error_message = command_status_to_tool_status(command_status)

    assert tool_status == expected_tool_status
    assert error_message == expected_error_message


def test_preview_write_file_creates_pending_change_without_mutating_file(
    tmp_path: Path,
) -> None:
    store = SessionStore(tmp_path / "hao.db", tmp_path / "sessions")
    session = store.create_session(
        cwd=str(tmp_path),
        agent_id="default",
        mode="confirm",
        target="host",
    )
    target = tmp_path / "notes.md"
    target.write_text("old\n", encoding="utf-8")

    result = execute_local_tool(
        "preview_write_file",
        {"path": "notes.md", "content": "new\n"},
        tmp_path,
        session_store=store,
        session_id=session.id,
    )

    assert result.status == "SUCCESS"
    assert target.read_text(encoding="utf-8") == "old\n"
    change_id = result.output_json["change_id"]
    assert change_id.startswith("change-")
    assert result.output_json["change_status"] == "pending"
    assert "-old" in result.output_json["diff"]
    assert "+new" in result.output_json["diff"]

    change = store.get_pending_change(change_id)
    assert change is not None
    assert change["status"] == "pending"
    assert change["target_paths"] == ["notes.md"]
    assert change["before_hashes"] == {"notes.md": sha256(b"old\n").hexdigest()}
    assert change["after_hashes"] == {"notes.md": sha256(b"new\n").hexdigest()}

    artifact = tmp_path / "sessions" / session.id / "pending-changes" / f"{change_id}.json"
    payload = json.loads(artifact.read_text(encoding="utf-8"))
    assert payload["id"] == change_id
    assert payload["status"] == "pending"


def test_preview_write_file_uses_missing_hash_for_new_file_without_creating_it(
    tmp_path: Path,
) -> None:
    store = SessionStore(tmp_path / "hao.db", tmp_path / "sessions")
    session = store.create_session(
        cwd=str(tmp_path),
        agent_id="default",
        mode="confirm",
        target="host",
    )

    result = execute_local_tool(
        "preview_write_file",
        {"path": "new.txt", "content": "created\n"},
        tmp_path,
        session_store=store,
        session_id=session.id,
    )

    assert result.status == "SUCCESS"
    assert not (tmp_path / "new.txt").exists()
    change = store.get_pending_change(result.output_json["change_id"])
    assert change is not None
    assert change["before_hashes"] == {"new.txt": "__missing__"}
    assert change["after_hashes"] == {"new.txt": sha256(b"created\n").hexdigest()}


def test_commit_write_file_applies_only_by_pending_change_id(tmp_path: Path) -> None:
    store = SessionStore(tmp_path / "hao.db", tmp_path / "sessions")
    session = store.create_session(
        cwd=str(tmp_path),
        agent_id="default",
        mode="confirm",
        target="host",
    )
    target = tmp_path / "notes.md"
    target.write_text("old\n", encoding="utf-8")
    preview = execute_local_tool(
        "preview_write_file",
        {"path": "notes.md", "content": "new\n"},
        tmp_path,
        session_store=store,
        session_id=session.id,
    )

    bad_commit = execute_local_tool(
        "commit_write_file",
        {"path": "notes.md", "content": "bad\n"},
        tmp_path,
        session_store=store,
        session_id=session.id,
    )
    assert bad_commit.status == "FAILED"
    assert target.read_text(encoding="utf-8") == "old\n"

    commit = execute_local_tool(
        "commit_write_file",
        {"change_id": preview.output_json["change_id"]},
        tmp_path,
        session_store=store,
        session_id=session.id,
    )

    assert commit.status == "SUCCESS"
    assert commit.output_json["change_status"] == "committed"
    assert target.read_text(encoding="utf-8") == "new\n"
    change = store.get_pending_change(preview.output_json["change_id"])
    assert change is not None
    assert change["status"] == "committed"


def test_preview_and_commit_apply_patch_are_diff_first(tmp_path: Path) -> None:
    store = SessionStore(tmp_path / "hao.db", tmp_path / "sessions")
    session = store.create_session(
        cwd=str(tmp_path),
        agent_id="default",
        mode="confirm",
        target="host",
    )
    target = tmp_path / "notes.md"
    target.write_text("old\n", encoding="utf-8")
    patch = """--- a/notes.md
+++ b/notes.md
@@ -1 +1 @@
-old
+new
"""

    preview = execute_local_tool(
        "preview_apply_patch",
        {"patch": patch},
        tmp_path,
        session_store=store,
        session_id=session.id,
    )

    assert preview.status == "SUCCESS"
    assert target.read_text(encoding="utf-8") == "old\n"
    assert preview.output_json["change_id"].startswith("change-")
    assert preview.output_json["change_status"] == "pending"

    commit = execute_local_tool(
        "commit_apply_patch",
        {"change_id": preview.output_json["change_id"]},
        tmp_path,
        session_store=store,
        session_id=session.id,
    )

    assert commit.status == "SUCCESS"
    assert target.read_text(encoding="utf-8") == "new\n"
    change = store.get_pending_change(preview.output_json["change_id"])
    assert change is not None
    assert change["status"] == "committed"


def test_commit_pending_change_rejects_stale_hash_without_overwriting_file(
    tmp_path: Path,
) -> None:
    store = SessionStore(tmp_path / "hao.db", tmp_path / "sessions")
    session = store.create_session(
        cwd=str(tmp_path),
        agent_id="default",
        mode="confirm",
        target="host",
    )
    target = tmp_path / "notes.md"
    target.write_text("old\n", encoding="utf-8")
    preview = execute_local_tool(
        "preview_write_file",
        {"path": "notes.md", "content": "new\n"},
        tmp_path,
        session_store=store,
        session_id=session.id,
    )
    target.write_text("external\n", encoding="utf-8")

    commit = execute_local_tool(
        "commit_write_file",
        {"change_id": preview.output_json["change_id"]},
        tmp_path,
        session_store=store,
        session_id=session.id,
    )

    assert commit.status == "FAILED"
    assert commit.output_json["change_status"] == "stale"
    assert target.read_text(encoding="utf-8") == "external\n"
    change = store.get_pending_change(preview.output_json["change_id"])
    assert change is not None
    assert change["status"] == "stale"


def test_reject_pending_change_leaves_workspace_unchanged_and_records_denied(
    tmp_path: Path,
    monkeypatch,
) -> None:
    app = _make_hao_app(tmp_path, monkeypatch, target="host")
    app.session = app.store.create_session(
        cwd=str(tmp_path),
        agent_id="default",
        mode="confirm",
        target="host",
    )
    target = tmp_path / "notes.md"
    target.write_text("old\n", encoding="utf-8")
    preview = execute_local_tool(
        "preview_write_file",
        {"path": "notes.md", "content": "new\n"},
        tmp_path,
        session_store=app.store,
        session_id=app.session.id,
    )

    app._handle_command(f"/reject {preview.output_json['change_id']}")

    assert target.read_text(encoding="utf-8") == "old\n"
    change = app.store.get_pending_change(preview.output_json["change_id"])
    assert change is not None
    assert change["status"] == "rejected"
    assert app.store.list_tool_events(app.session.id)[-1]["status"] == "DENIED"


def test_model_facing_write_file_request_is_converted_to_pending_preview(
    tmp_path: Path,
    monkeypatch,
) -> None:
    app = _make_hao_app(tmp_path, monkeypatch, permission_mode="confirm", target="host")
    app.session = app.store.create_session(
        cwd=str(tmp_path),
        agent_id="default",
        mode="confirm",
        target="host",
    )
    app.run_id = "run-1"

    class FakeClient:
        def record_local_tool_event(self, run_id: str, payload: dict) -> dict:
            del run_id, payload
            return {"tool_call": {"id": "tool-call-1"}}

    app.api_client = FakeClient()  # type: ignore[assignment]
    target = tmp_path / "notes.md"
    target.write_text("old\n", encoding="utf-8")
    event = SSEEvent(
        event="tool_call_requested",
        data={
            "tool_call_id": "tool-1",
            "tool_name": "write_file",
            "input_json": {"path": "notes.md", "content": "new\n"},
        },
        raw="event: tool_call_requested\ndata: {}",
    )

    result_message = app._handle_tool_request(event, "chat")

    assert result_message is None
    assert app.pending_tools == {}
    assert target.read_text(encoding="utf-8") == "old\n"
    changes = app.store.list_pending_changes(app.session.id)
    assert len(changes) == 1
    assert changes[0]["tool_name"] == "write_file"
    assert changes[0]["status"] == "pending"


def test_model_facing_apply_patch_request_is_converted_to_pending_preview(
    tmp_path: Path,
    monkeypatch,
) -> None:
    app = _make_hao_app(tmp_path, monkeypatch, permission_mode="confirm", target="host")
    app.session = app.store.create_session(
        cwd=str(tmp_path),
        agent_id="default",
        mode="confirm",
        target="host",
    )
    app.run_id = "run-1"

    class FakeClient:
        def record_local_tool_event(self, run_id: str, payload: dict) -> dict:
            del run_id, payload
            return {"tool_call": {"id": "tool-call-1"}}

    app.api_client = FakeClient()  # type: ignore[assignment]
    target = tmp_path / "notes.md"
    target.write_text("old\n", encoding="utf-8")
    patch = """--- a/notes.md
+++ b/notes.md
@@ -1 +1 @@
-old
+new
""".replace("++++ b/", "+++ b/")
    event = SSEEvent(
        event="tool_call_requested",
        data={
            "tool_call_id": "tool-1",
            "tool_name": "apply_patch",
            "input_json": {"patch": patch},
        },
        raw="event: tool_call_requested\ndata: {}",
    )

    result_message = app._handle_tool_request(event, "chat")

    assert result_message is None
    assert app.pending_tools == {}
    assert target.read_text(encoding="utf-8") == "old\n"
    changes = app.store.list_pending_changes(app.session.id)
    assert len(changes) == 1
    assert changes[0]["tool_name"] == "apply_patch"
    assert changes[0]["status"] == "pending"


def test_pending_tool_ids_are_prefixed_away_from_change_ids(
    tmp_path: Path,
    monkeypatch,
) -> None:
    app = _make_hao_app(tmp_path, monkeypatch, permission_mode="confirm", target="host")
    app.session = app.store.create_session(
        cwd=str(tmp_path),
        agent_id="default",
        mode="confirm",
        target="host",
    )
    app.run_id = "run-1"
    event = SSEEvent(
        event="tool_call_requested",
        data={
            "tool_call_id": "change-conflict",
            "tool_name": "run_shell",
            "input_json": {"command": "pytest"},
        },
        raw="event: tool_call_requested\ndata: {}",
    )

    result_message = app._handle_tool_request(event, "chat")

    assert result_message is None
    assert "change-conflict" not in app.pending_tools
    assert "tool-change-conflict" in app.pending_tools


def test_approve_pending_change_commits_after_pending_tool_ids(
    tmp_path: Path,
    monkeypatch,
) -> None:
    app = _make_hao_app(tmp_path, monkeypatch, permission_mode="confirm", target="host")
    app.session = app.store.create_session(
        cwd=str(tmp_path),
        agent_id="default",
        mode="confirm",
        target="host",
    )
    target = tmp_path / "notes.md"
    target.write_text("old\n", encoding="utf-8")
    preview = execute_local_tool(
        "preview_write_file",
        {"path": "notes.md", "content": "new\n"},
        tmp_path,
        session_store=app.store,
        session_id=app.session.id,
    )

    HaoApp.approve_change_worker.__wrapped__(app, preview.output_json["change_id"])

    assert target.read_text(encoding="utf-8") == "new\n"
    change = app.store.get_pending_change(preview.output_json["change_id"])
    assert change is not None
    assert change["status"] == "committed"


def test_session_store_migrates_v1_database_without_losing_messages_and_tool_events(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "hao.db"
    sessions_dir = tmp_path / "sessions"
    now = "2026-05-31T00:00:00+00:00"
    with sqlite3.connect(db_path) as connection:
        connection.executescript(
            """
            create table sessions (
                id text primary key,
                cwd text not null,
                agent_id text not null,
                mode text not null,
                target text not null,
                run_id text,
                title text not null,
                created_at text not null,
                updated_at text not null
            );
            create table messages (
                id text primary key,
                session_id text not null references sessions(id) on delete cascade,
                seq integer not null,
                role text not null,
                content text not null,
                state text not null,
                run_id text,
                metadata_json text not null,
                created_at text not null
            );
            create table tool_events (
                id text primary key,
                session_id text not null references sessions(id) on delete cascade,
                run_id text,
                tool_call_id text,
                tool_name text not null,
                status text not null,
                input_json text not null,
                output_json text not null,
                duration_ms integer not null,
                created_at text not null
            );
            """
        )
        connection.execute(
            """
            insert into sessions
            (id, cwd, agent_id, mode, target, run_id, title, created_at, updated_at)
            values (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "session-1",
                "/tmp/work",
                "default",
                "confirm",
                "host",
                "run-1",
                "hao legacy",
                now,
                now,
            ),
        )
        connection.execute(
            """
            insert into messages
            (id, session_id, seq, role, content, state, run_id, metadata_json, created_at)
            values (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("msg-1", "session-1", 1, "user", "hello", "done", "run-1", "{}", now),
        )
        connection.execute(
            """
            insert into messages
            (id, session_id, seq, role, content, state, run_id, metadata_json, created_at)
            values (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "msg-2",
                "session-1",
                2,
                "tool",
                "tool result",
                "done",
                "run-1",
                json.dumps({"tool_name": "read_file"}),
                now,
            ),
        )
        connection.execute(
            """
            insert into tool_events
            (id, session_id, run_id, tool_call_id, tool_name, status, input_json,
             output_json, duration_ms, created_at)
            values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "event-1",
                "session-1",
                "run-1",
                "tool-1",
                "read_file",
                "SUCCESS",
                "{}",
                "{}",
                1,
                now,
            ),
        )

    store = SessionStore(db_path, sessions_dir)

    loaded = store.get_session("session-1")
    assert loaded is not None
    assert loaded.active_leaf_id == "msg-2"
    messages = store.list_messages("session-1")
    assert [message["id"] for message in messages] == ["msg-1", "msg-2"]
    assert messages[0]["parent_id"] is None
    assert messages[0]["children_ids"] == ["msg-2"]
    assert messages[0]["branch_id"] == "msg-1"
    assert messages[1]["parent_id"] == "msg-1"
    assert messages[1]["branch_id"] == "msg-1"
    assert [message["id"] for message in store.list_active_path("session-1")] == [
        "msg-1",
        "msg-2",
    ]
    assert store.list_tool_events("session-1")[0]["id"] == "event-1"
