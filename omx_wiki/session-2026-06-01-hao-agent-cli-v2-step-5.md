# hao Agent CLI v2 Step 5

Category: `session-log`

Tags: `hao`, `cli`, `local-execution`, `session-log`, `audit`, `workflow`

## Summary

hao v2 Step 5 closed out the backend protocol and audit surface instead of adding a new execution layer. `cli_agent` remains the executable stream path, `codex_plan` remains plan-only from the CLI side, and local host tool results continue only after backend audit succeeds. Workflow metadata now stays visible across stream requests, local audit payloads, backend `ToolCall` snapshots, backend `AgentEvent` payloads, and local tool messages.

## Evidence

```text
cd services/api-server && uv run pytest tests/test_hao_cli.py tests/test_hao_cli_v2.py -q -> 76 passed
cd services/api-server && uv run pytest -q -> 637 passed, 2 warnings
cd services/api-server && uv run ruff check app/cli/hao app/api/agents/agent_cli.py app/api/schemas.py tests/test_hao_cli.py tests/test_hao_cli_v2.py -> passed
python3 scripts/validate-docs.py -> docs validation passed
git diff --check -> passed
```

Subagent gate:

```text
Architecture/protocol review -> approved Step 5 for writeback; only remaining work was task-progress/wiki evidence.
Test review -> approved Step 5 coverage; cited workflow metadata audit, tool message retention, and plan-only stream tests.
```

## Notes

- `AgentChatStreamRequest` and `AgentLocalToolEventRequest` accept `interaction_mode` and optional `act_intent`.
- Backend local-tool audit writes workflow metadata into `ToolCall.capability_snapshot_json` and `AgentEvent.payload_json`.
- `TOOL_CALLED`, `TOOL_DENIED_BY_POLICY`, `TOOL_RESULT_RECEIVED`, `TOOL_FAILED`, and `TOOL_TIMEOUT` paths keep the same workflow metadata.
- `codex_plan` mode does not execute host or sandbox local tools from the CLI even if a tool request appears in the stream.
- Host local-tool audit failure records local `AUDIT_FAILED` evidence, skips the `tool` message, and stops auto-continuation.
- Workspace context keeps local `tool` role messages available to the next stream.
- Full backend regression covered the broader harness surface and completed with `637 passed, 2 warnings`.

## Next Step

Move to Step 6: final verification and user-facing docs closeout for hao v2.
