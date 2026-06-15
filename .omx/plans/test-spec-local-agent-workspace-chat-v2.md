# Test Spec: 本地 Agent Workspace Chat V2

## Scope

验证本地 Agent 已接入现有 Agent Workspace 对话面，而不是独立聊天页。重点覆盖连接选择、binding create/resume、API-backed `AgentSession` 历史投影、本地 send API、pending/offline 状态、权限边界和 V1 pairing UI 回归。

## Backend Tests

### Connection Status Projection

- 注册连接后，正常 list 返回 online/busy 等真实状态。
- 当 `last_seen_at` 超过 offline 阈值且状态是 online/busy 时，`GET /local-agent/connections` 返回 `offline` 投影。
- revoked 连接仍按 revoked 返回，不被 offline 投影覆盖。

### Binding List

- owner 可列出自己 connection 的 bindings。
- admin 可列出同组织 connection 的 bindings。
- operator 即使有 list role，也不能列出非 owner bindings。
- 跨组织访问返回 403/404。
- bindings 按 `updated_at desc, created_at desc` 返回，便于前端恢复最新会话。

### Local Send Contract

- owner 通过 binding message API 发送消息时：
  - 写入 user `AgentMessage`。
  - 创建或绑定 Workspace Run。
  - 创建 `LocalAgentBridgeTask`。
  - append local queued `AgentEvent`。
  - 返回 `bridge_task_id`、`run_id`、`agent_session_id`、`user_message_id`。
- 相同 `client_message_id` 重放返回已有 task，不重复写入消息。
- non-owner/operator 不能执行。
- revoked connection 不能执行。

### Bridge Completion Projection

- `assistant_delta` 写入 local Agent event，但不直接写通用 message。
- `assistant_done` 写入 assistant `AgentMessage`、完成 bridge task、完成 Run。
- duplicate bridge event 通过 receipt 幂等。

## Frontend Tests

### Workspace Local Mode

- Workspace 渲染本地 Agent control strip。
- `GET /api/agents/local-agent/connections` 返回当前 Agent connection 时，control strip 显示 connection name、adapter、status、workspace root。
- 没有 connection 时显示“接入本地 Agent”入口。
- 切换 connection 后 local mode remains enabled and binding state resets for selected connection.

### Binding Create / Resume

- 启用本地 Agent 模式时：
  - 先调用 binding list API。
  - 若返回 active binding，使用该 binding。
  - 若为空，调用 binding create API。
  - 创建成功后加载 `GET /api/agents/sessions/{session_id}/messages`。
- UI 显示 session id，并把会话加入左侧历史栏。

### Message Projection

- API 返回 user/assistant `AgentMessage` 时，现有 `ChatSurface` message list 显示这些消息。
- Projection 使用 deterministic node ids，重复 refetch 不产生重复消息。
- Local conversation id 使用 `local-agent:<binding_id>`。
- Pending node 存在时，session message refetch 不丢失 pending user/assistant 节点。
- 服务端 assistant message 出现后，pending assistant 不再保留。

### Local Send

- 本地 Agent 模式关闭时，composer 继续调用 normal stream。
- 本地 Agent 模式开启时，composer 调用 local binding message API。
- Local send body includes `content` and generated `client_message_id`。
- 发送后同屏显示 user node 和 pending assistant node。
- API 返回 `run_id` 后 Workspace active Run link updates。
- Pending 时 composer does not submit a second local message。
- Send failure marks pending assistant as error and shows toast.

### Offline / Reconnect UI

- Connection status offline 时 control strip 显示 offline tone。
- Offline send shows queued/pending explanation.
- Session history remains readable when connection is offline.
- Refetching messages after bridge completion replaces pending projection with authoritative assistant message.

### Regression

- Agent Studio pairing still shows “选择职业模板” and “接入本地 Agent” and does not show “新建云端 Agent”。
- Browser still never calls `/api/agents/local-agent/connections/register`。
- `ChatSurface` shell tests remain green without local Agent props.
- Existing Team launcher behavior in Workspace remains green.

## Required Commands

```bash
cd services/api-server && .venv/bin/python -m pytest tests/test_local_agents.py -q

cd services/api-server && .venv/bin/python -m ruff check \
  app/api/agents/agent_local.py \
  app/api/schemas.py \
  tests/test_local_agents.py

cd services/api-server && .venv/bin/python -m py_compile \
  app/api/agents/agent_local.py \
  app/api/schemas.py \
  tests/test_local_agents.py

cd apps/agent-console && npm test -- AgentWorkspacePage.team-launch.test.tsx
cd apps/agent-console && npm test -- AgentListPage.studio.test.tsx ChatSurface.shell.test.tsx AgentWorkspacePage.team-launch.test.tsx
cd apps/agent-console && npm run lint -- --pretty false

python3 scripts/validate-docs.py
git diff --check
```

## Acceptance Evidence

- Backend local Agent regression passes with binding list and offline projection coverage.
- Frontend Workspace regression proves local Agent binding send occurs inside existing ChatSurface.
- Studio regression proves pairing UI remains intact and browser registration remains forbidden.
- Typecheck proves `ChatSurface` local-Agent props are additive and existing callers remain valid.
