import httpx
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.db.models import Capability
from app.main import app
from app.sandbox.docker_manager import SandboxCommandResult
from app.tools.capabilities import CapabilityRegistry
from app.tools.mcp_protocol.client import MCPClient
from app.tools.mcp_protocol.transports.http_transport import MCPHTTPTransport
from app.tools.mcp_protocol.transports.stdio_transport import MCPStdioSandboxTransport
from tests.conftest import AUTH_HEADERS
from tests.test_tool_registry import _create_agent


def test_mcp_http_client_initializes_and_lists_tools(monkeypatch) -> None:
    responses = [
        httpx.Response(
            200,
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "result": {"protocolVersion": "2024-11-05", "capabilities": {}},
            },
        ),
        httpx.Response(200, json={"jsonrpc": "2.0", "result": {}}),
        httpx.Response(
            200,
            json={
                "jsonrpc": "2.0",
                "id": 2,
                "result": {
                    "tools": [
                        {
                            "name": "read_file",
                            "description": "Read file",
                            "inputSchema": {"type": "object"},
                            "annotations": {"readOnlyHint": True},
                        }
                    ]
                },
            },
        ),
    ]
    calls = []

    def fake_post(*args, **kwargs):
        calls.append(kwargs["json"])
        return responses.pop(0)

    monkeypatch.setattr("app.tools.mcp_protocol.transports.http_transport.httpx.post", fake_post)
    client = MCPClient(MCPHTTPTransport(endpoint_url="https://mcp.test/rpc"))

    tools = client.list_tools()

    assert calls[0]["method"] == "initialize"
    assert calls[0]["params"]["protocolVersion"] == "2024-11-05"
    assert calls[2]["method"] == "tools/list"
    assert tools[0].name == "read_file"
    assert tools[0].annotations == {"readOnlyHint": True}


def test_mcp_stdio_transport_runs_handshake_inside_sandbox_executor() -> None:
    calls = []

    def executor(command: str, cwd: str, timeout_seconds: int) -> SandboxCommandResult:
        calls.append({"command": command, "cwd": cwd, "timeout_seconds": timeout_seconds})
        return SandboxCommandResult(
            stdout=(
                '__HARNESS_MCP_RESPONSE__={"jsonrpc":"2.0","id":7,'
                '"result":{"content":[{"type":"text","text":"ok"}]}}\n'
            ),
            stderr="",
            exit_code=0,
            duration_ms=4,
        )

    transport = MCPStdioSandboxTransport(
        command="node",
        args=["server.js"],
        sandbox_executor=executor,
    )

    response = transport.request(
        {
            "jsonrpc": "2.0",
            "id": 7,
            "method": "tools/call",
            "params": {"name": "read_file", "arguments": {"path": "README.md"}},
        },
        timeout_seconds=12,
    )

    assert response["id"] == 7
    assert calls[0]["cwd"] == "/workspace"
    assert calls[0]["timeout_seconds"] == 12
    assert "harness-stdio-initialize" in calls[0]["command"]
    assert "notifications/initialized" in calls[0]["command"]


def test_mcp_discovery_endpoint_registers_child_tools(
    db_session: Session,
    monkeypatch,
) -> None:
    _create_agent(db_session, agent_id="mcp-discovery-agent", tools=[])
    client = TestClient(app)
    preflight = client.post(
        "/api/tools/capabilities/preflight/marketplace",
        headers=AUTH_HEADERS,
        json={
            "source_uri": "https://example.com/mcp/filesystem",
            "pinned_ref": "marketplace-sha256:mcp-filesystem",
            "marketplace_source": "test",
            "marketplace_item_id": "filesystem",
            "display_name": "Filesystem MCP",
            "description": "Filesystem MCP server",
            "package_type": "mcp_server",
            "permissions": ["mcp:remote"],
            "manifest": {
                "name": "filesystem",
                "version": "1.0.0",
                "description": "Filesystem MCP server",
                "package_type": "mcp_server",
                "permissions": ["mcp:remote"],
                "transport": "http",
                "mcp_server": {"qualified_name": "filesystem"},
            },
        },
    )
    assert preflight.status_code == 201
    package_id = preflight.json()["package"]["id"]
    approved = client.post(
        f"/api/tools/capabilities/packages/{package_id}/approve",
        headers=AUTH_HEADERS,
        json={"reason": "test"},
    )
    assert approved.status_code == 200
    attached = client.post(
        f"/api/tools/capabilities/packages/{package_id}/attachments",
        headers=AUTH_HEADERS,
        json={"agent_id": "mcp-discovery-agent", "enabled": True, "priority": 10},
    )
    assert attached.status_code == 201
    configured = client.patch(
        "/api/tools/capabilities/runtime-config",
        headers=AUTH_HEADERS,
        json={
            "agent_id": "mcp-discovery-agent",
            "tool_name": "filesystem",
            "transport": "http",
            "endpoint_url": "https://mcp.test/rpc",
            "timeout_seconds": 10,
        },
    )
    assert configured.status_code == 200

    class FakeDiscovery:
        ok = True
        resources_count = 1
        message = "discovered 1 MCP tools"

        class Tool:
            name = "read_file"
            description = "Read file"
            input_schema = {"type": "object", "properties": {"path": {"type": "string"}}}
            annotations = {"readOnlyHint": True}

        tools = [Tool()]

    monkeypatch.setattr("app.api.tools.discover_tools", lambda **kwargs: FakeDiscovery())

    discovered = client.post(
        "/api/tools/mcp-servers/filesystem/discover",
        headers=AUTH_HEADERS,
        params={"agent_id": "mcp-discovery-agent"},
    )

    assert discovered.status_code == 200
    payload = discovered.json()
    assert payload["discovery_status"] == "ready"
    assert payload["discovered_tools"][0]["slug"] == "mcp.filesystem.read_file"
    assert payload["registered_runtime_configs"][0]["tool_name"] == "mcp.filesystem.read_file"
    registry, _snapshot = CapabilityRegistry(db_session, "dev-org").tool_registry_for_agent(
        "mcp-discovery-agent"
    )
    assert "mcp.filesystem.read_file" in registry.tools
    child_capability = (
        db_session.query(Capability)
        .filter(
            Capability.organization_id == "dev-org",
            Capability.capability_key == "tool:mcp.filesystem.read_file",
        )
        .one()
    )
    assert child_capability.organization_id == "dev-org"


