import json
import re
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.model_gateway import ModelGatewayError, ModelResponse, ModelStreamChunk
from app.agents.planner import DeterministicPlanner
from app.api.agents import _normalize_grounding_citations
from app.db.models import (
    Agent,
    AgentAssignment,
    AgentEvent,
    CitationRecord,
    ExecutionPlan,
    SandboxInstance,
    SystemSetting,
    Task,
    TaskStep,
    ToolApproval,
    ToolCall,
    utc_now,
)
from app.main import app
from app.sandbox.docker_manager import SandboxCommandResult
from app.workers.agent_assignment_worker import execute_agent_assignment
from tests.conftest import AUTH_HEADERS


def parse_sse_events(body: str) -> list[tuple[str, dict]]:
    events: list[tuple[str, dict]] = []
    for frame in body.strip().split("\n\n"):
        event_line = next((line for line in frame.splitlines() if line.startswith("event:")), None)
        data_line = next((line for line in frame.splitlines() if line.startswith("data:")), None)
        if event_line is None or data_line is None:
            continue
        events.append(
            (
                event_line.removeprefix("event:").strip(),
                json.loads(data_line.removeprefix("data:").strip()),
            )
        )
    return events


def test_normalize_grounding_citations_supports_web_citation_keys() -> None:
    grounding = SimpleNamespace(citations=[SimpleNamespace(citation_key="[W1]")])

    normalized = _normalize_grounding_citations(
        content="Valid web citation [W1], unsupported web citation [W999].",
        grounding=grounding,
    )

    assert "[W1]" in normalized
    assert "[W999]" not in normalized
    assert "[unsupported-citation]" in normalized


class FakeWarmPoolManager:
    def __init__(self, *args, **kwargs) -> None:
        pass

    def acquire(
        self,
        *,
        session: Session,
        task_id: str,
        agent_run_id: str | None = None,
    ) -> SandboxInstance:
        sandbox = SandboxInstance(
            task_id=task_id,
            agent_run_id=agent_run_id,
            container_id=f"fake-{task_id}",
            image="fake-sandbox",
            status="IDLE",
            cpu_limit="1",
            memory_limit_mb=512,
            network_enabled=False,
            warm_pool_reused=True,
        )
        session.add(sandbox)
        session.flush()
        return sandbox

    def release(self, *, session: Session, sandbox: SandboxInstance) -> SandboxInstance:
        sandbox.status = "IDLE"
        session.flush()
        return sandbox


def fake_run_command(
    self,
    *,
    session: Session,
    sandbox: SandboxInstance,
    command: str,
    timeout_seconds: int | None,
    cwd: str = "/workspace",
) -> SandboxCommandResult:
    return SandboxCommandResult(
        stdout=f"{command}\n",
        stderr="",
        exit_code=0,
        duration_ms=1,
    )


def test_agent_workspace_pro_chat_stream_answers_normal_chat_without_plan(
    db_session: Session,
    monkeypatch,
) -> None:
    def fake_complete(self, request_payload):
        assert request_payload.response_format == "text"
        return ModelResponse(
            content="我是由测试模型返回的真实回答",
            model_provider=request_payload.model_provider,
            model_name=request_payload.model_name,
            usage={"prompt_tokens": 12, "completion_tokens": 8},
            raw_response={"mode": "test-model"},
        )

    monkeypatch.setattr("app.api.agents.AuditedModelGateway.complete", fake_complete)

    client = TestClient(app)
    response = client.post(
        "/api/agents/default/runs/chat/stream",
        headers=AUTH_HEADERS,
        json={
            "goal": "你是谁",
            "messages": [
                {
                    "id": "user-normal-chat",
                    "parent_id": None,
                    "children_ids": [],
                    "role": "user",
                    "content": "你是谁",
                    "state": "done",
                    "metadata": {},
                    "tool_calls": [],
                    "artifacts": [],
                }
            ],
            "active_leaf_id": "user-normal-chat",
            "active_branch_id": "branch-chat",
            "pinned_node_ids": [],
            "context_window_turns": 8,
        },
    )

    assert response.status_code == 200
    events = parse_sse_events(response.text)
    event_names = [event for event, _payload in events]
    run_created = next(payload for event, payload in events if event == "run_created")
    delta = next(payload for event, payload in events if event == "delta")
    done = next(payload for event, payload in events if event == "done")
    full_answer = "".join(
        payload["content"] for event, payload in events if event == "delta"
    )
    assert "think_delta" not in event_names
    assert "artifact_created" not in event_names
    assert "tool_call_requested" not in event_names
    assert delta["content"].startswith("我是由测试模型返回的真实回答")
    assert "Sources:" not in full_answer
    assert done["step_count"] == 0
    assert done["status"] == "COMPLETED"
    assert done["knowledge_grounding"] == (
        "Local knowledge is insufficient; no web research provider is configured."
    )
    assert db_session.execute(select(ExecutionPlan)).scalar_one_or_none() is None
    run = db_session.get(Task, run_created["run_id"])
    assert run is not None
    assert run.status == "COMPLETED"
    workspace = client.get(
        f"/api/agents/runs/{run_created['run_id']}/workspace",
        headers=AUTH_HEADERS,
    )
    assert workspace.status_code == 200
    grounding = workspace.json()["knowledge_grounding"]
    assert grounding["prompt_manifest"]["included_retrieval_hit_ids_json"] == []
    assert grounding["policy_audits"][0]["decision"] == "no_omission_applicable"


def test_agent_workspace_chat_stream_rewrites_unbound_citation_keys(
    db_session: Session,
    monkeypatch,
) -> None:
    def fake_complete(self, request_payload):
        assert request_payload.response_format == "text"
        return ModelResponse(
            content="模型给出未绑定引用 [999] 和 [W999]",
            model_provider=request_payload.model_provider,
            model_name=request_payload.model_name,
            usage={"prompt_tokens": 12, "completion_tokens": 8},
            raw_response={"mode": "test-model"},
        )

    monkeypatch.setattr("app.api.agents.AuditedModelGateway.complete", fake_complete)

    client = TestClient(app)
    response = client.post(
        "/api/agents/default/runs/chat/stream",
        headers=AUTH_HEADERS,
        json={
            "goal": "不存在的事实",
            "messages": [
                {
                    "id": "user-invalid-citation",
                    "parent_id": None,
                    "children_ids": [],
                    "role": "user",
                    "content": "不存在的事实",
                    "state": "done",
                    "metadata": {},
                    "tool_calls": [],
                    "artifacts": [],
                }
            ],
            "active_leaf_id": "user-invalid-citation",
            "active_branch_id": "branch-chat",
            "pinned_node_ids": [],
            "context_window_turns": 8,
        },
    )

    assert response.status_code == 200
    events = parse_sse_events(response.text)
    run_created = next(payload for event, payload in events if event == "run_created")
    full_answer = "".join(
        payload["content"] for event, payload in events if event == "delta"
    )
    persisted_keys = set(
        db_session.execute(
            select(CitationRecord.citation_key).where(
                CitationRecord.run_id == run_created["run_id"],
            )
        ).scalars()
    )
    emitted_keys = set(re.findall(r"\[(?:(?:web-)?\d+|W\d+)\]", full_answer))

    assert "[999]" not in full_answer
    assert "[W999]" not in full_answer
    assert "[unsupported-citation]" in full_answer
    assert not emitted_keys
    assert emitted_keys <= persisted_keys


