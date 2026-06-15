from __future__ import annotations

import asyncio
import importlib
import io
import json
import subprocess
import sys
import types
from pathlib import Path
from typing import Any

import httpx
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.model_gateway import ModelStreamChunk
from app.agents.registry import ensure_default_agents
from app.api.agents._workspace_chat_helpers import _workspace_context_messages
from app.api.schemas import AgentChatStreamRequest, ConversationNode
from app.cli.hao.api_client import HarnessApiClient, parse_sse_stream
from app.cli.hao.config import (
    HaoConfig,
    clear_persisted_token,
    load_config,
    load_persisted_config,
    save_auth,
)
from app.cli.hao.local_tools import ToolExecutionResult, execute_local_tool, safe_join
from app.cli.hao.permissions import PermissionEngine, command_is_dangerous
from app.cli.hao.session_store import SessionStore
from app.db.models import AgentEvent, Task, ToolCall, utc_now
from app.main import app
from tests.conftest import AUTH_HEADERS


def test_hao_config_env_overrides_file(tmp_path: Path, monkeypatch) -> None:
    config = HaoConfig(home=tmp_path)
    save_auth(config, api_url="http://stored.example", token="stored-token")
    monkeypatch.setenv("HAO_HOME", str(tmp_path))
    assert load_config().api_url == "http://stored.example"
    monkeypatch.setenv("HAO_API_URL", "http://env.example")
    monkeypatch.setenv("HAO_API_TOKEN", "env-token")

    loaded = load_config()

    assert loaded.api_url == "http://env.example"
    assert loaded.token == "env-token"


def test_hao_logout_clears_persisted_token_but_keeps_api_url(tmp_path: Path) -> None:
    config = HaoConfig(home=tmp_path)
    save_auth(config, api_url="http://stored.example", token="stored-token")

    assert clear_persisted_token(config) is True

    persisted = load_persisted_config({"HAO_HOME": str(tmp_path)})
    assert persisted.api_url == "http://stored.example"
    assert persisted.token == ""
    assert not (tmp_path / "sessions").exists()
    assert not (tmp_path / "hao.db").exists()


def test_hao_logout_is_idempotent_without_persisted_config(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("HAO_HOME", str(tmp_path))
    monkeypatch.setenv("HAO_API_TOKEN", "env-token")
    config = load_config()

    assert config.token == "env-token"
    assert clear_persisted_token(config) is False

    persisted = load_persisted_config({"HAO_HOME": str(tmp_path)})
    assert persisted.token == ""
    assert load_config().token == "env-token"
    assert not config.config_path.exists()


def test_hao_sse_parser_handles_chat_events() -> None:
    events = parse_sse_stream(
        'event: run_created\ndata: {"run_id": "r1"}\n\n'
        'event: delta\ndata: {"content": "hi"}\n\n'
    )

    assert [event.event for event in events] == ["run_created", "delta"]
    assert events[0].data["run_id"] == "r1"
    assert events[1].data["content"] == "hi"


def test_hao_api_client_ignores_environment_proxy_for_local_calls(monkeypatch) -> None:
    client_kwargs: list[dict] = []

    class FakeResponse:
        def __init__(self, payload: dict | None = None) -> None:
            self.payload = payload or {"status": "ok"}

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return self.payload

        def iter_text(self):
            yield 'event: done\ndata: {"ok": true}\n\n'

        def __enter__(self):
            return self

        def __exit__(self, *args) -> None:
            return None

    class FakeClient:
        def __init__(self, **kwargs) -> None:
            client_kwargs.append(kwargs)

        def __enter__(self):
            return self

        def __exit__(self, *args) -> None:
            return None

        def get(self, *args, **kwargs) -> FakeResponse:
            del args, kwargs
            return FakeResponse({"status": "ok"})

        def stream(self, *args, **kwargs) -> FakeResponse:
            del args, kwargs
            return FakeResponse()

    monkeypatch.setattr("app.cli.hao.api_client.httpx.Client", FakeClient)

    client = HarnessApiClient("http://127.0.0.1:8000", "token", timeout=5)

    assert client.health() == {"status": "ok"}
    assert [event.event for event in client.stream_chat("default", {"goal": "hi"})] == [
        "done"
    ]
    assert client_kwargs == [
        {"timeout": 5, "trust_env": False},
        {"timeout": None, "trust_env": False},
    ]


def test_hao_bridge_pair_once_registers_and_reports_fake_task(tmp_path: Path, monkeypatch) -> None:
    calls: list[tuple[str, dict]] = []

    class FakeBridgeClient:
        def __init__(self, api_url: str, token: str = "", timeout: float = 120.0) -> None:
            calls.append(("init", {"api_url": api_url, "token": token, "timeout": timeout}))

        def register_local_agent_connection(self, **payload) -> dict:
            calls.append(("register", payload))
            return {
                "connection": {"id": "connection-1"},
                "device_token": "device-token-1",
            }

        def heartbeat_local_agent_connection(self, **payload) -> dict:
            calls.append(("heartbeat", payload))
            return {"connection": {"id": payload["connection_id"]}}

        def pull_local_agent_bridge_tasks(self, **payload) -> dict:
            calls.append(("pull", payload))
            return {
                "items": [
                    {
                        "id": "bridge-task-1",
                        "payload": {"message": "hello local"},
                    }
                ]
            }

        def ack_local_agent_bridge_task(self, **payload) -> dict:
            calls.append(("ack", payload))
            return {"id": payload["bridge_task_id"]}

        def report_local_agent_bridge_event(self, **payload) -> dict:
            calls.append(("event", payload))
            return {"receipt_id": payload["payload"]["event_id"], "duplicate": False}

    monkeypatch.setenv("HAO_HOME", str(tmp_path))
    hao_main_module = importlib.import_module("app.cli.hao.main")
    monkeypatch.setattr(hao_main_module, "HarnessApiClient", FakeBridgeClient)

    exit_code = hao_main_module.main(
        [
            "bridge",
            "pair",
            "--api",
            "http://127.0.0.1:8000",
            "--pair-token",
            "pair-token",
            "--pair-code",
            "ABC123",
            "--adapter",
            "fake",
            "--cwd",
            str(tmp_path),
            "--once",
        ]
    )

    assert exit_code == 0
    bridge_state = tmp_path / "bridge.json"
    assert bridge_state.exists()
    assert bridge_state.stat().st_mode & 0o777 == 0o600
    persisted = bridge_state.read_text(encoding="utf-8")
    assert '"cwd"' not in persisted
    assert "device-token-1" not in persisted
    assert "device_token_ref" in persisted
    assert str(tmp_path) not in persisted
    token_file = tmp_path / "bridge.device-token"
    assert token_file.read_text(encoding="utf-8") == "device-token-1"
    assert token_file.stat().st_mode & 0o777 == 0o600
    assert [name for name, _payload in calls].count("event") == 2
    register = next(payload for name, payload in calls if name == "register")
    assert register["adapter_kind"] == "fake"
    assert register["pair_token"] == "pair-token"
    assert register["workspace_root"] == str(tmp_path)
    heartbeat = next(payload for name, payload in calls if name == "heartbeat")
    assert heartbeat["connection_id"] == "connection-1"
    ack = next(payload for name, payload in calls if name == "ack")
    assert ack["bridge_task_id"] == "bridge-task-1"
    done = [payload for name, payload in calls if name == "event"][-1]["payload"]
    assert done["event_type"] == "assistant_done"
    assert "hello local" in done["content"]


def test_hao_bridge_task_passes_harness_context_to_headless(
    tmp_path: Path,
    monkeypatch,
) -> None:
    hao_main_module = importlib.import_module("app.cli.hao.main")
    monkeypatch.setenv("HAO_HOME", str(tmp_path / "hao-home"))
    config = hao_main_module.load_config()
    events: list[dict] = []
    captured: dict[str, object] = {}

    class FakeClient:
        def report_local_agent_bridge_event(self, *, device_token: str, payload: dict) -> dict:
            events.append({"device_token": device_token, **payload})
            return {"receipt_id": payload["event_id"], "duplicate": False}

    def fake_run_headless_once(**kwargs) -> object:
        captured.update(kwargs)
        return hao_main_module.HeadlessRunResult(
            exit_code=0,
            status="completed",
            stdout_json={"assistant": "hao done"},
        )

    monkeypatch.setattr(hao_main_module, "run_headless_once", fake_run_headless_once)

    hao_main_module._handle_hao_bridge_task(
        config=config,
        state={"cwd": str(tmp_path)},
        client=FakeClient(),
        device_token="device-token",
        task={
            "id": "bridge-task-1",
            "payload": {
                "message": "hello local",
                "run_id": "run-1",
                "agent_id": "default",
                "resume_mode": "native_resume",
                "model_provider": "deepseek",
                "model_name": "deepseek-v4",
                "conversation_context": [
                    {"role": "user", "content": "prior user"},
                    {"role": "assistant", "content": "prior answer"},
                ],
                "tool_mentions": [{"name": "read_file", "source": "local"}],
                "attachment_names": ["README.md"],
                "attachments": [
                    {
                        "name": "README.md",
                        "content_text": "attachment body",
                    },
                ],
                "compressed_context": {"summary": "compressed summary"},
            },
        },
    )

    prompt = str(captured["prompt"])
    assert "You are running under the AI Harness local-agent bridge as the hao adapter." in prompt
    assert "Harness selected model: provider=deepseek, model=deepseek-v4." in prompt
    assert "Harness requested tools: local:read_file." in prompt
    assert "Harness attachments: README.md." in prompt
    assert "Compressed workspace context: compressed summary" in prompt
    assert "Attachment README.md: attachment body" in prompt
    assert "user: prior user" in prompt
    assert "assistant: prior answer" in prompt
    assert "User message:\nhello local" in prompt
    assert captured["model_provider"] == "deepseek"
    assert captured["model_name"] == "deepseek-v4"
    assert events[-1]["event_type"] == "assistant_done"
    assert events[-1]["content"] == "hao done"


def test_hao_bridge_task_uses_plan_command_and_stream_token(
    tmp_path: Path,
    monkeypatch,
) -> None:
    hao_main_module = importlib.import_module("app.cli.hao.main")
    monkeypatch.setenv("HAO_HOME", str(tmp_path / "hao-home"))
    config = hao_main_module.load_config()
    events: list[dict] = []
    captured: dict[str, object] = {}
    stream_clients: list[Any] = []

    class FakeBridgeClient:
        api_url = "http://127.0.0.1:8000"

        def report_local_agent_bridge_event(self, *, device_token: str, payload: dict) -> dict:
            events.append({"device_token": device_token, **payload})
            return {"receipt_id": payload["event_id"], "duplicate": False}

    class FakeStreamClient:
        def __init__(self, api_url: str, token: str = "", timeout: float = 120.0) -> None:
            self.api_url = api_url
            self.token = token
            self.timeout = timeout
            stream_clients.append(self)

    def fake_run_headless_once(**kwargs) -> object:
        captured.update(kwargs)
        return hao_main_module.HeadlessRunResult(
            exit_code=0,
            status="completed",
            stdout_json={"assistant": "plan ready"},
        )

    monkeypatch.setattr(hao_main_module, "HarnessApiClient", FakeStreamClient)
    monkeypatch.setattr(hao_main_module, "run_headless_once", fake_run_headless_once)

    hao_main_module._handle_hao_bridge_task(
        config=config,
        state={"cwd": str(tmp_path), "api_url": "http://127.0.0.1:8000"},
        client=FakeBridgeClient(),
        device_token="device-token",
        task={
            "id": "bridge-plan-task",
            "payload": {
                "message": "plan before acting",
                "run_id": "run-plan",
                "agent_id": "default",
                "workspace_request": {"mode": "plan"},
                "harness_stream_token": "stream-token",
            },
        },
    )

    assert captured["command"] == "plan"
    assert captured["api_client"] is stream_clients[0]
    assert stream_clients[0].api_url == "http://127.0.0.1:8000"
    assert stream_clients[0].token == "stream-token"
    assert events[-1]["device_token"] == "device-token"
    assert events[-1]["event_type"] == "assistant_done"
    assert events[-1]["content"] == "plan ready"


def test_hao_headless_forwards_bridge_deltas_and_model_call_usage(tmp_path: Path) -> None:
    hao_main_module = importlib.import_module("app.cli.hao.main")
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    store = SessionStore(tmp_path / "hao.db", tmp_path / "sessions")
    bridge_events: list[dict] = []

    class FakeClient:
        def stream_chat(self, agent_id: str, payload: dict):
            assert agent_id == "default"
            assert payload["local_bridge_task_id"] == "bridge-task-1"
            yield hao_main_module.SSEEvent(
                event="run_created",
                data={"run_id": "run-1"},
                raw='event: run_created\ndata: {"run_id":"run-1"}\n\n',
            )
            yield hao_main_module.SSEEvent(
                event="delta",
                data={"content": "Hello "},
                raw='event: delta\ndata: {"content":"Hello "}\n\n',
            )
            yield hao_main_module.SSEEvent(
                event="delta",
                data={"content": "world"},
                raw='event: delta\ndata: {"content":"world"}\n\n',
            )
            yield hao_main_module.SSEEvent(
                event="usage",
                data={"model_call_id": "model-call-1", "prompt_tokens": 3, "completion_tokens": 2},
                raw='event: usage\ndata: {"model_call_id":"model-call-1"}\n\n',
            )
            yield hao_main_module.SSEEvent(
                event="done",
                data={},
                raw="event: done\ndata: {}\n\n",
            )

        def report_local_agent_bridge_event(self, *, device_token: str, payload: dict) -> dict:
            bridge_events.append({"device_token": device_token, **payload})
            return {"receipt_id": payload["event_id"], "duplicate": False}

    result = hao_main_module.run_headless_once(
        command="act",
        prompt="say hello",
        cwd=workspace,
        session_store=store,
        session_id=None,
        permission_mode="confirm",
        target="host",
        max_auto_turns=1,
        api_client=FakeClient(),
        agent_id="default",
        model_provider="deepseek",
        model_name="deepseek-v4",
        bridge_context=hao_main_module.BridgeToolContext(
            bridge_task_id="bridge-task-1",
            device_token="device-token",
        ),
    )

    assert result.exit_code == 0
    assert result.stdout_json["assistant"] == "Hello world"
    assert result.stdout_json["model_call_id"] == "model-call-1"
    assert result.stdout_json["bridge_delta_count"] == 2
    assert [event["event_type"] for event in bridge_events] == [
        "assistant_delta",
        "assistant_delta",
    ]
    assert [event["content"] for event in bridge_events] == ["Hello ", "world"]
    assert [event["sequence"] for event in bridge_events] == [1, 2]
    assert [event["event_id"] for event in bridge_events] == [
        "bridge-task-1:delta:1",
        "bridge-task-1:delta:2",
    ]


def test_hao_bridge_pending_tool_preserves_selected_model_for_resume(
    tmp_path: Path,
    monkeypatch,
) -> None:
    hao_main_module = importlib.import_module("app.cli.hao.main")
    monkeypatch.setenv("HAO_HOME", str(tmp_path / "hao-home"))
    config = hao_main_module.load_config()
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "README.md").write_text("hello from workspace\n", encoding="utf-8")
    state = {"cwd": str(workspace), "api_url": "http://127.0.0.1:8000"}
    calls: list[tuple[str, dict]] = []
    shared = {"pending": True, "stream_count": 0}

    class FakeClient:
        def __init__(
            self,
            api_url: str = "http://127.0.0.1:8000",
            token: str = "",
            timeout: float = 30.0,
        ) -> None:
            self.api_url = api_url
            self.token = token
            self.timeout = timeout
            calls.append(("client_init", {"api_url": api_url, "token": token, "timeout": timeout}))

        def stream_chat(self, agent_id: str, payload: dict):
            calls.append(
                (
                    "stream",
                    {"agent_id": agent_id, "payload": payload, "client_token": self.token},
                )
            )
            shared["stream_count"] += 1
            yield hao_main_module.SSEEvent(
                event="run_created",
                data={"run_id": "run-local"},
                raw='event: run_created\ndata: {"run_id":"run-local"}\n\n',
            )
            if shared["stream_count"] > 1:
                yield hao_main_module.SSEEvent(
                    event="delta",
                    data={"content": "done with approved tool"},
                    raw='event: delta\ndata: {"content":"done with approved tool"}\n\n',
                )
                yield hao_main_module.SSEEvent(
                    event="usage",
                    data={
                        "model_call_id": "resume-model-call-1",
                        "prompt_tokens": 2,
                        "completion_tokens": 3,
                    },
                    raw='event: usage\ndata: {"model_call_id":"resume-model-call-1"}\n\n',
                )
                yield hao_main_module.SSEEvent(
                    event="done",
                    data={},
                    raw="event: done\ndata: {}\n\n",
                )
                return
            yield hao_main_module.SSEEvent(
                event="delta",
                data={"content": "pre approval context"},
                raw='event: delta\ndata: {"content":"pre approval context"}\n\n',
            )
            yield hao_main_module.SSEEvent(
                event="tool_call_requested",
                data={
                    "tool_name": "read_file",
                    "tool_call_id": "tool-read",
                    "input_json": {"path": "README.md"},
                },
                raw="event: tool_call_requested\ndata: {}\n\n",
            )

        def create_local_agent_tool_request(self, *, device_token: str, payload: dict) -> dict:
            calls.append(("tool_request", {"device_token": device_token, **payload}))
            return {
                "tool_request_id": payload["tool_request_id"],
                "bridge_task_id": payload["bridge_task_id"],
                "tool_call_id": "backend-tool-read",
                "approval_id": "approval-read",
                "decision": "approval_required" if shared["pending"] else "approved",
                "status": "approval_required" if shared["pending"] else "approved",
                "executable": not shared["pending"],
                "server_execution": False,
                "tool_name": payload["tool_name"],
                "input_json": payload["input_json"],
                "decision_json": {
                    "metadata": {
                        **payload["metadata"],
                        "harness_stream_token": "fresh-scoped-stream-token",
                    }
                },
            }

        def list_pending_local_agent_tool_requests(self, *, device_token: str) -> dict:
            calls.append(("list_pending", {"device_token": device_token}))
            return {"items": []}

        def get_local_agent_tool_decision(
            self,
            *,
            device_token: str,
            tool_request_id: str,
        ) -> dict:
            calls.append(
                (
                    "decision",
                    {"device_token": device_token, "tool_request_id": tool_request_id},
                )
            )
            return {
                "tool_request_id": tool_request_id,
                "bridge_task_id": "bridge-task-1",
                "decision": "approved",
                "status": "approved",
                "executable": True,
                "server_execution": False,
                "tool_name": "read_file",
                "input_json": {"path": "README.md"},
                "reason": "",
            }

        def report_local_agent_tool_result(
            self,
            *,
            device_token: str,
            tool_request_id: str,
            payload: dict,
        ) -> dict:
            calls.append(
                (
                    "tool_result",
                    {"device_token": device_token, "tool_request_id": tool_request_id, **payload},
                )
            )
            return {
                "tool_request_id": tool_request_id,
                "tool_call_id": "backend-tool-read",
                "decision": "succeeded",
                "status": "succeeded",
            }

        def report_local_agent_bridge_event(self, *, device_token: str, payload: dict) -> dict:
            calls.append(("bridge_event", {"device_token": device_token, **payload}))
            return {"receipt_id": payload["event_id"], "duplicate": False}

    monkeypatch.setattr(hao_main_module, "HarnessApiClient", FakeClient)
    client = FakeClient(token="daemon-token")
    hao_main_module._handle_hao_bridge_task(
        config=config,
        state=state,
        client=client,
        device_token="device-token",
        task={
            "id": "bridge-task-1",
            "payload": {
                "message": "read the file",
                "agent_id": "default",
                "run_id": "run-local",
                "model_provider": "deepseek",
                "model_name": "deepseek-v4",
                "harness_stream_token": "queued-scoped-stream-token",
            },
        },
    )

    persisted_state = hao_main_module._load_bridge_state(config)
    [pending_tool] = persisted_state["pending_tool_requests"]
    assert pending_tool["model_provider"] == "deepseek"
    assert pending_tool["model_name"] == "deepseek-v4"
    assert pending_tool["harness_stream_token"] == "fresh-scoped-stream-token"
    assert pending_tool["bridge_delta_count"] == "1"
    tool_request = next(payload for name, payload in calls if name == "tool_request")
    assert tool_request["metadata"]["model_provider"] == "deepseek"
    assert tool_request["metadata"]["model_name"] == "deepseek-v4"
    assert tool_request["metadata"]["bridge_delta_count"] == 1

    shared["pending"] = False
    hao_main_module._resume_bridge_pending_tools(
        config=config,
        state=persisted_state,
        client=client,
        device_token="device-token",
    )

    followup_streams = [payload for name, payload in calls if name == "stream"]
    assert len(followup_streams) == 2
    assert [stream["client_token"] for stream in followup_streams] == [
        "queued-scoped-stream-token",
        "fresh-scoped-stream-token",
    ]
    assert followup_streams[-1]["payload"]["model_provider"] == "deepseek"
    assert followup_streams[-1]["payload"]["model_name"] == "deepseek-v4"
    bridge_events = [payload for name, payload in calls if name == "bridge_event"]
    assert [event["event_type"] for event in bridge_events] == [
        "assistant_delta",
        "assistant_delta",
        "assistant_done",
    ]
    assert bridge_events[0]["content"] == "pre approval context"
    assert bridge_events[0]["sequence"] == 1
    assert bridge_events[1]["content"] == "done with approved tool"
    assert bridge_events[1]["sequence"] == 2
    assert bridge_events[2]["content"] == "done with approved tool"
    assert bridge_events[2]["sequence"] == 3
    assert bridge_events[2]["metadata"]["model_call_id"] == "resume-model-call-1"
    assert bridge_events[2]["metadata"]["usage"]["completion_tokens"] == 3
    reloaded_state = hao_main_module._load_bridge_state(config)
    assert reloaded_state.get("pending_tool_requests") in (None, [])


