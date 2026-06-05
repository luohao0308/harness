# PRD: 本地 Agent Claude Code Permission Bridge V6

## Summary

V6 在 V5 Claude Code 只读 assistant-response adapter 的基础上，规划第一版 Claude Code host tool permission bridge。目标是让 Claude Code 能在现有 Workspace ChatSurface 中提出写文件、Edit、Bash、Git 等本地主机操作请求，但执行权仍归 Harness：Claude Code 的工具请求必须先进入 V3 `LocalAgentToolRequest` / `ToolApproval` / `ToolCall` / `AgentEvent` 链路，用户或策略批准后才允许本地 bridge 执行，结果必须绑定同一个 authorized request。

V6 不是原生 Claude session resume 版本，也不是把 Claude Code 的内置权限系统替换成另一个旁路。API/DB 继续是唯一真相；bridge/daemon 仍是不可信执行端；Claude Code 只作为本地意图生成器和工具请求来源。V6 的验收范围是单轮 permission bridge slice：Claude Code 进程在同一运行中等待 Harness 审批；审批超过本地进程可等待的生命周期时，任务保持 pending/offline，V7 再评估 Claude Code `defer` / persisted session / native resume。

## External Reference Notes

Official Claude Code docs checked on 2026-06-05:

- `https://code.claude.com/docs/llms.txt`
- `https://code.claude.com/docs/en/agent-sdk/permissions.md`
- `https://code.claude.com/docs/en/agent-sdk/user-input.md`
- `https://code.claude.com/docs/en/agent-sdk/sessions.md`
- `https://code.claude.com/docs/en/agent-sdk/python.md`
- `https://code.claude.com/docs/en/cli-reference.md`

Reference facts used by this plan:

- Agent SDK permission evaluation falls through to `canUseTool` when hooks, deny rules, permission mode, and allow rules do not resolve a tool request.
- `canUseTool` pauses execution for tool permission requests and `AskUserQuestion` until the application returns allow or deny.
- The callback can return allow with original or modified input, or deny with a message visible to Claude.
- SDK docs describe `defer` for cases where a process should exit and resume later from persisted session, but V6 defers that cross-process resume path to V7.
- SDK session docs distinguish in-process continuation, specific session resume, and persisted sessions; sessions persist conversation/tool history, not filesystem state.
- SDK Python reference includes `ClaudeSDKClient`, `permission_mode`, `allowed_tools`, `disallowed_tools`, `can_use_tool`, `interrupt`, and `set_permission_mode`.

## Requirements Summary

- `adapter_kind=claude_code` gains a V6 permission-bridge execution mode only when explicit local bridge capability `claude_permission_bridge_v1=true` is reported and server-normalized.
- V5 headless bare no-tools path remains the default fallback and regression baseline.
- V6 bridge must use a Claude Code SDK-driven path, preferably Python `claude_agent_sdk`, because the official SDK exposes `can_use_tool` as an application callback. The CLI `--permission-prompt-tool` path remains a researched fallback, not the preferred implementation path for V6.
- Claude Code tool intent must map into V3 local host tool names and classification:
  - `Bash` -> `run_shell` or denied pattern
  - `Write` -> `write_file`
  - `Edit` / `MultiEdit` -> `apply_patch`
  - filesystem delete/move -> `delete_file` / `move_file` and denied or approval-required
  - network-like Bash -> `network` or approval-required critical command
  - env/secret patterns -> `env_read` / `secret_read` and denied or critical approval
