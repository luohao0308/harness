# Local Agent Claude Code Permission Bridge V6

Category: `session-log`

Tags: `local-agent`, `claude-code`, `permission-bridge`, `implementation`, `tool-safety`

## Summary

Local Agent Claude Code Permission Bridge V6 is implemented and verified on branch `feature/local-agent-claude-code-permission-bridge-v6`.

V6 upgrades Claude Code from the V5 no-tools adapter into an opt-in SDK intent-capture path. Claude Code can request local host tools, but side-effect intent is captured by the bridge, routed through Harness V3 `LocalAgentToolRequest`, `ToolApproval`, `ToolCall`, `AgentEvent`, pending-change, and command lifecycle authority, then executed by Harness-owned host-tool logic instead of Claude SDK native execution.

## Planning Documents

- `.omx/plans/prd-local-agent-claude-code-permission-bridge-v6.md`
- `.omx/plans/test-spec-local-agent-claude-code-permission-bridge-v6.md`

## Implemented Scope

- Added explicit V6 capability normalization and scoped entitlement gates for Claude Code permission bridge mode.
- Preserved V5 Claude Code no-tools behavior for connections without V6 permission bridge support.
- Integrated the official Claude Agent SDK permission callback as an intent-capture surface only; it does not authorize native side-effect execution.
- Mapped Claude Code host-tool requests into the existing V3 local tool request, approval, pending-change, and command lifecycle models before host side effects.
- Forced V6 execution metadata to `permission_bridge=harness_local_tool_request_v1`, `execution_mode=agent_sdk_intent_capture_harness_executor`, `permission_bridge_execution=harness_owned_executor`, and `sdk_native_tool_execution_enabled=false`.
- Required SDK side-effect tools to reach Harness approval; SDK allowed-tools/settings cannot pre-approve Bash, Write, Edit, MultiEdit, git/network/env/secret-like operations, or mutation-capable custom tools.
- Denied duplicate native execution after Harness-owned execution by returning an SDK deny result from the callback after the Harness executor completes.
- Terminalized pending V6 tool state on task cancel, including local tool requests, tool approvals, tool calls, pending changes, commands, and bridge tasks.
- Added deterministic smoke and fixture coverage for SDK unavailable, approve write, modified approval, reject bash, revoke pending, approval timeout, bypass attempt, API failure fail-closed, approved shell execution, cancelled execution, and V5 heartbeat upgrade denial.
- Updated Agent Studio to expose separate Claude Code V5 and Claude Code V6 pairing options and status badges.
- Updated Agent Workspace to distinguish Claude Code V5/V6 connection labels, surface Claude V6 local-tool approval pending state with a Run Detail approvals link, and keep template creation copy scoped to `使用此模板` / `Use template`.
- Kept native Claude Code resume, deferred tool resume after process exit, live credential UX, remote-control/web/cloud sessions, MCP/plugins/hooks/subagents/browser/computer-use, and server-side Claude credential handling out of V6.

## External Reference Evidence

Official Claude Code docs checked on 2026-06-05:

- `https://code.claude.com/docs/llms.txt`
- `https://code.claude.com/docs/en/agent-sdk/permissions.md`
- `https://code.claude.com/docs/en/agent-sdk/user-input.md`
- `https://code.claude.com/docs/en/agent-sdk/sessions.md`
- `https://code.claude.com/docs/en/agent-sdk/python.md`
- `https://code.claude.com/docs/en/cli-reference.md`

Key planning facts:

- Agent SDK permission evaluation falls through to `canUseTool` when hooks, deny rules, permission mode, and allow rules do not resolve a tool request.
- `canUseTool` pauses execution for tool permission requests and `AskUserQuestion` until the application returns allow or deny.
- The callback can allow with original/modified input or deny with a message.
- SDK docs describe `defer` for process-exit-and-resume cases, but V6 defers that path to V7.

## Review Gate

Planning review completed before implementation:

- Architecture/protocol reviewer: initial `PASS`; final re-review `PASS`.
- Security/test reviewer: initial `REVISE/BLOCK`; final re-review `PASS`.

Planning blockers fixed before implementation:

- SDK allow-rule bypass was made explicitly forbidden and covered by negative fixtures.
- API/decision/callback/SDK/runner fail-closed cases were required.
- Modified approval was tightened to require execution-level proof that original requested path/content/command remains untouched.
- Adversarial fake SDK smoke and chmod verification were added to the plan.

Implementation review completed after code changes:

- Architecture review: `CLEAR`.
- Code/security review: `APPROVE`.

V1-V6 cross-review completed after the implementation closeout:

- Architecture/protocol reviewer: `CLEAR`; API/DB authority, scoped entitlement, V5/V6 upgrade controls, approval path, and cancellation/revoke fail-closed behavior remain coherent across V1-V6.
- Test reviewer: initial `WATCH`; resolved by adding exact V6 deterministic smoke scenarios for `claude-approve-write`, `claude-reject-bash`, `claude-revoke-pending`, `claude-approval-timeout`, `claude-bypass-attempt`, and `claude-api-failure-fail-closed`.
- Design reviewer: initial `WATCH`; resolved by adding Workspace Claude V5/V6 selector labels, Claude V6 local-tool approval pending text plus approvals link, and template-scoped `Use template` copy.
- Code/security reviewer: no blocking findings.

Security-critical fixes already applied before final review:

- V5 Claude connections cannot self-upgrade to V6 through heartbeat capability reports.
- V6 enablement requires scoped pairing entitlement and capability normalization together.
- Fake SDK mode is only reachable with explicit env and fixture activation, not by accidental fallback.
- Modified approval now updates the executable input hash, requires refreshed pending-change preview evidence for `write_file` and `apply_patch`, and fail-closes stale original preview results.
- Cancelled or revoked paths fail closed and return explicit non-executable decisions to the bridge.

## Validation Evidence

- Planning architecture/protocol reviewer final verdict: `PASS`.
- Planning security/test reviewer final verdict: `PASS`.
- Implementation architecture reviewer final verdict: `CLEAR`.
- Implementation code/security reviewer final verdict: `APPROVE`.
- `python3 -m py_compile scripts/smoke-test-local-agent-v6.py services/api-server/app/cli/hao/main.py services/api-server/app/api/agents/agent_local.py services/api-server/app/api/tasks.py services/api-server/tests/test_local_agents.py services/api-server/tests/test_hao_cli.py` passed.
- `cd services/api-server && .venv/bin/python -m pytest tests/test_local_agents.py -q` -> `46 passed`.
- `cd services/api-server && .venv/bin/python -m pytest tests/test_hao_cli.py -q -k "claude and (bridge or permission or fake_sdk or sdk)"` -> `13 passed, 37 deselected`.
- `cd services/api-server && .venv/bin/python -m pytest tests/test_local_agents.py tests/test_hao_cli.py tests/test_hao_cli_v2.py tests/test_tool_approvals.py tests/test_tool_runner.py -q` -> `236 passed`.
- `cd services/api-server && .venv/bin/python -m ruff check app/api/agents/agent_local.py app/api/tasks.py app/cli/hao/api_client.py app/cli/hao/main.py tests/test_local_agents.py tests/test_hao_cli.py tests/test_hao_cli_v2.py tests/test_tool_approvals.py tests/test_tool_runner.py` passed.
- `python3 scripts/smoke-test-local-agent-v6.py --scenario claude-sdk-unavailable` passed.
- `python3 scripts/smoke-test-local-agent-v6.py --scenario claude-approve-write` passed.
- `python3 scripts/smoke-test-local-agent-v6.py --scenario claude-reject-bash` passed.
- `python3 scripts/smoke-test-local-agent-v6.py --scenario claude-revoke-pending` passed.
- `python3 scripts/smoke-test-local-agent-v6.py --scenario claude-approval-timeout` passed.
- `python3 scripts/smoke-test-local-agent-v6.py --scenario claude-bypass-attempt` passed.
- `python3 scripts/smoke-test-local-agent-v6.py --scenario claude-api-failure-fail-closed` passed.
- `python3 scripts/smoke-test-local-agent-v6.py --scenario claude-permission-bridge-approved` passed.
- `python3 scripts/smoke-test-local-agent-v6.py --scenario claude-permission-bridge-cancel` passed.
- `python3 scripts/smoke-test-local-agent-v6.py --scenario claude-v5-heartbeat-upgrade-denied` passed.
- `python3 scripts/smoke-test-local-agent-v6.py --scenario claude-modified-approval` passed.
- 2026-06-06 follow-up for `docs/test-suite-v1-v6-local-agent.md`: fixed the smoke runner contract so `python3 scripts/smoke-test-local-agent-v6.py --all` runs every deterministic V6 scenario instead of failing argument parsing; the aggregate command passed all 11 scenarios.
- 2026-06-06 follow-up verification: `python3 -m py_compile scripts/smoke-test-local-agent-v6.py`; `cd services/api-server && .venv/bin/python -m pytest tests/test_local_agents.py tests/test_tool_approvals.py -q` -> `51 passed`; `cd services/api-server && .venv/bin/python -m pytest tests/test_hao_cli.py tests/test_hao_cli_v2.py -q` -> `174 passed`; targeted Ruff passed; `cd apps/agent-console && npm test -- AgentListPage.studio.test.tsx AgentWorkspacePage.team-launch.test.tsx` -> `15 passed`; frontend lint/build, docs validation, and diff check passed.
- `cd services/api-server && .venv/bin/python -m pytest tests/test_local_agents.py -q -k "v6 or local_agent_v3_approval_after_ttl or revoke_terminalizes or deny"` -> `12 passed, 34 deselected`.
- `cd services/api-server && .venv/bin/python -m pytest tests/test_hao_cli.py -q -k "permission_bridge or fake_sdk or bridge_v6"` -> `11 passed, 39 deselected`.
- `cd services/api-server && .venv/bin/python -m ruff check app/api/agents/agent_local.py app/api/tasks.py app/cli/hao/main.py tests/test_local_agents.py tests/test_hao_cli.py` passed.
- `cd apps/agent-console && npm test -- AgentListPage.studio.test.tsx AgentWorkspacePage.team-launch.test.tsx ChatSurface.shell.test.tsx` -> `23 passed`.
- `cd apps/agent-console && npm run lint -- --pretty false` passed.
- `python3 scripts/validate-docs.py` passed.
- `git diff --check` passed.

## Current Status

- Branch: `feature/local-agent-claude-code-permission-bridge-v6`
- Status: implemented, V1-V6 cross-reviewed, optimized, and verified locally
- Next step: commit and push this branch without staging unrelated `omx_wiki/session-log-2026-06-04-*` files.