def test_agent_workspace_chat_stream_uses_selected_model_and_attachment_context(
    db_session: Session,
    monkeypatch,
) -> None:
    captured_messages = []

    def fake_complete(self, request_payload):
        assert request_payload.model_provider == "deepseek-flash"
        assert request_payload.model_name == "deepseek-v4-flash"
        captured_messages.extend(request_payload.messages)
        return ModelResponse(
            content="收到上下文",
            model_provider=request_payload.model_provider,
            model_name=request_payload.model_name,
            usage={"prompt_tokens": 10, "completion_tokens": 4},
            raw_response={"mode": "test-model"},
        )

    monkeypatch.setattr("app.api.agents.AuditedModelGateway.complete", fake_complete)

    client = TestClient(app)
    response = client.post(
        "/api/agents/default/runs/chat/stream",
        headers=AUTH_HEADERS,
        json={
            "goal": "继续",
            "model_provider": "deepseek-flash",
            "model_name": "deepseek-v4-flash",
            "messages": [],
            "active_leaf_id": None,
            "active_branch_id": "branch-chat",
            "pinned_node_ids": [],
            "context_window_turns": 8,
            "attachment_names": ["reference.png"],
            "attachments": [
                {
                    "name": "卡密导出_20260510.txt",
                    "mime_type": "text/plain",
                    "size_bytes": 18,
                    "content_status": "ready",
                    "content_text": "卡号: 真实卡号\n密码: 真实密码",
                    "truncated": False,
                },
                {
                    "name": "reference.png",
                    "mime_type": "image/png",
                    "size_bytes": 512,
                    "content_status": "unsupported",
                    "content_text": None,
                    "truncated": False,
                },
            ],
        },
    )

    assert response.status_code == 200
    events = parse_sse_events(response.text)
    run_created = next(payload for event, payload in events if event == "run_created")
    run = db_session.get(Task, run_created["run_id"])
    assert run is not None
    assert run.model_provider == "deepseek-flash"
    assert run.model_name == "deepseek-v4-flash"
    assert any(
        message.role == "system"
        and "卡密导出_20260510.txt" in message.content
        and "卡号: 真实卡号" in message.content
        and "do not infer or fabricate" in message.content
        and "reference.png" in message.content
        for message in captured_messages
    )


