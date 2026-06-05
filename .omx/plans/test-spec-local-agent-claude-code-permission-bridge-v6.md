# Test Spec: 本地 Agent Claude Code Permission Bridge V6

## Scope

验证 V6 是否把 Claude Code 的 host tool permission request 接入现有 V3 local tool approval 链路，而不是绕过 Harness 执行本地主机操作。

V6 验收范围：

- Claude Code V6 permission bridge capability normalization。
- V5 no-tools Claude Code regression。
- SDK probe / missing SDK fail-before-register。
- `can_use_tool` / tool permission callback -> V3 `LocalAgentToolRequest`。
- Approval required / allowed / denied / modified / expired / revoked decision handling。
- Authorized result binding to the same `ToolCall` / local request。
- Pending change, command lifecycle, cancel/retry projection for Claude-origin local tools。
- Workspace / Run Detail / Agent Studio UI projection。
- Privacy, credential, and fail-closed negative tests。

V6 不验收 native Claude Code resume、deferred tool resume after process exit、remote-control/web/cloud sessions、Claude teams/subagents、required live credentials、or server-side Claude credential handling。

## Backend Tests

### Capability Gate

- `adapter_kind=claude_code` with no V6 permission bridge capability still returns `host_tools_authorized=false` and rejects `/bridge/tool-requests` with 409。
- `adapter_kind=claude_code` with reported `claude_permission_bridge_v1=true` normalizes to:
  - `enabled_in_v6=true`
  - `execution_mode=agent_sdk_permission_bridge`
  - `permission_bridge=harness_local_tool_request_v1`
  - `host_tools_authorized=true`
  - `supports_resume=false`
  - `resume_mode=context_replay_new_session`
  - `supports_cancel=true`
- Bridge cannot self-enable `bypassPermissions`, native resume, remote-control, MCP/plugin/hook/subagent/browser, env/secret read, or unclassified network capability through capabilities JSON。
- V6 risk capabilities are allowlisted to approval-required categories only。
- Codex and V5 Claude no-tools capability normalization remains unchanged。

### Pairing And Registration

- V6-scoped pairing command includes explicit permission bridge mode, for example `--adapter claude_code --permission-bridge sdk`。
- Missing `claude_agent_sdk` probe fails before registration, does not consume pair token, does not create `LocalAgentConnection`, and leaves token usable for a valid V5/V6 attempt according to scope。
- V5 Claude Code pairing without permission bridge still works with no-tools capabilities。
- Explicit `scope.adapters=["claude_code"]` and `scope.permission_bridge=["sdk"]` cannot be consumed by Codex/hao/fake。
- Replayed, expired, revoked, cross-org, and cross-user tokens fail as in V1/V5。
- Registration audit event includes adapter kind and permission bridge mode, but no raw device token, pair token, Claude credential, SDK config, or workspace root。

### Tool Request Mapping

- Claude SDK `Bash` permission request maps to `tool_name=run_shell` with command, description, timeout, cwd, risk telemetry, and stable `tool_request_id`。
- Claude SDK `Write` maps to `write_file` with target path, content hash, pending change preview when possible, and no raw full content beyond cap。
- Claude SDK `Edit` / `MultiEdit` maps to `apply_patch` or an equivalent diff-first local pending change request with frozen target path/diff hash。
- Claude SDK `Read`, `Glob`, `Grep`, `LS` remain read-only only if explicitly allowed and path-constrained; otherwise they are denied or mapped to approval-required host read according to policy。
- `WebFetch`, `WebSearch`, MCP tools, plugin tools, browser/computer tools, subagent/task tools, and unknown tool names are denied unless a future capability explicitly maps them。
- `AskUserQuestion` is not treated as a host tool; V6 either denies it with a message asking Claude to respond in chat or records a non-executing observation. It cannot create `ToolCall(SUCCESS)`。
- Same bridge task + SDK tool use id replay returns the same local request decision。
- Different tool use ids with same command are distinct requests unless client idempotency key matches exactly。

### Policy And Approval