def test_hao_bridge_daemon_uses_protected_state_without_device_token_argv(
    tmp_path: Path,
    monkeypatch,
) -> None:
    calls: list[tuple[str, dict]] = []
    popen_commands: list[list[str]] = []

    class FakeBridgeClient:
        def __init__(self, api_url: str, token: str = "", timeout: float = 120.0) -> None:
            calls.append(("init", {"api_url": api_url, "token": token, "timeout": timeout}))

        def register_local_agent_connection(self, **payload) -> dict:
            calls.append(("register", payload))
            return {
                "connection": {"id": "connection-1"},
                "device_token": "device-token-secret",
            }

    class FakePopen:
        def __init__(self, command: list[str], **kwargs) -> None:
            popen_commands.append(command)
            calls.append(("popen", kwargs))

    monkeypatch.setenv("HAO_HOME", str(tmp_path))
    hao_main_module = importlib.import_module("app.cli.hao.main")
    monkeypatch.setattr(hao_main_module, "HarnessApiClient", FakeBridgeClient)
    monkeypatch.setattr(hao_main_module.subprocess, "Popen", FakePopen)

    exit_code = hao_main_module.main(
        [
            "bridge",
            "pair",
            "--api",
            "http://127.0.0.1:8000",
            "--pair-token",
            "pair-token",
            "--pair-code",
            "ABC123",
            "--adapter",
            "fake",
            "--cwd",
            str(tmp_path),
            "--daemon",
        ]
    )

    assert exit_code == 0
    bridge_state = tmp_path / "bridge.json"
    assert bridge_state.stat().st_mode & 0o777 == 0o600
    persisted = bridge_state.read_text(encoding="utf-8")
    assert "device-token-secret" not in persisted
    assert "device_token_ref" in persisted
    assert '"cwd"' not in persisted
    assert str(tmp_path) not in persisted
    token_file = tmp_path / "bridge.device-token"
    assert token_file.read_text(encoding="utf-8") == "device-token-secret"
    assert token_file.stat().st_mode & 0o777 == 0o600
    command = popen_commands[0]
    assert "--device-token" not in command
    assert "device-token-secret" not in command
    assert "--cwd" in command
    assert str(tmp_path) in command