- The bridge must call `POST /api/agents/local-agent/bridge/tool-requests` before any side-effect host action is considered executable.
- The bridge must block inside `can_use_tool` while polling the existing decision endpoint; it returns SDK deny after Harness-owned execution succeeds or fails, so Claude Code's native side-effect executor cannot run a second time.
- The bridge must execute only server-approved modified input through the Harness-owned local executor, never the original input when Harness returned a sanitized replacement.
- SDK configuration must not pre-approve side-effect tools before Harness sees them. V6 required path must keep `allowed_tools` / SDK settings / hooks from auto-allowing `Bash`, `Write`, `Edit`, `MultiEdit`, git/network/env/secret-like operations, or any mutation-capable custom tool. Those requests must reach the Harness `can_use_tool` callback first or be denied.
- The actual host side effect is Harness-owned local tool execution after intent capture and approval; result evidence must bind to the same V3 `tool_request_id` and `tool_call_id`.
- V6 must not use `bypassPermissions`, `acceptEdits`, `auto`, `dontAsk`, `--dangerously-skip-permissions`, remote-control, background sessions, web/cloud sessions, project/user `.claude` hooks/plugins/subagents, or unbounded settings sources in the required path.
- V6 must preserve workspace identity enforcement from V4/V5: local sidecar raw workspace root hash must match server task `workspace_identity_hash` before any Claude SDK run or local tool execution.
- V6 may expose paired workspace files to Claude Code only through explicitly enabled, server-classified Claude tools and path guards. This is a change from V5 private cwd/no workspace access and must be visible in capabilities/UI.
- V6 must not advertise `host_tools_authorized=true` until the runner proves dangerous permission modes, pre-approval allow rules for side effects, unmanaged settings, hooks, plugins, MCP, subagents, browser/computer-use tools, and remote-control surfaces are disabled or denied.
- UI remains unified: Agent Studio badges, local connection row badges, Workspace pending approval state, Run Detail approval cards and command lifecycle; no new standalone Claude Code chat.
- Required tests and smoke use deterministic fake SDK/subprocess fixtures. Live Claude Code credential smoke remains optional and cannot block required validation.

## Evidence From Current Code

- Backend adapter registry and default scopes already include `claude_code` in `services/api-server/app/api/agents/agent_local.py:14-17`.
- V5 currently treats Codex and Claude Code as restricted assistant adapters at `services/api-server/app/api/agents/agent_local.py:69`, and `_ensure_host_tool_protocol_allowed()` rejects their host tool protocol use at `services/api-server/app/api/agents/agent_local.py:228-233`.
- V3 local tool request, decision, result, command lifecycle, pending change, TTL, retry, and revoke APIs exist in `services/api-server/app/api/agents/agent_local.py:1082-1882`.
- V3 local tool request creation already resolves capabilities, creates `ToolCall`, creates optional `ToolApproval`, stores `LocalAgentToolRequest`, writes events, and returns decision at `services/api-server/app/api/agents/agent_local.py:1082-1309`.
- Claude Code assistant success currently requires API-side V5 safety proof at `services/api-server/app/api/agents/agent_local.py:3083-3086` and `services/api-server/app/api/agents/agent_local.py:3236-3253`.
- V5 CLI capabilities for Claude Code currently report `host_tools_authorized=false` and `execution_mode=headless_bare_no_session_no_tools` at `services/api-server/app/cli/hao/main.py:728-742`.
- V5 Claude Code command builder disables tools with `--tools ""` and forbids dangerous flags at `services/api-server/app/cli/hao/main.py:1035-1082`.
- Agent Studio already lists Claude Code as V5 enabled in `apps/agent-console/src/features/agents/pages/AgentListPage.tsx:837-846` and renders host-tool disabled badges from connection capabilities at `apps/agent-console/src/features/agents/pages/AgentListPage.tsx:889-891`.

## Goals

1. Capability and adapter mode
   - Add server-normalized Claude Code capability fields:

```json
{
  "adapter_kind": "claude_code",
  "enabled_in_v6": true,
  "execution_mode": "agent_sdk_intent_capture_harness_executor",
  "host_tools_authorized": true,
  "permission_bridge": "harness_local_tool_request_v1",
  "permission_bridge_execution": "harness_owned_executor",
  "sdk_native_tool_execution_enabled": false,
  "supports_streaming": true,
  "supports_resume": false,
  "supports_cancel": true,
  "resume_mode": "context_replay_new_session",
  "permission_defer_supported": false
}
```

   - Capability is opt-in. A V5 connection without `claude_permission_bridge_v1=true` remains no-tools.
   - Server still strips bridge-reported unsupported risk capabilities and treats all tool details as advisory until classified.

