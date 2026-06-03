# hao Agent CLI v2 Step 1A

Category: `session-log`

Tags: `hao`, `cli`, `branching`, `migration`, `local-execution`, `task-progress`

## Summary

Completed Step 1A for hao v2: the local `SessionStore` now persists a minimal tree model, `resume` restores the active path instead of the full linear log, and legacy `~/.hao/hao.db` files upgrade through additive SQLite columns plus backfill.

This step stays inside the local CLI boundary. It does not yet change `/chat` / `/plan` / `/act` payload mapping or backend stream mode routing.

## Implemented

- Added `sessions.active_leaf_id` plus message-level `parent_id`, `branch_id`, `source_message_id`, and `tool_event_id` persistence.
- Made `append_message()` attach to the current active leaf by default, while allowing explicit parent branching for sibling histories.
- Added `list_active_path(session_id)` and taught `list_messages(session_id)` to return real `parent_id` and computed `children_ids`.
- Updated `hao resume` TUI loading to restore only the active path.
- Added additive SQLite schema migration and backfill logic for pre-v2 `hao.db` files.
- Added `services/api-server/tests/test_hao_cli_v2.py` for tree persistence, active-path recovery, resume, and v1 migration coverage.

## Validation

- `cd services/api-server && uv run pytest tests/test_hao_cli_v2.py tests/test_hao_cli.py -q` -> `12 passed`.
- `cd services/api-server && uv run ruff check app/cli/hao tests/test_hao_cli_v2.py tests/test_hao_cli.py` -> passed.
- `cd services/api-server && uv run hao --help` -> passed.
- `cd services/api-server && HAO_HOME=/tmp/hao-test-home uv run hao doctor` -> passed with API health skipped because no token was configured.
- `python3 scripts/validate-docs.py` -> passed.
- `git diff --check` -> passed.

## Residual Risk

- Step 1B still remains: explicit `/chat` / `/plan` / `/act` workflow routing and payload mapping.
- Longer-running command lifecycle and diff-first write flow are still v2 follow-up work.