def test_hao_bridge_pair_without_adapter_auto_registers_detected_local_agents(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    calls: list[tuple[str, dict]] = []
    popen_commands: list[list[str]] = []
    popen_kwargs: list[dict] = []

    class FakeBridgeClient:
        def __init__(self, api_url: str, token: str = "", timeout: float = 120.0) -> None:
            calls.append(("init", {"api_url": api_url, "token": token, "timeout": timeout}))

        def register_local_agent_connection(self, **payload) -> dict:
            calls.append(("register", payload))
            adapter_kind = payload["adapter_kind"]
            return {
                "connection": {"id": f"{adapter_kind}-connection"},
                "device_token": f"{adapter_kind}-device-token",
            }

    class FakePopen:
        def __init__(self, command: list[str], **kwargs) -> None:
            popen_commands.append(command)
            popen_kwargs.append(kwargs)

    monkeypatch.setenv("HAO_HOME", str(tmp_path))
    hao_main_module = importlib.import_module("app.cli.hao.main")
    codex_probe = hao_main_module.CodexCliProbe(
        installed=True,
        executable="/usr/local/bin/codex",
        version="codex 1.0",
        exec_help="--json --output-last-message -C --sandbox read-only",
        resume_help="resume --json --output-last-message -c",
    )
    monkeypatch.setattr(hao_main_module, "_probe_codex_cli", lambda: codex_probe)
    monkeypatch.setattr(
        hao_main_module,
        "_probe_claude_code_cli",
        lambda: _claude_probe(hao_main_module),
    )
    monkeypatch.setattr(hao_main_module, "HarnessApiClient", FakeBridgeClient)
    monkeypatch.setattr(hao_main_module.subprocess, "Popen", FakePopen)

    exit_code = hao_main_module.main(
        [
            "bridge",
            "pair",
            "--api",
            "http://127.0.0.1:8000",
            "--pair-token",
            "pair-token",
            "--pair-code",
            "ABC123",
            "--cwd",
            str(tmp_path),
            "--daemon",
        ]
    )

    assert exit_code == 0
    registered = [payload for name, payload in calls if name == "register"]
    assert [payload["adapter_kind"] for payload in registered] == [
        "hao",
        "codex",
        "claude_code",
    ]
    assert (tmp_path / "bridges" / "hao" / "bridge.json").exists()
    assert (tmp_path / "bridges" / "codex" / "bridge.json").exists()
    assert (tmp_path / "bridges" / "claude_code" / "bridge.json").exists()
    assert len(popen_commands) == 3
    assert [
        kwargs["env"]["HAO_HOME"]
        for kwargs in popen_kwargs
    ] == [
        str(tmp_path / "bridges" / "hao"),
        str(tmp_path / "bridges" / "codex"),
        str(tmp_path / "bridges" / "claude_code"),
    ]
    assert all("--device-token" not in command for command in popen_commands)
    stdout_lines = [
        json.loads(line)
        for line in capsys.readouterr().out.splitlines()
        if line.strip().startswith("{")
    ]
    paired_lines = [line for line in stdout_lines if line["status"] == "paired"]
    daemon_lines = [line for line in stdout_lines if line["status"] == "daemon_started"]
    assert [line["adapter_kind"] for line in paired_lines] == [
        "hao",
        "codex",
        "claude_code",
    ]
    assert [line["adapter_kind"] for line in daemon_lines] == [
        "hao",
        "codex",
        "claude_code",
    ]
    assert all(line["next_step"] == "return_to_platform_refresh_discovery" for line in paired_lines)
    assert "勾选确认后才会接入" in paired_lines[0]["message"]
    assert "我已执行，刷新识别" in daemon_lines[0]["message"]


def test_hao_bridge_state_migrates_raw_device_token_out_of_bridge_json(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("HAO_HOME", str(tmp_path))
    hao_main_module = importlib.import_module("app.cli.hao.main")
    config = load_config()
    (tmp_path / "bridge.json").write_text(
        '{"api_url": "http://127.0.0.1:8000", "connection_id": "connection-1", '
        '"device_token": "legacy-device-token", "adapter_kind": "fake"}',
        encoding="utf-8",
    )

    state = hao_main_module._load_bridge_state(config)

    assert state["device_token"] == "legacy-device-token"
    bridge_json = (tmp_path / "bridge.json").read_text(encoding="utf-8")
    assert "legacy-device-token" not in bridge_json
    assert "device_token_ref" in bridge_json
    token_file = tmp_path / "bridge.device-token"
    assert token_file.read_text(encoding="utf-8") == "legacy-device-token"
    assert token_file.stat().st_mode & 0o777 == 0o600


def test_hao_bridge_v4_codex_pair_fails_before_register_when_unavailable(
    tmp_path: Path,
    monkeypatch,
) -> None:
    calls: list[tuple[str, dict]] = []

    class FakeBridgeClient:
        def __init__(self, api_url: str, token: str = "", timeout: float = 120.0) -> None:
            calls.append(("init", {"api_url": api_url, "token": token, "timeout": timeout}))

        def register_local_agent_connection(self, **payload) -> dict:
            calls.append(("register", payload))
            return {}

    monkeypatch.setenv("HAO_HOME", str(tmp_path))
    hao_main_module = importlib.import_module("app.cli.hao.main")
    monkeypatch.setattr(hao_main_module, "HarnessApiClient", FakeBridgeClient)
    monkeypatch.setattr(hao_main_module.shutil, "which", lambda name: None)

    exit_code = hao_main_module.main(
        [
            "bridge",
            "pair",
            "--api",
            "http://127.0.0.1:8000",
            "--pair-token",
            "pair-token",
            "--pair-code",
            "ABC123",
            "--adapter",
            "codex",
            "--cwd",
            str(tmp_path),
        ]
    )

    assert exit_code == 1
    assert [name for name, _payload in calls] == []
    assert not (tmp_path / "bridge.json").exists()


def test_hao_bridge_v4_codex_state_uses_workspace_sidecar_and_safe_daemon_argv(
    tmp_path: Path,
    monkeypatch,
) -> None:
    calls: list[tuple[str, dict]] = []
    popen_commands: list[list[str]] = []
    popen_kwargs: list[dict] = []

    class FakeBridgeClient:
        def __init__(self, api_url: str, token: str = "", timeout: float = 120.0) -> None:
            calls.append(("init", {"api_url": api_url, "token": token, "timeout": timeout}))

        def register_local_agent_connection(self, **payload) -> dict:
            calls.append(("register", payload))
            return {
                "connection": {"id": "codex-connection-1"},
                "device_token": "codex-device-token",
            }

    class FakePopen:
        def __init__(self, command: list[str], **kwargs) -> None:
            popen_commands.append(command)
            popen_kwargs.append(kwargs)

    monkeypatch.setenv("HAO_HOME", str(tmp_path))
    hao_main_module = importlib.import_module("app.cli.hao.main")
    probe = hao_main_module.CodexCliProbe(
        installed=True,
        executable="/usr/local/bin/codex",
        version="codex 1.0",
        exec_help="--json --output-last-message -C --sandbox read-only",
        resume_help="resume --json --output-last-message -c",
    )
    monkeypatch.setattr(hao_main_module, "_probe_codex_cli", lambda: probe)
    monkeypatch.setattr(hao_main_module, "HarnessApiClient", FakeBridgeClient)
    monkeypatch.setattr(hao_main_module.subprocess, "Popen", FakePopen)

    exit_code = hao_main_module.main(
        [
            "bridge",
            "pair",
            "--api",
            "http://127.0.0.1:8000",
            "--pair-token",
            "pair-token",
            "--pair-code",
            "ABC123",
            "--adapter",
            "codex",
            "--cwd",
            str(tmp_path),
            "--daemon",
        ]
    )

    assert exit_code == 0
    bridge_json = (tmp_path / "bridge.json").read_text(encoding="utf-8")
    assert "codex-device-token" not in bridge_json
    assert str(tmp_path) not in bridge_json
    assert '"cwd"' not in bridge_json
    assert "workspace_identity_hash" in bridge_json
    assert "workspace_root_ref" in bridge_json
    workspace_sidecar = tmp_path / "bridge.workspace-root"
    assert workspace_sidecar.read_text(encoding="utf-8") == str(tmp_path.resolve())
    assert workspace_sidecar.stat().st_mode & 0o777 == 0o600
    register = next(payload for name, payload in calls if name == "register")
    assert register["adapter_kind"] == "codex"
    assert register["metadata"]["workspace_identity_hash"]
    assert register["risk_capabilities"] == ["host_read", "host_write", "shell", "git", "network"]
    command = popen_commands[0]
    assert "--cwd" not in command
    assert str(tmp_path) not in command
    assert "codex-device-token" not in command
    assert popen_kwargs[0]["cwd"] != str(tmp_path)


def _claude_probe(hao_main_module, *, executable: str = "/opt/claude/bin/claude"):
    help_text = (
        "--bare -p --print --output-format stream-json --include-partial-messages "
        "--no-session-persistence --permission-mode --tools"
    )
    return hao_main_module.ClaudeCodeCliProbe(
        installed=True,
        executable=executable,
        version="claude 1.0",
        help_text=help_text,
        print_help=help_text,
    )


def _claude_sdk_probe(hao_main_module, *, installed: bool = True):
    return hao_main_module.ClaudeAgentSdkProbe(
        installed=installed,
        version="0.1-test" if installed else "",
        error_message="" if installed else "sdk missing",
        symbols=(
            "ClaudeSDKClient",
            "ClaudeAgentOptions",
            "PermissionResultAllow",
            "PermissionResultDeny",
            "HookMatcher",
            "AssistantMessage",
        )
        if installed
        else (),
    )


def _install_fake_claude_agent_sdk(monkeypatch, captured: dict[str, Any]) -> None:
    sdk_module = types.ModuleType("claude_agent_sdk")
    types_module = types.ModuleType("claude_agent_sdk.types")
    sdk_module.__version__ = "0.1.80-test"

    class HookMatcher:
        def __init__(
            self,
            *,
            matcher: str | None = None,
            hooks: list | None = None,
            timeout: float | None = None,
        ) -> None:
            self.matcher = matcher
            self.hooks = hooks or []
            self.timeout = timeout

    class PermissionResultAllow:
        def __init__(self, *, updated_input: dict | None = None) -> None:
            self.updated_input = updated_input or {}

    class PermissionResultDeny:
        def __init__(self, *, message: str = "") -> None:
            self.message = message

    class AssistantMessage:
        def __init__(self, content: str) -> None:
            self.content = content

    class ClaudeAgentOptions:
        def __init__(
            self,
            *,
            permission_mode: str | None = None,
            allowed_tools: list | None = None,
            can_use_tool=None,
            hooks: dict | None = None,
            setting_sources: list | None = None,
            disallowed_tools: list | None = None,
            mcp_servers: dict | None = None,
            strict_mcp_config: bool | None = None,
            agents: dict | None = None,
            plugins: list | None = None,
            skills: list | None = None,
            include_hook_events: bool | None = None,
            cwd: str | None = None,
        ) -> None:
            captured["options_kwargs"] = {
                "permission_mode": permission_mode,
                "allowed_tools": allowed_tools,
                "can_use_tool": can_use_tool,
                "hooks": hooks,
                "setting_sources": setting_sources,
                "disallowed_tools": disallowed_tools,
                "mcp_servers": mcp_servers,
                "strict_mcp_config": strict_mcp_config,
                "agents": agents,
                "plugins": plugins,
                "skills": skills,
                "include_hook_events": include_hook_events,
                "cwd": cwd,
            }

    class ClaudeSDKClient:
        def __init__(self, options=None) -> None:
            captured["client_options"] = options

        async def __aenter__(self):
            captured["entered"] = True
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:
            captured["exited"] = True

        async def query(self, prompt, session_id: str = "default") -> None:
            captured["query_session_id"] = session_id
            captured["prompt_is_streaming"] = hasattr(prompt, "__aiter__")
            captured["prompt_items"] = []
            async for item in prompt:
                captured["prompt_items"].append(item)

        async def receive_response(self):
            yield AssistantMessage("sdk bridge reply")

    sdk_module.ClaudeSDKClient = ClaudeSDKClient
    sdk_module.ClaudeAgentOptions = ClaudeAgentOptions
    sdk_module.PermissionResultAllow = PermissionResultAllow
    sdk_module.PermissionResultDeny = PermissionResultDeny
    sdk_module.HookMatcher = HookMatcher
    sdk_module.AssistantMessage = AssistantMessage
    types_module.PermissionResultAllow = PermissionResultAllow
    types_module.PermissionResultDeny = PermissionResultDeny
    types_module.HookMatcher = HookMatcher
    types_module.AssistantMessage = AssistantMessage
    monkeypatch.setitem(sys.modules, "claude_agent_sdk", sdk_module)
    monkeypatch.setitem(sys.modules, "claude_agent_sdk.types", types_module)


def test_hao_bridge_v5_claude_pair_fails_before_register_when_unavailable(
    tmp_path: Path,
    monkeypatch,
) -> None:
    calls: list[tuple[str, dict]] = []

    class FakeBridgeClient:
        def __init__(self, api_url: str, token: str = "", timeout: float = 120.0) -> None:
            calls.append(("init", {"api_url": api_url, "token": token, "timeout": timeout}))

        def register_local_agent_connection(self, **payload) -> dict:
            calls.append(("register", payload))
            return {}

    monkeypatch.setenv("HAO_HOME", str(tmp_path))
    hao_main_module = importlib.import_module("app.cli.hao.main")
    monkeypatch.setattr(hao_main_module, "HarnessApiClient", FakeBridgeClient)
    monkeypatch.setattr(
        hao_main_module,
        "_probe_claude_code_cli",
        lambda: hao_main_module.ClaudeCodeCliProbe(
            installed=False,
            error_message="claude executable not found",
        ),
    )

    exit_code = hao_main_module.main(
        [
            "bridge",
            "pair",
            "--api",
            "http://127.0.0.1:8000",
            "--pair-token",
            "pair-token",
            "--pair-code",
            "ABC123",
            "--adapter",
            "claude_code",
            "--cwd",
            str(tmp_path),
        ]
    )

    assert exit_code == 1
    assert [name for name, _payload in calls] == []
    assert not (tmp_path / "bridge.json").exists()


def test_hao_bridge_v6_claude_pair_fails_before_register_when_sdk_unavailable(
    tmp_path: Path,
    monkeypatch,
) -> None:
    calls: list[tuple[str, dict]] = []

    class FakeBridgeClient:
        def __init__(self, api_url: str, token: str = "", timeout: float = 120.0) -> None:
            calls.append(("init", {"api_url": api_url, "token": token, "timeout": timeout}))

        def register_local_agent_connection(self, **payload) -> dict:
            calls.append(("register", payload))
            return {}

    monkeypatch.setenv("HAO_HOME", str(tmp_path))
    hao_main_module = importlib.import_module("app.cli.hao.main")
    monkeypatch.setattr(hao_main_module, "HarnessApiClient", FakeBridgeClient)
    monkeypatch.setattr(
        hao_main_module,
        "_probe_claude_code_cli",
        lambda: _claude_probe(hao_main_module),
    )
    monkeypatch.setattr(
        hao_main_module,
        "_probe_claude_agent_sdk",
        lambda: _claude_sdk_probe(hao_main_module, installed=False),
    )

    exit_code = hao_main_module.main(
        [
            "bridge",
            "pair",
            "--api",
            "http://127.0.0.1:8000",
            "--pair-token",
            "pair-token",
            "--pair-code",
            "ABC123",
            "--adapter",
            "claude_code",
            "--permission-bridge",
            "sdk",
            "--cwd",
            str(tmp_path),
        ]
    )

    assert exit_code == 1
    assert [name for name, _payload in calls] == []
    assert not (tmp_path / "bridge.json").exists()


def test_hao_bridge_v5_claude_state_uses_workspace_sidecar_and_safe_daemon_argv(
    tmp_path: Path,
    monkeypatch,
) -> None:
    calls: list[tuple[str, dict]] = []
    popen_commands: list[list[str]] = []
    popen_kwargs: list[dict] = []

    class FakeBridgeClient:
        def __init__(self, api_url: str, token: str = "", timeout: float = 120.0) -> None:
            calls.append(("init", {"api_url": api_url, "token": token, "timeout": timeout}))

        def register_local_agent_connection(self, **payload) -> dict:
            calls.append(("register", payload))
            return {
                "connection": {"id": "claude-connection-1"},
                "device_token": "claude-device-token",
            }

    class FakePopen:
        def __init__(self, command: list[str], **kwargs) -> None:
            popen_commands.append(command)
            popen_kwargs.append(kwargs)

    monkeypatch.setenv("HAO_HOME", str(tmp_path))
    hao_main_module = importlib.import_module("app.cli.hao.main")
    monkeypatch.setattr(
        hao_main_module,
        "_probe_claude_code_cli",
        lambda: _claude_probe(hao_main_module),
    )
    monkeypatch.setattr(hao_main_module, "HarnessApiClient", FakeBridgeClient)
    monkeypatch.setattr(hao_main_module.subprocess, "Popen", FakePopen)

    exit_code = hao_main_module.main(
        [
            "bridge",
            "pair",
            "--api",
            "http://127.0.0.1:8000",
            "--pair-token",
            "pair-token",
            "--pair-code",
            "ABC123",
            "--adapter",
            "claude_code",
            "--cwd",
            str(tmp_path),
            "--daemon",
        ]
    )

    assert exit_code == 0
    bridge_json = (tmp_path / "bridge.json").read_text(encoding="utf-8")
    assert "claude-device-token" not in bridge_json
    assert str(tmp_path) not in bridge_json
    assert '"cwd"' not in bridge_json
    assert "workspace_identity_hash" in bridge_json
    assert "workspace_root_ref" in bridge_json
    workspace_sidecar = tmp_path / "bridge.workspace-root"
    assert workspace_sidecar.read_text(encoding="utf-8") == str(tmp_path.resolve())
    assert workspace_sidecar.stat().st_mode & 0o777 == 0o600
    register = next(payload for name, payload in calls if name == "register")
    assert register["adapter_kind"] == "claude_code"
    assert register["metadata"]["workspace_identity_hash"]
    assert register["risk_capabilities"] == ["host_read", "host_write", "shell", "git", "network"]
    assert register["capabilities"]["execution_mode"] == "headless_harness_tool_bridge"
    command = popen_commands[0]
    assert "--cwd" not in command
    assert str(tmp_path) not in command
    assert "claude-device-token" not in command
    assert popen_kwargs[0]["cwd"] != str(tmp_path)


def test_hao_bridge_v6_claude_pair_registers_permission_bridge_and_safe_daemon_argv(
    tmp_path: Path,
    monkeypatch,
) -> None:
    calls: list[tuple[str, dict]] = []
    popen_commands: list[list[str]] = []

    class FakeBridgeClient:
        def __init__(self, api_url: str, token: str = "", timeout: float = 120.0) -> None:
            calls.append(("init", {"api_url": api_url, "token": token, "timeout": timeout}))

        def register_local_agent_connection(self, **payload) -> dict:
            calls.append(("register", payload))
            return {
                "connection": {"id": "claude-v6-connection"},
                "device_token": "claude-v6-device-token",
            }

    class FakePopen:
        def __init__(self, command: list[str], **kwargs) -> None:
            del kwargs
            popen_commands.append(command)

    monkeypatch.setenv("HAO_HOME", str(tmp_path))
    hao_main_module = importlib.import_module("app.cli.hao.main")
    monkeypatch.setattr(
        hao_main_module,
        "_probe_claude_code_cli",
        lambda: _claude_probe(hao_main_module),
    )
    monkeypatch.setattr(
        hao_main_module,
        "_probe_claude_agent_sdk",
        lambda: _claude_sdk_probe(hao_main_module),
    )
    monkeypatch.setattr(hao_main_module, "HarnessApiClient", FakeBridgeClient)
    monkeypatch.setattr(hao_main_module.subprocess, "Popen", FakePopen)

    exit_code = hao_main_module.main(
        [
            "bridge",
            "pair",
            "--api",
            "http://127.0.0.1:8000",
            "--pair-token",
            "pair-token",
            "--pair-code",
            "ABC123",
            "--adapter",
            "claude_code",
            "--permission-bridge",
            "sdk",
            "--cwd",
            str(tmp_path),
            "--daemon",
        ]
    )

    assert exit_code == 0
    register = next(payload for name, payload in calls if name == "register")
    assert register["adapter_kind"] == "claude_code"
    assert register["risk_capabilities"] == [
        "host_read",
        "host_write",
        "shell",
        "git",
        "network",
    ]
    capabilities = register["capabilities"]
    assert capabilities["claude_permission_bridge_v1"] is True
    assert capabilities["permission_bridge"] == "harness_local_tool_request_v1"
    assert capabilities["permission_bridge_mode"] == "sdk"
    assert capabilities["host_tools_authorized"] is True
    assert capabilities["sdk_allowed_tools_preapproved"] is False
    assert capabilities["allowed_tools"] == []
    assert capabilities["mcp_enabled"] is False
    assert capabilities["browser_enabled"] is False
    bridge_json = (tmp_path / "bridge.json").read_text(encoding="utf-8")
    assert '"permission_bridge": "sdk"' in bridge_json
    assert "claude-v6-device-token" not in bridge_json
    command = popen_commands[0]
    assert "--permission-bridge" in command
    assert command[command.index("--permission-bridge") + 1] == "sdk"
    assert "claude-v6-device-token" not in command
    assert str(tmp_path) not in command


def test_hao_bridge_v4_codex_command_builder_and_env_are_safe(
    tmp_path: Path,
    monkeypatch,
) -> None:
    hao_main_module = importlib.import_module("app.cli.hao.main")
    output_path = tmp_path / "last.txt"
    probe = hao_main_module.CodexCliProbe(
        installed=True,
        executable="/opt/codex/bin/codex",
        exec_help="--json --output-last-message -C --sandbox read-only --skip-git-repo-check",
    )

    command = hao_main_module._codex_command(
        probe=probe,
        workspace_root=tmp_path,
        output_last_message=output_path,
    )

    assert command[:2] == ["/opt/codex/bin/codex", "exec"]
    assert "--json" in command
    assert "--output-last-message" in command
    assert "-C" in command
    assert str(tmp_path) in command
    assert "--skip-git-repo-check" in command
    assert command.index("--skip-git-repo-check") < command.index("-")
    assert command[-1] == "-"
    assert "--dangerously-bypass-approvals-and-sandbox" not in command
    assert "danger-full-access" not in command
    assert "--last" not in command
    assert "secret prompt" not in command

    monkeypatch.setenv("HARNESS_SECRET", "harness-secret")
    monkeypatch.setenv("HAO_API_TOKEN", "hao-token")
    monkeypatch.setenv("LOCAL_AGENT_DEVICE_TOKEN", "device-token")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-proj-1234567890abcdef")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "anthropic-secret")
    monkeypatch.setenv("HTTPS_PROXY", "http://proxy.example")
    source_codex_home = tmp_path / "source-codex"
    source_codex_home.mkdir()
    (source_codex_home / "auth.json").write_text(
        json.dumps(
            {
                "OPENAI_API_KEY": "sk-proj-authjson1234567890abcdef",
                "tokens": {"access_token": "codex-access-token"},
            },
        ),
        encoding="utf-8",
    )
    (source_codex_home / "config.toml").write_text(
        """
model = "gpt-5.5"
model_provider = "custom.provider"
model_reasoning_effort = "high"
model_verbosity = "low"
model_context_window = 1000000
disable_response_storage = true
approval_policy = "never"
sandbox_mode = "danger-full-access"

[model_providers."custom.provider"]
name = "Custom Provider"
base_url = "https://codex-provider.example/v1"
wire_api = "responses"
requires_openai_auth = false
experimental_bearer_token = "provider-secret-token"
extra_secret = "do-not-copy"

[features]
codex_hooks = true

[hooks]
pre_model = "leaky-hook"

[mcp_servers.filesystem]
command = "npx"
args = ["-y", "@modelcontextprotocol/server-filesystem", "/Users/luohao"]
""",
        encoding="utf-8",
    )
    monkeypatch.setenv("CODEX_HOME", str(source_codex_home))
    env = hao_main_module._codex_subprocess_env(
        executable="/opt/codex/bin/codex",
        temp_dir=tmp_path,
    )

    assert env["TMPDIR"] == str(tmp_path)
    assert Path(env["HOME"]).parent == tmp_path
    assert Path(env["CODEX_HOME"]).parent == tmp_path
    assert "HARNESS_SECRET" not in env
    assert "HAO_API_TOKEN" not in env
    assert "LOCAL_AGENT_DEVICE_TOKEN" not in env
    assert "OPENAI_API_KEY" not in env
    assert "ANTHROPIC_API_KEY" not in env
    assert "HTTPS_PROXY" not in env
    isolated_codex_home = Path(env["CODEX_HOME"])
    isolated_auth = isolated_codex_home / "auth.json"
    isolated_config = isolated_codex_home / "config.toml"
    assert isolated_auth.is_file()
    assert isolated_config.is_file()
    assert isolated_auth.stat().st_mode & 0o777 == 0o600
    assert isolated_config.stat().st_mode & 0o777 == 0o600
    assert json.loads(isolated_auth.read_text(encoding="utf-8"))["tokens"] == {
        "access_token": "codex-access-token",
    }
    isolated_config_text = isolated_config.read_text(encoding="utf-8")
    isolated_config_data = hao_main_module.tomllib.loads(isolated_config_text)
    assert isolated_config_data["model"] == "gpt-5.5"
    assert isolated_config_data["model_provider"] == "custom.provider"
    assert isolated_config_data["disable_response_storage"] is True
    provider_config = isolated_config_data["model_providers"]["custom.provider"]
    assert provider_config == {
        "base_url": "https://codex-provider.example/v1",
        "experimental_bearer_token": "provider-secret-token",
        "name": "Custom Provider",
        "requires_openai_auth": False,
        "wire_api": "responses",
    }
    assert "approval_policy" not in isolated_config_text
    assert "sandbox_mode" not in isolated_config_text
    assert "features" not in isolated_config_text
    assert "codex_hooks" not in isolated_config_text
    assert "hooks" not in isolated_config_text
    assert "mcp_servers" not in isolated_config_text
    assert "do-not-copy" not in isolated_config_text


def test_hao_bridge_v4_codex_minimal_toml_quotes_provider_names() -> None:
    hao_main_module = importlib.import_module("app.cli.hao.main")
    malicious_provider = 'bad"]\n[mcp_servers.injected]\ncommand = "oops'

    output = hao_main_module._dump_minimal_toml(
        {
            "model": "gpt-5.5",
            "model_provider": malicious_provider,
            "model_providers": {
                malicious_provider: {
                    "name": "Injected Provider",
                    "base_url": "https://codex-provider.example/v1",
                    "wire_api": "responses",
                    "experimental_bearer_token": "provider-secret-token",
                },
            },
        },
    )

    parsed = hao_main_module.tomllib.loads(output)
    assert parsed["model_provider"] == malicious_provider
    assert set(parsed["model_providers"]) == {malicious_provider}
    assert parsed["model_providers"][malicious_provider]["experimental_bearer_token"] == (
        "provider-secret-token"
    )
    assert "mcp_servers" not in parsed
    assert "hooks" not in parsed


def test_hao_bridge_v4_codex_probe_uses_sanitized_env(monkeypatch) -> None:
    hao_main_module = importlib.import_module("app.cli.hao.main")
    captured_envs: list[dict] = []

    def fake_run(command: list[str], **kwargs) -> subprocess.CompletedProcess:
        captured_envs.append(dict(kwargs.get("env") or {}))
        if command[-2:] == ["exec", "--help"]:
            stdout = "--json --output-last-message -C --sandbox read-only"
        elif command[-3:] == ["exec", "resume", "--help"]:
            stdout = "resume -c --config"
        else:
            stdout = "codex 1.0"
        return subprocess.CompletedProcess(command, 0, stdout=stdout, stderr="")

    monkeypatch.setattr(hao_main_module.shutil, "which", lambda name: "/opt/codex/bin/codex")
    monkeypatch.setattr(hao_main_module.subprocess, "run", fake_run)
    monkeypatch.setenv("HARNESS_SECRET", "harness-secret")
    monkeypatch.setenv("HAO_API_TOKEN", "hao-token")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-proj-1234567890abcdef")
    monkeypatch.setenv("HTTP_PROXY", "http://proxy.example")
    monkeypatch.setenv("HOME", "/Users/luohao")
    monkeypatch.setenv("CODEX_HOME", "/Users/luohao/.codex")

    probe = hao_main_module._probe_codex_cli()

    assert probe.installed is True
    assert len(captured_envs) == 3
    for env in captured_envs:
        assert "HARNESS_SECRET" not in env
        assert "HAO_API_TOKEN" not in env
        assert "OPENAI_API_KEY" not in env
        assert "HTTP_PROXY" not in env
        assert "HOME" not in env
        assert "CODEX_HOME" not in env


def test_hao_bridge_v5_claude_command_builder_and_env_are_safe(
    tmp_path: Path,
    monkeypatch,
) -> None:
    hao_main_module = importlib.import_module("app.cli.hao.main")
    probe = _claude_probe(hao_main_module)

    command = hao_main_module._claude_code_command(probe=probe)

    assert command == [
        "/opt/claude/bin/claude",
        "--bare",
        "-p",
        "--output-format",
        "stream-json",
        "--verbose",
        "--include-partial-messages",
        "--no-session-persistence",
        "--permission-mode",
        "default",
        "--tools",
        "",
    ]
    forbidden = {
        "--dangerously-skip-permissions",
        "--permission-mode bypassPermissions",
        "bypassPermissions",
        "acceptEdits",
        "auto",
        "dontAsk",
        "--continue",
        "-c",
        "--resume",
        "-r",
        "--session-id",
        "--add-dir",
        "--remote",
        "--remote-control",
        "--mcp-config",
        "--plugin-dir",
        "--plugin-url",
        "--agents",
        "--allowedTools",
        "--settings",
        "--setting-sources",
        "--include-hook-events",
    }
    assert not forbidden.intersection(command)
    assert "secret prompt" not in command

    monkeypatch.setenv("HARNESS_SECRET", "harness-secret")
    monkeypatch.setenv("HAO_API_TOKEN", "hao-token")
    monkeypatch.setenv("LOCAL_AGENT_DEVICE_TOKEN", "device-token")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-proj-1234567890abcdef")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-secret")
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    monkeypatch.delenv("ANTHROPIC_BASE_URL", raising=False)
    monkeypatch.delenv("ANTHROPIC_MODEL", raising=False)
    monkeypatch.delenv("ANTHROPIC_DEFAULT_SONNET_MODEL", raising=False)
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "oauth-token")
    monkeypatch.setenv("HTTPS_PROXY", "http://proxy.example")
    source_home = tmp_path / "source-home"
    source_claude = source_home / ".claude"
    source_claude.mkdir(parents=True)
    (source_claude / "settings.json").write_text(
        json.dumps(
            {
                "env": {
                    "ANTHROPIC_AUTH_TOKEN": "settings-auth-token",
                    "ANTHROPIC_BASE_URL": "https://claude.example",
                    "ANTHROPIC_MODEL": "claude-settings-model",
                    "ANTHROPIC_DEFAULT_SONNET_MODEL": "claude-sonnet-settings",
                    "ANTHROPIC_API_KEY": "settings-api-key-must-not-load",
                    "CLAUDE_CODE_OAUTH_TOKEN": "settings-oauth-must-not-load",
                    "HTTPS_PROXY": "http://settings-proxy.example",
                },
                "hooks": {"PreToolUse": [{"matcher": "*", "hooks": []}]},
                "mcpServers": {"unsafe": {"command": "node"}},
            },
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("HOME", str(source_home))
    env = hao_main_module._claude_code_subprocess_env(
        executable="/opt/claude/bin/claude",
        temp_dir=tmp_path,
    )

    assert env["TMPDIR"] == str(tmp_path)
    assert Path(env["HOME"]).parent == tmp_path
    assert Path(env["CLAUDE_CONFIG_DIR"]).parent == tmp_path
    assert env["CLAUDE_CODE_SKIP_PROMPT_HISTORY"] == "1"
    assert env["CLAUDE_CODE_DISABLE_AUTO_MEMORY"] == "1"
    assert env["CLAUDE_AGENT_SDK_DISABLE_BUILTIN_AGENTS"] == "1"
    assert env["ANTHROPIC_AUTH_TOKEN"] == "settings-auth-token"
    assert env["ANTHROPIC_BASE_URL"] == "https://claude.example"
    assert env["ANTHROPIC_MODEL"] == "claude-settings-model"
    assert env["ANTHROPIC_DEFAULT_SONNET_MODEL"] == "claude-sonnet-settings"
    assert env["HOME"] != str(source_home)
    assert "HARNESS_SECRET" not in env
    assert "HAO_API_TOKEN" not in env
    assert "LOCAL_AGENT_DEVICE_TOKEN" not in env
    assert "OPENAI_API_KEY" not in env
    assert "ANTHROPIC_API_KEY" not in env
    assert "CLAUDE_CODE_OAUTH_TOKEN" not in env
    assert "HTTPS_PROXY" not in env

    monkeypatch.setenv("HAO_CLAUDE_CODE_ALLOW_ANTHROPIC_API_KEY", "1")
    env_with_key = hao_main_module._claude_code_subprocess_env(
        executable="/opt/claude/bin/claude",
        temp_dir=tmp_path / "allowed",
    )
    assert env_with_key["ANTHROPIC_API_KEY"] == "sk-ant-secret"


def test_hao_bridge_v5_claude_probe_uses_sanitized_env(monkeypatch) -> None:
    hao_main_module = importlib.import_module("app.cli.hao.main")
    captured_envs: list[dict] = []
    help_text = (
        "--bare -p --print --output-format stream-json --include-partial-messages "
        "--no-session-persistence --permission-mode --tools"
    )

    def fake_run(command: list[str], **kwargs) -> subprocess.CompletedProcess:
        captured_envs.append(dict(kwargs.get("env") or {}))
        stdout = "claude 1.0" if command[-1] == "--version" else help_text
        return subprocess.CompletedProcess(command, 0, stdout=stdout, stderr="")

    monkeypatch.setattr(hao_main_module.shutil, "which", lambda name: "/opt/claude/bin/claude")
    monkeypatch.setattr(hao_main_module.subprocess, "run", fake_run)
    monkeypatch.setenv("HARNESS_SECRET", "harness-secret")
    monkeypatch.setenv("HAO_API_TOKEN", "hao-token")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-secret")
    monkeypatch.setenv("HTTP_PROXY", "http://proxy.example")
    monkeypatch.setenv("HOME", "/Users/luohao")
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", "/Users/luohao/.claude")

    probe = hao_main_module._probe_claude_code_cli()

    assert probe.installed is True
    assert len(captured_envs) == 3
    for env in captured_envs:
        assert "HARNESS_SECRET" not in env
        assert "HAO_API_TOKEN" not in env
        assert "ANTHROPIC_API_KEY" not in env
        assert "HTTP_PROXY" not in env
        assert "HOME" not in env
        assert "CLAUDE_CONFIG_DIR" not in env


def test_hao_bridge_v6_claude_capabilities_require_cli_and_sdk() -> None:
    hao_main_module = importlib.import_module("app.cli.hao.main")

    missing_sdk = hao_main_module._claude_code_bridge_capabilities(
        _claude_probe(hao_main_module),
        permission_bridge="sdk",
        sdk_probe=_claude_sdk_probe(hao_main_module, installed=False),
    )
    assert missing_sdk["host_tools_authorized"] is True
    assert missing_sdk["permission_bridge_mode"] == "sdk"
    assert "claude_permission_bridge_v1" not in missing_sdk

    v6 = hao_main_module._claude_code_bridge_capabilities(
        _claude_probe(hao_main_module),
        permission_bridge="sdk",
        sdk_probe=_claude_sdk_probe(hao_main_module),
    )
    assert v6["enabled_in_v6"] is True
    assert v6["host_tools_authorized"] is True
    assert v6["supports_cancel"] is True
    assert v6["permission_bridge"] == "harness_local_tool_request_v1"
    assert v6["execution_mode"] == "agent_sdk_intent_capture_harness_executor"
    assert v6["permission_bridge_execution"] == "harness_owned_executor"
    assert v6["sdk_native_tool_execution_enabled"] is False
    assert v6["allowed_tools"] == []
    assert v6["sdk_allowed_tools_preapproved"] is False
    assert v6["mcp_enabled"] is False
    assert v6["subagents_enabled"] is False
    assert v6["browser_enabled"] is False


def test_hao_bridge_v6_claude_tool_mapping_allows_only_harness_mapped_tools() -> None:
    hao_main_module = importlib.import_module("app.cli.hao.main")

    bash = hao_main_module._map_claude_tool_request("Bash", {"command": "printf ok"})
    assert bash.allowed is True
    assert bash.tool_name == "run_shell"
    assert bash.input_json["command"] == "printf ok"

    write = hao_main_module._map_claude_tool_request(
        "Write",
        {"file_path": "notes.md", "content": "hello"},
    )
    assert write.allowed is True
    assert write.tool_name == "write_file"
    assert write.input_json == {"path": "notes.md", "content": "hello"}
    assert write.target_paths == ["notes.md"]

    denied = hao_main_module._map_claude_tool_request("WebFetch", {"url": "https://example.com"})
    assert denied.allowed is False
    assert "not mapped" in denied.reason
    mcp = hao_main_module._map_claude_tool_request("mcp__server__tool", {})
    assert mcp.allowed is False
    unknown = hao_main_module._map_claude_tool_request("DangerTool", {})
    assert unknown.allowed is False
    assert "denied by default" in unknown.reason


def test_hao_bridge_v6_real_sdk_options_use_streaming_prompt_and_pretool_hook(
    tmp_path: Path,
    monkeypatch,
) -> None:
    hao_main_module = importlib.import_module("app.cli.hao.main")
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
    captured: dict[str, Any] = {}
    _install_fake_claude_agent_sdk(monkeypatch, captured)

    class FakeClient:
        pass

    result = hao_main_module._run_claude_permission_bridge_sdk(
        client=FakeClient(),
        device_token="device-token-claude",
        bridge_task_id="bridge-task-claude",
        config=config,
        state=state,
        payload={
            "message": "please inspect the repository",
            "agent_id": "default",
            "run_id": "run-claude-v6",
            "workspace_identity_hash": state["workspace_identity_hash"],
        },
    )

    assert result.status == "completed"
    assert result.content == "sdk bridge reply"
    assert result.metadata is not None
    assert result.metadata["permission_bridge_pre_tool_hook_configured"] is True
    assert result.metadata["permission_bridge_dummy_hook_only"] is True
    assert captured["prompt_is_streaming"] is True
    assert captured["prompt_items"][0]["type"] == "user"
    assert "V6 permission bridge is active" in captured["prompt_items"][0]["message"]["content"]
    options = captured["options_kwargs"]
    assert options["permission_mode"] == "default"
    assert options["allowed_tools"] == []
    assert callable(options["can_use_tool"])
    assert options["setting_sources"] == []
    assert options["mcp_servers"] == {}
    assert options["strict_mcp_config"] is True
    assert options["agents"] == {}
    assert options["plugins"] == []
    assert options["skills"] == []
    assert options["include_hook_events"] is False
    assert options["cwd"] == str(workspace)
    assert "WebFetch" in options["disallowed_tools"]
    hook_matchers = options["hooks"]["PreToolUse"]
    assert len(hook_matchers) == 1
    assert hook_matchers[0].matcher is None
    assert len(hook_matchers[0].hooks) == 1
    hook_result = asyncio.run(hook_matchers[0].hooks[0]({}, "tool-use-1", {}))
    assert hook_result == {"continue_": True}


def test_hao_bridge_v6_real_sdk_callback_denies_native_execution_and_uses_server_input(
    tmp_path: Path,
    monkeypatch,
) -> None:
    hao_main_module = importlib.import_module("app.cli.hao.main")
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
    captured: dict[str, Any] = {}
    calls: list[tuple[str, dict]] = []
    _install_fake_claude_agent_sdk(monkeypatch, captured)

    class FakeClient:
        def create_local_agent_tool_request(self, *, device_token: str, payload: dict) -> dict:
            calls.append(("tool_request", {"device_token": device_token, **payload}))
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

        def get_local_agent_tool_decision(self, *, device_token: str, tool_request_id: str) -> dict:
            calls.append(
                (
                    "decision",
                    {"device_token": device_token, "tool_request_id": tool_request_id},
                )
            )
            return {
                "tool_request_id": tool_request_id,
                "decision": "approved",
                "status": "approved",
                "executable": True,
                "server_execution": False,
                "tool_name": "run_shell",
                "input_json": {"command": "printf server-approved"},
                "reason": "",
            }

        def report_local_agent_command_event(
            self,
            *,
            device_token: str,
            command_id: str,
            payload: dict,
        ) -> dict:
            calls.append(
                (
                    "command_event",
                    {"device_token": device_token, "command_id": command_id, **payload},
                )
            )
            return {"command_id": command_id, "status": payload["event_type"]}

        def get_local_agent_command_status(
            self,
            *,
            device_token: str,
            command_id: str,
        ) -> dict:
            calls.append(
                (
                    "command_status",
                    {"device_token": device_token, "command_id": command_id},
                )
            )
            return {"command_id": command_id, "status": "running", "cancel_requested": False}

        def report_local_agent_tool_result(
            self,
            *,
            device_token: str,
            tool_request_id: str,
            payload: dict,
        ) -> dict:
            calls.append(
                (
                    "tool_result",
                    {"device_token": device_token, "tool_request_id": tool_request_id, **payload},
                )
            )
            return {
                "tool_request_id": tool_request_id,
                "tool_call_id": "server-claude-tool",
                "decision": "succeeded",
                "status": "succeeded",
            }

    def fake_local_tool(tool_name: str, input_json: dict, workspace_root: Path, **kwargs):
        session_store = kwargs["session_store"]
        session_id = kwargs["session_id"]
        command = session_store.create_command(
            session_id,
            tool_name=tool_name,
            command=input_json["command"],
            command_json=input_json,
            timeout_seconds=30,
        )
        session_store.start_command(command["id"])
        session_store.record_command_output(command["id"], stream="stdout", chunk="server-approved")
        session_store.finish_command(
            command["id"],
            status="success",
            exit_code=0,
            stdout_truncated=False,
            stderr_truncated=False,
        )
        return ToolExecutionResult(
            tool_name=tool_name,
            status="SUCCESS",
            input_json=input_json,
            output_json={
                "command_id": command["id"],
                "command": input_json["command"],
                "command_status": "success",
                "stdout": "server-approved",
            },
            duration_ms=1,
        )

    monkeypatch.setattr(hao_main_module, "execute_local_tool", fake_local_tool)
    monkeypatch.setattr(hao_main_module, "CLAUDE_PERMISSION_DECISION_POLL_SECONDS", 0.001)

    result = hao_main_module._run_claude_permission_bridge_sdk(
        client=FakeClient(),
        device_token="device-token-claude",
        bridge_task_id="bridge-task-claude",
        config=config,
        state=state,
        payload={
            "message": "please inspect the repository",
            "agent_id": "default",
            "run_id": "run-claude-v6",
            "workspace_identity_hash": state["workspace_identity_hash"],
        },
    )

    assert result.status == "completed"
    callback = captured["options_kwargs"]["can_use_tool"]
    native_result = asyncio.run(
        callback("Bash", {"command": "printf model-proposed", "tool_use_id": "bash-1"})
    )
    deny_type = sys.modules["claude_agent_sdk"].PermissionResultDeny
    assert isinstance(native_result, deny_type)
    assert "Harness approved and executed" in native_result.message
    assert "server-approved" in native_result.message
    tool_request = next(payload for name, payload in calls if name == "tool_request")
    assert tool_request["input_json"]["command"] == "printf model-proposed"
    tool_result = next(payload for name, payload in calls if name == "tool_result")
    assert tool_result["status"] == "SUCCESS"
    assert tool_result["output_json"]["command"] == "printf server-approved"


def test_hao_bridge_v6_fake_sdk_executes_server_approved_input_and_reports_safety(
    tmp_path: Path,
    monkeypatch,
) -> None:
    hao_main_module = importlib.import_module("app.cli.hao.main")
    monkeypatch.setenv("HAO_CLAUDE_PERMISSION_BRIDGE_FAKE_SDK", "1")
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
    calls: list[tuple[str, dict]] = []

    class FakeClient:
        def create_local_agent_tool_request(self, *, device_token: str, payload: dict) -> dict:
            calls.append(("tool_request", {"device_token": device_token, **payload}))
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

        def get_local_agent_tool_decision(self, *, device_token: str, tool_request_id: str) -> dict:
            calls.append(
                (
                    "decision",
                    {"device_token": device_token, "tool_request_id": tool_request_id},
                )
            )
            return {
                "tool_request_id": tool_request_id,
                "decision": "approved",
                "status": "approved",
                "executable": True,
                "server_execution": False,
                "tool_name": "run_shell",
                "input_json": {"command": "printf server-approved"},
                "reason": "",
            }

        def report_local_agent_command_event(
            self,
            *,
            device_token: str,
            command_id: str,
            payload: dict,
        ) -> dict:
            calls.append(
                (
                    "command_event",
                    {"device_token": device_token, "command_id": command_id, **payload},
                )
            )
            return {"command_id": command_id, "status": payload["event_type"]}

        def get_local_agent_command_status(
            self,
            *,
            device_token: str,
            command_id: str,
        ) -> dict:
            calls.append(
                (
                    "command_status",
                    {"device_token": device_token, "command_id": command_id},
                )
            )
            return {"command_id": command_id, "status": "running", "cancel_requested": False}

        def report_local_agent_tool_result(
            self,
            *,
            device_token: str,
            tool_request_id: str,
            payload: dict,
        ) -> dict:
            calls.append(
                (
                    "tool_result",
                    {"device_token": device_token, "tool_request_id": tool_request_id, **payload},
                )
            )
            return {
                "tool_request_id": tool_request_id,
                "tool_call_id": "server-claude-tool",
                "decision": "succeeded",
                "status": "succeeded",
            }

    def fake_local_tool(tool_name: str, input_json: dict, workspace_root: Path, **kwargs):
        session_store = kwargs["session_store"]
        session_id = kwargs["session_id"]
        command = session_store.create_command(
            session_id,
            tool_name=tool_name,
            command=input_json["command"],
            command_json=input_json,
            timeout_seconds=30,
        )
        session_store.start_command(command["id"])
        session_store.record_command_output(command["id"], stream="stdout", chunk="server-approved")
        session_store.finish_command(
            command["id"],
            status="success",
            exit_code=0,
            stdout_truncated=False,
            stderr_truncated=False,
        )
        return ToolExecutionResult(
            tool_name=tool_name,
            status="SUCCESS",
            input_json=input_json,
            output_json={
                "command_id": command["id"],
                "command": input_json["command"],
                "command_status": "success",
                "stdout": "server-approved",
            },
            duration_ms=1,
        )

    monkeypatch.setattr(hao_main_module, "execute_local_tool", fake_local_tool)
    monkeypatch.setattr(hao_main_module, "CLAUDE_PERMISSION_DECISION_POLL_SECONDS", 0.001)

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
                {"type": "assistant", "content": "done"},
            ],
        },
    )

    assert result.status == "completed"
    assert "server-approved" in result.content
    assert "done" in result.content
    assert result.metadata is not None
    assert result.metadata["permission_bridge_active"] is True
    assert result.metadata["permission_bridge_version"] == "harness_local_tool_request_v1"
    assert result.metadata["computer_use_disabled"] is True
    assert result.metadata["allowed_tools"] == []
    tool_request = next(payload for name, payload in calls if name == "tool_request")
    assert tool_request["input_json"]["command"] == "printf model-proposed"
    tool_result = next(payload for name, payload in calls if name == "tool_result")
    assert tool_result["status"] == "SUCCESS"
    assert tool_result["output_json"]["command"] == "printf server-approved"
    command_events = [payload for name, payload in calls if name == "command_event"]
    assert [event["event_type"] for event in command_events] == [
        "started",
        "output",
        "finished",
    ]


