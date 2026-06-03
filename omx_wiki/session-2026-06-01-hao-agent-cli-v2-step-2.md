# hao Agent CLI v2 Step 2

Category: `session-log`

Tags: `hao`, `cli`, `local-execution`, `session-log`, `command-lifecycle`, `cancel`, `retry`

## Summary

hao v2 Step 2 finished the command lifecycle lane for local shell/test/git execution. The CLI now persists command records, streams output to `commands.jsonl`, tracks pending/running/success/failed/timeout/cancelled states, supports retry clones, links backend tool events back to local command rows, and exposes `/cancel` and `/retry` in the TUI.

## Evidence

```text
cd services/api-server && uv run pytest tests/test_hao_cli.py tests/test_hao_cli_v2.py -q -> 48 passed
cd services/api-server && uv run ruff check app/cli/hao tests/test_hao_cli.py tests/test_hao_cli_v2.py -> passed
cd services/api-server && uv run python -m py_compile app/cli/hao/local_tools.py app/cli/hao/session_store.py app/cli/hao/tui.py -> passed
```

## Notes

- `SessionStore` now guards command transitions so terminal commands cannot be restarted or finished twice.
- `execute_local_command_tool()` creates the command record, starts the subprocess, captures stdout/stderr, and persists the terminal lifecycle record.
- Output streaming is byte-capped per stream, writes `output_truncated` markers, and stops appending unbounded chunks to JSONL artifacts.
- Startup failures now transition the command from `pending` to `running` to `failed` instead of leaving a stranded pending row.
- `retry_command()` only accepts terminal commands, preventing live command cloning.
- `execute_local_tool()` delegates shell/test/git execution to the lifecycle runner when session context is available.
- `HaoApp._record_tool_result()` links `command_id` back to `tool_event_id` after the backend audit row is written.
- `HaoApp._handle_command()` now accepts `/cancel <command_id>` and `/retry <command_id>`.

## Next Step

Move to Step 3: diff-first preview/commit for write operations.