def test_agent_workspace_context_compression_endpoint_excludes_pinned_and_hashes(
    db_session: Session,
    monkeypatch,
) -> None:
    captured_messages = []

    def fake_complete(self, request_payload):
        captured_messages.extend(request_payload.messages)
        return ModelResponse(
            content="用户要修复上下文压缩；保留 pinned raw。",
            model_provider=request_payload.model_provider,
            model_name=request_payload.model_name,
            usage={"prompt_tokens": 40, "completion_tokens": 8},
            raw_response={"mode": "compression-test"},
        )

    monkeypatch.setattr("app.api.agents.AuditedModelGateway.complete", fake_complete)

    client = TestClient(app)
    response = client.post(
        "/api/agents/default/context/compress",
        headers=AUTH_HEADERS,
        json={
            "model_provider": " DeepSeek ",
            "model_name": " Chat ",
            "messages": [
                {
                    "id": "old-user",
                    "parent_id": None,
                    "children_ids": ["pinned"],
                    "role": "user",
                    "content": "请修复上下文压缩",
                    "state": "done",
                    "metadata": {},
                    "tool_calls": [],
                    "artifacts": [],
                    "created_at": "2026-05-14T00:00:00Z",
                },
                {
                    "id": "pinned",
                    "parent_id": "old-user",
                    "children_ids": [],
                    "role": "assistant",
                    "content": "这条必须 raw 注入",
                    "state": "done",
                    "metadata": {},
                    "tool_calls": [],
                    "artifacts": [],
                    "created_at": "2026-05-14T00:00:01Z",
                },
            ],
            "pinned_node_ids": ["pinned"],
            "summary_schema_version": "workspace-context-summary-v1",
            "compression_prompt_version": "workspace-context-compression-v1",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["cache_status"] == "recomputed"
    assert payload["coverage_node_ids"] == ["old-user"]
    assert len(payload["coverage_path_hash"]) == 64
    assert payload["compressor_provider"] == "deepseek"
    assert payload["compressor_model"] == "chat"
    prompt = captured_messages[-1].content
    assert "请修复上下文压缩" in prompt
    assert "这条必须 raw 注入" not in prompt


def test_agent_workspace_chat_prompt_orders_compressed_pinned_recent(
    db_session: Session,
    monkeypatch,
) -> None:
    captured_messages = []

    def fake_complete(self, request_payload):
        captured_messages.extend(request_payload.messages)
        return ModelResponse(
            content="ok",
            model_provider=request_payload.model_provider,
            model_name=request_payload.model_name,
            usage={"prompt_tokens": 12, "completion_tokens": 1},
            raw_response={"mode": "prompt-order-test"},
        )

    monkeypatch.setattr("app.api.agents.AuditedModelGateway.complete", fake_complete)

    client = TestClient(app)
    response = client.post(
        "/api/agents/default/runs/chat/stream",
        headers=AUTH_HEADERS,
        json={
            "goal": "current goal",
            "messages": [
                {
                    "id": "covered",
                    "parent_id": None,
                    "children_ids": ["pinned"],
                    "role": "user",
                    "content": "covered raw should not repeat",
                    "state": "done",
                    "metadata": {},
                    "tool_calls": [],
                    "artifacts": [],
                    "created_at": "2026-05-14T00:00:00Z",
                },
                {
                    "id": "pinned",
                    "parent_id": "covered",
                    "children_ids": ["recent"],
                    "role": "assistant",
                    "content": "pinned raw wins",
                    "state": "done",
                    "metadata": {},
                    "tool_calls": [],
                    "artifacts": [],
                    "created_at": "2026-05-14T00:00:01Z",
                },
                {
                    "id": "recent",
                    "parent_id": "pinned",
                    "children_ids": [],
                    "role": "user",
                    "content": "recent uncovered",
                    "state": "done",
                    "metadata": {},
                    "tool_calls": [],
                    "artifacts": [],
                    "created_at": "2026-05-14T00:00:02Z",
                },
            ],
            "pinned_node_ids": ["pinned"],
            "context_window_turns": 8,
            "compressed_context": {
                "summary": "compressed older context",
                "coverage_node_ids": ["covered", "pinned"],
                "coverage_path_hash": "abc",
                "summary_schema_version": "workspace-context-summary-v1",
                "compression_prompt_version": "workspace-context-compression-v1",
                "compressor_provider": "default",
                "compressor_model": "default",
            },
        },
    )

    assert response.status_code == 200
    contents = [message.content for message in captured_messages]
    summary_index = contents.index(next(c for c in contents if "Compressed prior" in c))
    assert summary_index < contents.index("pinned raw wins")
    assert contents.index("pinned raw wins") < contents.index("recent uncovered")
    assert contents[-1] == "current goal"
    assert "covered raw should not repeat" not in contents


def test_agent_workspace_pro_chat_stream_drains_terminal_model_chunk(
    db_session: Session,
    monkeypatch,
) -> None:
    drained = {"value": False}

    def fake_stream(self, request_payload, *, fallback_requests=None):
        assert request_payload.response_format == "text"
        yield ModelStreamChunk(text="terminal drain check")
        yield ModelStreamChunk(
            usage={"prompt_tokens": 3, "completion_tokens": 5},
            raw_response={"mode": "terminal-drain"},
            done=True,
        )
        drained["value"] = True

    monkeypatch.setattr("app.api.agents.AuditedModelGateway.stream", fake_stream)

    response = TestClient(app).post(
        "/api/agents/default/runs/chat/stream",
        headers=AUTH_HEADERS,
        json={
            "goal": "verify terminal drain",
            "messages": [
                {
                    "id": "user-terminal-drain",
                    "parent_id": None,
                    "children_ids": [],
                    "role": "user",
                    "content": "verify terminal drain",
                    "state": "done",
                    "metadata": {},
                    "tool_calls": [],
                    "artifacts": [],
                }
            ],
            "active_leaf_id": "user-terminal-drain",
            "active_branch_id": "branch-terminal-drain",
            "pinned_node_ids": [],
            "context_window_turns": 8,
        },
    )

    assert response.status_code == 200
    events = parse_sse_events(response.text)
    done = next(payload for event, payload in events if event == "done")
    run = db_session.get(Task, done["run_id"])
    assert drained["value"] is True
    assert run is not None
    assert run.status == "COMPLETED"


def test_agent_workspace_pro_chat_stream_rejects_empty_model_chat_response(
    db_session: Session,
    monkeypatch,
) -> None:
    def fake_complete(self, request_payload):
        assert request_payload.response_format == "text"
        return ModelResponse(
            content="{}",
            model_provider=request_payload.model_provider,
            model_name=request_payload.model_name,
            usage={"prompt_tokens": 1, "completion_tokens": 0},
            raw_response={"mode": "mock"},
        )

    monkeypatch.setattr("app.api.agents.AuditedModelGateway.complete", fake_complete)

    response = TestClient(app).post(
        "/api/agents/default/runs/chat/stream",
        headers=AUTH_HEADERS,
        json={
            "goal": "你是谁",
            "messages": [
                {
                    "id": "user-empty-chat",
                    "parent_id": None,
                    "children_ids": [],
                    "role": "user",
                    "content": "你是谁",
                    "state": "done",
                    "metadata": {},
                    "tool_calls": [],
                    "artifacts": [],
                }
            ],
            "active_leaf_id": "user-empty-chat",
            "active_branch_id": "branch-empty",
            "pinned_node_ids": [],
            "context_window_turns": 8,
        },
    )

    assert response.status_code == 200
    events = parse_sse_events(response.text)
    assert [payload for event, payload in events if event == "delta"] == []
    error = next(payload for event, payload in events if event == "error")
    run_created = next(payload for event, payload in events if event == "run_created")
    assert error["recoverable"] is True
    assert "模型网关没有返回可展示的真实聊天内容" in error["message"]
    run = db_session.get(Task, run_created["run_id"])
    assert run is not None
    assert run.status == "FAILED"


def test_agent_workspace_pro_chat_mode_does_not_auto_promote_plan_keywords(
    db_session: Session,
    monkeypatch,
) -> None:
    def fake_complete(self, request_payload):
        assert request_payload.response_format == "text"
        return ModelResponse(
            content="普通聊天仍然返回模型文本",
            model_provider=request_payload.model_provider,
            model_name=request_payload.model_name,
            usage={"prompt_tokens": 10, "completion_tokens": 9},
            raw_response={"mode": "test-model"},
        )

    monkeypatch.setattr("app.api.agents.AuditedModelGateway.complete", fake_complete)

    response = TestClient(app).post(
        "/api/agents/default/runs/chat/stream",
        headers=AUTH_HEADERS,
        json={
            "mode": "chat",
            "goal": "帮我 plan 一下怎么执行这个工具任务",
            "messages": [
                {
                    "id": "user-chat-keywords",
                    "parent_id": None,
                    "children_ids": [],
                    "role": "user",
                    "content": "帮我 plan 一下怎么执行这个工具任务",
                    "state": "done",
                    "metadata": {},
                    "tool_calls": [],
                    "artifacts": [],
                }
            ],
            "active_leaf_id": "user-chat-keywords",
            "active_branch_id": "branch-chat-keywords",
            "pinned_node_ids": [],
            "context_window_turns": 8,
            "tool_mentions": [{"name": "read_file", "source": "builtin", "payload": {}}],
        },
    )

    assert response.status_code == 200
    events = parse_sse_events(response.text)
    event_names = [event for event, _payload in events]
    delta = next(payload for event, payload in events if event == "delta")
    done = next(payload for event, payload in events if event == "done")
    assert delta["content"].startswith("普通聊天仍然返回模型文本")
    assert done["step_count"] == 0
    assert "think_delta" not in event_names
    assert "artifact_created" not in event_names
    assert "tool_call_requested" not in event_names
    assert db_session.execute(select(ExecutionPlan)).scalar_one_or_none() is None


def test_agent_workspace_pro_markdown_plan_streams_markdown_plan_without_plan_act(
    db_session: Session,
) -> None:
    response = TestClient(app).post(
        "/api/agents/default/runs/chat/stream",
        headers=AUTH_HEADERS,
        json={
            "mode": "markdown_plan",
            "goal": "把当前项目的页面改成 chat-first UI 式聊天体验",
            "messages": [
                {
                    "id": "user-markdown-plan",
                    "parent_id": None,
                    "children_ids": [],
                    "role": "user",
                    "content": "把当前项目的页面改成 chat-first UI 式聊天体验",
                    "state": "done",
                    "metadata": {},
                    "tool_calls": [],
                    "artifacts": [],
                }
            ],
            "active_leaf_id": "user-markdown-plan",
            "active_branch_id": "branch-markdown-plan",
            "pinned_node_ids": [],
            "context_window_turns": 8,
            "tool_mentions": [{"name": "run_shell", "source": "builtin", "payload": {}}],
        },
    )

    assert response.status_code == 200
    events = parse_sse_events(response.text)
    event_names = [event for event, _payload in events]
    run_created = next(payload for event, payload in events if event == "run_created")
    delta = next(payload for event, payload in events if event == "delta")
    done = next(payload for event, payload in events if event == "done")
    assert delta["content"].startswith("测试模型回复：")
    assert done["step_count"] == 0
    assert done["status"] == "COMPLETED"
    assert "think_delta" not in event_names
    assert "artifact_created" not in event_names
    assert "tool_call_requested" not in event_names
    assert "tool_call_result" not in event_names
    run = db_session.get(Task, run_created["run_id"])
    assert run is not None
    assert run.status == "COMPLETED"
    assert db_session.execute(select(ExecutionPlan)).scalar_one_or_none() is None
    assert db_session.execute(select(ToolCall)).scalar_one_or_none() is None


def test_agent_workspace_pro_chat_stream_plan_mode_forces_plan_act(
    db_session: Session,
) -> None:
    response = TestClient(app).post(
        "/api/agents/default/runs/chat/stream",
        headers=AUTH_HEADERS,
        json={
            "mode": "plan",
            "goal": "你是谁",
            "messages": [
                {
                    "id": "user-plan-mode",
                    "parent_id": None,
                    "children_ids": [],
                    "role": "user",
                    "content": "你是谁",
                    "state": "done",
                    "metadata": {},
                    "tool_calls": [],
                    "artifacts": [],
                }
            ],
            "active_leaf_id": "user-plan-mode",
            "active_branch_id": "branch-plan-mode",
            "pinned_node_ids": [],
            "context_window_turns": 8,
        },
    )

    assert response.status_code == 200
    events = parse_sse_events(response.text)
    event_names = [event for event, _payload in events]
    assert "think_delta" in event_names
    assert "run_created" in event_names
    assert "artifact_created" in event_names
    assert "delta" in event_names
    assert db_session.execute(select(ExecutionPlan)).scalar_one_or_none() is not None


def test_agent_workspace_pro_chat_mode_does_not_resume_plan_run(
    db_session: Session,
    monkeypatch,
) -> None:
    client = TestClient(app)
    planned_response = client.post(
        "/api/agents/default/runs/chat/stream",
        headers=AUTH_HEADERS,
        json={
            "mode": "plan",
            "goal": "Create a plan run",
            "messages": [],
            "active_leaf_id": "root",
            "active_branch_id": "branch-plan-run",
            "pinned_node_ids": [],
            "context_window_turns": 8,
        },
    )
    plan_run_id = next(
        payload
        for event, payload in parse_sse_events(planned_response.text)
        if event == "run_created"
    )["run_id"]

    def fake_complete(self, request_payload):
        assert request_payload.response_format == "text"
        return ModelResponse(
            content="chat mode created a normal model reply",
            model_provider=request_payload.model_provider,
            model_name=request_payload.model_name,
            usage={"prompt_tokens": 9, "completion_tokens": 8},
            raw_response={"mode": "test-model"},
        )

    monkeypatch.setattr("app.api.agents.AuditedModelGateway.complete", fake_complete)

    chat_response = client.post(
        "/api/agents/default/runs/chat/stream",
        headers=AUTH_HEADERS,
        json={
            "mode": "chat",
            "goal": "continue with a tool plan",
            "run_id": plan_run_id,
            "messages": [],
            "active_leaf_id": "assistant-plan",
            "active_branch_id": "branch-chat-run",
            "pinned_node_ids": [],
            "context_window_turns": 8,
            "tool_mentions": [{"name": "read_file", "source": "builtin", "payload": {}}],
        },
    )

    assert chat_response.status_code == 200
    events = parse_sse_events(chat_response.text)
    event_names = [event for event, _payload in events]
    run_created = next(payload for event, payload in events if event == "run_created")
    delta = next(payload for event, payload in events if event == "delta")
    done = next(payload for event, payload in events if event == "done")
    assert run_created["run_id"] != plan_run_id
    assert delta["content"].startswith("chat mode created a normal model reply")
    assert done["step_count"] == 0
    assert "think_delta" not in event_names
    assert "artifact_created" not in event_names
    assert "tool_call_requested" not in event_names
    assert db_session.get(Task, plan_run_id).status == "PLANNED"


def test_agent_workspace_pro_chat_stream_creates_auditable_run(db_session: Session) -> None:
    client = TestClient(app)
    response = client.post(
        "/api/agents/default/runs/chat/stream",
        headers=AUTH_HEADERS,
        json={
            "goal": "Build a Workspace Pro regression plan",
            "mode": "plan",
            "messages": [
                {
                    "id": "user-1",
                    "parent_id": None,
                    "children_ids": [],
                    "role": "user",
                    "content": "Build a Workspace Pro regression plan",
                    "state": "done",
                    "metadata": {},
                    "tool_calls": [],
                    "artifacts": [],
                }
            ],
            "active_leaf_id": "user-1",
            "active_branch_id": "branch-1",
            "pinned_node_ids": ["user-1"],
            "context_window_turns": 8,
            "tool_mentions": [{"name": "read_file", "source": "builtin", "payload": {}}],
        },
    )

    assert response.status_code == 200
    body = response.text
    assert "event: think_delta" in body
    assert "event: run_created" in body
    assert "event: tool_call_requested" in body
    assert "event: tool_call_result" in body
    assert "event: artifact_created" in body
    assert "event: usage" in body
    assert "event: done" in body
    events = parse_sse_events(body)
    requested = next(payload for event, payload in events if event == "tool_call_requested")
    result = next(payload for event, payload in events if event == "tool_call_result")
    usage = next(payload for event, payload in events if event == "usage")
    done = next(payload for event, payload in events if event == "done")
    assert requested["tool_call_id"] == result["tool_call_id"]
    assert requested["status"] == "running"
    assert result["status"] == "success"
    assert result["output_summary"]
    assert isinstance(result["duration_ms"], int)
    assert done["active_branch_id"] == "branch-1"
    assert done["continue_from_node_id"] is None
    assert usage["cost_usd"] is None
    assert usage["cost_unavailable"] is True
    assert db_session.execute(select(Task)).scalar_one_or_none() is not None


def test_agent_workspace_pro_chat_stream_continue_preserves_run_identity(
    db_session: Session,
    monkeypatch,
) -> None:
    def fake_complete(self, request_payload):
        return ModelResponse(
            content="continued model response",
            model_provider=request_payload.model_provider,
            model_name=request_payload.model_name,
            usage={"prompt_tokens": 8, "completion_tokens": 6},
            raw_response={"mode": "test-model"},
        )

    monkeypatch.setattr("app.api.agents.AuditedModelGateway.complete", fake_complete)

    client = TestClient(app)
    created = client.post(
        "/api/agents/default/runs/chat/stream",
        headers=AUTH_HEADERS,
        json={
            "goal": "Create a run for continue",
            "messages": [
                {
                    "id": "user-continue",
                    "parent_id": None,
                    "children_ids": [],
                    "role": "user",
                    "content": "Create a run for continue",
                    "state": "done",
                    "metadata": {},
                    "tool_calls": [],
                    "artifacts": [],
                }
            ],
            "active_leaf_id": "user-continue",
            "active_branch_id": "branch-a",
            "pinned_node_ids": [],
            "context_window_turns": 8,
        },
    )
    assert created.status_code == 200
    run_id = next(
        payload for event, payload in parse_sse_events(created.text) if event == "done"
    )["run_id"]

    continued = client.post(
        "/api/agents/default/runs/chat/stream",
        headers=AUTH_HEADERS,
        json={
            "goal": "Continue the same run",
            "run_id": run_id,
            "active_branch_id": "branch-a",
            "continue_from_node_id": "assistant-paused",
            "partial_assistant_content": "partial",
            "messages": [
                {
                    "id": "assistant-paused",
                    "parent_id": "user-continue",
                    "children_ids": [],
                    "role": "assistant",
                    "content": "partial",
                    "state": "paused",
                    "run_id": run_id,
                    "metadata": {},
                    "tool_calls": [],
                    "artifacts": [],
                }
            ],
            "active_leaf_id": "assistant-paused",
            "pinned_node_ids": [],
            "context_window_turns": 8,
        },
    )

    assert continued.status_code == 200
    done = next(payload for event, payload in parse_sse_events(continued.text) if event == "done")
    assert done["run_id"] == run_id
    assert done["active_branch_id"] == "branch-a"
    assert done["continue_from_node_id"] == "assistant-paused"


def test_agent_workspace_chat_run_can_be_promoted_to_full_harness_execution(
    db_session: Session,
    monkeypatch,
) -> None:
    def fake_complete(self, request_payload):
        return ModelResponse(
            content="chat response before promotion",
            model_provider=request_payload.model_provider,
            model_name=request_payload.model_name,
            usage={"prompt_tokens": 8, "completion_tokens": 6},
            raw_response={"mode": "test-model"},
        )

    monkeypatch.setattr("app.api.agents.AuditedModelGateway.complete", fake_complete)

    client = TestClient(app)
    created = client.post(
        "/api/agents/default/runs/chat/stream",
        headers=AUTH_HEADERS,
        json={
            "mode": "chat",
            "goal": "Create a chat run that later needs full Harness execution",
            "messages": [],
            "active_leaf_id": "root",
            "active_branch_id": "branch-promote",
            "pinned_node_ids": [],
            "context_window_turns": 8,
        },
    )

    assert created.status_code == 200
    run_id = next(
        payload for event, payload in parse_sse_events(created.text) if event == "done"
    )["run_id"]
    assert db_session.get(Task, run_id).status == "COMPLETED"
    assert (
        db_session.execute(select(ExecutionPlan).where(ExecutionPlan.task_id == run_id)).first()
        is None
    )

    promoted = client.post(f"/api/tasks/{run_id}/start", headers=AUTH_HEADERS)

    assert promoted.status_code == 202
    assert promoted.json()["id"] == run_id
    assert promoted.json()["status"] in {"COMPLETED", "WAITING_SUBAGENTS", "WAITING_APPROVAL"}
    assert (
        db_session.execute(select(ExecutionPlan).where(ExecutionPlan.task_id == run_id)).first()
        is not None
    )


def test_agent_workspace_pro_chat_stream_invalid_continue_is_recoverable(
    db_session: Session,
) -> None:
    response = TestClient(app).post(
        "/api/agents/default/runs/chat/stream",
        headers=AUTH_HEADERS,
        json={
            "goal": "Continue missing run",
            "run_id": "missing-run",
            "active_branch_id": "branch-missing",
            "continue_from_node_id": "assistant-paused",
            "messages": [],
            "active_leaf_id": "assistant-paused",
            "pinned_node_ids": [],
            "context_window_turns": 8,
        },
    )

    assert response.status_code == 200
    error = next(payload for event, payload in parse_sse_events(response.text) if event == "error")
    assert error["recoverable"] is True
    assert error["run_id"] == "missing-run"


def test_agent_workspace_pro_chat_stream_side_effect_tool_stays_pending(
    db_session: Session,
) -> None:
    client = TestClient(app)
    response = client.post(
        "/api/agents/default/runs/chat/stream",
        headers=AUTH_HEADERS,
        json={
            "goal": "Do not auto execute shell",
            "mode": "plan",
            "messages": [],
            "active_leaf_id": "root",
            "pinned_node_ids": [],
            "context_window_turns": 8,
            "tool_mentions": [
                {"name": "run_shell", "source": "builtin", "payload": {"command": "echo unsafe"}}
            ],
        },
    )

    assert response.status_code == 200
    events = parse_sse_events(response.text)
    run_created = next(payload for event, payload in events if event == "run_created")
    requested = next(payload for event, payload in events if event == "tool_call_requested")
    assert requested["status"] == "pending_approval"
    assert requested["approval_id"]
    assert not [payload for event, payload in events if event == "tool_call_result"]
    run_id = run_created["run_id"]
    tool_call = db_session.execute(select(ToolCall).where(ToolCall.task_id == run_id)).scalar_one()
    approval = db_session.execute(
        select(ToolApproval).where(ToolApproval.task_id == run_id)
    ).scalar_one()
    run = db_session.get(Task, run_id)
    assert requested["tool_call_id"] == tool_call.id
    assert requested["approval_id"] == approval.id
    assert approval.tool_call_id == tool_call.id
    assert tool_call.status == "PENDING_APPROVAL"
    assert run is not None
    assert run.status == "WAITING_APPROVAL"

    workspace = client.get(f"/api/agents/runs/{run_id}/workspace", headers=AUTH_HEADERS)
    assert workspace.status_code == 200
    assert workspace.json()["approvals"][0]["id"] == approval.id


@pytest.fixture(autouse=True)
def fake_sandbox_runtime(monkeypatch) -> None:
    monkeypatch.setattr("app.agents.executor.WarmPoolManager", FakeWarmPoolManager)
    monkeypatch.setattr("app.sandbox.docker_manager.DockerManager.run_command", fake_run_command)


@pytest.fixture(autouse=True)
def fake_workspace_plan_model(monkeypatch) -> None:
    def fake_audited_stream(self, request_payload, *, fallback_requests=None):
        response = self.complete(request_payload)
        if response.content.strip() != "{}":
            yield ModelStreamChunk(text=response.content)
        yield ModelStreamChunk(
            usage=response.usage,
            raw_response=response.raw_response,
            done=True,
        )

    class FakeGateway:
        def complete(self, request_payload):
            if request_payload.response_format == "text":
                goal = next(
                    (
                        message.content.strip()
                        for message in reversed(request_payload.messages)
                        if message.role == "user" and message.content.strip()
                    ),
                    "Workspace chat",
                )
                return ModelResponse(
                    content=f"测试模型回复：{goal}",
                    model_provider=request_payload.model_provider,
                    model_name=request_payload.model_name,
                    usage={"prompt_tokens": 12, "completion_tokens": 8},
                    raw_response={"mode": "test-chat"},
                )

            goal = next(
                (
                    message.content.strip()
                    for message in reversed(request_payload.messages)
                    if message.role == "user" and message.content.strip()
                ),
                "Workspace plan",
            )
            task = Task(
                organization_id="dev-org",
                created_by="dev-engineer",
                title=goal[:48] or "Workspace Plan",
                goal=goal,
                status="RUNNING",
                model_provider=request_payload.model_provider,
                model_name=request_payload.model_name,
                max_runtime_seconds=1800,
                max_subagents=5,
                enable_sandbox=True,
                enable_network=False,
            )
            plan = DeterministicPlanner().create_plan(task)
            return ModelResponse(
                content=json.dumps(plan.model_dump(), ensure_ascii=False),
                model_provider=request_payload.model_provider,
                model_name=request_payload.model_name,
                usage={"prompt_tokens": 12, "completion_tokens": 8},
                raw_response={"mode": "test-plan"},
            )

    monkeypatch.setattr(
        "app.agents.model_gateway.model_gateway_for_provider",
        lambda provider, *, timeout_seconds=30: FakeGateway(),
    )
    monkeypatch.setattr("app.api.agents.AuditedModelGateway.stream", fake_audited_stream)


def test_list_agents_initializes_named_agent_registry(db_session: Session) -> None:
    response = TestClient(app).get("/api/agents", headers=AUTH_HEADERS)

    assert response.status_code == 200
    payload = response.json()
    agent_ids = [agent["id"] for agent in payload["items"]]
    assert agent_ids == ["coder", "default", "operator", "researcher", "reviewer"]
    researcher = next(agent for agent in payload["items"] if agent["id"] == "researcher")
    assert researcher["role"] == "researcher"
    assert "network_request" in researcher["tools_json"]
    assert "research" in researcher["routing_tags"]


def test_get_agent_returns_named_agent_detail(db_session: Session) -> None:
    response = TestClient(app).get("/api/agents/coder", headers=AUTH_HEADERS)

    assert response.status_code == 200
    payload = response.json()
    assert payload["id"] == "coder"
    assert payload["name"] == "Coder Agent"
    assert payload["model_provider"] == "default"
    assert "run_tests" in payload["tools_json"]


def test_agent_chat_session_persists_messages(db_session: Session) -> None:
    client = TestClient(app)
    created = client.post(
        "/api/agents/default/sessions",
        headers=AUTH_HEADERS,
        json={"title": "Chat smoke"},
    )
    assert created.status_code == 201
    session_id = created.json()["id"]

    response = client.post(
        f"/api/agents/sessions/{session_id}/messages",
        headers=AUTH_HEADERS,
        json={"content": "你好，先聊一下平台能力"},
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["session"]["id"] == session_id
    assert [message["role"] for message in payload["messages"]] == ["user", "assistant"]
    assert "default 已收到" in payload["messages"][1]["content"]

    listed = client.get(f"/api/agents/sessions/{session_id}/messages", headers=AUTH_HEADERS)
    assert listed.status_code == 200
    assert [message["role"] for message in listed.json()["items"]] == ["user", "assistant"]


def test_agent_plan_mode_creates_plan_without_execution(db_session: Session) -> None:
    response = TestClient(app).post(
        "/api/agents/plan",
        headers=AUTH_HEADERS,
        json={
            "agent_id": "default",
            "goal": "分析项目结构并规划后续实现，不执行工具",
            "model_provider": "openai-compatible",
            "model_name": "default",
            "max_subagents": 5,
            "enable_sandbox": True,
            "enable_network": False,
        },
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["agent_id"] == "default"
    assert payload["task"]["status"] == "PLANNED"
    assert payload["plan"]["steps"]
    assert "未执行任何工具" in payload["message"]

    task = db_session.get(Task, payload["run_id"])
    assert task is not None
    assert task.status == "PLANNED"
    plan = db_session.execute(
        select(ExecutionPlan).where(ExecutionPlan.task_id == task.id)
    ).scalar_one()
    assert plan.status == "GENERATED"
    assert db_session.execute(select(TaskStep).where(TaskStep.task_id == task.id)).all() == []
    event_types = [
        event.event_type
        for event in db_session.execute(
            select(AgentEvent).where(AgentEvent.task_id == task.id).order_by(AgentEvent.sequence)
        ).scalars()
    ]
    assert event_types == [
        "TASK_CREATED",
        "PLAN_REQUESTED",
        "MODEL_CALLED",
        "MODEL_RESPONSE_RECEIVED",
        "PLAN_GENERATED",
    ]


def test_agent_plan_mode_surfaces_model_gateway_failure_without_fallback(
    db_session: Session,
    monkeypatch,
) -> None:
    class BrokenGateway:
        def complete(self, request_payload):
            raise ModelGatewayError("model unavailable")

    monkeypatch.setattr(
        "app.agents.model_gateway.model_gateway_for_provider",
        lambda provider, *, timeout_seconds=30: BrokenGateway(),
    )

    response = TestClient(app).post(
        "/api/agents/plan",
        headers=AUTH_HEADERS,
        json={
            "agent_id": "default",
            "goal": "计划失败时应该显式报错",
            "model_provider": "openai-compatible",
            "model_name": "default",
            "max_subagents": 5,
            "enable_sandbox": True,
            "enable_network": False,
        },
    )

    assert response.status_code == 502
    assert "Plan 模型调用失败" in response.json()["detail"]
    task = db_session.execute(
        select(Task).where(Task.goal == "计划失败时应该显式报错")
    ).scalar_one()
    assert task.status == "FAILED"
    assert (
        db_session.execute(select(ExecutionPlan).where(ExecutionPlan.task_id == task.id))
        .scalar_one_or_none()
        is None
    )
    event_types = [
        event.event_type
        for event in db_session.execute(
            select(AgentEvent).where(AgentEvent.task_id == task.id).order_by(AgentEvent.sequence)
        ).scalars()
    ]
    assert event_types == [
        "TASK_CREATED",
        "PLAN_REQUESTED",
        "MODEL_CALLED",
        "MODEL_CALL_FAILED",
        "TASK_FAILED",
    ]


def test_agent_run_create_surfaces_model_gateway_failure_without_fallback(
    db_session: Session,
    monkeypatch,
) -> None:
    class BrokenGateway:
        def complete(self, request_payload):
            raise ModelGatewayError("model unavailable")

    monkeypatch.setattr(
        "app.agents.model_gateway.model_gateway_for_provider",
        lambda provider, *, timeout_seconds=30: BrokenGateway(),
    )

    response = TestClient(app).post(
        "/api/agents/default/runs",
        headers=AUTH_HEADERS,
        json={
            "goal": "Primary run planning should fail when the model gateway is down",
            "model_provider": "openai-compatible",
            "model_name": "default",
            "max_subagents": 5,
            "enable_sandbox": True,
            "enable_network": False,
        },
    )

    assert response.status_code == 502
    assert "Plan 模型调用失败" in response.json()["detail"]
    task = db_session.execute(
        select(Task).where(
            Task.goal == "Primary run planning should fail when the model gateway is down"
        )
    ).scalar_one()
    assert task.status == "FAILED"
    assert (
        db_session.execute(select(ExecutionPlan).where(ExecutionPlan.task_id == task.id))
        .scalar_one_or_none()
        is None
    )
    event_types = [
        event.event_type
        for event in db_session.execute(
            select(AgentEvent).where(AgentEvent.task_id == task.id).order_by(AgentEvent.sequence)
        ).scalars()
    ]
    assert event_types == [
        "TASK_CREATED",
        "PLAN_REQUESTED",
        "MODEL_CALLED",
        "MODEL_CALL_FAILED",
        "TASK_FAILED",
    ]


def test_agent_run_create_uses_deterministic_plan_when_model_output_is_unparseable(
    db_session: Session,
    monkeypatch,
) -> None:
    class InvalidGateway:
        def complete(self, request_payload):
            return ModelResponse(
                content="not json at all",
                model_provider=request_payload.model_provider,
                model_name=request_payload.model_name,
                usage={"prompt_tokens": 9, "completion_tokens": 4},
                raw_response={"mode": "test-model"},
            )

    monkeypatch.setattr(
        "app.agents.model_gateway.model_gateway_for_provider",
        lambda provider, *, timeout_seconds=30: InvalidGateway(),
    )

    response = TestClient(app).post(
        "/api/agents/default/runs",
        headers=AUTH_HEADERS,
        json={
            "goal": "计划输出不可解析时应该生成可审计计划",
            "model_provider": "openai-compatible",
            "model_name": "default",
            "max_subagents": 5,
            "enable_sandbox": True,
            "enable_network": False,
        },
    )

    assert response.status_code == 201
    run_id = response.json()["run_id"]
    task = db_session.execute(
        select(Task).where(Task.goal == "计划输出不可解析时应该生成可审计计划")
    ).scalar_one()
    assert task.status == "PLANNED"
    plan = (
        db_session.execute(select(ExecutionPlan).where(ExecutionPlan.task_id == task.id))
        .scalars()
        .one()
    )
    assert task.id == run_id
    assert plan.plan_json["planner_source"] == "deterministic"
    assert plan.plan_json["steps"]
    event_types = [
        event.event_type
        for event in db_session.execute(
            select(AgentEvent).where(AgentEvent.task_id == task.id).order_by(AgentEvent.sequence)
        ).scalars()
    ]
    assert event_types == [
        "TASK_CREATED",
        "PLAN_REQUESTED",
        "MODEL_CALLED",
        "MODEL_RESPONSE_RECEIVED",
        "PLAN_REJECTED",
        "MODEL_CALLED",
        "MODEL_RESPONSE_RECEIVED",
        "PLAN_REJECTED",
        "PLAN_GENERATED",
    ]


def test_agent_run_create_records_repair_failure_before_deterministic_plan(
    db_session: Session,
    monkeypatch,
) -> None:
    class RepairFailureGateway:
        calls = 0

        def complete(self, request_payload):
            self.calls += 1
            if self.calls == 1:
                return ModelResponse(
                    content="not json at all",
                    model_provider=request_payload.model_provider,
                    model_name=request_payload.model_name,
                    usage={"prompt_tokens": 9, "completion_tokens": 4},
                    raw_response={"mode": "test-model"},
                )
            raise ModelGatewayError("repair unavailable")

    gateway = RepairFailureGateway()
    monkeypatch.setattr(
        "app.agents.model_gateway.model_gateway_for_provider",
        lambda provider, *, timeout_seconds=30: gateway,
    )

    response = TestClient(app).post(
        "/api/agents/default/runs",
        headers=AUTH_HEADERS,
        json={
            "goal": "Repair failure should still leave auditable planning events",
            "model_provider": "openai-compatible",
            "model_name": "default",
            "max_subagents": 5,
            "enable_sandbox": True,
            "enable_network": False,
        },
    )

    assert response.status_code == 201
    task = db_session.execute(
        select(Task).where(
            Task.goal == "Repair failure should still leave auditable planning events"
        )
    ).scalar_one()
    plan = (
        db_session.execute(select(ExecutionPlan).where(ExecutionPlan.task_id == task.id))
        .scalars()
        .one()
    )
    assert task.status == "PLANNED"
    assert plan.plan_json["planner_source"] == "deterministic"
    events = list(
        db_session.execute(
            select(AgentEvent).where(AgentEvent.task_id == task.id).order_by(AgentEvent.sequence)
        ).scalars()
    )
    assert [event.event_type for event in events] == [
        "TASK_CREATED",
        "PLAN_REQUESTED",
        "MODEL_CALLED",
        "MODEL_RESPONSE_RECEIVED",
        "PLAN_REJECTED",
        "MODEL_CALLED",
        "MODEL_CALL_FAILED",
        "PLAN_REJECTED",
        "PLAN_GENERATED",
    ]
    plan_rejection_reasons = [
        event.payload_json["reason"]
        for event in events
        if event.event_type == "PLAN_REJECTED"
    ]
    assert plan_rejection_reasons == [
        "model_plan_schema_invalid",
        "model_plan_repair_call_failed",
    ]


def test_agent_run_create_entry_and_workspace_projection(db_session: Session) -> None:
    client = TestClient(app)

    created = client.post(
        "/api/agents/default/runs",
        headers=AUTH_HEADERS,
        json={
            "mode": "plan",
            "goal": "通过 Agent Workspace 创建 Run 并查看聚合视图",
            "model_provider": "openai-compatible",
            "model_name": "default",
            "max_subagents": 5,
            "enable_sandbox": True,
            "enable_network": False,
        },
    )

    assert created.status_code == 201
    run_id = created.json()["run_id"]

    listed = client.get("/api/agents/runs", headers=AUTH_HEADERS)
    assert listed.status_code == 200
    assert any(item["id"] == run_id for item in listed.json()["items"])

    workspace = client.get(f"/api/agents/runs/{run_id}/workspace", headers=AUTH_HEADERS)

    assert workspace.status_code == 200
    payload = workspace.json()
    assert payload["run"]["id"] == run_id
    assert payload["plan"]["steps"]
    assert [event["event_type"] for event in payload["events"]] == [
        "TASK_CREATED",
        "PLAN_REQUESTED",
        "MODEL_CALLED",
        "MODEL_RESPONSE_RECEIVED",
        "PLAN_GENERATED",
    ]
    assert payload["tool_calls"] == []
    assert payload["model_calls"][0]["model_provider"] == "openai-compatible"


def test_agent_execute_run_uses_existing_plan_without_replanning(db_session: Session) -> None:
    client = TestClient(app)
    plan_response = client.post(
        "/api/agents/plan",
        headers=AUTH_HEADERS,
        json={
            "agent_id": "default",
            "goal": "分析项目结构并执行现有计划",
            "model_provider": "openai-compatible",
            "model_name": "default",
            "max_subagents": 5,
            "enable_sandbox": True,
            "enable_network": False,
        },
    )
    assert plan_response.status_code == 201
    run_id = plan_response.json()["run_id"]

    execute_response = client.post(f"/api/agents/runs/{run_id}/execute", headers=AUTH_HEADERS)

    assert execute_response.status_code == 202
    assert execute_response.json()["status"] == "COMPLETED"
    plans = list(
        db_session.execute(select(ExecutionPlan).where(ExecutionPlan.task_id == run_id)).scalars()
    )
    assert len(plans) == 1
    assert db_session.execute(select(TaskStep).where(TaskStep.task_id == run_id)).scalars().all()
    event_types = [
        event.event_type
        for event in db_session.execute(
            select(AgentEvent).where(AgentEvent.task_id == run_id).order_by(AgentEvent.sequence)
        ).scalars()
    ]
    assert event_types.count("PLAN_GENERATED") == 1
    assert "TASK_STARTED" in event_types
    assert "STEP_STARTED" in event_types
    assert "STEP_COMPLETED" in event_types
    assert event_types[-1] == "TASK_COMPLETED"


def test_agent_execute_run_rejects_non_planned_status(db_session: Session) -> None:
    task = Task(
        organization_id="dev-org",
        created_by="dev-engineer",
        title="Created run",
        goal="尚未规划",
        status="CREATED",
        model_provider="openai-compatible",
        model_name="default",
        max_runtime_seconds=1800,
        max_subagents=5,
        enable_sandbox=True,
        enable_network=False,
    )
    db_session.add(task)
    db_session.commit()

    response = TestClient(app).post(f"/api/agents/runs/{task.id}/execute", headers=AUTH_HEADERS)

    assert response.status_code == 409


def test_agent_execute_run_waits_for_admin_approval(db_session: Session) -> None:
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
    db_session.commit()
    client = TestClient(app)
    plan_response = client.post(
        "/api/agents/plan",
        headers=AUTH_HEADERS,
        json={
            "agent_id": "default",
            "goal": "规划后执行只读检查，并在策略要求时等待审批",
            "model_provider": "openai-compatible",
            "model_name": "default",
            "max_subagents": 0,
            "enable_sandbox": False,
            "enable_network": False,
        },
    )
    assert plan_response.status_code == 201
    run_id = plan_response.json()["run_id"]

    execute_response = client.post(f"/api/agents/runs/{run_id}/execute", headers=AUTH_HEADERS)

    assert execute_response.status_code == 202
    assert execute_response.json()["status"] == "WAITING_APPROVAL"
    run = db_session.get(Task, run_id)
    assert run is not None
    assert run.status == "WAITING_APPROVAL"
    tool_call = db_session.execute(select(ToolCall).where(ToolCall.task_id == run_id)).scalar_one()
    assert tool_call.status == "PENDING_APPROVAL"
    approval = db_session.execute(
        select(ToolApproval).where(ToolApproval.task_id == run_id)
    ).scalar_one()
    assert approval.status == "PENDING"
    failed_event = db_session.execute(
        select(AgentEvent)
        .where(AgentEvent.task_id == run_id, AgentEvent.event_type == "TASK_FAILED")
        .order_by(AgentEvent.sequence.desc())
    ).scalars().first()
    assert failed_event is not None
    assert failed_event.payload_json["awaiting_approval"] is True


def test_agent_orchestrate_run_creates_named_assignments_and_events(
    db_session: Session,
) -> None:
    client = TestClient(app)
    plan_response = client.post(
        "/api/agents/plan",
        headers=AUTH_HEADERS,
        json={
            "agent_id": "default",
            "goal": "分析项目结构，安排研究与审查 Agent 协作",
            "model_provider": "openai-compatible",
            "model_name": "default",
            "max_subagents": 5,
            "enable_sandbox": True,
            "enable_network": False,
        },
    )
    assert plan_response.status_code == 201
    run_id = plan_response.json()["run_id"]

    response = client.post(f"/api/agents/runs/{run_id}/orchestrate", headers=AUTH_HEADERS)

    assert response.status_code == 201
    payload = response.json()
    assert payload["strategy"] == "deterministic_fallback"
    assert payload["routing_reasoning"]
    assignment_agent_ids = [item["agent_id"] for item in payload["assignments"]]
    assert "default" in assignment_agent_ids
    assert "researcher" in assignment_agent_ids
    assert "reviewer" in assignment_agent_ids
    assert payload["handoffs"]

    assignments = list(
        db_session.execute(
            select(AgentAssignment).where(AgentAssignment.run_id == run_id)
        ).scalars()
    )
    assert len(assignments) == len(payload["assignments"])
    event_types = [
        event.event_type
        for event in db_session.execute(
            select(AgentEvent).where(AgentEvent.task_id == run_id).order_by(AgentEvent.sequence)
        ).scalars()
    ]
    assert "AGENT_SELECTED" in event_types
    assert "AGENT_PARALLEL_FANOUT_STARTED" in event_types
    assert "AGENT_ASSIGNMENT_CREATED" in event_types
    assert "AGENT_HANDOFF_COMPLETED" in event_types
    assert "AGENT_REDUCE_STARTED" in event_types
    selected_event = db_session.execute(
        select(AgentEvent)
        .where(AgentEvent.task_id == run_id, AgentEvent.event_type == "AGENT_SELECTED")
        .order_by(AgentEvent.sequence.desc())
    ).scalars().first()
    assert selected_event is not None
    assert selected_event.payload_json["router_prompt_version"] == "agent-router-v1"

    listed = client.get(f"/api/agents/runs/{run_id}/assignments", headers=AUTH_HEADERS)
    assert listed.status_code == 200
    assert len(listed.json()) == len(payload["assignments"])


def test_agent_orchestrate_uses_llm_router_when_model_returns_valid_decision(
    db_session: Session,
    monkeypatch,
) -> None:
    client = TestClient(app)
    plan_response = client.post(
        "/api/agents/plan",
        headers=AUTH_HEADERS,
        json={
            "agent_id": "default",
            "goal": "需要编码和审查协作",
            "model_provider": "openai-compatible",
            "model_name": "default",
            "max_subagents": 5,
            "enable_sandbox": True,
            "enable_network": False,
        },
    )
    run_id = plan_response.json()["run_id"]

    def fake_complete(self, request_payload, *, fallback_requests=None):
        if "Agent Router" in request_payload.messages[0].content:
            return ModelResponse(
                content=(
                    '{"selected_agent_ids":["default","coder"],'
                    '"strategy":"llm_router","reasoning":"coding work requires coder"}'
                ),
                model_provider=request_payload.model_provider,
                model_name=request_payload.model_name,
            )
        return ModelResponse(
            content="{}",
            model_provider=request_payload.model_provider,
            model_name=request_payload.model_name,
        )

    monkeypatch.setattr("app.agents.orchestrator.AuditedModelGateway.complete", fake_complete)

    response = client.post(f"/api/agents/runs/{run_id}/orchestrate", headers=AUTH_HEADERS)

    assert response.status_code == 201
    payload = response.json()
    assert payload["strategy"] == "llm_router"
    assert payload["routing_reasoning"] == "coding work requires coder"
    assignment_agent_ids = [item["agent_id"] for item in payload["assignments"]]
    assert assignment_agent_ids == ["default", "coder", "reviewer"]


def test_agent_orchestration_execute_runs_assignments_and_reduces(
    db_session: Session,
) -> None:
    client = TestClient(app)
    plan_response = client.post(
        "/api/agents/plan",
        headers=AUTH_HEADERS,
        json={
            "agent_id": "default",
            "goal": "分析项目结构，安排研究与审查 Agent 协作",
            "model_provider": "openai-compatible",
            "model_name": "default",
            "max_subagents": 5,
            "enable_sandbox": True,
            "enable_network": False,
        },
    )
    run_id = plan_response.json()["run_id"]
    client.post(f"/api/agents/runs/{run_id}/orchestrate", headers=AUTH_HEADERS)

    response = client.post(
        f"/api/agents/runs/{run_id}/orchestrate/execute",
        headers=AUTH_HEADERS,
    )

    assert response.status_code == 202
    payload = response.json()
    assert all(item["status"] == "SUCCESS" for item in payload["assignments"])
    reviewer = next(item for item in payload["assignments"] if item["agent_id"] == "reviewer")
    assert "reduced_summary" in reviewer["output_json"]
    assert "tool_call_id" in reviewer["output_json"]

    event_types = [
        event.event_type
        for event in db_session.execute(
            select(AgentEvent).where(AgentEvent.task_id == run_id).order_by(AgentEvent.sequence)
        ).scalars()
    ]
    assert "AGENT_ASSIGNMENT_STARTED" in event_types
    assert "AGENT_ASSIGNMENT_COMPLETED" in event_types
    assert "AGENT_PARALLEL_BRANCH_COMPLETED" in event_types
    assert "AGENT_REDUCE_COMPLETED" in event_types
    assert "TOOL_CALLED" in event_types
    assert "TOOL_RESULT_RECEIVED" in event_types


def test_agent_orchestration_enqueue_marks_assignments_for_worker(
    db_session: Session,
    monkeypatch,
) -> None:
    sent_assignment_ids: list[str] = []

    class FakeActor:
        @staticmethod
        def send(assignment_id: str) -> None:
            sent_assignment_ids.append(assignment_id)

    monkeypatch.setattr("app.workers.agent_assignment_worker.run_agent_assignment", FakeActor)
    client = TestClient(app)
    plan_response = client.post(
        "/api/agents/plan",
        headers=AUTH_HEADERS,
        json={
            "agent_id": "default",
            "goal": "分析项目结构，安排研究与审查 Agent 协作",
            "model_provider": "openai-compatible",
            "model_name": "default",
            "max_subagents": 5,
            "enable_sandbox": True,
            "enable_network": False,
        },
    )
    run_id = plan_response.json()["run_id"]
    client.post(f"/api/agents/runs/{run_id}/orchestrate", headers=AUTH_HEADERS)

    response = client.post(
        f"/api/agents/runs/{run_id}/orchestrate/enqueue",
        headers=AUTH_HEADERS,
    )

    assert response.status_code == 202
    payload = response.json()
    assert all(item["status"] == "QUEUED" for item in payload["assignments"])
    assert sorted(sent_assignment_ids) == sorted(
        item["id"] for item in payload["assignments"]
    )
    event_types = [
        event.event_type
        for event in db_session.execute(
            select(AgentEvent).where(AgentEvent.task_id == run_id).order_by(AgentEvent.sequence)
        ).scalars()
    ]
    assert "AGENT_ASSIGNMENT_QUEUED" in event_types


def test_agent_assignment_worker_executes_one_assignment_and_reduces_when_ready(
    db_session: Session,
) -> None:
    client = TestClient(app)
    plan_response = client.post(
        "/api/agents/plan",
        headers=AUTH_HEADERS,
        json={
            "agent_id": "default",
            "goal": "分析项目结构，安排研究与审查 Agent 协作",
            "model_provider": "openai-compatible",
            "model_name": "default",
            "max_subagents": 5,
            "enable_sandbox": True,
            "enable_network": False,
        },
    )
    run_id = plan_response.json()["run_id"]
    client.post(f"/api/agents/runs/{run_id}/orchestrate", headers=AUTH_HEADERS)
    assignments = list(
        db_session.execute(
            select(AgentAssignment)
            .where(AgentAssignment.run_id == run_id)
            .order_by(AgentAssignment.created_at.asc(), AgentAssignment.id.asc())
        ).scalars()
    )

    for assignment in assignments:
        status = execute_agent_assignment(assignment.id, session=db_session)
        assert status == "SUCCESS"

    reviewer = next(assignment for assignment in assignments if assignment.agent_id == "reviewer")
    assert "reduced_summary" in reviewer.output_json


def test_agent_assignment_respects_agent_tool_allowlist(db_session: Session) -> None:
    client = TestClient(app)
    plan_response = client.post(
        "/api/agents/plan",
        headers=AUTH_HEADERS,
        json={
            "agent_id": "default",
            "goal": "验证 Agent 工具权限边界",
            "model_provider": "openai-compatible",
            "model_name": "default",
            "max_subagents": 5,
            "enable_sandbox": True,
            "enable_network": False,
        },
    )
    run_id = plan_response.json()["run_id"]
    db_session.add(
        Agent(
            id="restricted",
            organization_id=None,
            name="Restricted Agent",
            description="Cannot list files",
            role="researcher",
            status="ACTIVE",
            model_provider="default",
            model_name="default",
            system_prompt="Restricted",
            tools_json=["read_file"],
            routing_tags=[],
        )
    )
    db_session.flush()
    assignment = AgentAssignment(
        run_id=run_id,
        agent_id="restricted",
        role="researcher",
        status="PENDING",
        input_json={},
        output_json={},
    )
    db_session.add(assignment)
    db_session.commit()

    status = execute_agent_assignment(assignment.id, session=db_session)

    assert status == "FAILED"
    assert assignment.output_json["permission_boundary"] == "agent.tools_json"
    assert assignment.output_json["tool_name"] == "list_files"


def test_agent_auto_mode_plans_orchestrates_and_executes_run(db_session: Session) -> None:
    response = TestClient(app).post(
        "/api/agents/auto",
        headers=AUTH_HEADERS,
        json={
            "agent_id": "default",
            "goal": "自动分析项目结构并完成执行",
            "model_provider": "openai-compatible",
            "model_name": "default",
            "max_subagents": 5,
            "enable_sandbox": True,
            "enable_network": False,
        },
    )

    assert response.status_code == 202
    payload = response.json()
    assert payload["task"]["status"] == "COMPLETED"
    assert payload["plan"]["steps"]
    assert all(
        assignment["status"] == "SUCCESS"
        for assignment in payload["orchestration"]["assignments"]
    )
    run_id = payload["run_id"]
    event_types = [
        event.event_type
        for event in db_session.execute(
            select(AgentEvent).where(AgentEvent.task_id == run_id).order_by(AgentEvent.sequence)
        ).scalars()
    ]
    assert "PLAN_GENERATED" in event_types
    assert "AGENT_REDUCE_COMPLETED" in event_types
    assert event_types[-1] == "TASK_COMPLETED"