- Bash/write/edit/git/network/env/secret requests default to `approval_required` or `denied`; bridge-reported low risk cannot auto-allow them。
- Network-looking Bash such as `curl`, `wget`, `ssh`, `git remote`, `npm install`, `pip install` is classified as network/mutation even if SDK metadata says low risk。
- Secret-looking Bash/read patterns such as `printenv`, `.env`, `TOKEN`, `SECRET`, `KEY`, `Authorization` are classified as critical approval or denied。
- Capability attachment is still required for executable local tools; detached capability returns denied。
- Approval-required request creates:
  - one `ToolCall(PENDING_APPROVAL)`
  - one `ToolApproval(PENDING)`
  - one `LocalAgentToolRequest(approval_required)`
  - optional `LocalAgentPendingChange`
  - Run waiting state
  - ordered request/policy/approval events
- Denied request creates denied evidence and SDK callback returns deny; no host side effect occurs。
- Local host approval branch still does not call server `_execute_approved_tool_call()` or `ToolRunner.execute_approved_call()`。

### Decision Polling

- `approval_required` causes bridge callback to poll decision endpoint and keep heartbeat current。
- Approve returns SDK allow with server-approved `input_json` and same `tool_request_id`。
- Reject returns SDK deny with bounded redacted reason。
- Expired approval returns SDK deny and terminalizes pending local tool state according to V3 TTL behavior。
- Revoked connection causes decision polling to stop, returns SDK deny/error, and prevents host execution。
- Cancelled bridge task causes callback to return deny or abort and prevents host execution。
- Duplicate approved decision polling is idempotent。
- Modified approval returns SDK allow with modified/sanitized input and records `decision_json.modified=true`。
- Modify cannot expand `tool_name`, execution target, target paths, diff hash, risk class, capability identity, network flag, or secret-read flag。

### Authorized Result Binding

- After SDK executes an approved tool, bridge submits result to V3 result endpoint with the same `tool_request_id`。
- Result updates the original `ToolCall` from `APPROVED` to `SUCCESS` / `FAILED` / `TIMEOUT` and does not create a second ToolCall。
- Duplicate result returns same terminal state。
- Fresh result after terminal success is rejected。
- Result before approval is rejected。
- Result for denied/expired/revoked request is rejected and cannot mutate terminal evidence。
- Legacy `LocalAgentBridgeEventRequest(event_type="tool_result")` remains rejected for Claude Code side-effect tools。
- If SDK does not expose reliable tool result data, bridge cannot submit success; it must submit failure/unsupported or use Harness-owned local executor under the same request id。

### Pending Change

- Claude Write/Edit/MultiEdit request creates redacted pending change preview with target paths, operation type, and `diff_sha256` when enough data exists。
- Approval freezes `diff_sha256` and target paths。
- Approved modified input preserves or narrows target paths and diff scope。
- Commit/result with mismatched diff hash returns 409 and cannot mark success。
- Reject/expiry/revoke marks pending change denied/expired and leaves files unchanged in deterministic fixture。
- Path traversal, writes outside paired workspace root, `.git` writes, `.claude` writes, home-directory writes, and oversized/secret-looking diffs are denied or fail closed。

### Command Lifecycle

- Approved Bash creates `LocalAgentCommand(running)` before or at execution start。
- Bounded output events redact secrets and home paths。
- Command finish updates command terminal status and then local request/tool result status。
- Duplicate command lifecycle events are idempotent。
- Fresh lifecycle events after terminal command are rejected except duplicate receipt。
- Cancel request records `cancel_requested_at`; SDK runner interrupts or denies continuing execution。
- Retry is allowed only from failed/timeout/cancelled commands and creates a fresh local request/command with retry links。
- Retry of success, pending approval, denied, or expired request returns 409。

### Assistant Completion

- `assistant_done` before unresolved Claude Code local tool request, command, or pending change returns 409 and writes no assistant message。
- `assistant_error` before unresolved local tool state returns 409 unless tool state is terminal/cancelled。
- After all local tool state is terminal and SDK returns final assistant content, exactly one assistant `AgentMessage` is written。
- Duplicate `assistant_done` event id is idempotent and does not duplicate assistant content。
- V5 `system_init_safe=true` empty-tool proof is not required for V6 permission-bridge success, but V6 must include a different proof: `permission_bridge_active=true`, `permission_bridge_version=harness_local_tool_request_v1`, and no forbidden permission modes/settings loaded。
- V6 success metadata with `bypassPermissions`, `acceptEdits`, `auto`, `dontAsk`, remote-control, unmanaged MCP/plugins/hooks/subagents, or disabled bridge proof is rejected。

