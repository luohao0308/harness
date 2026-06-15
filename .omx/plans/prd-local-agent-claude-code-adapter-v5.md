# PRD: 本地 Agent Claude Code Adapter V5

## Summary

V5 在 V1 pairing/daemon、V2 Workspace ChatSurface、V3 host tool safety、V4 Codex adapter 的基础上，接入第二个非 hao 的本地 Agent：Claude Code。

本版目标不是把 Claude Code 变成新的聊天旁路，也不是让 Claude Code 绕过 Harness 权限链。`adapter_kind=claude_code` 必须作为现有 local-agent bridge protocol 的一个实现：配对、注册、心跳、任务拉取、ack、assistant delta/done/error 上报、会话绑定、pending/offline projection 继续由 API/DB 统一管理。

V5 的安全边界沿用 V4 的保守策略：Claude Code 可以作为受限 assistant-response adapter 接入 Workspace，但不能默认写文件、执行 shell mutation、git mutation、network、env/secret read，也不能把 Claude Code 内部工具事件伪装成 Harness-authorized `ToolCall(SUCCESS)`。官方 Claude Code 当前支持 `-p/--print`、stdin 非交互输入、`--output-format stream-json`、`--resume/-r`、`--permission-mode`、`--permission-prompt-tool`、`--tools`、`--settings`、`--bare` 等能力；V5 只验收能在 Harness 安全边界内确定执行的子集，V6 再评估基于 MCP permission prompt / Agent SDK callback 的 host tool 授权闭环。

## External Reference Notes

- Official Claude Code CLI reference: `https://code.claude.com/docs/en/cli-reference`
- Official headless/programmatic usage: `https://code.claude.com/docs/en/headless`
- Official permission modes: `https://code.claude.com/docs/en/permission-modes`
- Official security guidance: `https://code.claude.com/docs/en/security`

Key reference facts used by this plan:

- `claude -p` runs non-interactively and can emit `json` or `stream-json`.
- Non-interactive mode reads stdin, so prompt text does not need to be passed in argv.
- `--include-partial-messages` requires print mode plus `stream-json`.
- `--bare` is documented for one-off scripted calls.
- `--tools ""` disables all built-in tools.
- `--no-session-persistence` disables session persistence in print mode so sessions are not saved to disk and cannot be resumed.
- `CLAUDE_CODE_SKIP_PROMPT_HISTORY=1` skips prompt history and session transcript writes.
- `CLAUDE_CONFIG_DIR` can isolate Claude Code settings, credentials, session history, and plugins under an adapter-owned temp directory.
- `bypassPermissions` / `--dangerously-skip-permissions` is unsafe outside isolated environments and is forbidden in V5.
- Claude Code uses strict read-only permissions by default and asks before edits/commands; V5 still deny-lists side-effect tools because a non-interactive bridge cannot rely on a human prompt.

## Requirements Summary

- 后端把 `claude_code` 从 disabled future adapter 升级为 V5 supported adapter，同时保留 `fake`、`hao`、`codex`。
- Agent Studio 的 local Agent 向导显示 Claude Code 为 V5 enabled，不再是 future disabled；新建云端 Agent 仍不存在。
- `hao bridge pair --adapter claude_code` 和 `hao bridge run --adapter claude_code` 可注册、心跳、拉取任务并投影 assistant output。
- Claude Code executable probe 在注册前运行；缺少 `claude` 或关键 CLI flags 时 fail closed，不消费 pair token、不创建 connection、不启动 daemon。
- V5 Claude Code subprocess 必须使用非交互形态，例如 `claude --bare -p --output-format stream-json --verbose --include-partial-messages --no-session-persistence --permission-mode default --tools ""`，并通过 stdin 或 mode `0600` temp file 传递 Harness prompt，不能把 prompt 放进 argv。
- V5 默认不启用 Claude Code host tools。任何 `Bash`、`Read`、`Edit`、`MultiEdit`、`Write`、`WebFetch`、`WebSearch`、MCP、plugin、hook、subagent 等能力必须通过 `--tools ""`、`--bare`、`--no-session-persistence`、隔离 `HOME` / `CLAUDE_CONFIG_DIR`、不传 `--settings` / `--setting-sources`，以及无 explicit `--mcp-config` / `--plugin-*` / `--agents` flags 禁止或保持未授权。
- V5 不使用 production native Claude resume；即使输出 `session_id`，也只能作为 redacted advisory metadata。服务端能力固定为 `supports_resume=false` 和 `resume_mode=context_replay_new_session`。
- Claude Code auth 只允许本地-only credential source 参与 subprocess；API、event、receipt、bridge.json、logs 不得保存 raw `ANTHROPIC_API_KEY`、OAuth token、helper output、home path、settings raw JSON 或 provider credential。
- Workspace 使用现有 local connection selector、binding、ChatSurface 和 pending/offline projection；不新增 Claude Code 独立 UI。
- V5 smoke 使用 mocked Claude subprocess 或 deterministic fixture；真实 Claude Code auth smoke 为 optional，不作为 required gate。

