# Local Agent Tool Safety V3

Category: `session-log`

Tags: `local-agent`, `tool-safety`, `approval`, `hao`, `bridge`, `audit`

## Summary

Local Agent Tool Safety V3 is implemented and verified as the host-tool safety baseline after V1/V2.

V3 closes the V1/V2 architecture watch item: bridge-reported `tool_result` stays observation-only until local host execution is governed by Harness-owned tool request, policy, approval, authorized result, command lifecycle, pending change, cancel/retry, privacy, and audit fail-closed contracts.

## Planning Documents

- `.omx/plans/prd-local-agent-tool-safety-v3.md`
- `.omx/plans/test-spec-local-agent-tool-safety-v3.md`

## Implemented Scope

- Added local tool request, decision, result, command lifecycle, cancel, retry, and pending-change APIs under the existing local-Agent bridge boundary.
- Kept API/DB as the only authority for `ToolCall`, `ToolApproval`, `AgentEvent`, Run/Task, `AgentSession`, local tool request state, and audit evidence.
- Treats bridge risk fields as advisory telemetry only; server-side classification remains deny-by-default and checks capability attachment before side-effect execution.
- Splits local host approval from generic server ToolRunner approval. Local approval unlocks bridge polling, not server-side execution.
- Rejects side-effect results that lack an authorized `tool_request_id` / `tool_call_id`.
- Preserves fake bridge and hao as the V3 acceptance adapters; Codex CLI and Claude Code remain disabled future adapters.
- Redacts command strings, secret-looking values, and `/Users` or `/home` paths before persisting local tool audit evidence.
- Keeps raw `cwd`, executable `input_json`, command text, home paths, and raw bridge `device_token` out of `bridge.json`; the device credential is stored in a separate `0600` `bridge.device-token` file and legacy inline tokens migrate out on load.

## Review And Fix Gate

Two independent plan reviewers reached PASS after revisions:

- Aristotle architecture review: `PASS`. Watch items are local `ToolCall(APPROVED)` semantics, event/OpenAPI/UI projection coverage, avoiding unnecessary new statuses, and tightly keying the local approval branch by provenance plus `LocalAgentToolRequest.tool_call_id`.
- Parfit security/test review: `PASS`. Watch items are strict separation from generic `ToolApproval -> ToolRunner`, deny-by-default server classification, service guards for SQLite cross-table invariants, exactly-once smoke side effects in a temp workspace, and a fixed redaction corpus.

Implementation review then found two blocking repair items and two WATCH items:

- Retry endpoint validated failed/timeout/cancelled commands but returned unconditional 409.
- Revoke and TTL paths could leave unresolved local tool requests, approvals, commands, pending changes, bridge tasks, or runs.
- Approval after TTL expiry was not fail-closed at the browser approval endpoint.
- Revoked device tokens blocked bridge access but did not terminalize already-pending local tool state.

All four items are fixed in this closeout. Final independent implementation reviewers then found two additional bridge-state privacy blockers: raw `cwd` and raw `device_token` could still be written into `bridge.json`. Both are fixed and re-reviewed.

## Repair Details

- Retry now creates a fresh `LocalAgentToolRequest`, `ToolCall`, and pending `LocalAgentCommand` with `retry_of_command_id`; the original terminal command and request remain immutable.
- Retry rejects success/running/denied parents and validates `retry_of_command_id` on bridge command start.
- TTL expiry now terminalizes the local request, expires pending `ToolApproval`, denies `ToolCall`, denies active pending changes, and allows bridge assistant cleanup without unresolved tool state.
- Connection revoke now terminalizes active local requests, approvals, pending changes, active commands, bridge tasks, and the Workspace Run; late bridge access with the revoked device token returns 403.
- `bridge.json` is now serialized through a disk allowlist that excludes raw cwd, executable input, command text, home paths, and raw device token.
- The raw bridge device token is split into `bridge.device-token` with mode `0600`; `bridge.json` stores only `device_token_ref`, and `_load_bridge_state()` migrates legacy inline tokens out of `bridge.json`.

## Final Review Gate

