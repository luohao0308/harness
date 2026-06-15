# PRD: 本地 Agent Tool Safety V3

## Summary

V3 在 V1/V2 的 pairing、bridge daemon、Workspace ChatSurface 和 API-owned pending projection 基础上，关闭最后一个架构 WATCH：bridge 上报的 `tool_result` 只能是 observation，不能作为 Harness 授权依据。

本版目标是把 hao 本地工具执行纳入 Harness 的 `ToolCall / ToolApproval / AgentEvent / Run` 安全链路：bridge 在执行 host tool、shell、文件写入、git、network、env/secret 读取前必须先向 API 申请 tool request；API 做策略判断、创建审计和审批；审批通过后 bridge 才能执行；结果回执必须绑定已授权 request。审计或策略链路失败时 fail closed。

V3 仍只验收 fake bridge 与 hao adapter。不启用 Codex CLI / Claude Code executable adapter。

## Requirements Summary

- 本地工具从“执行后上报”改为“执行前申请、执行后回执”。
- API/DB 继续是唯一真相：授权状态、审批、ToolCall、command lifecycle、pending change projection、Run 状态和审计都在服务端落地。
- bridge/daemon 仍是不可信执行端，只能申请、轮询 decision、执行已允许动作、上报结果。
- side-effect `tool_result` 如果没有已授权 `tool_request_id` / `tool_call_id`，服务端必须拒绝，不能创建 successful `ToolCall`。只有明确 safe-list 的 non-side-effect observation 才能保留为 observation，且状态不得是 `SUCCESS`。
- host 写文件、apply patch、git commit、shell、network、env/secret 读取默认需要 policy/approval 或 hao 等价 pending approval。
- audit fail closed：无法写 `ToolCall`、`ToolApproval`、`AgentEvent`、command lifecycle 或 pending change projection 时，bridge 不得继续执行或提交成功结果。
- 用户体验仍融入 Workspace/Run Detail，不新增独立安全控制台。

## Evidence From Current Code

- V2 local send 在 `services/api-server/app/api/agents/agent_local.py:598` 创建 user message、Workspace Run 和 `LocalAgentBridgeTask`。
- 当前 `tool_result` 在 `services/api-server/app/api/agents/agent_local.py:1143` 直接写 `ToolCall` observation，`requires_sandbox=False`，这是 V3 要收紧的边界。
- `ToolCall` / `ToolApproval` 已存在于 `services/api-server/app/db/models.py:1122` 和 `services/api-server/app/db/models.py:1150`。
- 已有普通工具审批 API 和 Run Detail UI：`services/api-server/tests/test_tool_approvals.py`、`apps/agent-console/src/features/runs/pages/RunDetailPage.tsx`、`apps/agent-console/src/features/tasks/api.ts`。
- 现有普通审批 approve 会调用 `_execute_approved_tool_call()` 并进入服务器 `ToolRunner.execute_approved_call()`：`services/api-server/app/api/tasks.py:926`、`services/api-server/app/api/tasks.py:954`、`services/api-server/app/api/tasks.py:971`。V3 local host approval 必须显式分叉，approval 只解锁 bridge poll decision，不能在服务器执行本地 host tool。
- hao 本地 CLI 已有本地 command、pending change、cancel/retry 能力：`services/api-server/app/cli/hao/session_store.py`、`services/api-server/app/cli/hao/local_tools.py`、`services/api-server/app/cli/hao/tui.py`。

## Goals

1. 新增本地 tool request 协议：
   - bridge 发送 `tool_request_id`、`bridge_task_id`、`tool_name`、`input_json`、`execution_target`、`risk_level`、`permission_mode`、`cwd`、`target_paths`、`requires_network`、`requires_secret_read`、`pending_change_preview`。
   - API 返回 `decision=allowed | approval_required | denied`，以及 `tool_call_id`、可选 `approval_id`、可选 sanitized/modified input。
   - 相同 `connection_id + tool_request_id` 幂等。
   - `risk_level`、`permission_mode`、`requires_network`、`requires_secret_read`、`target_paths` 等 bridge 字段只作为 advisory telemetry。服务端必须根据 `tool_name`、`execution_target`、input、pending change preview、capability attachment 和 policy settings 自行分类；bridge 自报与服务端分类不一致时采用更高风险或 deny。
   - unknown `tool_name`、未知 execution target、能力未 attach、scope 不匹配、policy 缺失或无法分类时默认 fail closed。

