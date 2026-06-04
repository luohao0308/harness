# PRD: 本地 Agent Workspace Chat V2

## Summary

V2 在 V1 pairing / bridge / hao adapter 的基础上，把本地 Agent 对话融入现有 Agent Workspace，而不是另建聊天页。目标是让用户在同一个 `ChatSurface` 里选择本地连接、创建或恢复 API 拥有的 `AgentSession`、读取服务端 `AgentMessage` 历史、发送消息到 bridge task 队列，并在本地 bridge 离线或尚未完成时保留可读历史与 pending 状态。

本版继续坚持 Harness 主权边界：API/DB 是连接、会话、消息、Run、事件、工具审计和权限的唯一真相；浏览器只选择已注册连接和发起受控消息，不注册 bridge、不消费 pair token、不直接写通用 messages。

## Goals

- Workspace 顶部/消息区附近展示本地 Agent 控制条。
- 控制条列出当前 Agent 的本地连接，显示 adapter、online/offline/busy/revoked 投影、workspace root 和接入入口。
- 用户启用本地 Agent 模式后，自动创建或恢复 `LocalAgentConversationBinding`。
- Workspace 加载 binding 对应的 `AgentSession` 消息，并投影为现有 `ConversationNode` 树。
- 本地 Agent 对话进入现有左侧历史栏和 `ChatSurface`，不新增独立聊天系统。
- 发送消息时调用 local-agent binding message API，并创建/关联 Workspace Run。
- bridge 尚未完成时显示 pending assistant 状态；离线时显示“已排队，bridge 恢复后继续”语义。
- bridge 上报完成后，服务端 `AgentMessage` 历史刷新替换 pending 投影。
- 保留 V1 安全边界：浏览器不得注册本地设备或消费配对 token。

## Non-Goals

- V2 不启用 Codex CLI / Claude Code executable adapter。
- V2 不实现浏览器内 bridge、浏览器本地命令执行或浏览器设备注册。
- V2 不实现多条本地消息并发队列 UI；同一 active binding pending 时先锁定提交。
- V2 不实现 cancel/retry/local tool approval 的完整交互面板；这些留给后续安全切片。
- V2 不改变普通 Workspace chat / plan / goal 的默认流式执行路径。

## Product Flow

### Entry

- 用户进入 `/agents/:agentId/workspace`。
- Workspace 正常加载普通 Agent、模型、工具、团队和 Run 状态。
- 页面同时轮询 `GET /api/agents/local-agent/connections`。
- 仅展示当前 `agentId` 且未 revoked 的 local connections。

### Enable Local Agent Mode

- 用户打开“本地 Agent”开关。
- 若已有当前连接：
  - 调用 `GET /api/agents/local-agent/connections/{connection_id}/bindings`。
  - 优先使用 active binding，否则使用最新 binding。
  - 若无 binding，调用 `POST /api/agents/local-agent/connections/{connection_id}/bindings` 创建。
- 若无连接：
  - 显示“接入本地 Agent”入口，跳回 Agent Studio pairing flow。

### Conversation Projection

- 有 active binding 后，调用 `GET /api/agents/sessions/{agent_session_id}/messages`。
- 将 `AgentMessage` 投影为 `ConversationNode`：
  - conversation id: `local-agent:<binding_id>`
  - message node id: `local-msg:<message_id>`
  - metadata includes `source=local_agent`、connection、binding、session、message id。
- 投影进入 `hydrateFromConversations`，因此同一左侧历史栏和同一 `ChatSurface` 使用本地会话。

### Send

- 用户在现有 composer 输入。
- 若本地 Agent 模式关闭，保持原 `useChatStream.start()`。
- 若本地 Agent 模式开启：
  - 乐观追加 user node。
  - 乐观追加 assistant pending node。
  - 调用 `POST /api/agents/local-agent/bindings/{binding_id}/messages`。
  - 设置 active Run id 为响应 `run_id`。
  - 刷新 session messages 和 run workspace。
- 若 connection offline：
  - pending assistant 文案明确 bridge 恢复后继续。
- 若 API send 失败：
  - pending assistant 变为 error，错误写入 node metadata。

## Interfaces

### Backend

- `GET /api/agents/local-agent/connections`
- `GET /api/agents/local-agent/connections/{connection_id}/bindings`
- `POST /api/agents/local-agent/connections/{connection_id}/bindings`
- `GET /api/agents/sessions/{session_id}/messages`
- `POST /api/agents/local-agent/bindings/{binding_id}/messages`

### Frontend

- `AgentWorkspacePage`
  - owns local connection selection, binding lifecycle, local session message loading, local send, and projection into workspace store.
- `ChatSurface`
  - accepts `localAgentPanel`, `localAgentPending`, and `onLocalAgentSubmit`.
  - remains generic; it does not know bridge protocol details.
- `tasks/api.ts`
  - exposes local connection/binding/session message/send APIs and local Agent DTOs.

## Data Contracts

- `LocalAgentConnection` describes device connection only, not business conversation ownership.
- `LocalAgentConversationBinding` binds a connection to a Harness-owned `AgentSession`.
- `AgentMessage` remains the durable conversation history.
- `ConversationNode` is a UI projection and may include temporary pending nodes until service-backed messages arrive.
- Browser-generated `client_message_id` is sent for idempotency and pending correlation.

## Acceptance Criteria

- Workspace shows a local Agent control strip when local connections are available.
- Enabling local Agent creates or resumes a binding without leaving Workspace.
- Existing local `AgentSession` messages render in the same `ChatSurface`.
- Local messages are sent through the binding message API, not through normal chat stream.
- Local sends create a pending assistant state in the same message list.
- Run detail link points to the local Agent-created Workspace Run after send.
- Offline local connections display readable warning/pending semantics.
- Browser still never calls `/api/agents/local-agent/connections/register`.
- Existing Agent Studio pairing flow and normal ChatSurface behavior remain green.

## Risks

- Hydrating service-backed local conversations can overwrite optimistic pending nodes if projection is not careful.
- React Query refetch timing can briefly show empty state unless enable flow eagerly creates or resumes bindings.
- Local history in UI must remain a projection; API/DB must stay authoritative after refresh or reconnect.
- Locking one pending local send at a time is conservative but avoids adapter ordering ambiguity in V2.
