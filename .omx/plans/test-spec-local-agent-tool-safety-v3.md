# Test Spec: 本地 Agent Tool Safety V3

## Scope

验证 V3 是否把本地 host tool 从 bridge 自报 observation 升级为 Harness 授权执行：tool request、policy decision、ToolApproval、authorized result、command lifecycle、pending change、cancel/retry、privacy/audit fail-closed、Workspace/Run Detail projection。

V3 验收只覆盖 fake bridge 和 hao adapter。Codex CLI / Claude Code adapter 继续 disabled。

## Backend Tests

### Tool Request Idempotency

- `POST /bridge/tool-requests` 使用 device token，revoked connection 返回 403。
- 同一 `connection_id + tool_request_id` 重放返回同一 decision、`tool_call_id`、`approval_id`。
- 跨 connection 重用 `tool_request_id` 不读取别的 connection decision。
- missing/unknown `bridge_task_id` 返回 404/403。
- terminal bridge task 不接受新的 side-effect tool request。

### Policy And Approval

- low-risk fake no-op request 返回 `allowed`，创建 `ToolCall` 和 `AgentEvent`。
- shell / write / apply_patch / git mutation / network / env_secret read 默认返回 `approval_required`。
- bridge 自报 `risk_level=low`、`permission_mode=full-auto`、`requires_network=false`、`requires_secret_read=false` 不能降低服务端分类。
- shell/write/git/network/env/apply_patch 请求伪装成 read-only 仍进入 approval 或 denied。
- command 包含 `curl`、`ssh`、`git remote`、`npm install`、管道安装脚本等 network/mutation pattern 时，即使 `requires_network=false` 也不得 auto-allow。
- env/token 文件读取或 `printenv`/`cat .env` pattern 即使 `requires_secret_read=false` 也进入 critical approval 或 denied。
- unknown `tool_name`、unknown execution target、capability 未 attach、scope 不匹配默认 fail closed。
- approval-required request 创建：
  - `ToolCall(status=PENDING_APPROVAL)`
  - `ToolApproval(status=PENDING)`
  - local tool request projection
  - Run `WAITING_APPROVAL`
  - redacted request payload
- denied policy 创建 `ToolCall(status=DENIED)` 和 denial event，bridge decision 为 `denied`。
- policy missing 或 settings 解析失败 fail closed，不能返回 allowed。
- local host tool approve 不调用服务器 `_execute_approved_tool_call()` / `ToolRunner.execute_approved_call()`；只让 bridge polling 看见 approved decision。

### Authorized Results

- `tool_result` / result endpoint without known `tool_request_id` returns 409/403 and cannot create successful `ToolCall`。
- legacy `LocalAgentBridgeEventRequest.event_type="tool_result"` path 对 shell/write/git/network/env/apply_patch/file delete 等 side-effect tool 没有 authorized `tool_request_id` 时返回 409/403，不能创建 `ToolCall(status=SUCCESS)`。
- legacy safe-list observation path 只能创建 `authorized=false` 的 observation/denied evidence，不能标记为 successful authorized execution。
- result for `approval_required` before approval returns 409。
- result after approval updates the same `ToolCall` to terminal success/failure and appends result event。
- duplicate result idempotently returns same terminal state。
- fresh result after terminal success is rejected。
- result for denied request is rejected and does not mutate denied evidence。

### Approval Decisions

- Run Detail approve endpoint makes decision visible to bridge decision polling。
- approve local host approval must set `server_execution=false` in decision/event payload and must not create sandbox/server ToolRunner side effects。
- reject makes decision visible as denied and does not allow execution。
- modify approval returns sanitized modified input to bridge and records `decision_json.modified=true`。
- modify approval may only narrow/sanitize input。
- modify that changes `tool_name`、execution target、target paths、diff hash、risk classification、network/secret flags、capability identity is rejected or forced through a new approval。
- modify that expands target path from one file to directory/glob is rejected。
- modify that changes pending change diff hash after approval is rejected。
- non-admin cannot approve admin-required local host tool。
- owner can request cancel/retry but operator/viewer cannot execute local tool decisions。
- approval decision has TTL；expired approval is not executable by bridge。
- connection revoke after pending approval makes decision polling and result reporting return 403。
- late result after approval expiry or connection revoke cannot mutate `ToolCall`/request terminal evidence。
- approval TTL must be enforced on both decision polling and result submission。
- approved-but-unexecuted decision expires into non-executable state and leaves clear pending/failed local tool projection。

### State Machine And DB Constraints