2. 接入 Harness policy / approval：
   - auto-allowed 低风险只允许明确 safe-list，例如 read-only metadata 或 fake bridge no-op。
   - high/critical、shell、host write、git mutation、network、env/secret read 默认进入 `ToolApproval`。
   - denied policy 创建 `ToolCall(status=DENIED)` 和事件，bridge 不执行。
   - approval required 创建 `ToolCall(status=PENDING_APPROVAL)`、`ToolApproval(status=PENDING)`，Run 进入现有 canonical `WAITING_APPROVAL`。

3. 审批恢复：
   - Run Detail 继续展示审批卡片并可 approve/reject/modify。
   - bridge 可轮询 decision；只有 `APPROVED` 才能执行。
   - `DENIED` / expired / revoked / stale decision 都不能执行。
   - modified approval 的 sanitized input 必须进入 bridge execution payload，并写入 decision audit。
   - local host `ToolApproval` 的 approve/modify/reject 分支不得调用服务器侧 `_execute_approved_tool_call()` / `ToolRunner.execute_approved_call()`。它只更新 `ToolApproval`、`ToolCall(status=APPROVED|DENIED)`、`LocalAgentToolRequest.decision_json` 和事件；真正执行由 bridge poll approved decision 后在本地完成。
   - modify 只能收窄或 sanitize input。不能静默改变 `tool_name`、`execution_target`、target paths、diff hash、risk classification、network/secret flags 或 capability identity；若修改触及这些安全字段，必须拒绝或重新 policy/approval。

4. command lifecycle：
   - shell/test/git/network 类工具上报 `command_started`、bounded `command_output`、`command_finished`。
   - 服务端记录 command id、status、started/finished/cancel_requested、exit_code、duration、stdout/stderr tail、retry_of。
   - Workspace pending projection 和 Run Detail 可见 running/cancelled/retried/failed/success 状态。

5. pending change：
   - 文件写入和 patch 必须先产生 diff preview、target paths、content hash、operation type。
   - approval 对象冻结 diff hash 和 target paths；approval 后 commit 必须 hash guard。
   - reject 必须把 pending change 标为 denied，不写文件、不生成成功 tool result。

6. cancel / retry：
   - UI 或 API 可请求取消当前 local command；bridge 收到 cancel 后停止命令并上报 terminal cancelled。
   - retry 只能从 failed/timeout/cancelled command 创建新 command id，保留 `retry_of_command_id`。
   - completed/denied/pending approval 状态不能被 retry/late result 改写。

7. privacy / audit：
   - 不上传 raw env、secret、完整家目录扫描。
   - stdout/stderr、input/output、diff preview 都做 byte cap、secret scan、path redaction。
   - audit failure fail closed，不能继续执行或上报成功。
   - decision transaction failure 显示为 denied/failed pending state，result/event failure 显示为 local tool failed state，不允许 Run 或 ToolCall 进入成功终态。

## Non-Goals

- V3 不接入 Codex CLI / Claude Code adapter。
- V3 不实现多设备协同编辑或 remote filesystem sync。
- V3 不把浏览器变成本地执行端。
- V3 不替换现有 ToolRunner；本地 host 执行通过 local-agent bridge request/decision 协议接入现有 `ToolCall` / `ToolApproval` / Run evidence。
- V3 不承诺电脑关机后继续执行，只承诺 daemon alive 时可继续、daemon 恢复后可按幂等协议恢复 pending/decision 状态。

## Backend Interfaces

Add or extend local-agent APIs under `services/api-server/app/api/agents/agent_local.py`:

- `POST /api/agents/local-agent/bridge/tool-requests`
  - Device-token only.
  - Creates or returns idempotent local tool request decision.
  - Writes `ToolCall`, optional `ToolApproval`, `AgentEvent`, and local lifecycle projection in one transaction.

- `GET /api/agents/local-agent/bridge/tool-requests/{tool_request_id}/decision`
  - Device-token only.
  - Lets daemon poll approved/denied/modified decisions.
  - Rejects revoked connection and cross-connection request ids.

- `POST /api/agents/local-agent/bridge/tool-requests/{tool_request_id}/result`
  - Device-token only.
  - Accepts result only for `allowed` or `approved` requests.
  - Rejects terminal duplicates except same idempotency key.

- `POST /api/agents/local-agent/bridge/commands/{command_id}/events`
  - Device-token only.
  - Records command lifecycle and bounded output events.

