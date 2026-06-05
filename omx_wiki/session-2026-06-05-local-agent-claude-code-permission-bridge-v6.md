# Local Agent Claude Code Permission Bridge V6

Category: `session-log`

Tags: `local-agent`, `claude-code`, `permission-bridge`, `planning`, `tool-safety`

## Summary

Local Agent Claude Code Permission Bridge V6 is planned and reviewed on branch `feature/local-agent-claude-code-permission-bridge-v6`.

V6 is not implemented yet. This session only records the required plan入库 and two-agent review gate. The planned V6 slice is a Claude Code Agent SDK permission bridge: Claude Code can request local host tools, but side-effect intent must route through Harness V3 `LocalAgentToolRequest`, `ToolApproval`, `ToolCall`, `AgentEvent`, pending-change, and command lifecycle authority before any local execution.

## Planning Documents

- `.omx/plans/prd-local-agent-claude-code-permission-bridge-v6.md`
- `.omx/plans/test-spec-local-agent-claude-code-permission-bridge-v6.md`

## Planned Scope

- Add an explicit V6 capability gate for Claude Code permission bridge mode.
- Preserve V5 Claude Code no-tools behavior for connections without V6 permission bridge support.
- Prefer official Claude Agent SDK `can_use_tool` / `canUseTool` callback as the primary permission integration path.
- Map Claude Code tool requests into V3 local tool requests before host side effects.
- Require SDK side-effect tools to reach Harness approval; SDK allowed-tools/settings cannot pre-approve Bash, Write, Edit, MultiEdit, git/network/env/secret-like operations, or mutation-capable custom tools.
- Fail closed on API request failure, decision polling failure, callback exception, SDK crash, runner death, or crash after approval before result.
- Prove modified approval at execution level: only server-approved modified input may cause side effects.
- Keep native Claude Code resume, deferred tool resume after process exit, live credential UX, remote-control/web/cloud sessions, MCP/plugins/hooks/subagents/browser/computer-use, and server-side Claude credential handling out of V6.

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

Two independent plan reviews were run before implementation:

- Architecture/protocol reviewer: initial `PASS`; final re-review `PASS`.
- Security/test reviewer: initial `REVISE/BLOCK`; final re-review `PASS`.

Security/test blockers fixed before final PASS:

- SDK allow-rule bypass is now explicitly forbidden and covered by negative fixtures.
- API/decision/callback/SDK/runner fail-closed cases are now required.
- Modified approval now requires execution-level proof that original requested path/content/command remains untouched.
- Adversarial fake SDK smoke and chmod verification were added to the required plan.

## Current Status

- Branch: `feature/local-agent-claude-code-permission-bridge-v6`
- Status: planning complete and reviewed
- Implementation status: not started
- Next step: implement V6 on this branch only after the plan commit is pushed.

## Validation Evidence

- Architecture/protocol planning reviewer final verdict: `PASS`.
- Security/test planning reviewer final verdict: `PASS`.
- Planned closeout validation:
  - `python3 scripts/validate-docs.py`
  - `git diff --check`