## CLI / Bridge Tests

### Probe And Parser

- `hao bridge pair --adapter claude_code --permission-bridge sdk` is accepted。
- `hao bridge run --adapter claude_code --permission-bridge sdk` is accepted。
- Unsupported permission bridge mode is rejected by parser。
- Missing SDK import returns unavailable reason without credentials or absolute home path。
- SDK probe checks required symbols/types without contacting Anthropic or reading raw credentials。
- Probe env excludes Harness/local-agent/provider/proxy secrets by default。
- V5 `--permission-bridge none` or omitted mode remains available and reports host tools disabled。

### SDK Runner Configuration

- Runner uses `permission_mode="default"` or stricter equivalent that still invokes `can_use_tool`。
- Runner never uses `bypassPermissions`, `acceptEdits`, `auto`, or `dontAsk` in required V6 path。
- Runner never places `Bash`, `Write`, `Edit`, `MultiEdit`, git/network/env/secret-like operations, or mutation-capable custom tools in SDK `allowed_tools` / `allowedTools` or equivalent pre-approval config。
- Runner denies or removes unmanaged settings, hooks, plugins, MCP servers, subagents, browser/computer-use tools, and remote-control surfaces before advertising `host_tools_authorized=true`。
- Negative fixture proves SDK config cannot resolve side-effect tools before Harness `can_use_tool`; every side-effect tool request is either seen by Harness callback or denied。
- Runner disallows remote-control, background/web/cloud sessions, unmanaged MCP servers, plugins, hooks, subagents, channels, browser/computer-use tools, and project/user settings unless explicitly proven disabled。
- Runner validates workspace identity hash before using paired workspace root。
- Runner env and state isolate `HOME`, Claude config/session storage, temp dir, and credential refs。
- Raw prompt, raw device token, raw workspace root, raw Claude credentials, and raw approval payloads do not appear in argv, `bridge.json`, API events, receipts, or logs。
- Adapter temp/session/config directories are chmod-verified as mode `0700` or stricter before runner start。
- `bridge.device-token` and workspace-root sidecars are chmod-verified as mode `0600` before runner start。

### Permission Callback

- Synthetic SDK `Bash` tool request calls API tool-request endpoint before execution。
- Callback blocks/polls while decision is pending and emits heartbeat/progress。
- Approved decision returns allow with server-approved input。
- Denied decision returns deny and Claude receives bounded reason。
- Modified decision returns allow with modified input。
- Timeout/expiry/revoke/cancel returns deny/error and no execution。
- Duplicate SDK tool use id is idempotent。
- POST `/bridge/tool-requests` 4xx/5xx/network timeout causes callback deny/abort and no host side effect。
- Decision endpoint 5xx/network timeout causes callback deny/abort or bounded retry followed by deny/abort; it cannot allow execution。
- Callback exception is caught, redacted, reported as assistant_error or deny, and cannot produce `ToolCall(SUCCESS)`。
- SDK crash while waiting for approval leaves local tool state pending/failed according to API truth and cannot execute host side effects。
- Runner death during execution marks command/request failed or cancelled and cannot produce success。
- SDK crash after approval but before result cannot submit success and leaves a retry/error path。

### Tool Result Capture

- Synthetic SDK post-tool success maps to result endpoint success for same request。
- Synthetic SDK post-tool failure maps to result endpoint failure。
- Missing post-tool result support causes assistant_error or unsupported result, not ToolCall success。
- Adversarial fake SDK that executes before callback is detected as protocol violation; no ToolCall success is written and the smoke fails if a side effect occurs。
- Adversarial fake SDK that ignores modified input is detected by path/content/hash checks; original requested path/content must remain untouched。
- Adversarial fake SDK that emits duplicate, mismatched, wrong request id, or post-denial tool results is rejected without mutating terminal evidence。
- Adversarial fake SDK that omits post-tool result data cannot be treated as success。
- Bash output is byte-capped and redacted before command output events。
- Write/Edit result verifies expected path/diff hash before success。