- `POST /api/agents/local-agent/bridge/commands/{command_id}/cancel-ack`
  - Device-token only.
  - Confirms cancellation terminal state.

- `POST /api/agents/local-agent/bindings/{binding_id}/commands/{command_id}/cancel`
  - User/API side cancel request.
  - Owner/admin only; operator/viewer read-only.

- `POST /api/agents/local-agent/bindings/{binding_id}/commands/{command_id}/retry`
  - Owner only in V3.
  - Creates retry request if terminal failed/timeout/cancelled.

## Approval Execution Boundary

Existing generic tool approvals execute immediately on server approval. V3 local host approvals must not use that path.

- Generic server/sandbox tools keep the current path:
  - `ToolApproval(APPROVED)` -> `_execute_approved_tool_call()` -> `ToolRunner.execute_approved_call()`.
- Local host tools take a new local-agent branch:
  - `ToolApproval(APPROVED)` -> update local decision projection -> append event -> bridge polls decision -> bridge executes locally -> bridge reports authorized result.
- A local host `ToolCall(status=APPROVED)` means "approved and awaiting bridge result", not "server executed".
- A local host approval reject sets `ToolCall(status=DENIED)`, `LocalAgentToolRequest(status=denied)`, appends rejection events, and never reaches bridge execution.
- A local host approval modify can only narrow/sanitize `input_json`. Any attempted expansion of tool identity, target paths, diff hash, network/secret capability, risk classification, or capability identity must be rejected or force a new tool request and approval.
- Approval decision TTL is required. Default V3 TTL should be short and explicit, for example 30 minutes, with server-side expiry checked on decision polling and result submission.
- Connection revoke invalidates all unexecuted approved/pending decisions immediately; bridge polling and result endpoints return 403 after revoke.

Implementation implication:

- The task approval API must branch on local-agent provenance, for example `ToolCall.capability_snapshot_json.source == "local_agent_bridge"` plus `LocalAgentToolRequest.tool_call_id`.
- The local-agent branch must be transactionally complete before returning approval success.
- If local decision projection or event append fails, the approval endpoint must roll back and leave bridge polling without an executable decision.

## Capability And Scope Contract

- Local host tool names are not accepted solely because the bridge reports them.
- Each executable local tool must map to an attached Harness capability or an explicit local-agent V3 safe-list entry.
- Capability identity fields must be server-owned:
  - `capability_id`
  - `capability_version_id`
  - `capability_type`
  - content/config hashes where applicable
- Bridge-reported `tool_name` is advisory until server classification resolves it to an allowed local capability.
- Unknown tools, detached capabilities, disabled capabilities, or capability/input mismatches fail closed.
- V3 safe-list is intentionally tiny:
  - fake bridge no-op
  - read-only local status/metadata needed for deterministic tests
  - no shell, file write, git mutation, network, package install, process control, env/secret read, or delete/move operation may be auto-allowed by bridge self-report.

## Data Model

Preferred V3 migration adds local-agent-specific projection tables without bypassing `ToolCall` / `ToolApproval`:

- `LocalAgentToolRequest`
  - `organization_id`, `connection_id`, `binding_id`, `bridge_task_id`, `task_id`
  - `tool_request_id` unique per connection
  - `tool_call_id`, optional `approval_id`
  - `tool_name`, `execution_target`, `risk_level`, `permission_mode`
  - `status`: `requested | allowed | approval_required | approved | denied | running | succeeded | failed | cancelled | expired`
  - redacted `input_json`, `policy_decision_json`, `decision_json`, timestamps

- `LocalAgentCommand`
  - `command_id` unique per connection
  - `tool_request_id`, `task_id`, `binding_id`, `status`
  - `retry_of_command_id`, `cancel_requested_at`, `started_at`, `finished_at`
  - `exit_code`, `duration_ms`, redacted bounded output summary

- `LocalAgentPendingChange`
  - `change_id` unique per connection
  - `tool_request_id`, `command_id`, `approval_id`
  - `target_paths_json`, `diff_sha256`, redacted `preview_json`
  - `status`: `previewed | approval_required | approved | committed | denied | failed`
  - `committed_at`, `denied_at`, timestamps

Required constraints and invariants:

- `LocalAgentToolRequest.tool_call_id` is a non-null FK to `ToolCall.id` and unique per local tool request.
- `LocalAgentToolRequest.approval_id` is nullable FK to `ToolApproval.id`; when present, `ToolApproval.tool_call_id` must equal the request `tool_call_id`.
- `(connection_id, tool_request_id)` is unique.
- `(connection_id, command_id)` is unique for `LocalAgentCommand`.
- `(connection_id, change_id)` is unique for `LocalAgentPendingChange`.
- `LocalAgentToolRequest.bridge_task_id`, `task_id`, `binding_id`, `connection_id`, and `organization_id` must be service-validated as one ownership chain before any decision is returned.
- `LocalAgentCommand.tool_request_id` must resolve to the same connection/task/binding as its parent request.
- `LocalAgentPendingChange` must bind to a tool request and, for commit, to an approved `approval_id` with frozen `diff_sha256` and target paths.
- Terminal states are immutable at API level: request `succeeded/failed/cancelled/denied/expired`, command `success/failed/timeout/cancelled`, pending change `committed/denied/failed`.
- Database constraints cannot express every cross-table organization invariant in SQLite; V3 implementation must enforce those in service code and cover them with negative tests.

## Canonical State Machine

### LocalAgentToolRequest

| From | Trigger | To | Side effects |
| --- | --- | --- | --- |
| none | valid request, safe-list allowed | `allowed` | create `ToolCall(APPROVED)` with `approval_id=null` and `decision_json.auto_allowed=true`, append request + policy events |
| none | valid request requires approval | `approval_required` | create `ToolCall(PENDING_APPROVAL)`, `ToolApproval(PENDING)`, set `Task.status=WAITING_APPROVAL`, append approval event |
| none | denied/missing policy/unknown tool | `denied` | create `ToolCall(DENIED)`, append policy denied event |
| `approval_required` | approval approve | `approved` | `ToolCall(APPROVED)`, decision visible to bridge; no server ToolRunner execution |
| `approval_required` | approval reject | `denied` | `ToolCall(DENIED)`, decision visible to bridge as denied |
| `approved` or `allowed` | bridge starts command | `running` | command projection starts |
| `approved`/`allowed`/`running` | authorized result success | `succeeded` | update same `ToolCall(SUCCESS)`, append result event |
| `approved`/`allowed`/`running` | authorized result failure/timeout | `failed` | update same `ToolCall(FAILED/TIMEOUT)`, append failure event |
| `running` | cancel ack | `cancelled` | update command/tool projection; do not complete assistant message |
| `approval_required`/`approved` | decision TTL expires or connection revoked | `expired` or `denied` | bridge polling/result rejected; no host execution |

ToolCall status mapping:

- `PENDING_APPROVAL`: local tool request is waiting for Run Detail approval.
- `APPROVED`: local tool request is approved and awaiting bridge execution/result, not server ToolRunner execution.
- `DENIED`: server policy or user rejected execution.
- Auto-allowed requests use `APPROVED` plus `approval_id=null` and `decision_json.auto_allowed=true`; V3 should avoid introducing a new `ToolCall` status unless implementation proves existing UI/API projections cannot represent this state.
- `SUCCESS` / `FAILED` / `TIMEOUT`: terminal result received and bound to the same authorized request.

### LocalAgentCommand

| From | Trigger | To | Invariant |
| --- | --- | --- | --- |
| none | authorized command start | `running` | parent request is `allowed` or `approved` |
| `running` | output event | `running` | bounded/redacted output only |
| `running` | finish success | `success` | parent request may become `succeeded` |
| `running` | finish non-zero | `failed` | parent request may become `failed` |
| `running` | timeout | `timeout` | terminal |
| `running` | cancel requested + ack | `cancelled` | terminal |
| `failed/timeout/cancelled` | retry | new command | old command immutable; new command has `retry_of_command_id` |

### LocalAgentPendingChange

| From | Trigger | To | Invariant |
| --- | --- | --- | --- |
| none | preview submitted | `previewed` | target paths and diff hash frozen |
| `previewed` | approval required | `approval_required` | approval request includes frozen hash |
| `approval_required` | approval approve | `approved` | commit may execute only with same hash |
| `approved` | commit result hash matches | `committed` | update same request/tool result |
| `approved` | hash/path mismatch | `failed` | no success result; event records mismatch |
| `approval_required` | reject/expiry/revoke | `denied` | no commit allowed |

### Task / Run, Bridge Task, Agent Session

