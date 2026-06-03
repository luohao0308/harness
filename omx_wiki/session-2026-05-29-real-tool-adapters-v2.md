# Session 2026-05-29 Real Tool Adapters v2

Category: `session-log`

Tags: `agent-knowledge-harness`, `mcp`, `tools`, `tool-adapters`, `github`, `slack`, `notion`, `linear`, `code-interpreter`, `sandbox`, `task-progress`

## Summary

Real Tool Adapters v2 is verified locally on `p7-release-demo-hardening`. The slice upgrades the v1 adapter boundary with a minimal MCP protocol client, MCP discovery into org-scoped child capabilities, Code Interpreter, write-capable GitHub/Slack operations, and Notion/Linear adapters. It keeps the PRD's no-migration boundary and routes side effects through the existing ToolRunner, capability, sandbox, approval, audit, and idempotency contracts.

## Delivered Scope

- Added `services/api-server/app/tools/mcp_protocol/` with JSON-RPC client/session/discovery plus HTTP, SSE-aware streamable HTTP, and stdio-over-sandbox transports. The MCP initialize handshake is locked to `2024-11-05`, and stdio calls replay initialize/initialized inside the sandbox process before target requests.
- Added MCP server list/discovery APIs under `/api/tools/mcp-servers`; discovery pulls `tools/list` and registers each discovered tool as an Agent-attached, org-scoped capability using existing capability tables.
- Extended `MCPAdapter` so registered adapters dispatch first, configured MCP protocol tools call `tools/call`, and stdio MCP tools require a sandbox command executor injected by `ToolRunner`.
- Added `code_interpreter.run_python` and `code_interpreter.install_package` adapters. Both require a run sandbox; Python execution has a denylist for dangerous imports/calls, dynamic lookup bypasses, and bounded stdout/stderr/generated-file output.
- Added write-capable GitHub tools: `github.create_issue_comment`, `github.create_issue`, and `github.create_pull_review`.
- Added write-capable Slack tools: `slack.post_message` and `slack.add_reaction`.
- Added Notion tools: `notion.search_pages`, `notion.get_page`, `notion.query_database`, and high-risk `notion.append_block`.
- Added Linear tools: `linear.list_issues`, `linear.get_issue`, `linear.create_issue`, and `linear.create_comment`.
- Added persistent 24h idempotency replay for non-idempotent tools using existing `SystemSetting` JSON storage, avoiding new tables.
- Added Tool Registry UI panels for MCP Servers discovery and Code Interpreter test invocation, plus API client types for the new MCP discovery surfaces.

## Safety Boundaries

- No new migrations, tables, or dependencies were added.
- Stdio MCP never forks from the host process. The stdio transport raises unless `ToolRunner` provides a sandbox command executor; admin API discovery for stdio returns a safe failure instead of launching a process.
- Non-idempotent MCP/adapter tools now require `idempotency_key` at runtime. Schema-only enforcement was not considered sufficient, so `ToolRunner.request_approval`, normal execution, approved execution, and discovered write tools all enforce or advertise the key.
- Write operations remain non-idempotent metadata-wise and high-risk/critical. Existing policy settings still decide whether high-risk tools auto-run for admins or queue for approval; the new idempotency guard prevents missing-key side effects before either path can execute.
- Code Interpreter only runs through sandbox injection and rejects blocked Python constructs before sending code to the sandbox runner.
- Discovered MCP child capabilities are org-scoped; built-in capabilities remain global to avoid duplicate visible capability rows across orgs.

## Review And Drift Checks

Code review found and fixed six real issues before completion:

- Built-in `ensure_builtin_capabilities()` was briefly using the discovered-tool org-scoped capability path, producing duplicate visible built-in capability keys. It now uses the global built-in path again, while discovery keeps org-scoped child capabilities.
- Discovered MCP write tools did not initially add `idempotency_key` to their input schema. Discovery now patches non-idempotent tool schemas with a required `idempotency_key`.
- ToolRunner initially cached idempotent replays but did not reject missing keys for non-idempotent tools. Runtime enforcement now denies missing keys before side effects, including explicit approval requests and approved-call execution.
- Slack reaction and mutating discovered MCP tools were not uniformly high-risk. Write-class MCP metadata now uses high-risk/critical defaults so default policies cannot auto-run these side effects as medium-risk tools.
- Stdio runtime configuration initially accepted shell fragments as the command field. Runtime config now requires a single executable path/name and rejects control characters in args.
- Stdio MCP calls initially sent a single request to a fresh sandbox process. The sandbox script now performs MCP initialize/initialized before non-initialize requests and selects the target response by id.
- Code Interpreter blocked common dangerous calls but allowed `subprocess` import and dynamic `getattr` bypass attempts. The denylist now blocks `subprocess`, `importlib`, and `getattr` before sandbox execution.

Drift review confirmed the implementation stayed inside the v2 lane:

- No migrations/tables/dependencies were introduced.
- OAuth, Jira/Confluence, GitHub merge/delete, Slack workflow automation, cross-task interpreter state, and external marketplace publishing remain out of scope.
- The MCP protocol implementation is a minimal JSON-RPC subset rather than a full SDK adoption, matching the PRD's fallback guidance.
- Streamable HTTP remains a one-request/SSE-aware facade; bidirectional streaming is still future work.
- Live external-provider smoke and live stdio MCP server smoke were not run because the task context did not include real provider credentials or a safe live stdio server fixture.

## Validation Evidence

```text
cd services/api-server && .venv/bin/python -m pytest tests/test_tool_runner.py tests/test_mcp_protocol_discovery.py tests/test_sandbox.py::test_tool_registry_matches_stage12_required_tools tests/test_adapters_code_interpreter.py -q
24 passed

cd services/api-server && .venv/bin/python -m pytest tests -q
487 passed, 3 warnings

cd services/api-server && .venv/bin/python -m ruff check app tests
passed

cd apps/agent-console && npm test -- src/features/tools/__tests__/ToolRegistryPage.marketplace.test.tsx src/features/tools/__tests__/ToolConfigurationPage.test.tsx src/features/tasks/__tests__/api.test.ts --run
3 files / 11 tests passed

cd apps/agent-console && npm test -- src/features/teams/__tests__/TeamPages.test.tsx --run
19 passed

cd apps/agent-console && npm test -- --run --pool forks --poolOptions.forks.singleFork
47 files / 222 tests passed

cd apps/agent-console && npm test -- --run
failed on the unrelated TeamPages branch-switch flaky (`分支 1/2`); all other files/tests passed

cd apps/agent-console && npm run lint -- --pretty false
passed

cd apps/agent-console && npm run build
passed with the existing Vite large-chunk warning

python3 scripts/validate-docs.py
passed

git diff --check
passed
```

The default parallel `npm test -- --run` exposed an unrelated TeamPages branch-switch flaky (`分支 1/2`) again. The same test file passed when run directly, and the full frontend suite passed under single-fork isolation, so this was recorded as a residual test isolation risk rather than a Real Tool Adapters v2 regression.

## Next Work

- Add a safe live stdio MCP fixture or containerized smoke so stdio discovery/call behavior can be verified beyond unit coverage.
- Run live provider smoke once real GitHub, Slack, Notion, and Linear credentials are available in a non-production test workspace.
- Consider hardening the unrelated TeamPages branch-switch test isolation so default parallel Vitest no longer flakes.

## Related Pages

- [[project-handoff-current-state]]
- [[agent-knowledge-harness-roadmap]]
- [[session-2026-05-17-agent-knowledge-p5-capability-registry]]
- [[session-2026-05-26-mcp-skill-tool-modal-config]]
- [[session-2026-05-28-real-tool-adapters-v1]]
