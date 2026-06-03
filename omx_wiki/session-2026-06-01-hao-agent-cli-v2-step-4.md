# hao Agent CLI v2 Step 4

Category: `session-log`

Tags: `hao`, `cli`, `local-execution`, `session-log`, `tui`, `workflow`, `audit`

## Summary

hao v2 Step 4 upgraded the TUI workbench and command layer. The status bar now shows workflow, active leaf/branch, pending approvals, and command counts. The right rail now exposes tools, diff, files, approvals, commands, plan, and outputs views. The command layer covers `/chat`, `/plan`, `/act`, `/continue`, `/branch`, `/retry`, `/approve`, `/reject`, and `/sessions`.

## Evidence

```text
cd services/api-server && uv run pytest tests/test_hao_cli.py tests/test_hao_cli_v2.py -q -> 75 passed
cd services/api-server && uv run pytest tests/test_hao_cli_v2.py -q -k "sandbox_write_and_shell_requests_never_call_local_runner or approve_command_executes_pending_tool_with_frozen_metadata or approve_command_commits_pending_change_through_handler or audit_failure_records_local_failure_without_tool_message or workflow_and_sessions_commands_persist_and_render or outputs_view_uses_persisted_tool_output_summaries or continue_command_resumes_active_path_without_user_message or continue_after_branch_switch_sends_only_active_path_messages" -> 12 passed
cd services/api-server && uv run ruff check app/cli/hao tests/test_hao_cli.py tests/test_hao_cli_v2.py -> passed
python3 scripts/validate-docs.py -> docs validation passed
git diff --check -> passed
```

Subagent gate:

```text
Code review -> initially blocked on audit fail-closed, then approved after fix
Test review -> initially blocked on sandbox/command coverage, then approved after fixes
```

## Notes

- `HaoApp._workbench_status()` now reports active leaf/branch, pending tool/change approvals, running/total command counts, and the current side view.
- `/view` now switches among tools, diff, files, approvals, commands, plan, and outputs.
- `/chat`, `/plan`, and `/act` persist `cli_mode` and workflow metadata through the command layer; `/continue` resumes the current active path; `/branch` reloads a selected leaf.
- `plan` view only collects assistant content for `interaction_mode=plan`; `outputs` view summarizes persisted tool events, command rows, and output artifacts.
- Sandbox target tool routing now proves `run_shell`, `write_file`, and `apply_patch` do not touch the local runner.
- Host audit failure now records local `AUDIT_FAILED` evidence and does not write a tool message or auto-continue.

## Next Step

Move to Step 5: tighten the remaining backend protocol / audit surfaces and continue the v2 closeout.