- `LocalAgentToolRequest.tool_call_id` is non-null FK and unique; result updates the same `ToolCall`。
- `approval_id` FK points to `ToolApproval` whose `tool_call_id` matches request `tool_call_id`。
- `(connection_id, tool_request_id)` unique idempotency holds under replay。
- `(connection_id, command_id)` unique idempotency holds under replay。
- `(connection_id, change_id)` unique idempotency holds under replay。
- request/command/change rows must all match one organization, connection, binding, bridge task, and task chain。
- terminal request/command/change statuses cannot be mutated by late events except exact duplicate receipts。
- `assistant_done` before unresolved approval/command/pending change is rejected with 409 and does not write assistant `AgentMessage`。

### Pending Change

- write/apply_patch request creates pending change projection with redacted preview, target paths, operation type, and `diff_sha256`。
- approval freezes `diff_sha256` and target paths。
- commit result with mismatched hash returns 409 and marks failure/denied evidence。
- reject marks pending change denied and prevents commit success。
- path traversal, home directory scan, raw secret diff, and oversized diff are rejected or redacted fail-closed。

### Command Lifecycle

- `command_started` creates/updates command projection with status `running`。
- bounded `command_output` stores redacted stdout/stderr tail and event sequence。
- `command_finished` marks success/failed/timeout/cancelled with exit code and duration。
- duplicate lifecycle events are idempotent by command event id。
- fresh lifecycle event after terminal command is rejected except duplicate receipt。
- command lifecycle appears in Run events in sequence.
- event sequence is stable: request -> policy checked -> approval requested/denied -> approval decision -> command started/output/finished -> tool result。
- local command events use V3 event ids such as `LOCAL_AGENT_COMMAND_STARTED`, `LOCAL_AGENT_COMMAND_OUTPUT`, and terminal command events。

### Cancel / Retry

- cancel request on running command records `cancel_requested_at` and exposes cancel intent to bridge。
- bridge `cancel-ack` marks command cancelled and updates ToolCall/Run state.
- repeated cancel is idempotent。
- retry allowed only for failed/timeout/cancelled commands。
- retry creates new command id with `retry_of_command_id` and does not mutate original command。
- retry of success/pending approval/denied returns 409。

### Privacy And Audit Fail-Closed

- stdout/stderr/input/output/diff redact `sk-...`、`sk-proj-...`、`sat-...`、env-like secrets and auth headers。
- path projection redacts home paths and does not upload full directory scans。
- simulated failure writing `LocalAgentToolRequest` rolls back and returns no allowed decision。
- simulated failure writing `LocalAgentCommand` rolls back command start and cannot mark request running。
- simulated failure writing `LocalAgentPendingChange` rolls back preview/approval state and cannot return approval-required executable decision。
- simulated failure writing `ToolCall` rolls back decision and returns error; bridge must not execute。
- simulated failure writing `ToolApproval` or `AgentEvent` returns error; no allowed decision is issued。
- command output event write failure cannot mark command/tool/run successful。
- result event write failure cannot mark `ToolCall` success or complete Run。
- result payload above byte cap is truncated with metadata, not stored raw。

## CLI / hao Bridge Tests

### Pre-Execution Authorization

- hao bridge intercepts shell/write/git/network/env tool intent and calls `tool-requests` before local execution。
- when decision is `approval_required`, local command is not started and local status is pending approval。
- when decision is `denied`, host side effect does not happen and local transcript shows denied result。
- when decision is `allowed`, command executes once and result binds to returned `tool_call_id`。

### Approval Resume

- bridge polls decision and executes only after approved。
- modified approval changes execution input to the server-returned sanitized input。
- daemon restart reloads protected bridge state and can continue polling pending decision。
- foreground terminal close does not lose daemon pending approval state。

### Pending Change

- file write/apply_patch creates local diff-first pending change and server pending change projection before commit。
- approval commit validates hash。
- reject leaves file unchanged。
- audit failure before pending change approval fails closed and stops stream.
- daemon restart after pending approval reloads state and resumes decision polling from API truth, not local memory。
- foreground terminal close while daemon is alive does not lose pending approval execution state。

### Command Lifecycle / Cancel / Retry

- shell command reports started/output/finished。
- `/cancel <command_id>` or API cancel stops running command and reports cancelled。
- `/retry <command_id>` creates new command record only for failed/timeout/cancelled。
- retry keeps original command immutable。

### Credential Handling

- daemon process argv never includes device token。
- bridge state file remains `0600`。
- logs do not contain device token or raw approval payload secrets。

## Frontend Tests

### Workspace

- Local Agent pending assistant displays waiting approval state when backend returns approval-required local tool。
- Offline/reconnect state distinguishes queued assistant message from pending local tool approval。
- Cancel action appears only for running local command owned by current user。
- Retry action appears only for failed/timeout/cancelled local command。
- Viewer/operator cannot execute cancel/retry actions。

