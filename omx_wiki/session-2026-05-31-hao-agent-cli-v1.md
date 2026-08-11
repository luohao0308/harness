# Hao Agent CLI V1

Category: `session-log`

Tags: `hao`, `cli`, `agent-console`, `tool-adapters`, `sandbox`, `policy-audit`, `local-execution`

## Summary

Implemented `hao` as a Python console CLI inside `services/api-server`, with a Textual/Rich TUI, local host tools, Harness sandbox target, local session persistence, resume, and backend audit for host-side tool evidence.

The product wording for docs uses "参考现代 Agentic Coding 产品" and keeps the official positioning as AI Harness local agent workflow, not a clone claim.

## Implemented

- Added `app/cli/hao` with `main.py`, `tui.py`, `api_client.py`, `session_store.py`, `permissions.py`, `local_tools.py`, `sandbox_tools.py`, and `diffs.py`.
- Exposed `hao = "app.cli.hao:main"` from `services/api-server/pyproject.toml` and added `textual`, `rich`, and `httpx` dependencies.
- Added host tools for `read_file`, `list_files`, `search_files`, `write_file`, `apply_patch`, `run_shell`, `run_tests`, and `git`.
- Added permission modes `confirm`, `auto-edit`, and `full-auto`, with dangerous shell command blocking and workspace path containment for file tools.
- Added a Textual TUI with status bar, streaming chat, side views for tools/diff/files/approvals, slash commands, local approvals, and target/mode switching.
- Added local session metadata in `~/.hao/hao.db` plus raw stream, tool-event, diff, and output artifacts under `~/.hao/sessions/<session_id>/`.
- Added `hao sessions` and `hao resume`; no-argument resume selects the most recent local session and restores its agent, cwd, mode, and target.
- Added backend `cli_agent` stream mode so model tool calls emit `tool_call_requested` with `pending_local` instead of running through backend host ToolRunner.
- Added `POST /api/agents/runs/{run_id}/local-tool-events` to write local host tool evidence into existing `ToolCall` and `AgentEvent` shapes.
- Preserved no-credential model smoke behavior by treating empty and `replace-me` OpenAI-compatible API keys as local mock credentials.
- Added `docs/development/cli/hao.md` covering install, auth, modes, targets, session recovery, and audit boundaries.

## Validation

- `cd services/api-server && uv run pytest tests/test_hao_cli.py -q` -> `8 passed`.
- `cd services/api-server && uv run pytest` -> `569 passed, 2 warnings`.
- `cd services/api-server && uv run ruff check app/cli/hao app/api/agents/agent_cli.py tests/test_hao_cli.py app/api/agents/agent_chat/streaming.py app/api/agents/_workspace_chat_helpers.py app/api/schemas.py app/agents/model_gateway.py` -> passed.
- `cd services/api-server && uv run hao --help` -> passed.
- `cd services/api-server && HAO_HOME=/tmp/hao-test-home uv run hao doctor` -> passed with API health skipped when token was missing.
- `python3 scripts/validate-docs.py` -> passed.
- `git diff --check` -> passed.

## Residual Risk

- The full-screen TUI was smoke-checked through CLI entrypoints and unit-covered logic, but no live interactive TUI session against a real model provider was run in this pass.
- `--target sandbox` delegates to the existing Harness sandbox/tool path; broader sandbox regression remains covered by the existing sandbox and ToolRunner suites, not by `test_hao_cli.py`.