- While local tool approval is pending, canonical `Task.status` is `WAITING_APPROVAL`.
- While an approved local command is running, `Task.status` remains non-terminal (`WAITING_APPROVAL` or an existing running status if available) until the assistant turn completes.
- `LocalAgentBridgeTask` stays `leased`/`running` while local tools are pending or running. `assistant_done` before unresolved approval/command/change is rejected with 409 unless it is a duplicate terminal event.
- `assistant_error` may fail the bridge task only after unresolved local tool projections are terminal or explicitly cancelled.
- `AgentSession` receives no assistant `AgentMessage` until `assistant_done` is accepted.
- Late result, late command, late pending change commit, or late `assistant_done` after terminal states is rejected except exact duplicate idempotency receipts.
- Approval expiry/revoke does not terminal-complete `LocalAgentBridgeTask`; it leaves the assistant turn pending/failed according to bridge follow-up. Bridge must either report `assistant_error` after all local projections are terminal, or receive a new user retry.

## Event Contract

V3 should reuse existing event names where they already express the Harness contract, and add local-agent-specific events only where command lifecycle needs stable replay.

Required order for approval-required local tool:

1. `TOOL_CALLED`
   - payload: `source=local_agent_bridge`, `tool_request_id`, `bridge_task_id`, `connection_id`, redacted input, server risk classification.
2. `POLICY_CHECKED`
   - payload: policy id, allowed/approval_required/denied, advisory bridge risk, server risk, reason.
3. `TOOL_APPROVAL_REQUESTED`
   - payload: `tool_call_id`, `approval_id`, pending change metadata if present.
4. `TOOL_APPROVAL_APPROVED` or `TOOL_APPROVAL_REJECTED`
   - existing event names; local approval payload includes `local_agent_tool_request_id` and `server_execution=false`.
5. `LOCAL_AGENT_COMMAND_STARTED`
   - new event type for command start.
6. `LOCAL_AGENT_COMMAND_OUTPUT`
   - new event type for bounded/redacted output chunks.
7. `LOCAL_AGENT_COMMAND_COMPLETED` or `LOCAL_AGENT_COMMAND_FAILED` or `LOCAL_AGENT_COMMAND_CANCELLED`
   - new event type for terminal command state.
8. `TOOL_RESULT_RECEIVED` or `TOOL_FAILED` / `TOOL_TIMEOUT` / `TOOL_DENIED_BY_POLICY`
   - final result updates the same `ToolCall`.

Required event additions in `services/api-server/app/events/event_types.py`:

- `LOCAL_AGENT_TOOL_REQUESTED`
- `LOCAL_AGENT_TOOL_DECISION_READY`
- `LOCAL_AGENT_COMMAND_STARTED`
- `LOCAL_AGENT_COMMAND_OUTPUT`
- `LOCAL_AGENT_COMMAND_COMPLETED`
- `LOCAL_AGENT_COMMAND_FAILED`
- `LOCAL_AGENT_COMMAND_CANCELLED`
- `LOCAL_AGENT_PENDING_CHANGE_PREVIEWED`
- `LOCAL_AGENT_PENDING_CHANGE_COMMITTED`
- `LOCAL_AGENT_PENDING_CHANGE_DENIED`

Replay contract:

- Events must carry ids, not raw host payloads: `connection_id`, `binding_id`, `bridge_task_id`, `tool_request_id`, `tool_call_id`, optional `approval_id`, optional `command_id`, optional `change_id`.
- Payloads must include enough redacted summary for Run Detail, but raw stdout/stderr/diff/env values stay capped/redacted.
- Event order is monotonic by `AgentEvent.sequence`; duplicate bridge event ids return the original receipt.

## Deterministic Smoke Requirements

V3 implementation must add a deterministic smoke entrypoint, preferred path:

- `scripts/smoke-test-local-agent-v3.py`

Required modes:

- `--scenario approve-shell`
  - starts or targets a local test API
  - pairs fake/hao bridge in once or daemon mode
  - uses a temporary workspace
  - triggers benign host command/write request
  - approves through API
  - verifies file/command side effect occurred exactly once
  - verifies DB links: `ToolCall`, `ToolApproval`, `LocalAgentToolRequest`, `LocalAgentCommand`, `AgentEvent`, Run status
- `--scenario reject-write`
  - triggers file write pending change
  - rejects approval
  - verifies no file mutation and denied evidence exists
- `--scenario revoke-pending`
  - creates pending/approved decision
  - revokes connection before bridge execution
  - verifies polling/result fail and no host side effect

