from app.tools.mcp_adapter import MCPAdapter
from app.tools.registry import ToolRegistry


def test_mcp_adapter_dispatches_registered_adapter_without_secret() -> None:
    metadata = ToolRegistry.default().tools["github.list_issues"]

    result = MCPAdapter().execute(
        metadata=metadata,
        input_json={"repo": "acme/repo"},
        config_json={},
        secret_value=None,
    )

    assert result.server == "github"
    assert result.method == "list_issues"
    assert result.output_json["error"] == "missing_secret"


def test_mcp_adapter_keeps_context_search_fallback() -> None:
    metadata = ToolRegistry.default().tools["mcp_context_search"]

    result = MCPAdapter().execute(
        metadata=metadata,
        input_json={"query": "release readiness", "limit": 2},
        config_json={},
        secret_value=None,
    )

    assert result.server == "local-context"
    assert result.method == "context.search"
    assert [item["id"] for item in result.output_json["items"]] == ["context-1", "context-2"]
    assert result.output_json["source"] == "mcp-adapter"


def test_mcp_adapter_calls_protocol_tool(monkeypatch) -> None:
    calls = []

    class FakeMCPClient:
        def __init__(self, transport, timeout_seconds: int = 30) -> None:
            self.transport = transport
            self.timeout_seconds = timeout_seconds

        def call_tool(self, name: str, arguments: dict):
            calls.append({"name": name, "arguments": arguments})

            class Result:
                content = [{"type": "text", "text": "ok"}]
                structured_content = {"ok": True}
                is_error = False

            return Result()

        def close(self) -> None:
            return None

    monkeypatch.setattr("app.tools.mcp_adapter.MCPClient", FakeMCPClient)
    metadata = ToolRegistry.default().tools["mcp_context_search"].model_copy(
        update={"name": "mcp.filesystem.read_file", "mcp_method": "read_file"}
    )

    result = MCPAdapter().execute(
        metadata=metadata,
        input_json={"path": "README.md"},
        config_json={
            "mcp_protocol": True,
            "runtime": {
                "transport": "http",
                "endpoint_url": "https://mcp.test/rpc",
                "mcp_tool_name": "read_file",
            },
        },
        secret_value="token",
    )

    assert calls == [{"name": "read_file", "arguments": {"path": "README.md"}}]
    assert result.output_json["source"] == "mcp-protocol"
    assert result.output_json["structured_content"] == {"ok": True}