2. Claude SDK permission bridge
   - Add a CLI mode such as `hao bridge run --adapter claude_code --permission-bridge sdk`.
   - Add SDK probe separate from V5 CLI probe:
     - package import / version check for `claude_agent_sdk`
     - `ClaudeSDKClient` / `query`
     - `ClaudeAgentOptions`
     - `can_use_tool`
     - `PermissionResultAllow` / `PermissionResultDeny`
   - If SDK is absent or lacks required permission callback types, registration fails before consuming pair token for V6-scoped pairing, or V5 no-tools mode remains available for V5-scoped pairing.
   - Bridge prompt must tell Claude Code that Harness owns approvals and that tool requests may be denied/modified by policy.

3. Tool mapping and request lifecycle
   - Implement a mapping layer from Claude tool names/input schemas to V3 local tool requests.
   - The mapping layer must produce stable `tool_request_id` values from bridge task id, SDK tool use id, normalized tool name, and sequence.
   - Tool request payload includes redacted tool input, cwd, target paths, pending-change preview when available, permission mode, risk telemetry, and Claude SDK metadata.
   - API response controls the callback:
     - `allowed` / already `approved`: return SDK allow with `decision_json.input_json` / modified input.
     - `approval_required`: poll decision until approved/denied/expired/revoked/cancelled.
     - `denied` / `expired` / `revoked`: return SDK deny with bounded policy reason.
   - Approval polling must be cancellable when bridge task is cancelled or connection is revoked.

4. Execution boundary
   - Required V6 path: Claude SDK captures host-tool intent through `can_use_tool`; Harness-owned local executor performs the approved side effect and reports through V3 result endpoints.
   - Required safety condition: SDK native side-effect execution stays disabled. The SDK callback returns deny after Harness execution so Claude Code cannot also execute the same side effect.
   - For `Write` / `Edit` / `MultiEdit`, V6 should favor diff-first pending change:
     - precompute pending change preview when possible;
     - approval freezes target paths and diff hash;
     - post-execution result verifies hash/path before `ToolCall(SUCCESS)`.
   - Bash command lifecycle must be represented with `LocalAgentCommand` start/output/finish events when Claude Code executes Bash or when the Harness-owned executor does.
   - `assistant_done` remains rejected while unresolved local tool state exists.

5. Approval UX and Run evidence
   - Workspace pending assistant state shows "等待 Claude Code 本地工具审批" using existing local-tool pending projection.
   - Run Detail approval cards show:
     - adapter `claude_code`
     - Claude tool name and mapped Harness tool
     - command or target path summary
     - server risk classification
     - pending change preview/diff hash when available
     - `server_execution=false`
   - Connection rows show `V6 权限桥`, `本地工具需审批`, `上下文重放`.
   - UI must not imply native Claude session resume.

6. Privacy and credential handling
   - Continue V5 local-only credential policy. No raw Claude API key, OAuth token, auth helper output, device token, prompt, stdin payload, stdout/stderr, full home path, or full workspace scan may be stored in API, bridge receipts, or `bridge.json`.
   - V6 may persist only safe refs/hashes for SDK auth readiness, SDK version, Claude session id advisory metadata, and permission bridge mode.
   - If SDK session persistence cannot be disabled in Python, the session directory must live under an adapter-owned mode `0700` sidecar, and raw session IDs remain advisory only. API cannot use them as resume authority in V6.
   - Secret/env reads remain denied or critical approval with redacted evidence. Approval cannot expand scope to include raw secret upload.

