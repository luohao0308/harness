# hao Agent CLI v2 Step 1B

Category: `session-log`

Tags: `hao`, `cli`, `workflow`, `local-execution`, `audit`, `task-progress`

## Summary

Completed Step 1B for hao v2: the CLI now has explicit `/chat`, `/plan`, and `/act` workflow routing, preserves workflow metadata through stream payloads and local messages, and writes the same metadata into backend local-tool audit records.

This step keeps the existing safety boundary. Host target tools still execute only inside the CLI process; the backend records audit evidence only.

## Implemented

- Added workflow metadata helpers in the TUI for `interaction_mode`, backend stream mode, and `/act` intent.
- Mapped `/chat` and `/act` to backend `cli_agent`; mapped `/plan` to backend `markdown_plan`.
- Added `act_intent={"source":"slash_command","allow_local_tools":true}` for `/act` payloads, local messages, and local-tool audit payloads.
- Persisted `interaction_mode` and `act_intent` in backend `ToolCall.capability_snapshot_json` and local-tool `AgentEvent.payload_json`.
- Suppressed local tool handling for `/plan`, even if the stream emits a `tool_call_requested` event.
- Froze pending tool workflow metadata, target, and permission mode at request time so approval after `/chat`, `/target`, or `/mode` switching cannot reroute or mislabel the tool.
- Added host/sandbox routing tests for non-plan `/chat` and `/act` tool requests.

## Validation

- `cd services/api-server && uv run pytest tests/test_hao_cli_v2.py -q` -> `18 passed`.
- `cd services/api-server && uv run pytest tests/test_hao_cli.py tests/test_hao_cli_v2.py -q` -> `26 passed`.
- `cd services/api-server && uv run ruff check app/cli/hao app/api/agents/agent_cli.py app/api/schemas.py tests/test_hao_cli_v2.py tests/test_hao_cli.py` -> passed.
- Two independent subagent reviews approved moving to the next step after the pending-approval metadata freeze and host/sandbox routing tests were added.

## Residual Risk

- Step 2 remains: command lifecycle persistence and runner state machine.
- Step 3 remains: diff-first preview/commit approval flow.