def test_hao_bridge_v6_execute_approved_write_refreshes_pending_change_and_commits_modified_input(
    tmp_path: Path,
) -> None:
    hao_main_module = importlib.import_module("app.cli.hao.main")
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    store = SessionStore(tmp_path / "hao.db", tmp_path / "sessions")
    local_session = store.create_session(
        cwd=str(workspace),
        agent_id="default",
        mode="confirm",
        cli_mode="claude_code",
        target="host",
    )
    original_preview = execute_local_tool(
        "preview_write_file",
        {"path": "notes.md", "content": "original\n"},
        workspace,
        session_store=store,
        session_id=local_session.id,
        pending_change_metadata={"source": "local_agent_bridge"},
    )
    original_change_id = str(original_preview.output_json["change_id"])
    pending = {
        "tool_request_id": "tool-req-write",
        "bridge_task_id": "bridge-task-write",
        "tool_call_id": "model-tool-write",
        "tool_name": "write_file",
        "local_session_id": local_session.id,
        "run_id": "run-write",
        "agent_id": "default",
        "command": "claude_code",
        "permission_mode": "confirm",
        "change_id": original_change_id,
        "diff_sha256": hao_main_module._sha256_text(
            str(original_preview.output_json.get("diff") or "")
        ),
    }
    decision = {
        "tool_request_id": "tool-req-write",
        "tool_name": "write_file",
        "input_json": {"path": "safe.md", "content": "sanitized\n"},
    }
    calls: list[tuple[str, dict[str, Any]]] = []

    class FakeClient:
        def refresh_local_agent_pending_change(
            self,
            *,
            device_token: str,
            tool_request_id: str,
            payload: dict,
        ) -> dict:
            calls.append(
                (
                    "refresh",
                    {
                        "device_token": device_token,
                        "tool_request_id": tool_request_id,
                        "payload": payload,
                    },
                )
            )
            return {
                "tool_request_id": tool_request_id,
                "decision": "approved",
                "status": "approved",
                "executable": True,
                "input_json": payload["input_json"],
                "decision_json": {"pending_change_preview": payload["pending_change_preview"]},
            }

        def report_local_agent_tool_result(
            self,
            *,
            device_token: str,
            tool_request_id: str,
            payload: dict,
        ) -> dict:
            calls.append(
                (
                    "tool_result",
                    {
                        "device_token": device_token,
                        "tool_request_id": tool_request_id,
                        "payload": payload,
                    },
                )
            )
            return {"tool_request_id": tool_request_id, "tool_call_id": "server-tool-write"}

    handled = hao_main_module._execute_approved_bridge_pending_tool(
        pending=pending,
        decision=decision,
        client=FakeClient(),
        device_token="device-token-write",
        store=store,
        local_session_id=local_session.id,
        cwd=workspace,
    )

    assert handled.status == "executed"
    assert handled.result is not None
    assert handled.result.status == "SUCCESS"
    assert handled.result.input_json == {"path": "safe.md", "content": "sanitized\n"}
    assert (workspace / "safe.md").read_text(encoding="utf-8") == "sanitized\n"
    assert not (workspace / "notes.md").exists()

    refresh_call = next(payload for name, payload in calls if name == "refresh")
    refresh_preview = refresh_call["payload"]["pending_change_preview"]
    assert refresh_call["payload"]["input_json"] == {"path": "safe.md", "content": "sanitized\n"}
    assert refresh_call["payload"]["target_paths"] == ["safe.md"]

    tool_result_call = next(payload for name, payload in calls if name == "tool_result")
    assert tool_result_call["payload"]["change_id"] == refresh_preview["change_id"]
    assert tool_result_call["payload"]["diff_sha256"] == refresh_preview["diff_sha256"]

    changes = {change["id"]: change for change in store.list_pending_changes(local_session.id)}
    assert changes[original_change_id]["status"] == "rejected"
    refreshed_change_id = str(handled.result.output_json["change_id"])
    assert refreshed_change_id != original_change_id
    assert changes[refreshed_change_id]["status"] == "committed"
    assert changes[refreshed_change_id]["input_json"] == {
        "path": "safe.md",
        "content": "sanitized\n",
    }