### Bridge State

- `bridge.json` stores only safe permission bridge mode, SDK version, auth readiness, device token ref, workspace root ref/hash, and no raw credentials。
- `bridge.device-token` remains mode `0600`。
- raw workspace root remains only in mode `0600` sidecar。
- SDK session id, if captured, is stored only as advisory metadata or safe hash/ref and never used as V6 resume authority。
- Daemon restart with pending approval reloads API truth and either continues if SDK task is alive or reports controlled failure/retry state; it does not fake native resume。
- Read/privacy negative fixtures cover `.env`, hidden config, symlink escape, `.git`, `.claude`, home paths, and oversized grep/read output redaction or denial。

## Frontend Tests

### Agent Studio

- Claude Code card shows:
  - V5 no-tools when permission bridge is absent。
  - V6 permission bridge when capability is present。
  - `本地工具需审批` / `Host tools require approval` badge。
  - `上下文重放` / `Context replay`, not native resume。
- Pairing command includes `--adapter claude_code --permission-bridge sdk` for V6 mode。
- Missing SDK or auth unavailable status is shown as local readiness, not server credential failure。
- Revoke works for V6 Claude connection and refreshes discovery list。

### Workspace

- Claude Code V6 connection appears in local Agent selector。
- Sending a request that triggers a tool shows pending assistant and waiting-approval state using existing ChatSurface。
- Offline/reconnect state keeps history readable and pending approval visible。
- Permission warning appears for write/shell/git/network requests and points to approval flow, not "tools disabled" copy。
- Viewer/operator cannot send executable V6 local messages or approve/cancel/retry。

### Run Detail

- Approval panel shows Claude Code provenance, mapped tool name, risk, reason, target paths, command summary, pending change preview, and `server_execution=false`。
- Approve/reject/modify optimistic UI works for Claude-origin local approvals。
- Tool Calls list shows final result bound to one ToolCall。
- Event Stream order is stable: request -> policy -> approval requested -> approval decision -> command/pending-change lifecycle -> result -> assistant completion。
- Cancel/retry actions appear only for eligible owner/admin cases and terminal command states。

## E2E / Smoke

### `claude-sdk-unavailable`

- Force SDK probe missing。
- Pair V6 permission bridge fails before registration。
- Pair token is not consumed。
- Error output excludes credentials, full home path, raw workspace root, and pair/device token。

### `claude-approve-write`

- Use deterministic fake SDK that requests `Write` or `Edit`。
- Bridge creates pending local tool approval and pending change preview。
- Approve through API with optional sanitized path/content。
- Bridge returns allow with server-approved input。
- Deterministic executor or fake SDK reports success。
- Verify file side effect occurs exactly once in temp workspace when supported by fixture。
- Verify ToolCall, ToolApproval, LocalAgentToolRequest, LocalAgentPendingChange, AgentEvent, Run, and AgentMessage evidence。

### `claude-modified-approval`

- Fake SDK requests Write/Edit to an unsafe or broad target。
- API approval modifies path/content/command to a sanitized replacement。
- Bridge returns SDK allow only with server-approved modified input。
- Verify original requested path/content/command is untouched。
- Verify modified target is the only side effect。
- Verify final result binds to the original local request and records `decision_json.modified=true`。
- Any original-side effect marks the scenario failed。

### `claude-reject-bash`

- Fake SDK requests Bash command。
- Backend classifies approval-required or denied。
- Reject approval。
- Bridge returns SDK deny。
- Verify command did not execute and no `ToolCall(SUCCESS)` exists。

### `claude-revoke-pending`

- Create pending Claude Code local tool approval。
- Revoke connection before approval or before execution。
- Decision polling returns revoked/denied。
- Verify no host side effect and bridge task/run state is clear。

### `claude-approval-timeout`

- Create approval-required request and force TTL expiry。
- Bridge callback returns deny/error after expiry。
- Verify ToolCall/request/pending change terminalized without success。

### `claude-bypass-attempt`

- Adversarial fake SDK attempts one or more bypasses:
  - side-effect tool is resolved by SDK allowed-tools before callback；
  - execution happens before callback returns allow；
  - modified input is ignored；
  - tool result has wrong request id；
  - post-tool result is omitted。