## Evidence From Current Code

- `services/api-server/app/api/agents/agent_local.py` 当前 V4 支持 `fake`、`hao`、`codex`，并把 `claude_code` 放在 disabled set。
- `_normalized_capabilities()` 已对 Codex 做 server-owned capability normalization，可复用为 Claude Code 的 deny-by-default normalization。
- local send 已按 adapter kind 创建 `AgentMessage`、Workspace Run、`LocalAgentBridgeTask`，并把 adapter metadata 放入 task payload。
- bridge event ingest 已通过 receipt 幂等写回 `AgentEvent` / `AgentMessage` / `Task`，并拒绝无授权 side-effect `tool_result`。
- `services/api-server/app/cli/hao/main.py` 已有 Codex adapter 的 probe、command builder、stdout parser、workspace sidecar、safe env、terminal event id 和 dispatch 模式。
- V4 已把 raw device token 放入 `bridge.device-token`，raw workspace root 放入 `bridge.workspace-root`，`bridge.json` 只保存 safe refs / hashes。
- Agent Studio adapter list 已包含 Claude Code future card，可升级为 V5 enabled card。

## Goals

1. Adapter enablement and pairing
   - `LOCAL_AGENT_SUPPORTED_ADAPTERS` includes `claude_code`。
   - `LOCAL_AGENT_DISABLED_ADAPTERS` no longer includes `claude_code`。
   - default pair adapter scope becomes `["fake", "hao", "codex", "claude_code"]` unless explicitly narrowed。
   - explicit `scope.adapters` must be validated before token consumption; a Codex-only token cannot register Claude Code and remains usable for Codex。
   - `claude_code` registration requires valid pair token, pair code, org/user/agent scope, device ownership, protocol version, and executable probe result。

2. Capability normalization
   - Server-normalized Claude Code capabilities:

```json
{
  "adapter_kind": "claude_code",
  "supports_streaming": true,
  "supports_resume": false,
  "supports_cancel": false,
  "enabled_in_v5": true,
  "host_tools_authorized": false,
  "resume_mode": "context_replay_new_session",
  "execution_mode": "headless_bare_no_session_no_tools"
}
```

   - Bridge self-report cannot enable host write, shell, git, network, env/secret read, MCP, plugin, hook, subagent, browser, remote-control, or native resume.
   - `risk_capabilities_json` defaults to empty or `workspace_read_denied`; V5 cannot advertise host side effects.

3. Claude Code bridge adapter
   - Add parser choices for `hao bridge pair/run --adapter claude_code`。
   - Add Claude Code probe:
     - `shutil.which("claude")`
     - `claude --version`
     - `claude --help` / `claude -p --help` or equivalent help checks
     - detect support for `--bare`, `-p`, `--output-format stream-json`, `--include-partial-messages`, `--no-session-persistence`, `--permission-mode`, and `--tools`
   - Probe must not require provider credentials and must run with sanitized env.
   - Pair fails before registration when executable or required flags are unavailable.
   - `hao bridge run` dispatches Claude Code tasks without running pending host-tool resume logic.

4. Command builder and subprocess boundary
   - Allowed command shape:

```text
claude --bare -p --output-format stream-json --verbose --include-partial-messages --no-session-persistence --permission-mode default --tools ""
```

   - Prompt transport uses stdin text, never argv prompt text.
   - Subprocess `cwd` defaults to an adapter-owned private temp directory, not the paired workspace root. The paired workspace hash is still validated before execution, but V5 does not expose raw workspace files to Claude Code.
   - Subprocess env must set adapter-owned temporary `HOME` and `CLAUDE_CONFIG_DIR`, plus `CLAUDE_CODE_SKIP_PROMPT_HISTORY=1`, `CLAUDE_CODE_DISABLE_AUTO_MEMORY=1`, and `CLAUDE_AGENT_SDK_DISABLE_BUILTIN_AGENTS=1`.
   - `--bare` is mandatory. If the CLI cannot prove bare mode is available, V5 reports Claude Code unavailable.
   - `--no-session-persistence` is mandatory. If the CLI cannot prove this flag is available, V5 reports Claude Code unavailable.
   - `--setting-sources` is not used in the V5 required path. V5 relies on `--bare` plus isolated temp `HOME` / `CLAUDE_CONFIG_DIR` and fails closed if `system/init` reports loaded settings/plugins/MCP/tools.
   - `--tools ""` must disable all built-in tools, including at minimum:
     - `Read`
     - `Bash`
     - `Edit`
     - `MultiEdit`
     - `Write`
     - `WebFetch`
     - `WebSearch`
     - `NotebookEdit`
     - MCP tools, plugins, hooks, subagents, browser/remote-control helpers.
   - If Claude Code cannot accept prompt through stdin or private temp input without argv leakage, fail closed.
   - Forbidden command properties:
     - `--dangerously-skip-permissions`
     - `--permission-mode bypassPermissions`
     - `--permission-mode acceptEdits`
     - `--permission-mode auto`
     - `--permission-mode dontAsk`
     - `--continue` / `-c`
     - `--resume` / `-r`
     - `--add-dir`
     - `--remote`
     - `--remote-control`
     - `--mcp-config` unless a future Harness permission bridge owns it
     - `--plugin-dir`, `--plugin-url`, `--agents`
     - `--allowedTools`
     - `--disallowedTools` as the primary no-tool mechanism
     - `--settings` in V5 required path
     - `--include-hook-events`
     - raw prompt text in argv
     - raw token, API key, helper output, bridge device credential, or workspace root in argv
   - `system/init` stream events are part of the safety contract. If they report any available tools, MCP servers, loaded plugins, hook activity, or custom agent/subagent surface, the bridge must emit `assistant_error` and not project assistant success.

5. Authentication and credential handling
   - V5 does not upload Claude credentials to API.
   - Required deterministic tests use a mocked Claude subprocess and do not require credentials.
   - V5 defers auth-helper and generated-settings support. Required implementation must not use `--settings` or `apiKeyHelper`.
   - Optional live manual smoke may support one local-only credential mode: an explicitly allowlisted `ANTHROPIC_API_KEY` env value copied only into the subprocess for that run and never persisted.
   - `bridge.json` may store only `claude_auth_mode`, local credential source hash/ref, and auth readiness status; it must not store helper output, API key, OAuth token, raw home path, or generated stdin payload.
   - Bare mode skips OAuth and keychain reads. V5 must not set or pass `CLAUDE_CODE_OAUTH_TOKEN`, `CLAUDE_CODE_OAUTH_REFRESH_TOKEN`, or home/keychain-derived credential paths.
   - If auth is missing, subprocess returns `assistant_error` / unavailable and never produces successful assistant output.

6. Output parsing and event projection
   - Parse `stream-json` line-by-line.
   - Require `system/init` or equivalent initial metadata when using stream-json. Final-output fallback may produce `assistant_done` only after a valid empty-tool/config safety proof has already been accepted; otherwise it fails closed.
   - Validate `system/init` safety metadata: no tools, no MCP servers, no loaded plugins, no hooks, no custom agents/subagents, no persisted session path.
   - Map text deltas to `assistant_delta` when present.
   - Map final result / assistant message / structured output to `assistant_done`.
   - Capture `session_id` only as redacted advisory metadata.
   - Unknown system/plugin/retry/hook events are ignored or recorded as bounded redacted observations only when they do not indicate a loaded capability surface; any event that indicates tools, MCP, plugins, hooks, channels, browser helpers, or custom agents/subagents are loaded must fail closed and cannot create `ToolCall(SUCCESS)`.
   - Non-zero exit, timeout, auth failure, missing executable, malformed output without fallback, empty answer, unsafe event, revoked connection, workspace hash mismatch, or terminal task conflict emits `assistant_error`.

7. Resume semantics
   - V5 always uses Harness-owned conversation context replay plus a fresh Claude Code external session.
   - Native Claude Code `--resume`, `--continue`, `--session-id`, background sessions, remote-control, and web sessions are future scope.
   - `LocalAgentConversationBinding.resume_mode` returns `context_replay_new_session` for Claude Code.
   - UI must show a context replay warning rather than native resume badge.

