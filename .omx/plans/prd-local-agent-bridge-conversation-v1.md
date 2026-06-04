# PRD: 本地 Agent Bridge Conversation V1

## Summary

V1 建立本地 Agent 接入 Harness 的安全基座：Agent Studio 生成配对命令，本地 `hao bridge` 使用一次性 pair token 注册设备，随后 bridge daemon 通过 device credential 心跳、拉取任务、ack 和上报事件。Harness API/DB 始终是连接、会话、消息、Run、Event、ToolCall、权限和审计的唯一真相；bridge 是不可信本地执行端，不能直接写通用消息。

V1 验收范围只启用 fake bridge 和 hao adapter。Codex CLI / Claude Code adapter 仅作为未来 disabled adapter 展示，不执行、不注册。

## Goals

- Agent Studio 保留“选择职业模板”和“接入本地 Agent”，不提供“新建云端 Agent”。
- 用户可生成本地连接命令：`hao bridge pair --api ... --pair-token ... --pair-code ... --daemon`。
- pair token 高熵、hash 存储、TTL 限制、单次消费；pair code 仅用于 UX。
- bridge 注册成功后换取长生命周期 device token，device token hash 存储，支持撤销。
- 连接列表显示 fake/hao/Codex/Claude adapter 状态、workspace root 脱敏、能力和恢复支持。
- owner 可创建 binding 并发送本地 Agent 消息；admin 可查看/revoke，operator/viewer 不可执行。
- local send 创建或绑定 `AgentSession`，创建 Workspace `Task` Run，写 `AgentEvent`，并排入 `LocalAgentBridgeTask`。
- bridge pull/ack/event report 以 device credential 鉴权，revoked 后拒绝。
- bridge event 通过 receipt 幂等；assistant done 写 `AgentMessage` 并完成 Run；tool result 写 `ToolCall` observation。
- fake bridge 可证明 pair/register/heartbeat/pull/ack/delta/done，不执行本地命令。
- hao bridge 可调用现有 `run_headless_once`，成功上报 `assistant_done`，失败上报 `assistant_error`。

## Non-Goals

- V1 不实现 Workspace 内统一 ChatSurface 体验；该能力属于 V2。
- V1 不实现 host tool approval 面板、pending change、cancel/retry 完整闭环；该能力属于 V3。
- V1 不启用 Codex CLI / Claude Code executable adapter。
- V1 不把浏览器变成 bridge，不允许浏览器消费 pair token 或注册 device credential。
- V1 不上传 raw env/secret/完整家目录扫描。

## Trust Boundary

- API/DB owns:
  - `LocalAgentPairingToken`
  - `LocalAgentConnection`
  - `LocalAgentConversationBinding`
  - `LocalAgentBridgeTask`
  - `LocalAgentBridgeEventReceipt`
  - `AgentSession`
  - `AgentMessage`
  - `Task` / Run
  - `AgentEvent`
  - `ToolCall`
  - permission and audit records
- bridge/daemon owns no business truth. It can only register through pairing, heartbeat, pull assigned tasks, ack task state, and report versioned events.
- Browser can create pair tokens and read/revoke connections through normal auth, but cannot call bridge registration or bridge task/event APIs.

## Backend Contract

- `POST /api/agents/local-agent/pairing-tokens`
- `POST /api/agents/local-agent/pairing-tokens/{token_id}/revoke`
- `POST /api/agents/local-agent/connections/register`
- `GET /api/agents/local-agent/connections`
- `POST /api/agents/local-agent/connections/{connection_id}/heartbeat`
- `POST /api/agents/local-agent/connections/{connection_id}/revoke`
- `POST /api/agents/local-agent/connections/{connection_id}/bindings`
- `GET /api/agents/local-agent/connections/{connection_id}/bindings`
- `POST /api/agents/local-agent/bindings/{binding_id}/messages`
- `GET /api/agents/local-agent/bindings/{binding_id}/tasks`
- `GET /api/agents/local-agent/bridge/tasks`
- `POST /api/agents/local-agent/bridge/tasks/{bridge_task_id}/ack`
- `POST /api/agents/local-agent/bridge/events`

## Security Requirements

- Pair token must be random, hash stored, TTL-bound, and single-use.
- Pairing registration must be race-resistant through DB constraints/locking.
- `LocalAgentConnection.pairing_token_id` must be unique.
- Device token must be hash stored server-side and never returned after registration.
- hao bridge state file must be `0600`; daemon launch must not pass device token through argv.
- Local sends are owner-only executable actions.
- Local sends must create user message, Run, queued event, and bridge task in one transaction.
- Bridge pull must only claim pending tasks and must not repeatedly return leased tasks.
- Terminal bridge tasks must reject new non-duplicate events.
- Event payloads, tool input/output, errors, and stdout/stderr must be bounded and secret-redacted.
- Lifecycle operations must emit audit records for create/register/heartbeat/revoke/expiry.

## Acceptance Criteria

- Agent Studio local-agent wizard generates a usable pair command and omits cloud-Agent creation.
- fake bridge can complete one deterministic reply without host execution.
- hao bridge can register, heartbeat, pull, ack, run headless, and report done/error.
- Revoked bridge cannot pull tasks.
- Reused pair token cannot create a second connection.
- Duplicate client message id is idempotent within one binding and does not collide across bindings.
- Duplicate bridge event id returns duplicate receipt; new terminal event after completion is rejected.
- Browser tests prove `/connections/register` is never called from UI.

