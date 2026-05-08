from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import AgentEvent, ToolCall
from app.main import app
from tests.conftest import AUTH_HEADERS


def _create_task(client: TestClient) -> str:
    response = client.post(
        "/api/tasks",
        headers=AUTH_HEADERS,
        json={
            "title": "MCP runtime",
            "goal": "Exercise MCP-shaped tools",
            "model_provider": "openai-compatible",
            "model_name": "default",
            "max_runtime_seconds": 1800,
            "max_subagents": 5,
            "enable_sandbox": True,
            "enable_network": False,
        },
    )
    assert response.status_code == 201
    return response.json()["id"]


def test_tool_registry_exposes_builtin_and_mcp_tools() -> None:
    response = TestClient(app).get("/api/tools/registry", headers=AUTH_HEADERS)

    assert response.status_code == 200
    payload = response.json()
    names = {item["name"] for item in payload["items"]}
    assert "read_file" in names
    assert "mcp_context_search" in names
    assert "mcp" in payload["sources"]
    mcp_tool = next(item for item in payload["items"] if item["name"] == "mcp_context_search")
    assert mcp_tool["source"] == "mcp"
    assert mcp_tool["mcp_server"] == "local-context"
    assert mcp_tool["mcp_method"] == "context.search"


def test_mcp_tool_uses_same_tool_runner_policy_and_audit_path(db_session: Session) -> None:
    client = TestClient(app)
    task_id = _create_task(client)

    response = client.post(
        f"/api/tasks/{task_id}/tools/execute",
        headers=AUTH_HEADERS,
        json={
            "tool_name": "mcp_context_search",
            "input_json": {"query": "event sourcing replay", "limit": 2},
        },
    )

    assert response.status_code == 202
    payload = response.json()
    assert payload["allowed"] is True
    assert payload["tool_call"]["tool_name"] == "mcp_context_search"
    assert payload["tool_call"]["status"] == "SUCCESS"
    assert payload["output"]["mcp_server"] == "local-context"
    assert payload["output"]["mcp_method"] == "context.search"
    assert len(payload["output"]["result"]["items"]) == 2

    tool_call = db_session.execute(
        select(ToolCall).where(
            ToolCall.task_id == task_id,
            ToolCall.tool_name == "mcp_context_search",
        )
    ).scalar_one()
    assert tool_call.status == "SUCCESS"
    assert tool_call.output_json["mcp_server"] == "local-context"
    event_types = [
        event.event_type
        for event in db_session.execute(
            select(AgentEvent).where(AgentEvent.task_id == task_id).order_by(AgentEvent.sequence)
        ).scalars()
    ]
    assert "POLICY_CHECKED" in event_types
    assert "TOOL_CALLED" in event_types
    assert "TOOL_RESULT_RECEIVED" in event_types