- Required outcome: bridge/API fail closed, no unauthorized host side effect remains, no `ToolCall(SUCCESS)` is written, and redacted error evidence explains the protocol violation。

### `claude-api-failure-fail-closed`

- Simulate `/bridge/tool-requests` failure, decision endpoint failure, callback exception, SDK crash after approval, and runner death during execution。
- Required outcome: deny/abort/failure state, no host side effect, no assistant success bypass, no `ToolCall(SUCCESS)`。

## Required Commands

```bash
cd services/api-server && .venv/bin/python -m pytest tests/test_local_agents.py -q
cd services/api-server && .venv/bin/python -m pytest tests/test_tool_approvals.py tests/test_tool_runner.py -q
cd services/api-server && .venv/bin/python -m pytest tests/test_hao_cli.py tests/test_hao_cli_v2.py -q -k "bridge or claude or permission or approval or pending_change or command"
cd services/api-server && .venv/bin/python -m ruff check app/api/agents/agent_local.py app/api/schemas.py app/events/event_types.py app/cli/hao tests/test_local_agents.py tests/test_hao_cli.py tests/test_hao_cli_v2.py
cd services/api-server && .venv/bin/python -m py_compile app/api/agents/agent_local.py app/api/schemas.py app/events/event_types.py app/cli/hao/api_client.py app/cli/hao/main.py tests/test_local_agents.py tests/test_hao_cli.py tests/test_hao_cli_v2.py
python3 scripts/smoke-test-local-agent-v6.py --scenario claude-sdk-unavailable
python3 scripts/smoke-test-local-agent-v6.py --scenario claude-approve-write
python3 scripts/smoke-test-local-agent-v6.py --scenario claude-modified-approval
python3 scripts/smoke-test-local-agent-v6.py --scenario claude-reject-bash
python3 scripts/smoke-test-local-agent-v6.py --scenario claude-revoke-pending
python3 scripts/smoke-test-local-agent-v6.py --scenario claude-approval-timeout
python3 scripts/smoke-test-local-agent-v6.py --scenario claude-bypass-attempt
python3 scripts/smoke-test-local-agent-v6.py --scenario claude-api-failure-fail-closed
cd apps/agent-console && npm test -- AgentListPage.studio.test.tsx AgentWorkspacePage.team-launch.test.tsx ChatSurface.shell.test.tsx RunDetailPage.helpers.test.ts RunDetailPage.optimizer.test.tsx
cd apps/agent-console && npm run lint -- --pretty false
python3 scripts/validate-docs.py
git diff --check
```

## Acceptance Evidence

- Backend proves Claude Code host-tool protocol is capability-gated and V5 no-tools remains restricted。
- Bridge proves SDK permission callback cannot execute side effects before V3 decision。
- Bridge proves SDK allowed-tools/settings cannot auto-approve side effects before Harness callback。
- Approval/reject/modify/expiry/revoke decisions control SDK allow/deny behavior。
- Modified approval proof shows the actual execution used only server-approved modified input。
- API/decision/callback/SDK/runner failures fail closed without host side effects or success evidence。
- Authorized result binds to one original ToolCall/local request and unauthorized legacy result remains rejected。
- Pending change and command lifecycle evidence appears in Run Detail through existing surfaces。
- Privacy tests prove raw credentials, raw prompts, raw workspace roots, full home paths, secret-looking payloads, and oversized output are redacted or absent。
- Smoke proves V6 permission bridge behavior without live Claude credentials。

## Out Of Scope For V6

- Native Claude Code resume/continue/fork/background/web/cloud sessions。
- Deferred tool resume after process exit。
- Required live Claude Code credential smoke。
- MCP/plugin/hook/subagent/browser/computer-use enablement。
- Server-side Claude credential storage or execution。
- New cloud Agent creation UI。

## Review Expectations

Two independent plan reviews must pass before implementation:

- Architecture/protocol reviewer: capability gate, SDK callback boundary, V3 contract reuse, workspace identity, resume deferral, and UI integration。
- Security/test reviewer: dangerous mode exclusion, credential/privacy handling, negative tests, approval modify constraints, fail-closed behavior, and smoke adequacy。

Implementation code review must run after V6 code is complete and before commit/push.