- Architecture reviewer Sagan: `PASS` after verifying `bridge.json` privacy, device-token split/migration, runtime cwd continuity, ToolRunner separation, and API/DB-owned tool truth.
- Security/code reviewer Schrodinger: `APPROVE` after verifying `bridge.json` excludes raw cwd/input/command/home path/device token, authorized tool results require executable API-created requests, and revoke/TTL fail closed.

## Branch And Delivery Policy

- V3 planning branch: `feature/local-agent-tool-safety-v3`.
- V1/V2 reviewed implementation branch: `feature/local-agent-bridge-v1-v2`.
- V3 implementation branch: `feature/local-agent-tool-safety-v3`.
- New functionality must stay off `main` until final review, commit, and push are complete.
- Each future version plan must be入库 first, then pass two independent agent reviews before execution.
- After each implementation slice, run code review, fix blockers, verify, commit, and push.

## Implementation Baseline

V3 implementation landed through these gates:

1. Protocol and migration for local tool request, command, and pending-change projection.
2. Backend policy/approval path that writes `ToolCall`, `ToolApproval`, `AgentEvent`, and Run state transactionally.
3. hao bridge pre-execution authorization, decision polling, lifecycle reporting, cancel/retry, and pending-change hash guards.
4. Workspace/Run Detail/Agent Studio projection using existing surfaces.
5. Security negative tests, deterministic smoke, docs validation, and code review before commit.

## Validation For This Implementation Closeout

```text
cd services/api-server && .venv/bin/python -m pytest tests/test_local_agents.py -q
# 27 passed

cd services/api-server && .venv/bin/python -m pytest tests/test_tool_approvals.py tests/test_tool_runner.py -q
# 17 passed

cd services/api-server && .venv/bin/python -m pytest tests/test_hao_cli.py tests/test_hao_cli_v2.py -q -k "bridge or approval or pending_change or command or cancel or retry or pending_state_file"
# 63 passed, 75 deselected

cd services/api-server && .venv/bin/python -m py_compile app/api/agents/agent_local.py app/api/agents/common.py app/api/schemas.py app/api/tasks.py app/db/models.py app/events/event_types.py app/cli/hao/api_client.py app/cli/hao/local_tools.py app/cli/hao/main.py app/cli/hao/session_store.py tests/test_local_agents.py tests/test_hao_cli.py tests/test_hao_cli_v2.py
# passed

cd services/api-server && .venv/bin/python -m ruff check app/api/agents/agent_local.py app/api/agents/common.py app/api/schemas.py app/api/tasks.py app/db/models.py app/events/event_types.py app/cli/hao tests/test_local_agents.py tests/test_hao_cli.py tests/test_hao_cli_v2.py
# passed

cd services/api-server && DATABASE_URL=sqlite:////tmp/harness-local-agent-v3.sqlite AUTH_JWT_SECRET=test-harness-jwt-secret-32-characters-min HARNESS_SECRET_ENCRYPTION_KEY=test-harness-secret-encryption-key-32-min .venv/bin/alembic upgrade head
# passed

python3 scripts/smoke-test-local-agent-v3.py --scenario approve-shell
# PASS local-agent-v3 {'scenario': 'approve-shell', 'connections': 1, 'tool_calls': 1, 'approvals': 1, 'tool_requests': 1, 'commands': 1, 'pending_changes': 0, 'events': 14}

python3 scripts/smoke-test-local-agent-v3.py --scenario reject-write
# PASS local-agent-v3 {'scenario': 'reject-write', 'connections': 1, 'tool_calls': 1, 'approvals': 1, 'tool_requests': 1, 'commands': 0, 'pending_changes': 1, 'events': 10}

python3 scripts/smoke-test-local-agent-v3.py --scenario revoke-pending
# PASS local-agent-v3 {'scenario': 'revoke-pending', 'connections': 1, 'tool_calls': 1, 'approvals': 1, 'tool_requests': 1, 'commands': 0, 'pending_changes': 0, 'events': 9}

cd apps/agent-console && npm test -- AgentWorkspacePage.team-launch.test.tsx AgentListPage.studio.test.tsx ChatSurface.shell.test.tsx RunDetailPage.helpers.test.ts RunDetailPage.optimizer.test.tsx
# 5 files / 27 tests passed

cd apps/agent-console && npm run lint -- --pretty false
# passed

python3 scripts/validate-docs.py
# passed

git diff --check
# passed
```