7. Cancel, timeout, and reconnect
   - `supports_cancel=true` only means the bridge can interrupt/poll-stop the in-process SDK run or mark the local turn cancelled. It does not mean native Claude session resume.
   - Approval wait has bounded heartbeat and state refresh. Foreground terminal close is okay if daemon remains alive.
   - Daemon kill while approval is pending keeps API history and pending approval readable; resumed V6 bridge must either continue if the SDK session is still alive or fail the Claude SDK task cleanly and leave a user retry path. Native deferred tool resume is V7.

## Non-Goals

- V6 does not implement native Claude Code `resume`, `continue`, fork, background sessions, remote-control, web/cloud execution, channels, or multi-agent Claude teams.
- V6 does not upload Claude credentials to the API or use Harness Secret Vault to materialize raw Claude credentials on the server.
- V6 does not enable `bypassPermissions`, `acceptEdits`, `auto`, `dontAsk`, or CLI danger flags in the required path.
- V6 does not trust bridge-reported risk, path, network, permission, or capability fields.
- V6 does not add a new chat UI, new cloud Agent creation flow, or a separate Claude Code approval console.
- V6 does not make Codex or V5 Claude no-tools behavior less restrictive.

## RALPLAN-DR Summary

### Principles

- Harness API/DB remains the authority for sessions, runs, events, approvals, policy, audit, and final messages.
- Claude Code permissions become Harness tool requests before host effects.
- Default-deny and fail-closed outrank adapter convenience.
- V6 must be deterministic without live provider credentials.
- UI stays in the existing Agent Studio / Workspace / Run Detail surfaces.

### Decision Drivers

- Security: prevent Claude Code from bypassing V3 local host approval and audit.
- Product utility: unlock real local coding usefulness beyond V5 assistant-only replies.
- Implementation risk: keep V6 to one permission bridge slice and defer native resume complexity.

### Viable Options

Option A: Agent SDK `can_use_tool` permission bridge with V3 local tool requests.

- Pros: official programmatic permission callback; supports allow/deny/modified input; maps naturally to Harness approval.
- Cons: new SDK dependency; Python SDK persistence and result-shape details require careful isolation.

Option B: CLI `--permission-prompt-tool` / MCP permission relay bridge.

- Pros: less new Python SDK surface if CLI is already installed; aligns with Claude Code permission prompt tooling.
- Cons: MCP/CLI permission contract is harder to keep deterministic in this repo; subprocess prompts and cross-process waits increase failure modes.

Option C: Keep V5 no-tools and only add better UX/credential setup.

- Pros: lowest security risk.
- Cons: does not move toward the user's target of local Claude Code doing useful work under Harness approvals.

Chosen for V6: Option A, with Option B documented as fallback research only and native resume deferred.

## ADR

### Decision

Implement V6 as an Agent SDK permission bridge planning slice: Claude Code tool permission callbacks become V3 local host tool requests and approvals, while Harness remains the authority for policy, approval, audit, command lifecycle, pending changes, assistant completion, and UI projection.

### Drivers

- V5 proved conservative Claude Code adapter integration but intentionally disabled host tools.
- V3 already supplies the correct approval/audit machinery for local host execution.
- Official Agent SDK `canUseTool` is the narrowest documented hook for interactive approval flows.

### Alternatives Considered

- CLI `--permission-prompt-tool`: rejected as primary V6 path because the SDK callback is a more direct application integration point; keep as fallback if SDK blocks implementation.
- Native resume plus permission bridge in one version: rejected because deferred tools, persisted sessions, workspace identity, and permission-mode continuity need separate proof.
- Server-side Claude execution: rejected because the user target is local Agent integration and credentials/files must stay local.

### Why Chosen

The SDK permission bridge gives Claude Code real local coding capability while preserving Harness-owned approval and event boundaries. It also keeps V6 focused enough to review and test.

### Consequences