### Run Detail

- Existing approval panel displays local host tool approvals with risk, reason, redacted input, adapter, workspace root, and pending change metadata。
- approve/reject/modify optimistic updates still work for local tool approvals。
- Tool Calls list shows local tool request provenance and final result bound to one `ToolCall`。
- Event Stream shows request, approval required, decision, command started/output/finished, and result events in order。

### Agent Studio

- Connection details show V3 capability badges: host tool approval, pending change, command lifecycle, cancel/retry。
- Codex/Claude remain disabled future adapters。
- Pairing UI still does not call `/connections/register` from browser。

## E2E / Smoke

- fake bridge V3 smoke:
  - pair/register/heartbeat
  - send Workspace local message
  - request fake low-risk tool
  - receive allowed decision
  - report result
  - assistant done
- hao bridge approval smoke:
  - pair daemon once
  - send message causing shell/write request
  - observe pending approval in Run Detail
  - approve
  - bridge executes and reports lifecycle/result
  - assistant completes
- negative smoke:
  - reject approval and verify no local side effect
  - revoke connection while approval pending and verify bridge cannot execute

### Deterministic Smoke Script

- V3 implementation must add `scripts/smoke-test-local-agent-v3.py` or an equivalent tracked smoke entrypoint.
- `approve-shell` scenario:
  - creates temp workspace
  - starts/targets local API
  - pairs fake/hao bridge in deterministic once/daemon mode
  - sends Workspace local message that triggers benign shell/write request
  - approves through API
  - verifies local side effect happened exactly once
  - verifies DB bindings across `ToolCall`、`ToolApproval`、`LocalAgentToolRequest`、`LocalAgentCommand`、`AgentEvent`、Run
- `reject-write` scenario:
  - creates temp workspace
  - triggers write/pending-change request
  - rejects approval
  - verifies file unchanged and denied evidence exists
- `revoke-pending` scenario:
  - creates pending or approved-but-unexecuted decision
  - revokes connection before bridge execution
  - verifies decision polling/result fail and no host side effect
- Smoke must not require external network or real provider credentials.

## Required Commands

```bash
cd services/api-server && .venv/bin/python -m pytest tests/test_local_agents.py -q
cd services/api-server && .venv/bin/python -m pytest tests/test_tool_approvals.py tests/test_tool_runner.py -q
cd services/api-server && .venv/bin/python -m pytest tests/test_hao_cli.py tests/test_hao_cli_v2.py -q -k "bridge or approval or pending_change or command or cancel or retry"
cd services/api-server && .venv/bin/python -m ruff check app/api/agents/agent_local.py app/api/schemas.py app/db/models.py app/events/event_types.py app/cli/hao tests/test_local_agents.py tests/test_hao_cli.py tests/test_hao_cli_v2.py
cd services/api-server && .venv/bin/python -m py_compile app/api/agents/agent_local.py app/api/schemas.py app/db/models.py app/events/event_types.py app/cli/hao/main.py app/cli/hao/local_tools.py app/cli/hao/session_store.py
cd services/api-server && DATABASE_URL=sqlite:////tmp/harness-local-agent-v3.sqlite AUTH_JWT_SECRET=test-harness-jwt-secret-32-characters-min HARNESS_SECRET_ENCRYPTION_KEY=test-harness-secret-encryption-key-32-min .venv/bin/alembic upgrade head
python3 scripts/smoke-test-local-agent-v3.py --scenario approve-shell
python3 scripts/smoke-test-local-agent-v3.py --scenario reject-write
python3 scripts/smoke-test-local-agent-v3.py --scenario revoke-pending
cd apps/agent-console && npm test -- AgentWorkspacePage.team-launch.test.tsx AgentListPage.studio.test.tsx ChatSurface.shell.test.tsx RunDetailPage.helpers.test.ts RunDetailPage.optimizer.test.tsx
cd apps/agent-console && npm run lint -- --pretty false
python3 scripts/validate-docs.py
git diff --check
```

## Acceptance Evidence

- Backend proves unauthorized side-effect result cannot mark success。
- Backend proves approval-required local tools wait for `ToolApproval` decision。
- hao bridge proves execution happens after approval, not before。
- Pending change hash guard prevents modified local commit after approval。
- Command lifecycle/cancel/retry are idempotent and terminal-safe。
- Frontend proves Workspace and Run Detail expose local tool safety state without a separate chat UI。
- Privacy tests prove secrets and raw local paths are not persisted in API/DB/event payloads。

## Out Of Scope For V3

- Codex CLI adapter execution。
- Claude Code adapter execution。
- Multi-device collaborative local execution。
- Remote sandbox-only replacement for local host tools。