def test_hao_bridge_v6_fake_sdk_requires_explicit_fixture_mode(
    tmp_path: Path,
    monkeypatch,
) -> None:
    hao_main_module = importlib.import_module("app.cli.hao.main")
    monkeypatch.setenv("HAO_CLAUDE_PERMISSION_BRIDGE_FAKE_SDK", "1")
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
    captured: dict[str, Any] = {}
    _install_fake_claude_agent_sdk(monkeypatch, captured)

    class FakeClient:
        def create_local_agent_tool_request(self, **kwargs) -> dict:
            raise AssertionError("fake SDK fixture mode should not activate without explicit flag")

    result = hao_main_module._run_claude_permission_bridge_sdk(
        client=FakeClient(),
        device_token="device-token-claude",
        bridge_task_id="bridge-task-claude",
        config=config,
        state=state,
        payload={
            "message": "real sdk path",
            "agent_id": "default",
            "run_id": "run-claude-v6",
            "workspace_identity_hash": state["workspace_identity_hash"],
            "fake_sdk_events": [
                {
                    "type": "tool_request",
                    "tool_name": "Bash",
                    "tool_use_id": "bash-1",
                    "input": {"command": "printf ignored"},
                }
            ],
        },
    )

    assert result.status == "completed"
    assert result.content == "sdk bridge reply"