The smoke must avoid external credentials and external network. It must use temporary directories and clean up after itself.

## Legacy `tool_result` Compatibility Boundary

V3 keeps backward compatibility only for non-side-effect observations:

- Legacy `LocalAgentBridgeEventRequest.event_type="tool_result"` without `tool_request_id` is rejected for side-effect tool names and patterns: shell, write, apply_patch, git mutation, network, env/secret read, file delete/move, package install, process control.
- Safe-list observations may be accepted only with non-success authority semantics, for example `status=OBSERVED` or `DENIED`, and `capability_snapshot_json.authorized=false`.
- Legacy observation must never set `requires_sandbox=false` as proof of safety; server classification decides.
- Test coverage must include the old bridge event path, not only the new result endpoint.

## Frontend / UX

- Workspace:
  - Existing local Agent pending assistant state remains.
  - Add compact local tool status under the pending assistant: waiting approval, running command, cancelled, retrying, failed.
  - Offline/reconnect state shows pending tool decision separately from pending assistant response.

- Run Detail:
  - Reuse existing approval card for local `ToolApproval`.
  - Show local tool request provenance: adapter, workspace root redacted, command id, pending change target paths, diff hash, risk, policy decision.
  - Add local command lifecycle row in Tool Calls or Event Stream area, without duplicating a new card-heavy panel.

- Agent Studio:
  - Connection details show `supports_cancel`, `supports_host_tool_approval`, and `supports_pending_change`.
  - No Codex/Claude enablement in V3.

## Bridge / hao Adapter Contract

- hao bridge must intercept local tool intents before execution and call `tool-requests`.
- If decision is `allowed`, execute once and report result.
- If `approval_required`, stop local execution, show pending approval locally, poll decision, and execute only after approval.
- If `denied`, create a local denied tool message/result without host side effect.
- For pending change tools, bridge sends preview hash before commit; commit validates approved hash.
- For shell commands, bridge reports command lifecycle and honors cancel requests.
- Device token remains only in protected state file and never in argv/log output.

## RALPLAN-DR Summary

### Principles

- Harness owns authorization; bridge owns execution only after authorization.
- Every host side effect has an API-owned audit record before execution.
- Missing policy, missing audit, revoked connection, stale approval, or idempotency conflict fails closed.
- UI surfaces safety state in existing Workspace/Run Detail surfaces.
- V3 narrows to hao/fake and leaves Codex/Claude adapters disabled.

### Decision Drivers

- Security: local host tools can mutate user machines and must not rely on bridge self-report.
- Continuity: terminal/foreground closure should not lose pending approvals or command state.
- Incrementality: reuse existing `ToolCall`, `ToolApproval`, Run Detail, and hao local tool machinery instead of inventing a parallel system.

### Viable Options

- Option A: Dedicated local tool request/decision protocol backed by `ToolCall`/`ToolApproval`.
  - Pros: closes trust boundary, clear idempotency, supports approval/cancel/retry, fits existing Run Detail.
  - Cons: requires migration and bridge adapter changes.
- Option B: Keep bridge `tool_result` only and add more redaction/audit fields.
  - Pros: small change.
  - Cons: does not close the authorization gap; bridge can still execute first and ask later.
- Option C: Force all local tools through remote sandbox ToolRunner.
  - Pros: strongest central control.
  - Cons: misses core requirement of local Agent operating on the user's local workspace, and does not fit daemon/hao use cases.

Chosen option: Option A.

## ADR

- Decision: Implement V3 as a local tool request/decision protocol with API-owned policy, approval, command lifecycle, pending change projection, and result binding.
- Drivers: host safety, resumable pending state, existing Harness audit model, and minimal adapter scope.
- Alternatives considered: observation-only `tool_result` hardening; remote-only ToolRunner execution; full Codex/Claude adapter enablement.
- Why chosen: it fixes the reviewer WATCH without expanding adapter scope or bypassing Harness truth.
- Consequences: V3 adds migration/API/CLI/UI work, but establishes the contract Codex/Claude adapters can reuse later.
- Follow-ups: V4 can enable Codex CLI adapter on the same protocol; V5 can enable Claude Code; V6 can harden multi-adapter operations and release acceptance.

## Pre-Mortem

