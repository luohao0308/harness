# Test Spec: 本地 Agent Bridge Conversation V1

## Scope

验证 V1 的本地 Agent bridge 基座：pairing/register/heartbeat/list/revoke、binding、owner-only send、bridge pull/ack/event、fake/hao adapter smoke、安全边界、审计和隐私保护。

## Backend Tests

### Pairing And Registration

- 创建 pair token 返回明文 token 仅一次，DB 只保存 hash。
- pair token TTL 过期后注册返回 410，并写生命周期 audit。
- pair token 被消费后重放返回 410。
- 并发/重复注册不能创建第二个 connection；`pairing_token_id` 唯一约束兜底。
- disabled adapter `codex` / `claude_code` 注册返回 400。
- unsupported protocol version 返回 400。

### Connection Lifecycle

- owner/admin/operator 可按角色查看连接列表；非 admin 只能看自己的连接。
- stale heartbeat 将 online/busy 投影为 offline，但 revoked 保持 revoked。
- heartbeat 更新 `last_seen_at`、status、bridge version、capabilities，并写 lifecycle audit。
- owner/admin 可 revoke；revoked 后 bridge pull 返回 403。
- revoke 写 lifecycle audit。

### Binding And Send

- owner 可为自己的 connection 创建或恢复 binding。
- operator/non-owner 不能创建 executable binding 或发送本地消息。
- local send 写入 user `AgentMessage`、创建 Workspace Run、写 queued `AgentEvent`、创建 `LocalAgentBridgeTask`。
- local send 必须同事务提交；失败不得留下孤儿 Run 或孤儿 user message。
- `client_message_id` 幂等范围是 `binding_id + client_message_id`。
- 同一 binding 重放返回已有 bridge task；不同 binding 可复用同一个 client id。

### Bridge Task Lifecycle

- bridge pull 只 claim `pending` task，返回后 task 变为 `leased`。
- 第二次 pull 不应再次返回已经 leased 的 task。
- ack leased/running 将 task 置为 running；failed ack 将 task 置为 failed。
- revoked connection 不能 pull/ack/report。

### Bridge Event Idempotency

- `assistant_delta` 写 `AgentEvent`，不直接写 `AgentMessage`。
- `assistant_done` 写 assistant `AgentMessage`、完成 bridge task、完成 Run。
- `assistant_error` 置 bridge task failed、Run failed。
- `tool_result` 写 `ToolCall` observation 和对应 event。
- 相同 `event_id` 重放返回 duplicate receipt。
- terminal task 对新的非重复 event id 返回 409，不能重复写 assistant message 或把 completed 翻转 failed。

### Privacy And Audit

- tool input/output 中 secret-like key 被 `[REDACTED]`。
- content/error/stdout/stderr 中 `sk-...`、`sk-proj-...`、`sk_...`、`sat-...` 等 provider-style token 被脱敏。
- workspace root 在 UI/API projection 中只显示脱敏路径。
- lifecycle audit 覆盖 pairing create/revoke/expire、connection register/heartbeat/revoke。

## CLI Tests

- `hao bridge pair --once --adapter fake` 注册、保存 bridge state、heartbeat、pull、ack、delta、done。
- `~/.hao/bridge.json` 使用 `0600` 权限。
- `hao bridge pair --daemon` 启动后台 bridge run 时不把 device token 放入 process argv。
- `hao bridge run` 可从 protected state 中读取 device token。
- hao adapter 复用 `run_headless_once`；无有效 auth 时通过 `assistant_error` fail closed。

## Frontend Tests

- Agent Studio 显示“选择职业模板”和“接入本地 Agent”，不显示“新建云端 Agent”。
- pairing wizard 生成命令、展示 pair code、自动识别 fake/hao 状态。
- Codex/Claude adapter 以 disabled future adapter 显示。
- revoke 按钮调用 revoke API 并刷新连接列表。
- 浏览器 never calls `/api/agents/local-agent/connections/register`。

## Required Commands

```bash
cd services/api-server && .venv/bin/python -m pytest tests/test_local_agents.py -q
cd services/api-server && .venv/bin/python -m pytest tests/test_hao_cli.py -q -k "bridge_pair_once or api_client_ignores or bridge_daemon"
cd services/api-server && .venv/bin/python -m pytest tests/test_agents.py -q -k "agent_studio_create_clone"
cd services/api-server && .venv/bin/python -m ruff check app/api/agents/agent_local.py app/api/agents/_workspace_chat_helpers.py app/api/schemas.py app/db/models.py app/events/event_types.py app/cli/hao/api_client.py app/cli/hao/main.py tests/test_local_agents.py tests/test_hao_cli.py alembic/versions/20260611_0038_create_local_agent_connections.py
cd services/api-server && .venv/bin/python -m py_compile app/api/agents/agent_local.py app/api/agents/_workspace_chat_helpers.py app/api/schemas.py app/db/models.py app/events/event_types.py app/cli/hao/api_client.py app/cli/hao/main.py tests/test_local_agents.py tests/test_hao_cli.py
cd apps/agent-console && npm test -- AgentListPage.studio.test.tsx
cd apps/agent-console && npm run lint -- --pretty false
python3 scripts/validate-docs.py
git diff --check
```
