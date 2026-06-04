# Local Agent Claude Code Adapter V5

Category: `session-log`

Tags: `local-agent`, `claude-code`, `bridge`, `adapter`, `planning`, `tool-safety`

## Summary

Local Agent Claude Code Adapter V5 planning is complete and reviewed on branch `feature/local-agent-claude-code-adapter-v5`.

V5 is planned as the second non-hao local-agent adapter after Codex. The adapter will use the existing Harness local-agent bridge and Workspace ChatSurface path: pairing, registration, heartbeat, task pull/ack, assistant delta/done/error projection, conversation binding, pending/offline state, Run/Event/Message ownership, and audit authority stay API/DB-owned.

The accepted V5 boundary is intentionally conservative. Claude Code is planned as an assistant-response adapter only: no host tools, no native resume, no MCP/plugin/hook/subagent/browser/remote-control surface, no cloud-Agent path, and no direct bridge-owned message writes.

## Planning Documents

- `.omx/plans/prd-local-agent-claude-code-adapter-v5.md`
- `.omx/plans/test-spec-local-agent-claude-code-adapter-v5.md`

## Planned Scope

- Enable `adapter_kind=claude_code` in the existing local-agent adapter registry.
- Keep `fake`, `hao`, and `codex` behavior unchanged.
- Require adapter-scoped pairing validation before token consumption.
- Probe Claude Code CLI availability before registration.
- Launch Claude Code through a constrained headless command shape:
  - `claude --bare -p --output-format stream-json --verbose --include-partial-messages --no-session-persistence --permission-mode default --tools ""`
- Pass Harness prompt content through stdin or a mode `0600` temp input file, never argv.
- Use adapter-owned temp `HOME`, temp `CLAUDE_CONFIG_DIR`, private temp cwd, and no paired workspace file exposure in V5 subprocesses.
- Set `CLAUDE_CODE_SKIP_PROMPT_HISTORY=1`, `CLAUDE_CODE_DISABLE_AUTO_MEMORY=1`, and `CLAUDE_AGENT_SDK_DISABLE_BUILTIN_AGENTS=1`.
- Do not use `--settings`, `--setting-sources`, `apiKeyHelper`, `--mcp-config`, plugin flags, agents flags, native resume flags, or permission bypass modes in the required V5 path.
- Normalize server capabilities to `supports_resume=false`, `supports_cancel=false`, `host_tools_authorized=false`, and `resume_mode=context_replay_new_session`.
- Require `system/init` or equivalent safety metadata proving empty tools/MCP/plugins/hooks/custom-agent surfaces before projecting assistant success.
- Treat Claude Code session ids as redacted advisory metadata only.
- Keep deterministic smoke mocked/fixture-based; live Claude credentials remain optional manual smoke only.

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

## Validation Evidence

- Plan consistency check for dangerous/ambiguous CLI terms was performed with `rg` across the V5 PRD and test spec.
- Architecture/protocol reviewer returned `PASS` after final updates.
- Security/test reviewer returned `PASS` after final updates.
- `python3 scripts/validate-docs.py` is the required docs validation before commit.
- `git diff --check` is the required whitespace validation before commit.

## Current Status

- Branch: `feature/local-agent-claude-code-adapter-v5`
- Status: plan reviewed, not implemented
- Next step: implement the V5 PRD/test spec, then run implementation code review before commit/push of implementation.