- Failure scenario 1: bridge executes before approval because old `tool_result` path still accepts success. Mitigation: require authorized `tool_request_id` for side-effect tool result and add negative tests.
- Failure scenario 2: approval state survives in UI but daemon restart loses it. Mitigation: decision polling and API-owned pending request/command/change projection.
- Failure scenario 3: redaction catches obvious secrets but leaks provider tokens in stdout/diff. Mitigation: byte caps, provider-token regex, path redaction, and negative privacy tests over input/output/diff/event payloads.

## Implementation Slices

1. Protocol and migration:
   - Add V3 schemas and migration for local tool request, command, and pending change projection.
   - Add idempotency constraints and terminal-state constraints.

2. Backend policy and approval:
   - Add tool request/decision/result APIs.
   - Reuse `ToolCall` and `ToolApproval` for policy outcome.
   - Mark Run waiting/running/failed/completed from local tool state without breaking V1/V2 message flow.

3. hao bridge integration:
   - Intercept host tool intents before execution.
   - Implement decision polling, approval-required local status, denied handling, authorized result binding.
   - Add command lifecycle, cancel, retry, and pending change hash guard.

4. Frontend projection:
   - Add local tool status to Workspace pending state.
   - Reuse Run Detail approval controls and add local command/pending-change evidence fields.
   - Add Agent Studio capability badges.

5. Security and regression:
   - Add negative tests for unauthorized result, revoked connection, stale approval, terminal replay, audit failure, secret leakage, cancel/retry terminal guards.
   - Keep V1/V2 tests green.

## Acceptance Criteria

- A side-effect `tool_result` without authorized `tool_request_id` is rejected and cannot mark `ToolCall` success.
- High-risk shell/write/git/network/env requests create `ToolApproval(PENDING)` and do not execute before approval.
- Approval from Run Detail lets hao bridge execute exactly once and report a result bound to the approved request.
- Rejection creates denied evidence and no host side effect.
- Pending change commit requires approved diff hash and target paths.
- Command lifecycle is visible and resumable after frontend reload and daemon reconnect.
- Cancel and retry are idempotent and cannot mutate terminal successful commands.
- Audit/redaction failures fail closed.
- V1/V2 pairing, message send, pending/offline projection, and fake/hao bridge smoke remain green.

## Verification Steps

- Backend: targeted `tests/test_local_agents.py`, new V3 local tool safety tests, `tests/test_tool_approvals.py`, `tests/test_tool_runner.py` approval regressions.
- CLI: focused `tests/test_hao_cli.py` and `tests/test_hao_cli_v2.py` for local tool approvals, pending changes, command lifecycle, cancel/retry.
- Frontend: Workspace local Agent test, Agent Studio test, Run Detail approval/helper tests, `ChatSurface.shell.test.tsx`.
- Static: Ruff, py_compile, frontend typecheck/lint, Alembic clean upgrade, docs validation, `git diff --check`.

## Available-Agent-Types Roster

- `architect`: state machine, trust boundary, migration/API review.
- `code-reviewer`: security, idempotency, redaction, authorization bypass review.
- `executor`: backend/frontend/CLI implementation slices.
- `test-engineer`: negative security and lifecycle regression suite.
- `verifier`: final evidence and claim validation.

## Follow-Up Staffing Guidance

- `$team` recommended for implementation because V3 has separable backend, hao bridge, frontend, and test lanes.
- Suggested lanes:
  - architect/backend executor for protocol/migration/API.
  - executor for hao bridge integration.
  - executor/designer-light for Workspace/Run Detail projection.
  - test-engineer for security negative tests.
  - code-reviewer/verifier for final gate.
- `$ralph` is suitable after team integration to persist through review fixes and final verification.
- `$ultragoal` can track V3 as one durable goal across branch, review, push, and later V4 handoff.

## Team Launch Hint

```text
$team "Implement .omx/plans/prd-local-agent-tool-safety-v3.md and .omx/plans/test-spec-local-agent-tool-safety-v3.md. Keep Codex/Claude disabled; split backend protocol, hao bridge, frontend projection, and tests; verify before shutdown."
```

Team verification path:

- Team proves targeted backend/CLI/frontend/security tests and docs checks.
- Ralph follow-up handles integration fixes, final code review, commit, and push.

## Goal-Mode Follow-Up Suggestions

- Use `$ultragoal` if V3 should be tracked as a durable multi-turn delivery goal.
- Use `$performance-goal` only if later V6 introduces measurable latency/throughput targets for bridge polling or local command streaming.
- Use `$autoresearch-goal` only if external adapter behavior or vendor docs become the main uncertainty.
