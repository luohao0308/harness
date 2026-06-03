# Session 2026-05-28 Real Tool Adapters v1

Category: `session-log`

Tags: `agent-knowledge-harness`, `mcp`, `tools`, `tool-adapters`, `github`, `slack`, `sandbox`, `task-progress`

## Summary

Real Tool Adapters v1 is verified locally on `p7-release-demo-hardening`. Tool execution now has a registry-backed adapter dispatch path for the first production-shaped adapters: GitHub, Slack, and sandbox file browser. The change keeps existing MCP-shaped fallback behavior intact while adding introspection, health checks, UI schema/try-it surfaces, and adapter hashes in ToolCall capability snapshots.

## Delivered Scope

- Added `services/api-server/app/tools/adapter_registry.py` with `ToolAdapter`, `AdapterRegistry`, metadata, health timing, and deterministic adapter/schema hashes.
- Added built-in adapter registration for:
  - GitHub: `github.list_issues`, `github.get_issue`, `github.list_pulls`, `github.get_pull`, `github.search_code`.
  - Slack: `slack.search_messages`, `slack.list_channels`, `slack.get_thread`.
  - Sandbox file browser: `sandbox.read_file`, `sandbox.list_files`, `sandbox.write_file`, `sandbox.delete_file`.
- `MCPAdapter` now dispatches registered adapters first and retains existing fallback behavior for `brave`, `mcp_context_search`, `mcp_artifact_put`, and generic marketplace smoke output.
- `ToolRunner` now records adapter metadata inside `ToolCall.capability_snapshot_json`, including adapter version, module path, source hash, and input/output schema hashes.
- Added `GET /api/tools/adapters` and `GET /api/tools/adapters/{slug}/health`; health probes are admin/engineer scoped, rate limited per org/slug, and resolve Agent runtime secrets when configured.
- Added Tool Registry, Tool Configuration, and Run Detail UI evidence for adapter health, schema, try-it execution, and adapter hash display.
- Kept the PRD no-migration boundary: no new migrations, no new tables, no persisted sandbox workspace root, and no new dependencies.

## Safety Boundaries

- GitHub and Slack v1 are read-only; no issue/comment/merge or `chat.postMessage` operations were added.
- Adapter provider failures return structured error payloads such as `missing_secret`, `rate_limited`, `github_api_error`, `slack_api_error`, and `sandbox_not_ready` instead of raising through ToolCall execution.
- Sandbox file adapter fails closed unless ToolRunner has a run sandbox object, blocks absolute and `..` paths, bounds file size/list depth, and keeps write/delete as high-risk approval-gated tools.
- WarmPool and Docker sandbox creation accept an optional runtime `workspace_root` mount, but `SandboxInstance` schema remains unchanged.

## Validation Evidence

```text
cd services/api-server && .venv/bin/python -m pytest tests/test_adapter_registry.py tests/test_adapters_github.py tests/test_adapters_slack.py tests/test_adapters_sandbox_file.py tests/test_mcp_adapter.py tests/test_tool_runner.py tests/test_sandbox.py tests/test_warm_pool.py tests/test_tool_registry.py -q
73 passed

cd services/api-server && .venv/bin/python -m pytest tests -q
456 passed, 3 warnings

cd services/api-server && .venv/bin/python -m ruff check app tests
passed

cd apps/agent-console && npm test -- AdapterHealthBadge AdapterSchemaDrawer ToolRegistryPage ToolConfigurationPage RunDetailPage
13 passed

cd apps/agent-console && npm test -- --run
46 files / 219 tests passed

cd apps/agent-console && npm test -- TeamPages
19 passed

cd apps/agent-console && npm run lint -- --pretty false
passed

cd apps/agent-console && npm run build
passed with the existing Vite large-chunk warning

python3 scripts/validate-docs.py
passed

git diff --check
passed
```

## Next Work

- Real MCP protocol support remains out of scope: JSON-RPC over stdio/SSE/streamable-http needs a separate sandboxed subprocess/transport design.
- OAuth, GitHub writes, Slack posting, Notion/Linear/Jira/Confluence adapters, and user-uploaded adapter marketplace sharing remain future lanes.
- Live provider smoke requires real GitHub PAT and Slack bot token configuration; current verification uses mocked provider responses plus runtime config/health contract coverage.

## Related Pages

- [[project-handoff-current-state]]
- [[agent-knowledge-harness-roadmap]]
- [[session-2026-05-17-agent-knowledge-p5-capability-registry]]
- [[session-2026-05-26-mcp-skill-tool-modal-config]]
