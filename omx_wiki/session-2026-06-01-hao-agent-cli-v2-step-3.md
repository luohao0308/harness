# hao Agent CLI v2 Step 3

Category: `session-log`

Tags: `hao`, `cli`, `local-execution`, `session-log`, `diff-first`, `approval`, `pending-change`

## Summary

hao v2 Step 3 finished the diff-first write approval lane. Host `write_file` and `apply_patch` requests now create pending changes with diffs and hashes before any workspace mutation. Approval commits by `change_id`; rejection records a denied local tool result without touching files.

## Evidence

```text
cd services/api-server && uv run pytest tests/test_hao_cli.py tests/test_hao_cli_v2.py -q -> 58 passed
cd services/api-server && uv run ruff check app/cli/hao tests/test_hao_cli.py tests/test_hao_cli_v2.py -> passed
python3 scripts/validate-docs.py -> docs validation passed
git diff --check -> passed
```

Subagent gate:

```text
Implementation review -> agree to proceed
Test coverage review -> initially blocked on two missing assertions, then agreed after fixes
```

## Notes

- `SessionStore` now persists pending changes in SQLite and writes durable JSON snapshots under `pending-changes/<change_id>.json`.
- Pending changes store target paths, before/after SHA-256 hashes, diff text, proposed content or patch, frozen workflow/target/permission/risk metadata, and status.
- Host `write_file` and `apply_patch` create pending changes when session context is present; the model-facing TUI path no longer routes them as ordinary pending tools.
- `commit_write_file` and `commit_apply_patch` require `change_id`, verify the pending change belongs to the active session and expected tool, and reject stale files by comparing current hashes to `before_hashes`.
- `/approve <id>` now handles both `tool-` pending tools and `change-` pending changes. Pending tool ids are normalized with a `tool-` prefix so they cannot collide with `change-` ids.
- `/reject <change_id>` marks the change rejected, records a `DENIED` tool event, and leaves the workspace untouched.
- `PermissionEngine` now recognizes `preview_write_file`, `preview_apply_patch`, `commit_write_file`, and `commit_apply_patch`.

## Next Step

Move to Step 4: improve the TUI/agent loop around visible diff review, approval ergonomics, and continuous edit-test-repair flow.
