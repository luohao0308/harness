# Local Agent Claude Code Adapter V5

Category: `session-log`

Tags: `local-agent`, `claude-code`, `bridge`, `adapter`, `implementation`, `tool-safety`

## Summary

Local Agent Claude Code Adapter V5 is implemented and verified on branch `feature/local-agent-claude-code-adapter-v5`.

V5 is the second non-hao local-agent adapter after Codex. The adapter uses the existing Harness local-agent bridge and Workspace ChatSurface path: pairing, registration, heartbeat, task pull/ack, assistant delta/done/error projection, conversation binding, pending/offline state, Run/Event/Message ownership, and audit authority stay API/DB-owned.

The accepted V5 boundary remains intentionally conservative. Claude Code is an assistant-response adapter only: no host tools, no native resume, no MCP/plugin/hook/subagent/browser/remote-control surface, no cloud-Agent path, and no direct bridge-owned message writes.

## Planning Documents

- `.omx/plans/prd-local-agent-claude-code-adapter-v5.md`
- `.omx/plans/test-spec-local-agent-claude-code-adapter-v5.md`

## Implemented Scope

- Enabled `adapter_kind=claude_code` in the existing local-agent adapter registry.
- Keep `fake`, `hao`, and `codex` behavior unchanged.
- Require adapter-scoped pairing validation before token consumption.
- Probe Claude Code CLI availability before registration.
- Launch Claude Code through a constrained headless command shape:
  - `claude --bare -p --output-format stream-json --verbose --include-partial-messages --no-session-persistence --permission-mode default --tools ""`
- Pass Harness prompt content through stdin, never argv.
- Use adapter-owned temp `HOME`, temp `CLAUDE_CONFIG_DIR`, private temp cwd, and no paired workspace file exposure in V5 subprocesses.
- Set `CLAUDE_CODE_SKIP_PROMPT_HISTORY=1`, `CLAUDE_CODE_DISABLE_AUTO_MEMORY=1`, and `CLAUDE_AGENT_SDK_DISABLE_BUILTIN_AGENTS=1`.
- Do not use `--settings`, `--setting-sources`, `apiKeyHelper`, `--mcp-config`, plugin flags, agents flags, native resume flags, or permission bypass modes in the required V5 path.
- Normalize server capabilities to `supports_resume=false`, `supports_cancel=false`, `host_tools_authorized=false`, and `resume_mode=context_replay_new_session`.
- Require `system/init` or equivalent safety metadata proving empty tools/MCP/plugins/hooks/custom-agent surfaces before projecting assistant success in both the CLI parser and API event ingest path.
- Treat Claude Code session ids as redacted advisory metadata only.
- Keep deterministic smoke fixture-based; live Claude credentials remain optional manual smoke only.

## Review Gate

Planning review completed before implementation:

- Architecture/protocol review: initial `BLOCK`, then `WATCH`, final `PASS`.
- Security/test review: initial `BLOCK`, then `PASS`, final `PASS`.

Important fixes applied during review:

- Mandatory `--bare`.
- Mandatory `--no-session-persistence`.
- Mandatory `--tools ""`.
- `--permission-mode default`; `bypassPermissions`, `acceptEdits`, `auto`, and `dontAsk` are forbidden.
- Isolated temp `HOME` and `CLAUDE_CONFIG_DIR`.
- No `--settings`, `--setting-sources`, or `apiKeyHelper` in V5 required path.
- Hostile config injection tests for `.claude`, `~/.claude`, hooks, MCP, plugins, skills, commands, CLAUDE.md, subagents, workflows, and auto-memory hints.
- Final-output fallback can only write assistant success after a valid empty-tool/config safety proof.
- Claude local transcript and prompt-history persistence must be absent after runs.

Implementation review completed after code changes:

- Code/security review: `APPROVE`, no blocking findings.
- Architecture review: `WATCH`, no blockers.
- The shared residual risk was fixed before commit: API event ingest now requires Claude Code `assistant_done` metadata to include `system_init_safe=true`, `tools_count=0`, and `mcp_servers_count=0`; missing or unsafe proof returns 409 before receipt or assistant message creation.
- A conservative parser hardening was also added so generic non-assistant `message` JSONL records do not project into assistant output.

## Validation Evidence

- Planning architecture/protocol reviewer returned `PASS` after final updates.
- Planning security/test reviewer returned `PASS` after final updates.
- Implementation code/security reviewer returned `APPROVE`.
- Implementation architecture reviewer returned `WATCH` with no blockers; the API-side Claude Code safety-proof guard was added and revalidated.
- `cd services/api-server && .venv/bin/python -m pytest tests/test_local_agents.py -q` -> `36 passed`.
- `cd services/api-server && .venv/bin/python -m pytest tests/test_hao_cli.py tests/test_hao_cli_v2.py -q -k "bridge or claude or codex or adapter or pending_state_file"` -> `32 passed, 130 deselected`.
- `cd services/api-server && .venv/bin/python -m pytest tests/test_tool_approvals.py tests/test_tool_runner.py -q` -> `17 passed`.
- Backend `py_compile` and targeted Ruff passed for local-agent and hao CLI paths.
- V5 deterministic smoke passed for `claude-unavailable`, `claude-readonly-reply`, `claude-resume-mode`, and `claude-side-effect-rejected`.
- `cd apps/agent-console && npm test -- AgentListPage.studio.test.tsx AgentWorkspacePage.team-launch.test.tsx ChatSurface.shell.test.tsx` -> `22 passed`.
- `cd apps/agent-console && npm run lint -- --pretty false` passed.
- `python3 scripts/validate-docs.py` passed.
- `git diff --check` passed.

## Current Status

- Branch: `feature/local-agent-claude-code-adapter-v5`
- Status: implemented and verified
- Next step: commit and push the implementation branch, then use V6 for any future Claude Code permission-bridge or native-resume expansion.
