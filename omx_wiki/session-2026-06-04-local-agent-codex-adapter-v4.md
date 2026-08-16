# Local Agent Codex Adapter V4

Category: `session-log`

Tags: `local-agent`, `codex`, `bridge`, `adapter`, `tool-safety`

## Summary

Local Agent Codex Adapter V4 is implemented and verified on branch `feature/local-agent-codex-adapter-v4`.

V4 enables Codex CLI as a constrained local-agent adapter inside the existing Harness local-agent bridge and Workspace ChatSurface flow. The implementation preserves the V3 host-tool safety boundary: Codex can pair, register, heartbeat, pull tasks, ack, run a constrained assistant-response subprocess, and project assistant delta/done/error into Harness-owned Run/Event/Message state, but it cannot report host-side tool results or native resume.

Claude Code remains disabled future scope.

## Planning Documents

- `.omx/plans/prd-local-agent-codex-adapter-v4.md`
- `.omx/plans/test-spec-local-agent-codex-adapter-v4.md`

## Implemented Scope

- `adapter_kind=codex` is now supported by the backend and hao bridge CLI.
- `adapter_kind=claude_code` remains disabled.
- Agent Studio exposes Codex as a V4-enabled local Agent adapter and generates adapter-scoped pairing requests.
- Backend default pairing scope includes Codex, and explicit `scope.adapters` is validated before token consumption.
- Codex capabilities are server-normalized to `supports_resume=false`, `supports_cancel=false`, `host_tools_authorized=false`, and `resume_mode=context_replay_new_session`.
- `hao bridge pair --adapter codex` probes Codex CLI support before registration.
- `hao bridge run --adapter codex` launches `codex exec` with stdin prompt input, JSONL output, `--output-last-message`, `-C <workspace>`, and `--sandbox read-only`.
- Dangerous Codex args such as `--dangerously-bypass-approvals-and-sandbox`, `danger-full-access`, and `--last` are forbidden.
- Runtime Codex subprocess env is allowlisted, strips provider keys/tokens/proxies, and uses isolated temp `HOME` and `CODEX_HOME`.
- Raw device token is stored only in `bridge.device-token`; raw Codex workspace root is stored only in `bridge.workspace-root`; `bridge.json` stores refs and hashes only.
- Codex workspace execution compares the local sidecar root hash with the server task `workspace_identity_hash` before spawning the subprocess.
- `hao bridge run --adapter codex --cwd` cannot rewrite an already paired Codex connection to a different workspace identity.
- Codex `adapter_started`, `assistant_delta`, `assistant_done`, and `assistant_error` events project through existing Harness-owned Run/Event/Message state.
- Codex legacy `tool_result` events are rejected before bridge receipt or `ToolCall` creation.

## Review Gate

Planning review completed before implementation:

- Gauss architecture review: `PASS`.
- Meitner security/test review: `PASS`.

Implementation review:

- Architecture review initially returned `BLOCK` for mutable local workspace identity.
- The architecture BLOCK was fixed by requiring server task `workspace_identity_hash` to match the local Codex sidecar root hash before subprocess spawn, plus regression coverage for sidecar mismatch and `--cwd` rewrite rejection.
- Final architecture review returned `WATCH` with no blockers. The WATCH noted native-resume wording in the test spec and pair-time workspace identity trust-boundary wording.
- The native-resume test spec is now aligned to V4: Codex always reports `supports_resume=false` and uses `resume_mode=context_replay_new_session`; native Codex resume remains future scope.
- Final code/security review returned `APPROVE` after the stale `omx_wiki/log.md` EOF whitespace blocker was fixed and `git diff --check` passed.

## Validation Evidence

- `cd services/api-server && .venv/bin/python -m pytest tests/test_local_agents.py -q` -> `34 passed`.
- `cd services/api-server && .venv/bin/python -m pytest tests/test_hao_cli.py tests/test_hao_cli_v2.py -q -k "bridge or codex or adapter or pending_state_file"` -> `23 passed, 130 deselected`.
- `cd services/api-server && .venv/bin/python -m pytest tests/test_tool_approvals.py tests/test_tool_runner.py -q` -> `17 passed`.
- `cd services/api-server && .venv/bin/python -m py_compile app/api/agents/agent_local.py app/api/schemas.py app/events/event_types.py app/cli/hao/api_client.py app/cli/hao/main.py tests/test_local_agents.py tests/test_hao_cli.py tests/test_hao_cli_v2.py` -> passed.
- `cd services/api-server && .venv/bin/python -m ruff check app/api/agents/agent_local.py app/api/schemas.py app/events/event_types.py app/cli/hao tests/test_local_agents.py tests/test_hao_cli.py tests/test_hao_cli_v2.py` -> passed.
- `python3 scripts/smoke-test-local-agent-v4.py --scenario codex-unavailable` -> passed.
- `python3 scripts/smoke-test-local-agent-v4.py --scenario codex-readonly-reply` -> passed.
- `python3 scripts/smoke-test-local-agent-v4.py --scenario codex-resume-mode` -> passed.
- `python3 scripts/smoke-test-local-agent-v4.py --scenario codex-side-effect-rejected` -> passed.
- `cd apps/agent-console && npm test -- AgentListPage.studio.test.tsx AgentWorkspacePage.team-launch.test.tsx ChatSurface.shell.test.tsx` -> `22 passed`.
- `cd apps/agent-console && npm run lint -- --pretty false` -> passed.
- `python3 scripts/validate-docs.py` -> rerun after docs closeout.
- `git diff --check` -> rerun after docs closeout.

## Current Status

- Branch: `feature/local-agent-codex-adapter-v4`
- Status: implemented, reviewed, verified
- Remaining watch: real Codex CLI auth under isolated `HOME` / `CODEX_HOME` may require a future explicit credential/sidecar design; V4 keeps isolation as the safer default.