def test_mcp_discovery_requires_idempotency_key_for_discovered_write_tools(
    db_session: Session,
    monkeypatch,
) -> None:
    _create_agent(db_session, agent_id="mcp-write-discovery-agent", tools=[])
    client = TestClient(app)
    preflight = client.post(
        "/api/tools/capabilities/preflight/marketplace",
        headers=AUTH_HEADERS,
        json={
            "source_uri": "https://example.com/mcp/tickets",
            "pinned_ref": "marketplace-sha256:mcp-tickets",
            "marketplace_source": "test",
            "marketplace_item_id": "tickets",
            "display_name": "Tickets MCP",
            "description": "Tickets MCP server",
            "package_type": "mcp_server",
            "permissions": ["mcp:remote"],
            "manifest": {
                "name": "tickets",
                "version": "1.0.0",
                "description": "Tickets MCP server",
                "package_type": "mcp_server",
                "permissions": ["mcp:remote"],
                "transport": "http",
                "mcp_server": {"qualified_name": "tickets"},
            },
        },
    )
    assert preflight.status_code == 201
    package_id = preflight.json()["package"]["id"]
    assert (
        client.post(
            f"/api/tools/capabilities/packages/{package_id}/approve",
            headers=AUTH_HEADERS,
            json={"reason": "test"},
        ).status_code
        == 200
    )
    assert (
        client.post(
            f"/api/tools/capabilities/packages/{package_id}/attachments",
            headers=AUTH_HEADERS,
            json={"agent_id": "mcp-write-discovery-agent", "enabled": True, "priority": 10},
        ).status_code
        == 201
    )
    assert (
        client.patch(
            "/api/tools/capabilities/runtime-config",
            headers=AUTH_HEADERS,
            json={
                "agent_id": "mcp-write-discovery-agent",
                "tool_name": "tickets",
                "transport": "http",
                "endpoint_url": "https://mcp.test/rpc",
            },
        ).status_code
        == 200
    )

    class FakeDiscovery:
        ok = True
        resources_count = 0
        message = "discovered 1 MCP tools"

        class Tool:
            name = "create_ticket"
            description = "Create ticket"
            input_schema = {"type": "object", "properties": {"title": {"type": "string"}}}
            annotations = {"readOnlyHint": False, "write": True}

        tools = [Tool()]

    monkeypatch.setattr("app.api.tools.discover_tools", lambda **kwargs: FakeDiscovery())

    discovered = client.post(
        "/api/tools/mcp-servers/tickets/discover",
        headers=AUTH_HEADERS,
        params={"agent_id": "mcp-write-discovery-agent"},
    )

    assert discovered.status_code == 200
    registry, _snapshot = CapabilityRegistry(db_session, "dev-org").tool_registry_for_agent(
        "mcp-write-discovery-agent"
    )
    metadata = registry.tools["mcp.tickets.create_ticket"]
    assert metadata.idempotent is False
    assert metadata.risk_level == "high"
    assert "idempotency_key" in metadata.input_schema["required"]
    assert metadata.input_schema["properties"]["idempotency_key"]["minLength"] == 1