def test_hao_bridge_v6_fake_sdk_fails_closed_on_decision_poll_error(
    tmp_path: Path,
    monkeypatch,
) -> None:
    hao_main_module = importlib.import_module("app.cli.hao.main")
    monkeypatch.setenv("HAO_CLAUDE_PERMISSION_BRIDGE_FAKE_SDK", "1")
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
        def create_local_agent_tool_request(self, *, device_token: str, payload: dict) -> dict:
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

        def get_local_agent_tool_decision(self, *, device_token: str, tool_request_id: str) -> dict:
            del device_token, tool_request_id
            calls.append("decision")
            raise RuntimeError("decision api unavailable")

    def fail_local_tool(*args, **kwargs):
        del args, kwargs
        raise AssertionError("SDK bridge must fail closed before local execution")

    monkeypatch.setattr(hao_main_module, "execute_local_tool", fail_local_tool)
    monkeypatch.setattr(hao_main_module, "CLAUDE_PERMISSION_DECISION_POLL_SECONDS", 0.001)

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

    assert result.status == "error"
    assert "approval polling failed" in result.error_message
    assert calls == ["tool_request", "decision"]


def test_hao_bridge_v6_cancelled_decision_returns_explicit_reason() -> None:
    hao_main_module = importlib.import_module("app.cli.hao.main")

    class FakeClient:
        def get_local_agent_tool_decision(self, *, device_token: str, tool_request_id: str) -> dict:
            del device_token, tool_request_id
            return {
                "tool_request_id": "tool-req",
                "decision": "cancelled",
                "status": "cancelled",
                "executable": False,
                "reason": "",
            }

    decision = hao_main_module._poll_local_tool_decision_for_claude(
        client=FakeClient(),
        device_token="device-token",
        tool_request_id="tool-req",
        timeout_seconds=0.01,
    )

    assert decision["decision"] == "cancelled"
    assert decision["executable"] is False
    assert decision["reason"] == "Claude Code permission bridge request was cancelled"


def test_hao_bridge_v4_run_codex_cli_success_uses_stdin_and_readonly_sandbox(
    tmp_path: Path,
    monkeypatch,
) -> None:
    hao_main_module = importlib.import_module("app.cli.hao.main")
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    config = type("Config", (), {"home": tmp_path / "hao-home"})()
    root_ref = hao_main_module._save_bridge_workspace_root(config, workspace)
    state = {
        "workspace_root_ref": root_ref,
        "workspace_identity_hash": hao_main_module._workspace_identity_hash(workspace),
    }
    probe = hao_main_module.CodexCliProbe(
        installed=True,
        executable="/opt/codex/bin/codex",
        exec_help="--json --output-last-message -C --sandbox read-only",
    )
    captured: dict[str, object] = {}

    def fake_run(command: list[str], **kwargs) -> subprocess.CompletedProcess:
        captured["command"] = command
        captured["kwargs"] = kwargs
        output_path = Path(command[command.index("--output-last-message") + 1])
        output_path.write_text("final answer from codex", encoding="utf-8")
        return subprocess.CompletedProcess(
            command,
            0,
            stdout='{"type":"assistant_delta","delta":"streamed"}\n',
            stderr="",
        )

    monkeypatch.setenv("HOME", "/Users/luohao")
    monkeypatch.setenv("CODEX_HOME", "/Users/luohao/.codex")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-proj-1234567890abcdef")
    monkeypatch.setattr(hao_main_module, "_probe_codex_cli", lambda: probe)
    monkeypatch.setattr(hao_main_module.subprocess, "run", fake_run)

    result = hao_main_module._run_codex_cli(
        config=config,
        state=state,
        payload={
            "message": "hello from workspace",
            "workspace_identity_hash": state["workspace_identity_hash"],
        },
    )

    assert result.status == "completed"
    assert result.content == "final answer from codex"
    command = captured["command"]
    assert isinstance(command, list)
    assert command[:2] == ["/opt/codex/bin/codex", "exec"]
    assert command[-1] == "-"
    assert "hello from workspace" not in command
    assert "--sandbox" in command
    assert "read-only" in command
    assert "--dangerously-bypass-approvals-and-sandbox" not in command
    assert "danger-full-access" not in command
    kwargs = captured["kwargs"]
    assert isinstance(kwargs, dict)
    assert "hello from workspace" in str(kwargs["input"])
    assert kwargs["cwd"] == str(workspace)
    env = kwargs["env"]
    assert isinstance(env, dict)
    assert "OPENAI_API_KEY" not in env
    assert env["HOME"] != "/Users/luohao"
    assert env["CODEX_HOME"] != "/Users/luohao/.codex"


def test_hao_bridge_v4_run_codex_cli_rejects_workspace_sidecar_mismatch(
    tmp_path: Path,
    monkeypatch,
) -> None:
    hao_main_module = importlib.import_module("app.cli.hao.main")
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    config = type("Config", (), {"home": tmp_path / "hao-home"})()
    root_ref = hao_main_module._save_bridge_workspace_root(config, workspace)
    probe = hao_main_module.CodexCliProbe(
        installed=True,
        executable="/opt/codex/bin/codex",
        exec_help="--json --output-last-message -C --sandbox read-only",
    )
    spawned: list[list[str]] = []

    def fake_run(command: list[str], **kwargs) -> subprocess.CompletedProcess:
        del kwargs
        spawned.append(command)
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr(hao_main_module, "_probe_codex_cli", lambda: probe)
    monkeypatch.setattr(hao_main_module.subprocess, "run", fake_run)

    result = hao_main_module._run_codex_cli(
        config=config,
        state={"workspace_root_ref": root_ref, "workspace_identity_hash": "wrong-hash"},
        payload={"message": "hello"},
    )

    assert result.status == "error"
    assert "workspace root sidecar" in result.error_message
    assert spawned == []


def test_hao_bridge_v4_run_codex_cli_reports_timeout_nonzero_and_empty_output(
    tmp_path: Path,
    monkeypatch,
) -> None:
    hao_main_module = importlib.import_module("app.cli.hao.main")
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    config = type("Config", (), {"home": tmp_path / "hao-home"})()
    root_ref = hao_main_module._save_bridge_workspace_root(config, workspace)
    state = {
        "workspace_root_ref": root_ref,
        "workspace_identity_hash": hao_main_module._workspace_identity_hash(workspace),
    }
    probe = hao_main_module.CodexCliProbe(
        installed=True,
        executable="/opt/codex/bin/codex",
        exec_help="--json --output-last-message -C --sandbox read-only",
    )
    source_codex_home = tmp_path / "source-codex"
    source_codex_home.mkdir()
    (source_codex_home / "config.toml").write_text(
        """
model = "gpt-5.5"
model_provider = "custom-provider"

[model_providers.custom-provider]
name = "Custom Provider"
base_url = "https://codex-provider.example/v1"
experimental_bearer_token = "provider-secret-token"
""",
        encoding="utf-8",
    )
    monkeypatch.setenv("CODEX_HOME", str(source_codex_home))
    monkeypatch.setattr(hao_main_module, "_probe_codex_cli", lambda: probe)

    def timeout_run(command: list[str], **kwargs) -> subprocess.CompletedProcess:
        del kwargs
        raise subprocess.TimeoutExpired(command, 1)

    monkeypatch.setattr(hao_main_module.subprocess, "run", timeout_run)
    timed_out = hao_main_module._run_codex_cli(
        config=config,
        state=state,
        payload={"message": "timeout", "workspace_identity_hash": state["workspace_identity_hash"]},
    )
    assert timed_out.status == "error"
    assert "timed out" in timed_out.error_message

    def nonzero_run(command: list[str], **kwargs) -> subprocess.CompletedProcess:
        del kwargs
        return subprocess.CompletedProcess(
            command,
            2,
            stdout="",
            stderr=(
                "failed token=sk-proj-1234567890abcdef "
                "provider-secret-token /Users/luohao/private/file.txt"
            ),
        )

    monkeypatch.setattr(hao_main_module.subprocess, "run", nonzero_run)
    nonzero = hao_main_module._run_codex_cli(
        config=config,
        state=state,
        payload={"message": "nonzero", "workspace_identity_hash": state["workspace_identity_hash"]},
    )
    assert nonzero.status == "error"
    assert "sk-proj" not in nonzero.error_message
    assert "provider-secret-token" not in nonzero.error_message
    assert "/Users/luohao" not in nonzero.error_message
    assert nonzero.metadata == {"exit_code": 2}

    def empty_run(command: list[str], **kwargs) -> subprocess.CompletedProcess:
        del kwargs
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr(hao_main_module.subprocess, "run", empty_run)
    empty = hao_main_module._run_codex_cli(
        config=config,
        state=state,
        payload={"message": "empty", "workspace_identity_hash": state["workspace_identity_hash"]},
    )
    assert empty.status == "error"
    assert "empty assistant output" in empty.error_message


def test_hao_bridge_v5_run_claude_cli_success_uses_stdin_private_cwd_and_no_tools(
    tmp_path: Path,
    monkeypatch,
) -> None:
    hao_main_module = importlib.import_module("app.cli.hao.main")
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    config = type("Config", (), {"home": tmp_path / "hao-home"})()
    root_ref = hao_main_module._save_bridge_workspace_root(config, workspace)
    state = {
        "adapter_kind": "claude_code",
        "workspace_root_ref": root_ref,
        "workspace_identity_hash": hao_main_module._workspace_identity_hash(
            workspace,
            adapter_kind="claude_code",
        ),
    }
    probe = _claude_probe(hao_main_module)
    captured: dict[str, object] = {}

    def fake_run(command: list[str], **kwargs) -> subprocess.CompletedProcess:
        captured["command"] = command
        captured["kwargs"] = kwargs
        stdout = (
            '{"type":"system","subtype":"init","tools":[],"mcp_servers":[]}\n'
            '{"type":"assistant","message":{"role":"assistant","content":[{"text":"hello "}]}}\n'
            '{"type":"result","result":"world","session_id":"claude-session-secret"}\n'
        )
        return subprocess.CompletedProcess(command, 0, stdout=stdout, stderr="")

    monkeypatch.setenv("HOME", "/Users/luohao")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-secret")
    monkeypatch.setattr(hao_main_module, "_probe_claude_code_cli", lambda: probe)
    monkeypatch.setattr(hao_main_module.subprocess, "run", fake_run)

    result = hao_main_module._run_claude_code_cli(
        config=config,
        state=state,
        payload={
            "message": "hello from workspace token=sk-ant-secret",
            "workspace_identity_hash": state["workspace_identity_hash"],
            "conversation_context": [
                {"role": "user", "content": "prior /Users/luohao/private/file.txt"},
                {"role": "assistant", "content": "answer sk-ant-abcdef123456"},
            ],
        },
    )

    assert result.status == "completed"
    assert result.content == "hello world"
    assert result.session_id == "claude-session-secret"
    command = captured["command"]
    assert isinstance(command, list)
    assert command[:2] == ["/opt/claude/bin/claude", "--bare"]
    assert "--tools" in command
    assert command[command.index("--tools") + 1] == ""
    assert "--no-session-persistence" in command
    assert "hello from workspace" not in command
    assert str(workspace) not in command
    kwargs = captured["kwargs"]
    assert isinstance(kwargs, dict)
    assert "hello from workspace token=[REDACTED]" in str(kwargs["input"])
    assert ".../private/file.txt" in str(kwargs["input"])
    assert "/Users/luohao" not in str(kwargs["input"])
    assert Path(str(kwargs["cwd"])).parent != workspace
    assert str(kwargs["cwd"]) != str(workspace)
    env = kwargs["env"]
    assert isinstance(env, dict)
    assert "ANTHROPIC_API_KEY" not in env
    assert env["HOME"] != "/Users/luohao"
    assert Path(env["CLAUDE_CONFIG_DIR"]).parent == Path(env["TMPDIR"])


def test_hao_bridge_v5_run_claude_cli_rejects_workspace_and_process_failures(
    tmp_path: Path,
    monkeypatch,
) -> None:
    hao_main_module = importlib.import_module("app.cli.hao.main")
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    config = type("Config", (), {"home": tmp_path / "hao-home"})()
    root_ref = hao_main_module._save_bridge_workspace_root(config, workspace)
    state = {
        "adapter_kind": "claude_code",
        "workspace_root_ref": root_ref,
        "workspace_identity_hash": hao_main_module._workspace_identity_hash(
            workspace,
            adapter_kind="claude_code",
        ),
    }
    probe = _claude_probe(hao_main_module)
    monkeypatch.setattr(hao_main_module, "_probe_claude_code_cli", lambda: probe)

    spawned: list[list[str]] = []

    def fake_run(command: list[str], **kwargs) -> subprocess.CompletedProcess:
        del kwargs
        spawned.append(command)
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr(hao_main_module.subprocess, "run", fake_run)
    sidecar_mismatch = hao_main_module._run_claude_code_cli(
        config=config,
        state={**state, "workspace_identity_hash": "wrong-local-sidecar"},
        payload={"message": "hello"},
    )
    assert sidecar_mismatch.status == "error"
    assert "workspace root sidecar" in sidecar_mismatch.error_message
    assert spawned == []

    server_mismatch = hao_main_module._run_claude_code_cli(
        config=config,
        state=state,
        payload={"message": "hello", "workspace_identity_hash": "wrong-server-hash"},
    )
    assert server_mismatch.status == "error"
    assert "server task" in server_mismatch.error_message
    assert spawned == []

    def timeout_run(command: list[str], **kwargs) -> subprocess.CompletedProcess:
        del kwargs
        raise subprocess.TimeoutExpired(command, 1)

    monkeypatch.setattr(hao_main_module.subprocess, "run", timeout_run)
    timed_out = hao_main_module._run_claude_code_cli(
        config=config,
        state=state,
        payload={"message": "timeout", "workspace_identity_hash": state["workspace_identity_hash"]},
    )
    assert timed_out.status == "error"
    assert "timed out" in timed_out.error_message

    source_home = tmp_path / "source-home"
    source_claude = source_home / ".claude"
    source_claude.mkdir(parents=True)
    (source_claude / "settings.json").write_text(
        json.dumps({"env": {"ANTHROPIC_AUTH_TOKEN": "settings-auth-token"}}),
        encoding="utf-8",
    )
    monkeypatch.setenv("HOME", str(source_home))
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    def nonzero_run(command: list[str], **kwargs) -> subprocess.CompletedProcess:
        del kwargs
        return subprocess.CompletedProcess(
            command,
            2,
            stdout="",
            stderr=(
                "failed auth settings-auth-token token=sk-ant-secret "
                "/Users/luohao/private/file.txt"
            ),
        )

    monkeypatch.setattr(hao_main_module.subprocess, "run", nonzero_run)
    nonzero = hao_main_module._run_claude_code_cli(
        config=config,
        state=state,
        payload={"message": "nonzero", "workspace_identity_hash": state["workspace_identity_hash"]},
    )
    assert nonzero.status == "error"
    assert "settings-auth-token" not in nonzero.error_message
    assert "sk-ant" not in nonzero.error_message
    assert "/Users/luohao" not in nonzero.error_message
    assert nonzero.metadata == {"exit_code": 2}


def test_hao_bridge_v4_run_codex_cli_rejects_server_workspace_mismatch(
    tmp_path: Path,
    monkeypatch,
) -> None:
    hao_main_module = importlib.import_module("app.cli.hao.main")
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    config = type("Config", (), {"home": tmp_path / "hao-home"})()
    root_ref = hao_main_module._save_bridge_workspace_root(config, workspace)
    state = {
        "workspace_root_ref": root_ref,
        "workspace_identity_hash": hao_main_module._workspace_identity_hash(workspace),
    }
    probe = hao_main_module.CodexCliProbe(
        installed=True,
        executable="/opt/codex/bin/codex",
        exec_help="--json --output-last-message -C --sandbox read-only",
    )
    spawned: list[list[str]] = []

    def fake_run(command: list[str], **kwargs) -> subprocess.CompletedProcess:
        del kwargs
        spawned.append(command)
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr(hao_main_module, "_probe_codex_cli", lambda: probe)
    monkeypatch.setattr(hao_main_module.subprocess, "run", fake_run)

    result = hao_main_module._run_codex_cli(
        config=config,
        state=state,
        payload={"message": "wrong workspace", "workspace_identity_hash": "server-hash"},
    )

    assert result.status == "error"
    assert "server task" in result.error_message
    assert spawned == []