8. Workspace anchoring and privacy
   - Reuse V4 workspace identity sidecar approach.
   - Server task payload includes `workspace_identity_hash`; bridge recomputes local raw workspace root sidecar hash before subprocess spawn.
   - Missing, unreadable, or mismatched workspace sidecar fails closed.
   - Claude Code subprocess cwd stays in a private temp directory for V5; it must not derive cwd from redacted API `workspace_root` or daemon process cwd.
   - `bridge.json`, API events, receipts, and logs cannot contain raw cwd, prompts, stdout/stderr beyond cap, raw stdin input, raw tokens, or full home paths.

9. Frontend
   - Agent Studio local adapter card:
     - Claude Code badge `V5 启用`
     - shows installed/unavailable
     - shows `host tools disabled`
     - shows `context replay`
     - shows optional auth unavailable warning
   - Pairing command includes `--adapter claude_code`.
   - Workspace connection selector shows Claude Code connections with same pending/offline/reconnect states.
   - ChatSurface/Workspace metadata shows `adapter_kind=claude_code` and resume warning.
   - Permission warning appears when a user asks for write/shell/git/network behavior in Claude Code local mode.

## Non-Goals

- V5 不开放 Claude Code host writes、apply_patch、shell mutation、git mutation、network、package install、env/secret read。
- V5 不实现 Claude Code native resume / continue / background sessions / remote-control。
- V5 不实现 MCP permission-prompt tool 或 Agent SDK callback 作为 Harness approval bridge；这是 V6 候选范围。
- V5 不把 Claude Code plugins/hooks/subagents/MCP servers 自动纳入 Harness capability registry。
- V5 不要求真实 Claude Code credential smoke 作为 required gate。
- V5 不承诺电脑关机后继续执行，只延续 daemon alive、offline/pending/reconnect 语义。

## RALPLAN-DR Summary

### Principles

- API/DB owns truth; local bridge is untrusted executor.
- Adapter enablement must preserve V3 host-tool authorization invariants.
- Use official Claude Code headless primitives, but only the deterministic safe subset.
- Credentials stay local-only and sidecar-only; API never receives raw Claude secrets.
- UI stays unified inside Agent Studio + Workspace ChatSurface.

### Decision Drivers

- Security: no unauthorized host side effects or secret exposure.
- Product continuity: Claude Code appears as a local Agent in the existing conversation surface.
- Verifiability: deterministic tests and smoke must not depend on paid/provider credentials.

### Viable Options

Option A: CLI assistant-response adapter, stdin prompt input, bare mode, no session persistence, `--tools ""`, private temp cwd/config.

- Pros: small diff, mirrors V4 Codex, testable without credentials, preserves V3 safety.
- Cons: less powerful than interactive Claude Code; no native resume or file edits.

Option B: CLI adapter with `--permission-prompt-tool` routed to Harness approval.

- Pros: could unlock real Claude Code host tools through Harness approval.
- Cons: larger protocol surface, MCP permission tool complexity, higher risk for V5.

Option C: Agent SDK adapter instead of CLI.

- Pros: richer callback/message objects and more direct programmatic permission controls.
- Cons: new dependency/runtime surface and a bigger adapter abstraction change.

Chosen for V5: Option A. Options B/C are deferred to V6 after the basic Claude Code adapter is integrated and reviewed.

## ADR

### Decision

Implement Claude Code as a V5 local-agent adapter using the existing bridge protocol, headless CLI print mode, stdin input, no built-in tools, no Claude Code session persistence, isolated temp config state, safe command generation, server-normalized capabilities, and forced context replay.

### Drivers

- The user’s roadmap explicitly wants Claude Code after Codex.
- Existing V4 Codex shape already proves a conservative non-hao adapter path.
- Official Claude Code exposes enough headless/streaming flags to support assistant projection without adopting a new SDK in V5.

### Alternatives Considered

- Enable native Claude resume immediately: rejected because session ownership, workspace identity, credential source, and permission-mode continuity need separate proof.
- Enable host tools through Claude Code permission prompts: rejected for V5 because it requires MCP/SDK approval bridge design and security review.
- Use only mocked Claude Code with no real adapter path: rejected because V5 should produce a concrete bridge contract, not just planning scaffolding.

### Why Chosen

The assistant-response CLI adapter gives the product-visible integration the user asked for while keeping the same Harness authority boundaries that V1-V4 established.

### Consequences

