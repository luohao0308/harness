from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.db.models import AgentRun
from app.main import app
from tests.conftest import AUTH_HEADERS
from tests.test_agents import parse_sse_events


def _workspace_chat_payload(content: str, *, orchestration_mode: str = "auto") -> dict:
    node_id = f"user-{abs(hash(content))}"
    return {
        "mode": "chat",
        "orchestration_mode": orchestration_mode,
        "goal": content,
        "messages": [
            {
                "id": node_id,
                "parent_id": None,
                "children_ids": [],
                "role": "user",
                "content": content,
                "state": "done",
                "metadata": {},
                "tool_calls": [],
                "artifacts": [],
            }
        ],
        "active_leaf_id": node_id,
        "active_branch_id": f"branch-{node_id}",
        "pinned_node_ids": [],
        "context_window_turns": 8,
    }


def _spawn_workspace_subagent(content: str, *, orchestration_mode: str = "auto") -> tuple[str, str]:
    response = TestClient(app).post(
        "/api/agents/default/runs/chat/stream",
        headers=AUTH_HEADERS,
        json=_workspace_chat_payload(content, orchestration_mode=orchestration_mode),
    )
    assert response.status_code == 200, response.text
    events = parse_sse_events(response.text)
    orchestration = next(payload for event, payload in events if event == "orchestration")
    assert orchestration["mode"] == "subagent"
    assert orchestration["agent_type"] == "subagent"
    return orchestration["run_id"], orchestration["subagent_id"]


def test_english_workspace_request_creates_inspectable_subagent_evidence(
    db_session: Session,
) -> None:
    run_id, subagent_id = _spawn_workspace_subagent(
        "Use a subagent to inspect release readiness",
        orchestration_mode="subagent",
    )

    subagent = db_session.get(AgentRun, subagent_id)
    assert subagent is not None
    assert subagent.agent_type == "subagent"
    assert subagent.task_id == run_id
    assert subagent.context_json["source"] == "workspace_chat"

    client = TestClient(app)
    workspace = client.get(f"/api/agents/runs/{run_id}/workspace", headers=AUTH_HEADERS)
    assert workspace.status_code == 200, workspace.text
    workspace_payload = workspace.json()
    assert workspace_payload["run"]["id"] == run_id
    assert [item["id"] for item in workspace_payload["subagents"]] == [subagent_id]
    assert any(
        event["event_type"] == "SUBAGENT_SPAWNED"
        and (
            event.get("agent_run_id") == subagent_id
            or event.get("payload_json", {}).get("subagent_id") == subagent_id
        )
        for event in workspace_payload["events"]
    )

    subagents = client.get("/api/subagents", headers=AUTH_HEADERS)
    assert subagents.status_code == 200, subagents.text
    listed = next(item for item in subagents.json()["items"] if item["id"] == subagent_id)
    assert listed["task_id"] == run_id
    assert listed["context_json"]["source"] == "workspace_chat"

    detail = client.get(f"/api/subagents/{subagent_id}", headers=AUTH_HEADERS)
    assert detail.status_code == 200, detail.text
    assert detail.json()["id"] == subagent_id


def test_chinese_workspace_request_with_spaced_subagent_label_is_projected(
    db_session: Session,
) -> None:
    run_id, subagent_id = _spawn_workspace_subagent("请调用子 Agent 检查发布清单")

    subagent = db_session.get(AgentRun, subagent_id)
    assert subagent is not None
    assert subagent.context_json["goal"] == "请调用子 Agent 检查发布清单"

    result = TestClient(app).get(f"/api/tasks/{run_id}/result", headers=AUTH_HEADERS)
    assert result.status_code == 200, result.text
    payload = result.json()
    assert payload["task_id"] == run_id
    assert any(item["id"] == subagent_id for item in payload["subagent_results"])


def test_workspace_follow_up_subagent_request_uses_recent_context(
    db_session: Session,
) -> None:
    response = TestClient(app).post(
        "/api/agents/default/runs/chat/stream",
        headers=AUTH_HEADERS,
        json={
            "mode": "chat",
            "orchestration_mode": "auto",
            "goal": "你现在调用一下",
            "messages": [
                {
                    "id": "assistant-subagent-context",
                    "parent_id": None,
                    "children_ids": ["user-follow-up"],
                    "role": "assistant",
                    "content": "当前没有可供调用的子Agent。",
                    "state": "done",
                    "metadata": {},
                    "tool_calls": [],
                    "artifacts": [],
                },
                {
                    "id": "user-follow-up",
                    "parent_id": "assistant-subagent-context",
                    "children_ids": [],
                    "role": "user",
                    "content": "你现在调用一下",
                    "state": "done",
                    "metadata": {},
                    "tool_calls": [],
                    "artifacts": [],
                },
            ],
            "active_leaf_id": "user-follow-up",
            "active_branch_id": "branch-follow-up-subagent",
            "pinned_node_ids": [],
            "context_window_turns": 8,
        },
    )

    assert response.status_code == 200, response.text
    events = parse_sse_events(response.text)
    orchestration = next(payload for event, payload in events if event == "orchestration")
    subagent = db_session.get(AgentRun, orchestration["subagent_id"])
    assert subagent is not None
    assert subagent.context_json["goal"] == "你现在调用一下"