def test_hao_bridge_v4_codex_run_cannot_rewrite_paired_workspace(
    tmp_path: Path,
    monkeypatch,
) -> None:
    hao_main_module = importlib.import_module("app.cli.hao.main")
    original = tmp_path / "original"
    other = tmp_path / "other"
    original.mkdir()
    other.mkdir()
    monkeypatch.setenv("HAO_HOME", str(tmp_path / "hao-home"))
    config = hao_main_module.load_config()
    workspace_ref = hao_main_module._save_bridge_workspace_root(config, original)
    hao_main_module._save_bridge_state(
        config,
        {
            "api_url": "http://127.0.0.1:8000",
            "connection_id": "codex-connection",
            "device_token": "codex-device-token",
            "adapter_kind": "codex",
            "workspace_root_ref": workspace_ref,
            "workspace_identity_hash": hao_main_module._workspace_identity_hash(original),
        },
    )

    exit_code = hao_main_module.main(
        [
            "bridge",
            "run",
            "--adapter",
            "codex",
            "--cwd",
            str(other),
            "--once",
        ]
    )

    assert exit_code == 1
    state = hao_main_module._load_bridge_state(config)
    assert state["workspace_identity_hash"] == hao_main_module._workspace_identity_hash(original)
    assert (config.home / str(state["workspace_root_ref"])).read_text(encoding="utf-8") == str(
        original.resolve()
    )


def test_hao_bridge_v4_run_preserves_saved_codex_adapter_without_adapter_arg(
    tmp_path: Path,
    monkeypatch,
) -> None:
    hao_main_module = importlib.import_module("app.cli.hao.main")
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    monkeypatch.setenv("HAO_HOME", str(tmp_path / "hao-home"))
    config = hao_main_module.load_config()
    workspace_ref = hao_main_module._save_bridge_workspace_root(config, workspace)
    hao_main_module._save_bridge_device_token(config, "codex-device-token")
    hao_main_module._save_bridge_state(
        config,
        {
            "api_url": "http://127.0.0.1:8000",
            "connection_id": "codex-connection",
            "device_token_ref": "bridge.device-token",
            "adapter_kind": "codex",
            "workspace_root_ref": workspace_ref,
            "workspace_identity_hash": hao_main_module._workspace_identity_hash(workspace),
        },
    )
    handled: list[str] = []

    class FakeClient:
        def __init__(self, api_url: str, token: str = "", timeout: float = 30.0) -> None:
            del api_url, token, timeout

        def heartbeat_local_agent_connection(self, **kwargs) -> dict:
            assert kwargs["device_token"] == "codex-device-token"
            return {}

        def pull_local_agent_bridge_tasks(self, *, device_token: str) -> dict:
            assert device_token == "codex-device-token"
            return {"items": [{"id": "task-1", "payload": {"message": "hello"}}]}

        def ack_local_agent_bridge_task(self, **kwargs) -> dict:
            assert kwargs["device_token"] == "codex-device-token"
            assert kwargs["status"] == "running"
            return {}

    def fake_handle_codex(**kwargs) -> None:
        handled.append(kwargs["state"]["adapter_kind"])

    resumed: list[str] = []

    def record_pending_tool_resume(**kwargs) -> None:
        resumed.append(kwargs["device_token"])

    monkeypatch.setattr(hao_main_module, "HarnessApiClient", FakeClient)
    monkeypatch.setattr(hao_main_module, "_handle_codex_bridge_task", fake_handle_codex)
    monkeypatch.setattr(hao_main_module, "_resume_bridge_pending_tools", record_pending_tool_resume)

    exit_code = hao_main_module.main(["bridge", "run", "--once"])

    assert exit_code == 0
    assert resumed == ["codex-device-token"]
    assert handled == ["codex"]
    state = hao_main_module._load_bridge_state(config)
    assert state["adapter_kind"] == "codex"


def test_hao_bridge_run_waits_for_onboarding_confirmation_before_pulling_tasks(
    tmp_path: Path,
    monkeypatch,
) -> None:
    hao_main_module = importlib.import_module("app.cli.hao.main")
    monkeypatch.setenv("HAO_HOME", str(tmp_path / "hao-home"))
    config = hao_main_module.load_config()
    hao_main_module._save_bridge_device_token(config, "device-token")
    hao_main_module._save_bridge_state(
        config,
        {
            "api_url": "http://127.0.0.1:8000",
            "connection_id": "connection-1",
            "device_token_ref": "bridge.device-token",
            "adapter_kind": "hao",
            "cwd": str(tmp_path),
        },
    )
    calls: list[str] = []

    class FakeClient:
        def __init__(self, api_url: str, token: str = "", timeout: float = 30.0) -> None:
            del api_url, token, timeout

        def heartbeat_local_agent_connection(self, **kwargs) -> dict:
            assert kwargs["device_token"] == "device-token"
            calls.append("heartbeat")
            return {"connection": {"id": kwargs["connection_id"], "onboarding_confirmed": False}}

        def pull_local_agent_bridge_tasks(self, *, device_token: str) -> dict:
            del device_token
            calls.append("pull")
            return {"items": [{"id": "task-1", "payload": {"message": "should not run"}}]}

    monkeypatch.setattr(hao_main_module, "HarnessApiClient", FakeClient)
    monkeypatch.setattr(hao_main_module, "_resume_bridge_pending_tools", lambda **kwargs: None)

    exit_code = hao_main_module.main(["bridge", "run", "--once"])

    assert exit_code == 0
    assert calls == ["heartbeat"]


def test_hao_bridge_run_treats_unconfirmed_pull_rejection_as_wait_state(
    tmp_path: Path,
    monkeypatch,
) -> None:
    hao_main_module = importlib.import_module("app.cli.hao.main")
    monkeypatch.setenv("HAO_HOME", str(tmp_path / "hao-home"))
    config = hao_main_module.load_config()
    hao_main_module._save_bridge_device_token(config, "device-token")
    hao_main_module._save_bridge_state(
        config,
        {
            "api_url": "http://127.0.0.1:8000",
            "connection_id": "connection-1",
            "device_token_ref": "bridge.device-token",
            "adapter_kind": "hao",
            "cwd": str(tmp_path),
        },
    )
    calls: list[str] = []

    class FakeClient:
        def __init__(self, api_url: str, token: str = "", timeout: float = 30.0) -> None:
            del api_url, token, timeout

        def heartbeat_local_agent_connection(self, **kwargs) -> dict:
            assert kwargs["device_token"] == "device-token"
            calls.append("heartbeat")
            return {"connection": {"id": kwargs["connection_id"]}}

        def pull_local_agent_bridge_tasks(self, *, device_token: str) -> dict:
            assert device_token == "device-token"
            calls.append("pull")
            request = httpx.Request("GET", "http://127.0.0.1:8000/api/agents/local-agent/bridge/tasks")
            response = httpx.Response(
                409,
                json={"detail": "Local Agent connection has not been confirmed"},
                request=request,
            )
            raise httpx.HTTPStatusError(
                "Local Agent connection has not been confirmed",
                request=request,
                response=response,
            )

    monkeypatch.setattr(hao_main_module, "HarnessApiClient", FakeClient)

    exit_code = hao_main_module.main(["bridge", "run", "--once"])

    assert exit_code == 0
    assert calls == ["heartbeat", "pull"]


def test_hao_bridge_v4_run_rejects_explicit_adapter_mismatch(
    tmp_path: Path,
    monkeypatch,
) -> None:
    hao_main_module = importlib.import_module("app.cli.hao.main")
    monkeypatch.setenv("HAO_HOME", str(tmp_path / "hao-home"))
    config = hao_main_module.load_config()
    hao_main_module._save_bridge_device_token(config, "codex-device-token")
    hao_main_module._save_bridge_state(
        config,
        {
            "api_url": "http://127.0.0.1:8000",
            "connection_id": "codex-connection",
            "device_token_ref": "bridge.device-token",
            "adapter_kind": "codex",
            "workspace_identity_hash": "hash-1",
        },
    )

    exit_code = hao_main_module.main(["bridge", "run", "--adapter", "hao", "--once"])

    assert exit_code == 1
    assert hao_main_module._load_bridge_state(config)["adapter_kind"] == "codex"


def test_hao_bridge_v4_codex_prompt_replays_bounded_redacted_context() -> None:
    hao_main_module = importlib.import_module("app.cli.hao.main")

    prompt = hao_main_module._codex_prompt_for_task(
        {
            "resume_mode": "context_replay_new_session",
            "conversation_context": [
                {
                    "role": "user",
                    "content": "First ask TOKEN=raw-token /Users/luohao/private/file.txt",
                },
                {"role": "assistant", "content": "First answer sk-proj-1234567890abcdef"},
                {"role": "system", "content": "ignored"},
            ],
            "message": "Second ask password=hunter2",
        }
    )

    assert "Harness conversation context from prior turns:" in prompt
    assert "user: First ask TOKEN=[REDACTED] .../private/file.txt" in prompt
    assert "assistant: First answer [REDACTED]" in prompt
    assert "ignored" not in prompt
    assert "Second ask password=[REDACTED]" in prompt
    assert "raw-token" not in prompt
    assert "hunter2" not in prompt
    assert "/Users/luohao" not in prompt


def test_hao_bridge_v4_codex_terminal_event_ids_are_stable(monkeypatch) -> None:
    hao_main_module = importlib.import_module("app.cli.hao.main")
    captured_payloads: list[dict] = []

    class FakeClient:
        def report_local_agent_bridge_event(self, *, device_token: str, payload: dict) -> dict:
            captured_payloads.append(payload)
            return {"ok": True}

    def completed_codex(**kwargs):
        on_delta = kwargs.get("on_delta")
        assert callable(on_delta)
        on_delta("do")
        on_delta("ne")
        return hao_main_module.CodexRunResult(
            status="completed",
            content="done",
            session_id="session-1",
            metadata={"exit_code": 0, "streamed_delta_count": 2},
        )

    monkeypatch.setattr(hao_main_module, "_run_codex_cli", completed_codex)

    hao_main_module._handle_codex_bridge_task(
        config=object(),
        state={"workspace_identity_hash": "hash-1"},
        client=FakeClient(),
        device_token="device-token",
        task={"id": "task-1", "payload": {"message": "hello"}},
    )

    assert [payload["event_id"] for payload in captured_payloads] == [
        "task-1:codex:started",
        "task-1:codex:delta:2",
        "task-1:codex:delta:3",
        "task-1:codex:done",
    ]
    assert [payload["sequence"] for payload in captured_payloads] == [1, 2, 3, 4]
    assert [payload.get("content") for payload in captured_payloads[1:3]] == ["do", "ne"]

    captured_payloads.clear()
    def failed_codex(**kwargs):
        on_delta = kwargs.get("on_delta")
        assert callable(on_delta)
        on_delta("partial ")
        return hao_main_module.CodexRunResult(
            status="error",
            error_message="codex unavailable",
        )

    monkeypatch.setattr(hao_main_module, "_run_codex_cli", failed_codex)

    hao_main_module._handle_codex_bridge_task(
        config=object(),
        state={"workspace_identity_hash": "hash-1"},
        client=FakeClient(),
        device_token="device-token",
        task={"id": "task-2", "payload": {"message": "hello"}},
    )

    assert [payload["event_id"] for payload in captured_payloads] == [
        "task-2:codex:started",
        "task-2:codex:delta:2",
        "task-2:codex:error",
    ]
    assert [payload["sequence"] for payload in captured_payloads] == [1, 2, 3]


def test_hao_bridge_v5_claude_terminal_event_ids_are_stable(monkeypatch) -> None:
    hao_main_module = importlib.import_module("app.cli.hao.main")
    captured_payloads: list[dict] = []

    class FakeClient:
        def report_local_agent_bridge_event(self, *, device_token: str, payload: dict) -> dict:
            captured_payloads.append(payload)
            return {"ok": True}

    def completed_claude(**kwargs):
        on_delta = kwargs.get("on_delta")
        assert callable(on_delta)
        on_delta("do")
        on_delta("ne")
        return hao_main_module.ClaudeCodeRunResult(
            status="completed",
            content="done",
            session_id="session-1",
            metadata={"exit_code": 0, "api_key": "sk-ant-secret", "streamed_delta_count": 2},
        )

    monkeypatch.setattr(hao_main_module, "_run_claude_code_cli", completed_claude)

    hao_main_module._handle_claude_code_bridge_task(
        config=object(),
        state={"workspace_identity_hash": "hash-1"},
        client=FakeClient(),
        device_token="device-token",
        task={"id": "task-1", "payload": {"message": "hello"}},
    )

    assert [payload["event_id"] for payload in captured_payloads] == [
        "task-1:claude_code:started",
        "task-1:claude_code:delta:2",
        "task-1:claude_code:delta:3",
        "task-1:claude_code:done",
    ]
    assert [payload["sequence"] for payload in captured_payloads] == [1, 2, 3, 4]
    assert [payload.get("content") for payload in captured_payloads[1:3]] == ["do", "ne"]
    assert captured_payloads[-1]["metadata"]["api_key"] == "[REDACTED]"

    captured_payloads.clear()
    def failed_claude(**kwargs):
        on_delta = kwargs.get("on_delta")
        assert callable(on_delta)
        on_delta("partial ")
        return hao_main_module.ClaudeCodeRunResult(
            status="error",
            error_message="claude unavailable",
            metadata={"stderr": "/Users/luohao/private token=sk-ant-secret"},
        )

    monkeypatch.setattr(hao_main_module, "_run_claude_code_cli", failed_claude)

    hao_main_module._handle_claude_code_bridge_task(
        config=object(),
        state={"workspace_identity_hash": "hash-1"},
        client=FakeClient(),
        device_token="device-token",
        task={"id": "task-2", "payload": {"message": "hello"}},
    )

    assert [payload["event_id"] for payload in captured_payloads] == [
        "task-2:claude_code:started",
        "task-2:claude_code:delta:2",
        "task-2:claude_code:error",
    ]
    assert [payload["sequence"] for payload in captured_payloads] == [1, 2, 3]
    assert "sk-ant" not in captured_payloads[-1]["metadata"]["stderr"]
    assert "/Users/luohao" not in captured_payloads[-1]["metadata"]["stderr"]


def test_hao_bridge_v4_run_codex_cli_streams_stdout_deltas(
    tmp_path: Path,
    monkeypatch,
) -> None:
    hao_main_module = importlib.import_module("app.cli.hao.main")
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    config = type("Config", (), {"home": tmp_path / "hao-home"})()
    root_ref = hao_main_module._save_bridge_workspace_root(config, workspace)
    state = {
        "workspace_root_ref": root_ref,
        "workspace_identity_hash": hao_main_module._workspace_identity_hash(workspace),
    }
    probe = hao_main_module.CodexCliProbe(
        installed=True,
        executable="/opt/codex/bin/codex",
        exec_help="--json --output-last-message -C --sandbox read-only",
    )
    streamed: list[str] = []

    class FakePopen:
        def __init__(self, command, **kwargs):
            output_path = Path(command[command.index("--output-last-message") + 1])
            output_path.write_text("final answer", encoding="utf-8")
            self.stdin = io.StringIO()
            self.stdout = io.StringIO(
                '{"type":"assistant_delta","delta":"Hello "}\n'
                '{"type":"assistant_delta","delta":"world"}\n'
            )
            self.returncode = 0

        def wait(self, timeout=None):
            del timeout
            return self.returncode

        def kill(self):
            self.returncode = -9

    monkeypatch.setattr(hao_main_module, "_probe_codex_cli", lambda: probe)
    monkeypatch.setattr(hao_main_module.subprocess, "Popen", FakePopen)

    result = hao_main_module._run_codex_cli(
        config=config,
        state=state,
        payload={
            "message": "hello",
            "workspace_identity_hash": state["workspace_identity_hash"],
        },
        on_delta=streamed.append,
    )

    assert result.status == "completed"
    assert result.content == "final answer"
    assert streamed == ["Hello ", "world"]
    assert result.metadata["streamed_delta_count"] == 2