- Claude Code will appear in the unified local Agent UI.
- V5 real usefulness is intentionally narrower than interactive Claude Code.
- V6 should focus on native resume and permission-bridge/tool authorization if the V5 adapter proves stable.

### Follow-Ups

- V6: evaluate `--permission-prompt-tool` or Agent SDK permission callbacks for Harness-owned local host tool approval.
- V6: evaluate native Claude Code resume only with workspace identity, user/device binding, and permission-mode continuity.
- V6: define live credential UX using local sidecars or Secret Vault-backed local helper without exposing raw secrets to API.

## Implementation Steps

1. Backend adapter gate
   - Enable `claude_code` in supported adapters.
   - Update default pair adapter scope and pairing command generation.
   - Add backend tests for Claude accepted, adapter-scoped token rejection before consumption, and Codex/fake/hao regressions.

2. Capability normalization and safety guards
   - Add Claude Code normalization branch mirroring Codex but with `enabled_in_v5`.
   - Force `supports_resume=false`, `supports_cancel=false`, `host_tools_authorized=false`.
   - Reject Claude Code local host tool requests and legacy side-effect tool results unless a future V6 authorization path exists.

3. CLI probe and state
   - Add `claude_code` parser choice.
   - Implement probe dataclass, sanitized help/version checks, unavailable failure before register.
   - Store only safe Claude adapter state in `bridge.json`; keep raw device token and workspace root sidecars unchanged.

4. CLI command builder and parser
   - Implement stdin prompt builder, no-tool CLI flags, no-session flags, and Claude temp config isolation.
   - Build safe `claude --bare -p --output-format stream-json --no-session-persistence --permission-mode default --tools "" ...` command.
   - Parse streaming JSON and final output into `assistant_delta` / `assistant_done` / `assistant_error`.
   - Add timeout, non-zero exit, empty output, malformed output and auth unavailable handling.

5. Bridge task dispatch
   - Add `_handle_claude_code_bridge_task()`.
   - Emit stable event ids:
     - `{task_id}:claude_code:started`
     - `{task_id}:claude_code:delta:{n}`
     - `{task_id}:claude_code:done`
     - `{task_id}:claude_code:error`
   - Keep fake/hao/codex behavior unchanged.

6. Frontend
   - Update `LOCAL_AGENT_ADAPTERS` for Claude Code V5 enabled.
   - Show host-tools disabled, auth readiness, context replay, and installed status.
   - Preserve existing ChatSurface local mode with no new nested UI.

7. Smoke and docs
   - Add `scripts/smoke-test-local-agent-v5.py` with deterministic mocked Claude subprocess scenarios.
   - Update wiki/session/progress after implementation.
   - Run targeted backend/CLI/frontend/docs verification before review.

## Acceptance Criteria

- `adapter_kind=claude_code` can pair/register/heartbeat/list/revoke through the same local-agent APIs.
- `hao bridge pair --adapter claude_code` fails before registration when `claude` is unavailable or lacks required flags.
- Workspace can bind/send to a Claude Code connection using existing ChatSurface local mode.
- Claude Code stream output projects into exactly one assistant message through Harness-owned Run/Event/Message state.
- Claude Code side-effect tool reports cannot create authorized `ToolCall(SUCCESS)`.
- Claude Code command builder never generates bypass permissions, edit-accepting/auto/dontAsk permission mode, native resume, workspace add-dir, remote-control, MCP/plugin/subagent flags, built-in tool allowlists, raw prompt argv, raw tokens, or raw workspace root argv.
- Claude Code `system/init` or equivalent metadata proves the actual run has empty tools/MCP/plugins/hooks/custom-agent surfaces; otherwise success projection is forbidden.
- API, bridge state, events, receipts and logs never persist raw Claude credentials or raw stdin input/helper output.
- UI shows Claude Code as V5 enabled with host tools disabled and context replay warning.
- Required smoke and tests pass without real Claude credentials.

## Risks And Mitigations

- Risk: Claude Code CLI output schema may change.
  - Mitigation: parser tolerates unknown records, uses bounded fallback, and fails closed on unparseable terminal output.
- Risk: `--bare` plus missing auth makes live usage unavailable.
  - Mitigation: deterministic acceptance does not require credentials; UI shows auth unavailable; V6 handles credential UX.
- Risk: Claude Code project memory/settings/hooks could run unexpectedly.
  - Mitigation: launch with `--bare`, private temp cwd, isolated temp `HOME` / `CLAUDE_CONFIG_DIR`, no `--add-dir`, `--no-session-persistence`, `--tools ""`, no plugin/MCP/hook flags, and keep paired workspace content out of V5 subprocess reach. Validate `system/init` metadata before success projection.
