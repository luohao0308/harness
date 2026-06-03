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