- V6 implementation will likely add an optional Python dependency or lazy import path for `claude_agent_sdk`.
- Claude Code V6 usefulness depends on local SDK availability and local credentials.
- Long approval waits across daemon restarts remain limited until V7 native deferred-tool resume.

### Follow-Ups

- V7: persisted Claude SDK session/deferred permission resume with workspace identity and permission-mode continuity.
- V8: live credential UX using local sidecars or Secret Vault-backed local helper without exposing raw secrets to API.
- Future: evaluate CLI permission-prompt tool if SDK callback cannot cover a platform.

## Implementation Steps

1. Backend capability gate
   - Replace the blanket Claude Code host-tool rejection with a capability-gated path.
   - Only allow `claude_code` tool requests when connection capability `permission_bridge=harness_local_tool_request_v1` and `host_tools_authorized=true` are server-normalized.
   - Keep V5 no-tools Claude Code connections rejected by `_ensure_host_tool_protocol_allowed()`.

2. Capability normalization
   - Add V6 normalization fields for Claude Code permission bridge.
   - Allow only a small risk capability set such as `workspace_read`, `host_write_approval_required`, `shell_approval_required`, `git_approval_required`, `pending_change`, `command_lifecycle`.
   - Preserve `supports_resume=false` and `resume_mode=context_replay_new_session`.

3. CLI/bridge SDK probe
   - Add `--permission-bridge sdk|none` or equivalent config.
   - Probe `claude_agent_sdk` without printing credentials.
   - Store SDK availability/version and mode in safe bridge state only.
   - Pairing with V6 permission bridge fails before token consumption if SDK is missing; V5 pairing remains unaffected.
   - Verify adapter temp/session/config directories are mode `0700` or stricter, and token/root sidecars remain `0600`.

4. Claude SDK runner
   - Add a V6 runner around `ClaudeSDKClient` or `query()` with `permission_mode="default"`.
   - Configure allowed/disallowed tools so no danger/bypass modes are reachable.
   - Disable or isolate project/user settings, plugins, hooks, MCP servers, subagents, and auto memory unless explicitly required and safety-proven.
   - Use paired workspace root only after workspace hash validation.
   - Stream assistant deltas/done/error through existing bridge event APIs.
   - Use the Harness-owned local executor after SDK intent capture and approval; keep `sdk_native_tool_execution_enabled=false` and report `permission_bridge_execution=harness_owned_executor`.

5. `can_use_tool` adapter
   - Map Claude tool requests to V3 tool request payloads.
   - Submit request, poll decision, return allow/deny/modified input.
   - Handle approval timeout, connection revoke, bridge task cancel, duplicate tool use ids, and daemon heartbeat.
   - Ensure `AskUserQuestion` is denied or converted into a normal assistant clarification in V6 unless a separate Harness question UI is deliberately added later.
   - Treat POST `/tool-requests` failure, decision endpoint 5xx/network timeout, callback exception, SDK crash, runner death, and SDK crash after approval but before result as fail-closed: no host side effect may be executed or marked successful.

6. Tool result and lifecycle mirroring
   - Use Harness-owned local executor for V6-supported tools and report results through existing V3 result endpoints.
   - Record command start/output/finish for Bash.
   - Record pending changes and hash guards for writes/edits.
   - Submit authorized results to V3 result endpoint using the same `tool_request_id`.
   - Prove modified approval at execution level: if Harness approves a sanitized replacement path/content/command, the original requested path/content/command must remain untouched, and any original-side effect is a failure.

7. Frontend projection
   - Update Agent Studio Claude card to show V6 permission bridge when capability is present.
   - Update connection row badges from "本地工具禁用" to "本地工具需审批" for V6 bridge connections.
   - Ensure Workspace and Run Detail use existing approval/pending/cancel/retry projections.

8. Smoke and docs
   - Add deterministic `scripts/smoke-test-local-agent-v6.py`.
   - Update wiki/task progress after implementation.
   - Keep live Claude credential smoke optional and separately labeled.