- Risk: users expect native Claude Code file edits.
  - Mitigation: explicit V5 badge/copy says host tools disabled; V6 tracks permission bridge.
- Risk: adapter drift between V4 Codex and V5 Claude Code.
  - Mitigation: share helper patterns for safe env, sidecar privacy, workspace hash enforcement, and event ids where practical.

## Verification Steps

- Backend:
  - `cd services/api-server && .venv/bin/python -m pytest tests/test_local_agents.py -q`
  - `cd services/api-server && .venv/bin/python -m pytest tests/test_tool_approvals.py tests/test_tool_runner.py -q`
- CLI:
  - `cd services/api-server && .venv/bin/python -m pytest tests/test_hao_cli.py tests/test_hao_cli_v2.py -q -k "bridge or claude or codex or adapter or pending_state_file"`
  - `cd services/api-server && .venv/bin/python -m py_compile app/api/agents/agent_local.py app/api/schemas.py app/events/event_types.py app/cli/hao/api_client.py app/cli/hao/main.py tests/test_local_agents.py tests/test_hao_cli.py tests/test_hao_cli_v2.py`
  - `cd services/api-server && .venv/bin/python -m ruff check app/api/agents/agent_local.py app/api/schemas.py app/events/event_types.py app/cli/hao tests/test_local_agents.py tests/test_hao_cli.py tests/test_hao_cli_v2.py`
- Smoke:
  - `python3 scripts/smoke-test-local-agent-v5.py --scenario claude-unavailable`
  - `python3 scripts/smoke-test-local-agent-v5.py --scenario claude-readonly-reply`
  - `python3 scripts/smoke-test-local-agent-v5.py --scenario claude-resume-mode`
  - `python3 scripts/smoke-test-local-agent-v5.py --scenario claude-side-effect-rejected`
- Frontend:
  - `cd apps/agent-console && npm test -- AgentListPage.studio.test.tsx AgentWorkspacePage.team-launch.test.tsx ChatSurface.shell.test.tsx`
  - `cd apps/agent-console && npm run lint -- --pretty false`
- Docs:
  - `python3 scripts/validate-docs.py`
  - `git diff --check`

## Available-Agent-Types Roster

- `architect`: protocol boundary and resume/credential design review.
- `critic`: adversarial plan review.
- `executor`: implementation across backend/CLI/frontend.
- `test-engineer`: test matrix and deterministic smoke coverage.
- `code-reviewer`: final code/security review.
- `verifier`: closeout evidence validation.

## Follow-Up Staffing Guidance

- `$ralph`: best for single-owner V5 implementation after this plan is approved; use `executor` plus final `code-reviewer` and `verifier`.
- `$team`: useful if implementation is split into backend adapter gate, CLI subprocess adapter, frontend UI, and smoke/tests. Suggested lanes: one executor for backend, one executor for CLI, one executor for frontend, one test-engineer for smoke/regression, then code-reviewer.
- Goal-mode follow-up: `$ultragoal` can track V5-to-V6 readiness; `$performance-goal` is not relevant unless Claude Code startup latency becomes the target; `$autoresearch-goal` is useful only if V6 depends on deeper official SDK/permission research.

## Launch Hints

```bash
omx team --task "Implement .omx/plans/prd-local-agent-claude-code-adapter-v5.md and .omx/plans/test-spec-local-agent-claude-code-adapter-v5.md with backend/CLI/frontend/test lanes"
```

Team verification path:

- Team proves targeted backend, CLI, frontend, smoke, docs, and diff checks.
- Ralph or solo closeout reruns critical gates, performs final code review, updates progress/wiki, commits, and pushes the V5 branch.

## Changelog

- 2026-06-04: Initial V5 PRD入库. Scope chosen as conservative Claude Code headless assistant-response adapter; host tools/native resume deferred to V6.
- 2026-06-04: Updated command contract to official `--bare`, stdin, `--no-session-persistence`, `--permission-mode default`, and `--tools ""` shape after documentation spot-check.
- 2026-06-04: Addressed plan-review BLOCK by adding mandatory empty built-in tool surface, temp `HOME` / `CLAUDE_CONFIG_DIR`, no settings/helper path in V5, no `--setting-sources` ambiguity, and `system/init` safety proof before any final-output fallback.