def test_hao_bridge_v5_run_claude_cli_streams_after_safety_init(
    tmp_path: Path,
    monkeypatch,
) -> None:
    hao_main_module = importlib.import_module("app.cli.hao.main")
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    config = type("Config", (), {"home": tmp_path / "hao-home"})()
    root_ref = hao_main_module._save_bridge_workspace_root(config, workspace)
    state = {
        "adapter_kind": "claude_code",
        "workspace_root_ref": root_ref,
        "workspace_identity_hash": hao_main_module._workspace_identity_hash(
            workspace,
            adapter_kind="claude_code",
        ),
    }
    streamed: list[str] = []

    class FakePopen:
        def __init__(self, command, **kwargs):
            del command, kwargs
            self.stdin = io.StringIO()
            self.stdout = io.StringIO(
                '{"type":"assistant","content":"queued "}\n'
                '{"type":"system","subtype":"init","tools":[],"mcp_servers":[]}\n'
                '{"type":"assistant","content":"streamed"}\n'
                '{"type":"result","result":"queued streamed","session_id":"session-1"}\n'
            )
            self.returncode = 0

        def wait(self, timeout=None):
            del timeout
            return self.returncode

        def kill(self):
            self.returncode = -9

    monkeypatch.setattr(
        hao_main_module,
        "_probe_claude_code_cli",
        lambda: _claude_probe(hao_main_module),
    )
    monkeypatch.setattr(hao_main_module.subprocess, "Popen", FakePopen)

    result = hao_main_module._run_claude_code_cli(
        config=config,
        state=state,
        payload={
            "message": "hello",
            "workspace_identity_hash": state["workspace_identity_hash"],
        },
        on_delta=streamed.append,
    )

    assert result.status == "completed"
    assert result.content == "queued streamed"
    assert result.session_id == "session-1"
    assert streamed == ["queued ", "streamed"]
    assert result.metadata["streamed_delta_count"] == 2


def test_hao_bridge_v4_codex_jsonl_parser_uses_fallback_and_redaction() -> None:
    hao_main_module = importlib.import_module("app.cli.hao.main")
    result = hao_main_module._parse_codex_output(
        '{"type":"assistant_delta","delta":"Hello "}\n'
        '{"item":{"role":"assistant","content":[{"text":"world"}]}}\n'
        'not-json\n',
        "final sk-proj-1234567890abcdef /Users/luohao/private/file.txt",
    )

    assert result.status == "completed"
    assert result.content == "final [REDACTED] .../private/file.txt"
    assert result.metadata == {"delta_count": 2, "used_fallback": True}


def test_hao_bridge_v4_codex_jsonl_parser_ignores_non_assistant_output() -> None:
    hao_main_module = importlib.import_module("app.cli.hao.main")
    result = hao_main_module._parse_codex_output(
        '{"type":"tool_output","output":"do not project"}\n'
        '{"type":"command","message":"do not project either"}\n'
        '{"message":{"role":"assistant","content":"assistant text"}}\n',
        "",
    )

    assert result.status == "completed"
    assert result.content == "assistant text"
    assert result.metadata == {"delta_count": 1, "used_fallback": False}


def test_hao_bridge_v5_claude_jsonl_parser_requires_empty_tool_safety_proof() -> None:
    hao_main_module = importlib.import_module("app.cli.hao.main")

    result = hao_main_module._parse_claude_code_output(
        '{"type":"system","subtype":"init","tools":[],"mcp_servers":[]}\n'
        '{"type":"assistant","message":{"role":"assistant","content":[{"text":"Hello"}]}}\n'
        '{"type":"result","result":" world sk-ant-secret123456 /Users/luohao/private.txt",'
        '"session_id":"session-1"}\n'
    )

    assert result.status == "completed"
    assert result.content == "Hello world [REDACTED] .../private.txt"
    assert result.session_id == "session-1"
    assert result.metadata == {
        "system_init_safe": True,
        "tools_count": 0,
        "mcp_servers_count": 0,
        "delta_count": 1,
        "result_text_present": True,
        "used_fallback": False,
    }

    unsafe = hao_main_module._parse_claude_code_output(
        '{"type":"system","subtype":"init","tools":["Read"],"mcp_servers":[]}\n'
        '{"type":"assistant","content":"should not project"}\n'
    )
    assert unsafe.status == "error"
    assert "unsafe system/init" in unsafe.error_message

    missing = hao_main_module._parse_claude_code_output(
        '{"type":"assistant","content":"missing safety"}\n'
    )
    assert missing.status == "error"
    assert "missing empty-tool" in missing.error_message


def test_hao_bridge_v5_claude_jsonl_parser_ignores_generic_non_assistant_records() -> None:
    hao_main_module = importlib.import_module("app.cli.hao.main")

    result = hao_main_module._parse_claude_code_output(
        '{"type":"system","subtype":"init","tools":[],"mcp_servers":[]}\n'
        '{"type":"message","content":"generic message must not project"}\n'
        '{"type":"message","message":{"role":"user","content":"user text must not project"}}\n'
        '{"type":"assistant","message":{"role":"assistant","content":"assistant text"}}\n'
    )

    assert result.status == "completed"
    assert result.content == "assistant text"
    assert result.metadata == {
        "system_init_safe": True,
        "tools_count": 0,
        "mcp_servers_count": 0,
        "delta_count": 1,
        "result_text_present": False,
        "used_fallback": False,
    }


def test_hao_session_store_persists_messages_and_tool_events(tmp_path: Path) -> None:
    store = SessionStore(tmp_path / "hao.db", tmp_path / "sessions")
    session = store.create_session(
        cwd="/tmp/work",
        agent_id="default",
        mode="confirm",
        target="host",
    )
    store.update_run_id(session.id, "run-1")
    store.record_stream_event(
        session.id,
        event="run_created",
        data={"run_id": "run-1"},
        raw='event: run_created\ndata: {"run_id": "run-1"}',
    )
    store.append_message(session.id, role="user", content="hello", run_id="run-1")
    store.append_message(
        session.id,
        role="tool",
        content="tool result",
        run_id="run-1",
        metadata={"tool_name": "read_file"},
    )
    store.record_tool_event(
        session.id,
        run_id="run-1",
        tool_call_id="tool-1",
        tool_name="read_file",
        status="SUCCESS",
        input_json={"path": "README.md"},
        output_json={
            "content": "ok",
            "command": "printf ok",
            "exit_code": 0,
            "stdout": "ok",
            "diff": "--- a/README.md\n+++ b/README.md\n",
        },
        duration_ms=1,
    )

    loaded = store.get_session(session.id)
    assert loaded is not None
    assert loaded.run_id == "run-1"
    assert store.list_messages(session.id)[0]["content"] == "hello"
    assert store.list_messages(session.id)[1]["role"] == "tool"
    assert store.list_sessions()[0].id == session.id
    assert store.list_tool_events(session.id)[0]["tool_name"] == "read_file"
    session_dir = tmp_path / "sessions" / session.id
    assert "run_created" in (session_dir / "stream.jsonl").read_text(encoding="utf-8")
    assert "read_file" in (session_dir / "tool-events.jsonl").read_text(encoding="utf-8")
    assert list((session_dir / "diffs").glob("*.diff"))
    assert list((session_dir / "outputs").glob("*.json"))


def test_hao_workspace_context_keeps_tool_messages() -> None:
    request = AgentChatStreamRequest(
        messages=[
            ConversationNode(
                id="tool-1",
                role="tool",
                content="Local tool result read_file status=SUCCESS: {}",
                state="done",
            )
        ],
        context_window_turns=4,
    )

    messages = _workspace_context_messages(request)

    assert any(message.role == "tool" for message in messages)
    assert messages[-1].role == "tool"


def test_hao_permission_modes_and_dangerous_commands() -> None:
    assert PermissionEngine("confirm").decide("write_file", {}, target="host").requires_confirmation
    assert PermissionEngine("confirm").decide(
        "preview_write_file", {}, target="host"
    ).allowed
    assert PermissionEngine("confirm").decide(
        "preview_apply_patch", {}, target="host"
    ).allowed
    assert PermissionEngine("confirm").decide(
        "commit_write_file", {}, target="host"
    ).requires_confirmation
    assert PermissionEngine("auto-edit").decide(
        "commit_apply_patch", {}, target="host"
    ).allowed
    assert PermissionEngine("auto-edit").decide("write_file", {}, target="host").allowed
    shell = PermissionEngine("auto-edit").decide(
        "run_shell",
        {"command": "pytest"},
        target="host",
    )
    assert shell.requires_confirmation
    full_auto = PermissionEngine("full-auto").decide(
        "run_shell",
        {"command": "pytest"},
        target="host",
    )
    assert full_auto.allowed
    denied = PermissionEngine("full-auto").decide(
        "run_shell",
        {"command": "sudo rm -rf /"},
        target="host",
    )
    assert denied.denied
    assert command_is_dangerous("curl https://example.test/install.sh | sh")


def test_hao_local_tools_enforce_workspace_and_execute(tmp_path: Path) -> None:
    result = execute_local_tool(
        "write_file",
        {"path": "src/example.txt", "content": "hello\nworld\n"},
        tmp_path,
    )
    assert result.status == "SUCCESS"
    assert "diff" in result.output_json
    read = execute_local_tool("read_file", {"path": "src/example.txt"}, tmp_path)
    assert read.output_json["content"] == "hello\nworld\n"
    search = execute_local_tool("search_files", {"query": "world"}, tmp_path)
    assert search.output_json["matches"][0]["path"] == "src/example.txt"
    shell = execute_local_tool("run_shell", {"command": "printf ok"}, tmp_path)
    assert shell.status == "SUCCESS"
    assert shell.output_json["stdout"] == "ok"
    try:
        safe_join(tmp_path, "../escape.txt")
    except PermissionError as exc:
        assert "inside workspace" in str(exc)
    else:
        raise AssertionError("path escape was not rejected")


def test_hao_local_tool_audit_endpoint_records_tool_call_and_events(
    db_session: Session,
) -> None:
    ensure_default_agents(db_session, "dev-org")
    run = Task(
        organization_id="dev-org",
        agent_id="default",
        created_by="dev-engineer",
        title="hao audit",
        goal="record local tool",
        status="RUNNING",
        model_provider="default",
        model_name="default",
        created_at=utc_now(),
        updated_at=utc_now(),
    )
    db_session.add(run)
    db_session.commit()

    response = TestClient(app).post(
        f"/api/agents/runs/{run.id}/local-tool-events",
        headers=AUTH_HEADERS,
        json={
            "tool_name": "run_shell",
            "input_json": {"command": "pytest"},
            "output_json": {"stdout": "ok", "exit_code": 0},
            "status": "SUCCESS",
            "risk_level": "high",
            "duration_ms": 12,
            "execution_target": "host",
            "permission_mode": "confirm",
            "local_session_id": "local-1",
            "cwd": "/tmp/work",
        },
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["tool_call"]["tool_name"] == "run_shell"
    assert payload["tool_call"]["status"] == "SUCCESS"
    tool_call = db_session.execute(select(ToolCall)).scalar_one()
    assert tool_call.task_id == run.id
    assert tool_call.agent_run_id is None
    events = list(
        db_session.execute(
            select(AgentEvent).where(AgentEvent.task_id == run.id).order_by(AgentEvent.sequence)
        ).scalars()
    )
    assert [event.event_type for event in events] == [
        "POLICY_CHECKED",
        "TOOL_CALLED",
        "TOOL_RESULT_RECEIVED",
    ]
    assert events[-1].payload_json["local_session_id"] == "local-1"


def test_hao_cli_agent_stream_requests_local_tool_execution(
    db_session: Session,
    monkeypatch,
) -> None:
    ensure_default_agents(db_session, "dev-org")

    class FakeGateway:
        def __init__(self, *args, **kwargs) -> None:
            del args, kwargs

        def stream(self, request):
            del request
            yield ModelStreamChunk(text="I will inspect the file.\n")
            yield ModelStreamChunk(
                text=(
                    "<function_calls><invoke name=\"read_file\">"
                    "<parameter name=\"path\">README.md</parameter>"
                    "</invoke></function_calls>"
                ),
                usage={"prompt_tokens": 1, "completion_tokens": 2},
                done=True,
            )

    monkeypatch.setattr(
        "app.api.agents.agent_chat.streaming.AuditedModelGateway",
        FakeGateway,
    )

    response = TestClient(app).post(
        "/api/agents/default/runs/chat/stream",
        headers=AUTH_HEADERS,
        json={
            "mode": "cli_agent",
            "goal": "inspect the workspace",
            "messages": [
                {
                    "id": "user-1",
                    "role": "user",
                    "content": "inspect the workspace",
                    "state": "done",
                    "children_ids": [],
                    "metadata": {},
                    "tool_calls": [],
                    "artifacts": [],
                }
            ],
        },
    )

    assert response.status_code == 200
    events = parse_sse_stream(response.text)
    assert [event.event for event in events if event.event != "usage"][:3] == [
        "run_created",
        "delta",
        "tool_call_requested",
    ]
    tool_request = next(event for event in events if event.event == "tool_call_requested")
    assert tool_request.data["status"] == "pending_local"
    assert tool_request.data["sandbox"] == "host"
    assert any(event.event == "done" for event in events)


def test_hao_markdown_plan_stream_does_not_request_local_tools(
    db_session: Session,
    monkeypatch,
) -> None:
    ensure_default_agents(db_session, "dev-org")

    class FakeGateway:
        def __init__(self, *args, **kwargs) -> None:
            del args, kwargs

        def stream(self, request):
            del request
            yield ModelStreamChunk(text="1. Inspect the current files.\n")
            yield ModelStreamChunk(
                text=(
                    "<function_calls><invoke name=\"read_file\">"
                    "<parameter name=\"path\">README.md</parameter>"
                    "</invoke></function_calls>"
                ),
                usage={"prompt_tokens": 1, "completion_tokens": 2},
                done=True,
            )

    monkeypatch.setattr(
        "app.api.agents.agent_chat.streaming.AuditedModelGateway",
        FakeGateway,
    )

    response = TestClient(app).post(
        "/api/agents/default/runs/chat/stream",
        headers=AUTH_HEADERS,
        json={
            "mode": "markdown_plan",
            "interaction_mode": "plan",
            "goal": "draft a safe plan",
            "messages": [
                {
                    "id": "user-1",
                    "role": "user",
                    "content": "draft a safe plan",
                    "state": "done",
                    "children_ids": [],
                    "metadata": {},
                    "tool_calls": [],
                    "artifacts": [],
                }
            ],
        },
    )

    assert response.status_code == 200
    events = parse_sse_stream(response.text)
    assert "tool_call_requested" not in [event.event for event in events]
    assert any(
        event.event == "delta" and "Inspect the current files" in event.data["content"]
        for event in events
    )
    done = next(event for event in events if event.event == "done")
    assert done.data["status"] == "COMPLETED"
