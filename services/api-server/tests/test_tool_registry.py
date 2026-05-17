from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Agent, AgentCapabilityAttachment, AgentEvent, ToolCall
from app.main import app
from app.tools.capabilities import CapabilityRegistry
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


def _create_agent(db_session: Session, *, agent_id: str, tools: list[str]) -> None:
    db_session.add(
        Agent(
            id=agent_id,
            organization_id=None,
            name=f"{agent_id} Agent",
            description="Capability-scoped test agent",
            role="tester",
            status="ACTIVE",
            model_provider="default",
            model_name="default",
            system_prompt="Use only attached tools.",
            tools_json=tools,
            routing_tags=[],
        )
    )
    db_session.flush()
    CapabilityRegistry(db_session, "dev-org").backfill_agent_attachments(
        agent_id,
        attached_by="test",
    )


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


def test_compat_tool_execute_denies_task_without_agent_scope(db_session: Session) -> None:
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
    assert payload["allowed"] is False
    assert payload["tool_call"]["tool_name"] == "mcp_context_search"
    assert payload["tool_call"]["status"] == "DENIED"
    assert payload["tool_call"]["error_message"] == "agent not found: __missing_agent__"
    assert payload["tool_call"]["capability_version_id"] is None
    assert payload["output"] == {}

    tool_call = db_session.execute(
        select(ToolCall).where(
            ToolCall.task_id == task_id,
            ToolCall.tool_name == "mcp_context_search",
        )
    ).scalar_one()
    assert tool_call.status == "DENIED"
    event_types = [
        event.event_type
        for event in db_session.execute(
            select(AgentEvent).where(AgentEvent.task_id == task_id).order_by(AgentEvent.sequence)
        ).scalars()
    ]
    assert "POLICY_CHECKED" in event_types
    assert "TOOL_DENIED_BY_POLICY" in event_types


def test_agent_scoped_mcp_test_invocation_uses_tool_runner_policy_and_audit_path(
    db_session: Session,
) -> None:
    _create_agent(db_session, agent_id="mcp-agent", tools=["mcp_context_search"])

    response = TestClient(app).post(
        "/api/tools/capabilities/test-invoke",
        headers=AUTH_HEADERS,
        json={
            "agent_id": "mcp-agent",
            "tool_name": "mcp_context_search",
            "input_json": {"query": "event sourcing replay", "limit": 2},
        },
    )

    assert response.status_code == 202
    payload = response.json()
    assert payload["allowed"] is True
    assert payload["tool_call"]["tool_name"] == "mcp_context_search"
    assert payload["tool_call"]["status"] == "SUCCESS"
    assert payload["tool_call"]["capability_version_id"] is not None
    assert payload["tool_call"]["capability_content_sha256"] is not None
    assert payload["tool_call"]["capability_snapshot_json"]["agent_id"] == "mcp-agent"
    assert payload["output"]["mcp_server"] == "local-context"
    assert payload["output"]["mcp_method"] == "context.search"
    assert len(payload["output"]["result"]["items"]) == 2

    tool_call = db_session.get(ToolCall, payload["tool_call"]["id"])
    assert tool_call is not None
    assert tool_call.status == "SUCCESS"
    assert tool_call.output_json["mcp_server"] == "local-context"
    event_types = [
        event.event_type
        for event in db_session.execute(
            select(AgentEvent)
            .where(AgentEvent.task_id == tool_call.task_id)
            .order_by(AgentEvent.sequence)
        ).scalars()
    ]
    assert "POLICY_CHECKED" in event_types
    assert "TOOL_CALLED" in event_types
    assert "TOOL_RESULT_RECEIVED" in event_types


def test_admin_validation_redacts_secrets_and_does_not_create_tool_call(
    db_session: Session,
) -> None:
    response = TestClient(app).post(
        "/api/tools/capabilities/admin-validate",
        headers=AUTH_HEADERS,
        json={
            "content": {"name": "private-tool"},
            "config": {
                "api_key": "clear-secret",
                "secret_ref": "vault://tool/api-key",
                "nested": {"authorization": "Bearer clear-secret"},
            },
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "valid"
    assert payload["redacted_payload"]["config"]["api_key"] == "[REDACTED]"
    assert payload["redacted_payload"]["config"]["secret_ref"] == "vault://tool/api-key"
    assert payload["redacted_payload"]["config"]["nested"]["authorization"] == "[REDACTED]"
    assert db_session.execute(select(ToolCall)).scalar_one_or_none() is None


def test_disabled_attachment_denies_even_when_tool_remains_in_legacy_tools_json(
    db_session: Session,
) -> None:
    _create_agent(db_session, agent_id="locked-agent", tools=["read_file"])
    registry = CapabilityRegistry(db_session, "dev-org")
    registry.backfill_agent_attachments("locked-agent", attached_by="test")
    attachment = db_session.execute(
        select(AgentCapabilityAttachment).where(
            AgentCapabilityAttachment.agent_id == "locked-agent",
        )
    ).scalar_one()
    attachment.enabled = False
    db_session.flush()

    response = TestClient(app).post(
        "/api/tools/capabilities/test-invoke",
        headers=AUTH_HEADERS,
        json={
            "agent_id": "locked-agent",
            "tool_name": "read_file",
            "input_json": {"path": "pyproject.toml"},
        },
    )

    assert response.status_code == 202
    payload = response.json()
    assert payload["allowed"] is False
    assert payload["tool_call"]["status"] == "DENIED"
    assert "not attached to capability read_file" in payload["tool_call"]["error_message"]
    assert payload["tool_call"]["capability_version_id"] is None


def test_legacy_tools_json_alone_does_not_authorize_or_lazy_backfill(
    db_session: Session,
) -> None:
    db_session.add(
        Agent(
            id="legacy-only-agent",
            organization_id=None,
            name="Legacy Only Agent",
            description="Has tools_json but no persisted capability attachment",
            role="tester",
            status="ACTIVE",
            model_provider="default",
            model_name="default",
            system_prompt="Legacy metadata only.",
            tools_json=["read_file"],
            routing_tags=[],
        )
    )
    db_session.flush()

    response = TestClient(app).post(
        "/api/tools/capabilities/test-invoke",
        headers=AUTH_HEADERS,
        json={
            "agent_id": "legacy-only-agent",
            "tool_name": "read_file",
            "input_json": {"path": "pyproject.toml"},
        },
    )

    assert response.status_code == 202
    payload = response.json()
    assert payload["allowed"] is False
    assert payload["tool_call"]["status"] == "DENIED"
    assert "not attached to capability read_file" in payload["tool_call"]["error_message"]
    assert (
        db_session.execute(
            select(AgentCapabilityAttachment).where(
                AgentCapabilityAttachment.agent_id == "legacy-only-agent",
            )
        ).scalar_one_or_none()
        is None
    )