## Acceptance Criteria

- V6 plan docs are入库 before implementation and receive two independent PASS reviews.
- Claude Code V6 connection can report permission bridge support, and server normalization permits host-tool protocol only for that mode.
- V5 Claude Code connections without permission bridge remain host-tools-disabled.
- Claude Code SDK permission callback creates a V3 `LocalAgentToolRequest` before any write/shell/git/network/env/secret side effect.
- SDK allow rules, SDK settings, hooks, or permission modes cannot auto-approve side-effect tools before Harness `can_use_tool` sees them.
- Approval-required Claude Code tool requests create `ToolCall(PENDING_APPROVAL)`, `ToolApproval(PENDING)`, Run waiting state, and ordered events.
- Approve returns SDK allow with server-approved input; reject/expire/revoke returns SDK deny and no host side effect.
- Modified approval passes sanitized input to Claude Code and cannot expand tool identity, target paths, risk class, network/secret flags, or diff hash.
- Authorized result updates the same `ToolCall` and local request; unauthorized legacy `tool_result` remains rejected.
- `assistant_done` cannot bypass unresolved Claude Code local tool state.
- Bridge state/API/events exclude raw Claude credentials, raw prompts, raw stdin/tool payload secrets, full home paths, full workspace scans, and oversized stdout/stderr.
- API failures, decision polling failures, callback exceptions, SDK crashes, and runner death fail closed without host side effects or `ToolCall(SUCCESS)`.
- Adapter directories and credential/workspace sidecars have enforced file modes before bridge support is advertised.
- Frontend shows V6 permission bridge status inside existing Agent Studio, Workspace, and Run Detail flows.
- Required validation passes without live Claude credentials.

## Risks And Mitigations

- Risk: SDK result stream does not expose enough post-tool lifecycle data.
  - Mitigation: V6 must fall back to Harness-owned local executor after approval or reduce supported tools until result evidence is reliable.
- Risk: SDK allow rules or settings short-circuit Harness approval.
  - Mitigation: required runner config forbids side-effect tools in SDK `allowed_tools`, blocks unmanaged settings/hooks/plugins/MCP/subagents, and includes adversarial fake SDK tests that try to execute before callback.
- Risk: API/decision failures leave the SDK in an ambiguous permission callback state.
  - Mitigation: any request creation, polling, callback, SDK, or runner failure returns deny/abort and cannot produce host side effects or success evidence.
- Risk: SDK Python session persistence writes local transcripts.
  - Mitigation: isolate session directory under mode `0700`, store only refs/hashes in bridge state, and keep native session ids advisory in V6.
- Risk: Claude Code built-in settings/plugins/hooks load unexpectedly.
  - Mitigation: required path uses controlled SDK options, isolated config/home, explicit disallowed tools/settings, and safety assertions before host-tool mode is advertised.
- Risk: Long approval waits outlive the SDK process.
  - Mitigation: V6 supports daemon-alive waits only; expired/daemon-killed waits leave API pending/failed state with retry. V7 handles `defer`/persisted resume.
- Risk: Users infer permission bridge means full autonomous access.
  - Mitigation: UI labels say "本地工具需审批"; dangerous modes remain forbidden; approval cards remain explicit.

## Verification Steps

- Backend:
  - `cd services/api-server && .venv/bin/python -m pytest tests/test_local_agents.py -q`
  - `cd services/api-server && .venv/bin/python -m pytest tests/test_tool_approvals.py tests/test_tool_runner.py -q`
  - `cd services/api-server && .venv/bin/python -m pytest tests/test_local_agents.py -q -k "claude or permission or tool_request or approval"`
- CLI:
  - `cd services/api-server && .venv/bin/python -m pytest tests/test_hao_cli.py tests/test_hao_cli_v2.py -q -k "bridge or claude or permission or approval or pending_change or command"`
  - `cd services/api-server && .venv/bin/python -m py_compile app/api/agents/agent_local.py app/api/schemas.py app/events/event_types.py app/cli/hao/api_client.py app/cli/hao/main.py tests/test_local_agents.py tests/test_hao_cli.py tests/test_hao_cli_v2.py`
  - `cd services/api-server && .venv/bin/python -m ruff check app/api/agents/agent_local.py app/api/schemas.py app/events/event_types.py app/cli/hao tests/test_local_agents.py tests/test_hao_cli.py tests/test_hao_cli_v2.py`
- Smoke:
  - `python3 scripts/smoke-test-local-agent-v6.py --scenario claude-sdk-unavailable`
  - `python3 scripts/smoke-test-local-agent-v6.py --scenario claude-approve-write`
  - `python3 scripts/smoke-test-local-agent-v6.py --scenario claude-modified-approval`
  - `python3 scripts/smoke-test-local-agent-v6.py --scenario claude-reject-bash`
  - `python3 scripts/smoke-test-local-agent-v6.py --scenario claude-revoke-pending`
  - `python3 scripts/smoke-test-local-agent-v6.py --scenario claude-approval-timeout`
  - `python3 scripts/smoke-test-local-agent-v6.py --scenario claude-bypass-attempt`
  - `python3 scripts/smoke-test-local-agent-v6.py --scenario claude-api-failure-fail-closed`
- Frontend:
  - `cd apps/agent-console && npm test -- AgentListPage.studio.test.tsx AgentWorkspacePage.team-launch.test.tsx ChatSurface.shell.test.tsx RunDetailPage.helpers.test.ts RunDetailPage.optimizer.test.tsx`
  - `cd apps/agent-console && npm run lint -- --pretty false`
- Docs:
  - `python3 scripts/validate-docs.py`
  - `git diff --check`

## Available-Agent-Types Roster

- `architect`: protocol boundary, SDK/CLI tradeoff, resume and capability normalization review.
- `critic`: adversarial plan review and shallow-alternative rejection.
- `dependency-expert`: optional SDK dependency and version risk evaluation.
- `executor`: implementation across backend/CLI/frontend/smoke.
- `test-engineer`: deterministic permission bridge, negative security, and smoke coverage.
- `code-reviewer`: post-implementation code/security review.
- `verifier`: final evidence validation and docs/progress consistency.

## Follow-Up Staffing Guidance

- `$ralph`: recommended for sequential V6 implementation after plan approval; use one executor to own the full bridge and one final code-reviewer/verifier pass.
- `$team`: recommended if splitting implementation into backend capability gate, CLI SDK runner, frontend projection, and smoke/test lanes. Suggested roles: backend executor, CLI executor, frontend executor, test-engineer, then code-reviewer.
- Goal-mode follow-up: `$ultragoal` can track V6->V7 milestones. `$autoresearch-goal` fits if SDK permission/defer behavior needs longer official-doc validation. `$performance-goal` is only relevant if Claude SDK startup/approval latency becomes an explicit target.

## Launch Hints

```bash
omx team --task "Implement .omx/plans/prd-local-agent-claude-code-permission-bridge-v6.md and .omx/plans/test-spec-local-agent-claude-code-permission-bridge-v6.md with backend capability, CLI SDK runner, frontend projection, and smoke/test lanes"
```

Team verification path:

- Team proves targeted backend, CLI, frontend, V6 smoke, docs, and diff checks.
- Ralph or solo closeout reruns critical gates, performs final code review, updates progress/wiki, commits, and pushes the V6 branch.

## Changelog

- 2026-06-05: Initial V6 PRD入库. Scope chosen as Claude Code Agent SDK permission bridge slice; native resume/deferred tools and credential UX deferred to later versions.
- 2026-06-05: Security/test review BLOCK addressed by adding SDK allow-rule bypass closure, fail-closed API/bridge failure contracts, modified-approval execution proof, adversarial fake SDK coverage, and file-mode verification requirements.
