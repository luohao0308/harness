# Forge Harness API Reference

Title: Forge Harness API
Version: 0.1.0

Generated from FastAPI OpenAPI metadata.

## Endpoints

### `GET /api/agents`

- Tags: agents
- Summary: 查询 Agent 注册表
- Responses: 200, 422

### `POST /api/agents`

- Tags: agents
- Summary: 创建 Agent 定义
- Responses: 201, 422

### `POST /api/agents/local-agent/bindings/{binding_id}/commands/{command_id}/cancel`

- Tags: agents
- Summary: 请求取消本地命令
- Responses: 202, 422

### `POST /api/agents/local-agent/bindings/{binding_id}/commands/{command_id}/retry`

- Tags: agents
- Summary: 请求重试本地命令
- Responses: 202, 422

### `POST /api/agents/local-agent/bindings/{binding_id}/messages`

- Tags: agents
- Summary: 通过 Harness 向本地 Agent 发送消息
- Responses: 202, 422

### `GET /api/agents/local-agent/bindings/{binding_id}/tasks`

- Tags: agents
- Summary: 查询本地 Agent 会话未完成任务
- Responses: 200, 422

### `GET /api/agents/local-agent/bridge/commands/{command_id}`

- Tags: agents
- Summary: Bridge 查询本地命令状态
- Responses: 200, 422

### `POST /api/agents/local-agent/bridge/commands/{command_id}/cancel-ack`

- Tags: agents
- Summary: Bridge 确认本地命令取消
- Responses: 202, 422

### `POST /api/agents/local-agent/bridge/commands/{command_id}/events`

- Tags: agents
- Summary: Bridge 上报本地命令生命周期
- Responses: 202, 422

### `POST /api/agents/local-agent/bridge/events`

- Tags: agents
- Summary: Bridge 上报本地 Agent 事件
- Responses: 201, 422

### `GET /api/agents/local-agent/bridge/tasks`

- Tags: agents
- Summary: Bridge 拉取待执行任务
- Responses: 200, 422

### `POST /api/agents/local-agent/bridge/tasks/{bridge_task_id}/ack`

- Tags: agents
- Summary: Bridge ack 待执行任务
- Responses: 200, 422

### `POST /api/agents/local-agent/bridge/tool-requests`

- Tags: agents
- Summary: Bridge 申请本地工具执行授权
- Responses: 201, 422

### `GET /api/agents/local-agent/bridge/tool-requests/pending`

- Tags: agents
- Summary: Bridge 查询服务端未决本地工具请求
- Responses: 200, 422

### `GET /api/agents/local-agent/bridge/tool-requests/{tool_request_id}/decision`

- Tags: agents
- Summary: Bridge 查询本地工具授权决定
- Responses: 200, 422

### `POST /api/agents/local-agent/bridge/tool-requests/{tool_request_id}/pending-change-refresh`

- Tags: agents
- Summary: Bridge 用批准后的输入刷新 pending change 预览
- Responses: 202, 422

### `POST /api/agents/local-agent/bridge/tool-requests/{tool_request_id}/result`

- Tags: agents
- Summary: Bridge 上报已授权本地工具结果
- Responses: 202, 422

### `GET /api/agents/local-agent/connections`

- Tags: agents
- Summary: 列出本地 Agent 连接
- Responses: 200

### `POST /api/agents/local-agent/connections/register`

- Tags: agents
- Summary: Bridge 使用配对 token 注册本地 Agent 连接
- Responses: 201, 422

### `PATCH /api/agents/local-agent/connections/{connection_id}`

- Tags: agents
- Summary: 更新本地 Agent 连接显示名称
- Responses: 200, 422

### `GET /api/agents/local-agent/connections/{connection_id}/bindings`

- Tags: agents
- Summary: 列出本地 Agent 连接的会话绑定
- Responses: 200, 422

### `POST /api/agents/local-agent/connections/{connection_id}/bindings`

- Tags: agents
- Summary: 绑定本地 Agent 与 Harness AgentSession
- Responses: 201, 422

### `POST /api/agents/local-agent/connections/{connection_id}/heartbeat`

- Tags: agents
- Summary: Bridge 心跳
- Responses: 200, 422

### `GET /api/agents/local-agent/connections/{connection_id}/recovery-command`

- Tags: agents
- Summary: 生成本地 Agent bridge 重启命令
- Responses: 200, 422

### `POST /api/agents/local-agent/connections/{connection_id}/revoke`

- Tags: agents
- Summary: 撤销本地 Agent 连接
- Responses: 200, 422

### `POST /api/agents/local-agent/pairing-tokens`

- Tags: agents
- Summary: 创建本地 Agent 配对命令
- Responses: 201, 422

### `POST /api/agents/local-agent/pairing-tokens/{token_id}/revoke`

- Tags: agents
- Summary: 撤销本地 Agent 配对令牌
- Responses: 200, 422

### `POST /api/agents/plan`

- Tags: agents
- Summary: Agent Plan 模式
- Responses: 201, 422

### `GET /api/agents/runs`

- Tags: agents
- Summary: 查询 Agent Run 历史
- Responses: 200, 422

### `GET /api/agents/runs/{run_id}/assignments`

- Tags: agents
- Summary: 查询 Run 的 Agent assignments
- Responses: 200, 422

### `POST /api/agents/runs/{run_id}/execute`

- Tags: agents
- Summary: 执行 Agent Run 的既有计划
- Responses: 202, 422

### `GET /api/agents/runs/{run_id}/handoffs`

- Tags: agents
- Summary: 查询 Run 的 Agent handoffs
- Responses: 200, 422

### `POST /api/agents/runs/{run_id}/local-tool-events`

- Tags: agents
- Summary: 记录 hao 本地工具事件
- Responses: 201, 422

### `POST /api/agents/runs/{run_id}/orchestrate`

- Tags: agents
- Summary: 创建多 Agent 编排分配
- Responses: 201, 422

### `POST /api/agents/runs/{run_id}/orchestrate/enqueue`

- Tags: agents
- Summary: 入队执行多 Agent 编排 assignments
- Responses: 202, 422

### `POST /api/agents/runs/{run_id}/orchestrate/execute`

- Tags: agents
- Summary: 执行多 Agent 编排 assignments
- Responses: 202, 422

### `GET /api/agents/runs/{run_id}/workspace`

- Tags: agents
- Summary: 查询 Agent Workspace 聚合视图
- Responses: 200, 422

### `GET /api/agents/sessions/{session_id}/messages`

- Tags: agents
- Summary: 查询 Agent 会话消息
- Responses: 200, 422

### `GET /api/agents/token-optimizer/presets`

- Tags: agents
- Summary: 查询内置 Token Optimizer 方案
- Responses: 200

### `GET /api/agents/{agent_id}`

- Tags: agents
- Summary: 查询 Agent 详情
- Responses: 200, 422

### `POST /api/agents/{agent_id}/capabilities/attachments`

- Tags: agents
- Summary: 为 Agent 附加能力
- Responses: 201, 422

### `POST /api/agents/{agent_id}/clone`

- Tags: agents
- Summary: 克隆 Agent 定义
- Responses: 201, 422

### `POST /api/agents/{agent_id}/context/compress`

- Tags: agents
- Summary: 压缩 Workspace 对话上下文
- Responses: 200, 422

### `GET /api/agents/{agent_id}/gateway-routes`

- Tags: api-gateway
- Summary: List Agent API Gateway routes
- Responses: 200, 422

### `POST /api/agents/{agent_id}/gateway-routes`

- Tags: api-gateway
- Summary: Create Agent API Gateway route
- Responses: 201, 422

### `DELETE /api/agents/{agent_id}/gateway-routes/{route_id}`

- Tags: api-gateway
- Summary: Delete Agent API Gateway route
- Responses: 204, 422

### `PATCH /api/agents/{agent_id}/gateway-routes/{route_id}`

- Tags: api-gateway
- Summary: Update Agent API Gateway route
- Responses: 200, 422

### `GET /api/agents/{agent_id}/knowledge/sources`

- Tags: agents
- Summary: 查询 Agent 知识源
- Responses: 200, 422

### `POST /api/agents/{agent_id}/knowledge/sources`

- Tags: agents
- Summary: 创建 Agent 知识源并索引文档
- Responses: 201, 422

### `POST /api/agents/{agent_id}/knowledge/sources/import`

- Tags: agents
- Summary: 通过 multipart 文件创建 Agent 知识源
- Responses: 201, 422

### `DELETE /api/agents/{agent_id}/knowledge/sources/{source_id}`

- Tags: agents
- Summary: 永久删除知识源
- Responses: 204, 422

### `PATCH /api/agents/{agent_id}/knowledge/sources/{source_id}`

- Tags: agents
- Summary: 更新知识源普通字段
- Responses: 200, 422

### `POST /api/agents/{agent_id}/knowledge/sources/{source_id}/archive`

- Tags: agents
- Summary: 归档知识源
- Responses: 200, 422

### `POST /api/agents/{agent_id}/knowledge/sources/{source_id}/disable`

- Tags: agents
- Summary: 停用知识源
- Responses: 200, 422

### `GET /api/agents/{agent_id}/knowledge/sources/{source_id}/documents`

- Tags: agents
- Summary: 查询知识源文档版本
- Responses: 200, 422

### `POST /api/agents/{agent_id}/knowledge/sources/{source_id}/documents`

- Tags: agents
- Summary: 向知识源添加文档
- Responses: 201, 422

### `POST /api/agents/{agent_id}/knowledge/sources/{source_id}/documents/import`

- Tags: agents
- Summary: 通过 multipart 文件添加知识源文档
- Responses: 201, 422

### `POST /api/agents/{agent_id}/knowledge/sources/{source_id}/documents/{document_id}/versions`

- Tags: agents
- Summary: 为文档创建新版本
- Responses: 201, 422

### `POST /api/agents/{agent_id}/knowledge/sources/{source_id}/documents/{document_id}/versions/import`

- Tags: agents
- Summary: 通过 multipart 文件创建文档新版本
- Responses: 201, 422

### `POST /api/agents/{agent_id}/knowledge/sources/{source_id}/enable`

- Tags: agents
- Summary: 启用知识源
- Responses: 200, 422

### `POST /api/agents/{agent_id}/knowledge/sources/{source_id}/scope`

- Tags: agents
- Summary: 变更知识源作用域
- Responses: 200, 422

### `GET /api/agents/{agent_id}/memories`

- Tags: agents
- Summary: List eligible agent memory records
- Responses: 200, 422

### `POST /api/agents/{agent_id}/memories`

- Tags: agents
- Summary: Create manual agent memory
- Responses: 201, 422

### `POST /api/agents/{agent_id}/memories/{memory_id}/lifecycle`

- Tags: agents
- Summary: Update memory lifecycle
- Responses: 200, 422

### `POST /api/agents/{agent_id}/runs`

- Tags: agents
- Summary: 创建 Agent Run
- Responses: 201, 422

### `POST /api/agents/{agent_id}/runs/chat/stream`

- Tags: agents
- Summary: Workspace Pro 对话流
- Responses: 200, 422

### `POST /api/agents/{agent_id}/runs/plan/stream`

- Tags: agents
- Summary: 流式创建 Agent Plan
- Responses: 200, 422

### `GET /api/agents/{agent_id}/sessions`

- Tags: agents
- Summary: 查询 Agent 会话
- Responses: 200, 422

### `POST /api/agents/{agent_id}/sessions`

- Tags: agents
- Summary: 创建 Agent 会话
- Responses: 201, 422

### `POST /api/agents/{agent_id}/token-optimizer`

- Tags: agents
- Summary: 选择 Agent 内置 Token Optimizer 方案
- Responses: 200, 422

### `GET /api/agents/{agent_id}/triggers`

- Tags: triggers
- Summary: List Agent triggers
- Responses: 200, 422

### `POST /api/agents/{agent_id}/triggers`

- Tags: triggers
- Summary: Create Agent trigger
- Responses: 201, 422

### `DELETE /api/agents/{agent_id}/triggers/{trigger_id}`

- Tags: triggers
- Summary: Delete Agent trigger
- Responses: 204, 422

### `PATCH /api/agents/{agent_id}/triggers/{trigger_id}`

- Tags: triggers
- Summary: Update Agent trigger
- Responses: 200, 422

### `GET /api/agents/{agent_id}/versions`

- Tags: agent-versions
- Summary: List Agent versions
- Responses: 200, 422

### `POST /api/agents/{agent_id}/versions`

- Tags: agent-versions
- Summary: Create Agent version snapshot
- Responses: 201, 422

### `PATCH /api/agents/{agent_id}/versions/{version_id}/activate`

- Tags: agent-versions
- Summary: Activate Agent version
- Responses: 200, 422

### `GET /api/api-keys`

- Tags: api-keys
- Summary: List Api Keys
- Responses: 200

### `POST /api/api-keys`

- Tags: api-keys
- Summary: Create Api Key
- Responses: 201, 422

### `DELETE /api/api-keys/{key_id}`

- Tags: api-keys
- Summary: Revoke Api Key
- Responses: 204, 422

### `GET /api/audit`

- Tags: audit
- Summary: List Audit Events
- Responses: 200, 422

### `GET /api/audit/export.csv`

- Tags: audit
- Summary: Export Audit Events Csv
- Responses: 200

### `GET /api/auth/config`

- Tags: auth
- Summary: Auth Config
- Responses: 200

### `POST /api/auth/login`

- Tags: auth
- Summary: Login
- Responses: 200, 422

### `POST /api/auth/logout`

- Tags: auth
- Summary: Logout
- Responses: 204

### `GET /api/auth/me`

- Tags: auth
- Summary: Me
- Responses: 200

### `POST /api/auth/me/avatar`

- Tags: auth
- Summary: Upload My Avatar
- Responses: 200

### `GET /api/auth/oauth/{provider}/callback`

- Tags: auth
- Summary: Oauth Callback
- Responses: 200, 422

### `GET /api/auth/oauth/{provider}/start`

- Tags: auth
- Summary: Oauth Start
- Responses: 200, 422

### `POST /api/auth/refresh`

- Tags: auth
- Summary: Refresh
- Responses: 200, 422

### `POST /api/auth/register`

- Tags: auth
- Summary: Register
- Responses: 201, 422

### `POST /api/auth/saml/acs`

- Tags: auth
- Summary: SAML Assertion Consumer Service
- Responses: 200, 422

### `POST /api/auth/saml/login`

- Tags: auth
- Summary: Initiate SAML SSO
- Responses: 200, 422

### `POST /api/auth/saml/logout`

- Tags: auth
- Summary: Initiate SAML Single Logout
- Responses: 200, 422

### `GET /api/auth/saml/metadata`

- Tags: auth
- Summary: Get SAML SP Metadata
- Responses: 200

### `GET /api/auth/saml/providers`

- Tags: auth
- Summary: List SAML Providers
- Responses: 200, 422

### `POST /api/auth/saml/providers`

- Tags: auth
- Summary: Create SAML Provider
- Responses: 201, 422

### `DELETE /api/auth/saml/providers/{provider_id}`

- Tags: auth
- Summary: Delete SAML Provider
- Responses: 204, 422

### `GET /api/auth/saml/providers/{provider_id}`

- Tags: auth
- Summary: Get SAML Provider
- Responses: 200, 422

### `PUT /api/auth/saml/providers/{provider_id}`

- Tags: auth
- Summary: Update SAML Provider
- Responses: 200, 422

### `POST /api/auth/saml/sls`

- Tags: auth
- Summary: SAML Single Logout Service
- Responses: 200, 422

### `DELETE /api/auth/sessions/current`

- Tags: auth
- Summary: Logout (Revoke Current Session)
- Responses: 200, 422

### `GET /api/auth/sessions/current`

- Tags: auth
- Summary: Validate Current Session
- Responses: 200, 422

### `POST /api/auth/sessions/refresh`

- Tags: auth
- Summary: Refresh Session
- Responses: 200, 422

### `POST /api/demo/load`

- Tags: demo
- Summary: 加载首轮 Demo 数据
- Responses: 200

### `POST /api/demo/reset`

- Tags: demo
- Summary: 重置首轮 Demo 数据
- Responses: 200, 422

### `POST /api/desktop/feedback`

- Tags: desktop-sync
- Summary: Submit Desktop Feedback
- Responses: 200, 422

### `POST /api/desktop/metrics`

- Tags: desktop-sync
- Summary: Record Desktop Metric Sample
- Responses: 200, 422

### `GET /api/desktop/metrics/summary`

- Tags: desktop-sync
- Summary: Get Desktop Metrics Summary
- Responses: 200

### `GET /api/desktop/sync`

- Tags: desktop-sync
- Summary: Sync Desktop Data
- Responses: 200, 422

### `GET /api/desktop/sync/changes`

- Tags: desktop-sync
- Summary: Get Sync Changes
- Responses: 200, 422

### `POST /api/desktop/sync/operations`

- Tags: desktop-sync
- Summary: Apply Sync Operations
- Responses: 200, 422

### `GET /api/desktop/updates/check`

- Tags: desktop-sync
- Summary: Check Desktop Updates
- Responses: 200, 422

### `GET /api/evals/datasets`

- Tags: evals
- Summary: 查询 Eval Dataset
- Responses: 200, 422

### `POST /api/evals/datasets`

- Tags: evals
- Summary: 创建 Eval Dataset
- Responses: 201, 422

### `PATCH /api/evals/datasets/{dataset_id}/baseline`

- Tags: evals
- Summary: 设置基线 Eval Run
- Responses: 200, 422

### `GET /api/evals/datasets/{dataset_id}/cases`

- Tags: evals
- Summary: 查询 Eval Case
- Responses: 200, 422

### `POST /api/evals/datasets/{dataset_id}/cases`

- Tags: evals
- Summary: 创建 Eval Case
- Responses: 201, 422

### `POST /api/evals/datasets/{dataset_id}/cases/from-run/{task_id}`

- Tags: evals
- Summary: 从 Agent Run 保存 Eval Case
- Responses: 201, 422

### `POST /api/evals/datasets/{dataset_id}/experiments`

- Tags: evals
- Summary: Create an Eval contrast experiment projection
- Responses: 201, 422

### `POST /api/evals/datasets/{dataset_id}/runs`

- Tags: evals
- Summary: 启动 Eval Run
- Responses: 201, 422

### `GET /api/evals/experiments`

- Tags: evals
- Summary: List Eval contrast experiments
- Responses: 200, 422

### `GET /api/evals/experiments/{experiment_id}`

- Tags: evals
- Summary: Get Eval contrast experiment detail
- Responses: 200, 422

### `GET /api/evals/results/pending-review`

- Tags: evals
- Summary: 查询待人工审核 Eval Result
- Responses: 200

### `PATCH /api/evals/results/{result_id}/review`

- Tags: evals
- Summary: 提交 Eval Result 人工审核
- Responses: 200, 422

### `GET /api/evals/runs`

- Tags: evals
- Summary: 查询 Eval Run 列表
- Responses: 200, 422

### `GET /api/evals/runs/{eval_run_id}`

- Tags: evals
- Summary: 查询 Eval Run 详情
- Responses: 200, 422

### `GET /api/evals/runs/{eval_run_id}/regression`

- Tags: evals
- Summary: 查询回归 Delta
- Responses: 200, 422

### `GET /api/frontend-errors`

- Tags: frontend-errors
- Summary: 查询前端错误
- Responses: 200, 422

### `POST /api/frontend-errors`

- Tags: frontend-errors
- Summary: 记录前端错误
- Responses: 201, 422

### `GET /api/frontend-errors/summary`

- Tags: frontend-errors
- Summary: 查询前端错误聚合
- Responses: 200

### `POST /api/gateway/{slug}/invoke`

- Tags: api-gateway
- Summary: Invoke published Agent API Gateway route
- Responses: 200, 422

### `GET /api/health/capabilities`

- Tags: health
- Summary: 可选运行能力
- Responses: 200

### `GET /api/health/liveness`

- Tags: health
- Summary: 进程存活探针
- Responses: 200

### `GET /api/health/readiness`

- Tags: health
- Summary: 服务就绪探针
- Responses: 200, 422

### `POST /api/local-runtime/desktop-session`

- Tags: local-runtime
- Summary: Create Desktop Session
- Responses: 204, 422

### `GET /api/local-runtime/model`

- Tags: local-runtime
- Summary: Local Model State
- Responses: 200

### `PUT /api/local-runtime/model-config`

- Tags: local-runtime
- Summary: Apply Model Config
- Responses: 200, 422

### `POST /api/local-runtime/model-discovery`

- Tags: local-runtime
- Summary: Discover Models
- Responses: 200, 422

### `DELETE /api/local-runtime/model-key`

- Tags: local-runtime
- Summary: Delete Model Key
- Responses: 200, 422

### `PUT /api/local-runtime/model-key`

- Tags: local-runtime
- Summary: Apply Model Key
- Responses: 200, 422

### `GET /api/local-runtime/status`

- Tags: local-runtime
- Summary: Local Runtime Status
- Responses: 200

### `POST /api/local-runtime/web-bootstrap`

- Tags: local-runtime
- Summary: Issue Web Bootstrap
- Responses: 200, 422

### `POST /api/local-runtime/web/bootstrap/exchange`

- Tags: local-runtime
- Summary: Exchange Web Bootstrap
- Responses: 204, 422

### `GET /api/mobile/devices`

- Tags: mobile
- Summary: List Mobile Devices
- Responses: 200

### `POST /api/mobile/devices`

- Tags: mobile
- Summary: Register Mobile Device
- Responses: 201, 422

### `GET /api/observability/alert-events`

- Tags: observability
- Summary: 查询告警事件
- Responses: 200, 422

### `GET /api/observability/alert-events/stream`

- Tags: observability
- Summary: 订阅告警事件
- Responses: 200, 422

### `GET /api/observability/alert-rules`

- Tags: observability
- Summary: 查询告警规则
- Responses: 200

### `POST /api/observability/alert-rules`

- Tags: observability
- Summary: 创建告警规则
- Responses: 201, 422

### `POST /api/observability/alert-rules/evaluate`

- Tags: observability
- Summary: 手动评估告警规则
- Responses: 200

### `DELETE /api/observability/alert-rules/{rule_id}`

- Tags: observability
- Summary: 删除告警规则
- Responses: 204, 422

### `PATCH /api/observability/alert-rules/{rule_id}`

- Tags: observability
- Summary: 更新告警规则
- Responses: 200, 422

### `GET /api/observability/architecture`

- Tags: observability
- Summary: 查询运行时架构能力
- Responses: 200

### `GET /api/observability/cost-rollup`

- Tags: observability
- Summary: 查询成本聚合
- Responses: 200, 422

### `GET /api/observability/exports`

- Tags: observability
- Summary: 查询观测导出入口
- Responses: 200

### `GET /api/observability/exports/grafana/dashboards`

- Tags: observability
- Summary: 导出 Grafana Dashboard
- Responses: 200

### `GET /api/observability/exports/history`

- Tags: observability
- Summary: 查询观测导出历史
- Responses: 200, 422

### `GET /api/observability/exports/history/{export_id}/download`

- Tags: observability
- Summary: 下载观测导出历史文件
- Responses: 200, 422

### `GET /api/observability/exports/logs`

- Tags: observability
- Summary: 导出结构化日志
- Responses: 200, 422

### `GET /api/observability/exports/services/health`

- Tags: observability
- Summary: 导出观测服务健康
- Responses: 200

### `GET /api/observability/exports/traces/{trace_id}`

- Tags: observability
- Summary: 导出 Trace 链路
- Responses: 200, 422

### `GET /api/observability/grafana/dashboards`

- Tags: observability
- Summary: 查询 Grafana Dashboard
- Responses: 200

### `GET /api/observability/grounding-quality`

- Tags: observability
- Summary: 查询 Grounding Quality 投影
- Responses: 200, 422

### `GET /api/observability/logs`

- Tags: observability
- Summary: 查询结构化日志
- Responses: 200, 422

### `GET /api/observability/notification-channels`

- Tags: observability
- Summary: 查询外部通知通道
- Responses: 200

### `POST /api/observability/notification-channels`

- Tags: observability
- Summary: 创建外部通知通道
- Responses: 201, 422

### `DELETE /api/observability/notification-channels/{channel_id}`

- Tags: observability
- Summary: 删除外部通知通道
- Responses: 204, 422

### `PATCH /api/observability/notification-channels/{channel_id}`

- Tags: observability
- Summary: 更新外部通知通道
- Responses: 200, 422

### `GET /api/observability/services/health`

- Tags: observability
- Summary: 查询观测服务健康
- Responses: 200

### `GET /api/observability/summary`

- Tags: observability
- Summary: 查询观测聚合摘要
- Responses: 200

### `GET /api/observability/token-savings`

- Tags: observability
- Summary: 查询 Token 节省页面数据
- Responses: 200, 422

### `GET /api/observability/traces`

- Tags: observability
- Summary: 查询 Trace 列表
- Responses: 200, 422

### `GET /api/observability/traces/{trace_id}`

- Tags: observability
- Summary: 查询 Trace 链路
- Responses: 200, 422

### `POST /api/onboarding/autofix/database`

- Tags: onboarding
- Summary: Auto-fix database setup (Story 3.2)
- Responses: 200

### `POST /api/onboarding/autofix/secrets`

- Tags: onboarding
- Summary: Auto-generate missing secrets (Story 3.1)
- Responses: 200

### `POST /api/onboarding/complete`

- Tags: onboarding
- Summary: 完成当前用户引导
- Responses: 200, 422

### `GET /api/onboarding/state`

- Tags: onboarding
- Summary: 查询当前用户引导状态
- Responses: 200

### `PATCH /api/onboarding/state`

- Tags: onboarding
- Summary: 更新当前用户引导进度
- Responses: 200, 422

### `GET /api/onboarding/status`

- Tags: onboarding
- Summary: Get onboarding status (first-run detection)
- Responses: 200

### `GET /api/onboarding/templates`

- Tags: onboarding
- Summary: Get all agent templates (Story 5.1)
- Responses: 200

### `POST /api/onboarding/validate/config`

- Tags: validation
- Summary: Validate configuration
- Responses: 200

### `POST /api/onboarding/validate/deployment`

- Tags: validation
- Summary: Validate deployment readiness
- Responses: 200

### `POST /api/onboarding/validate/system`

- Tags: validation
- Summary: Validate system requirements
- Responses: 200

### `POST /api/onboarding/wizard/complete-step`

- Tags: onboarding
- Summary: Mark wizard step as completed (Story 1.2)
- Responses: 200, 422

### `GET /api/onboarding/wizard/state/{user_id}`

- Tags: onboarding
- Summary: Get wizard state for user (Story 1.2)
- Responses: 200, 422

### `POST /api/onboarding/wizard/transition`

- Tags: onboarding
- Summary: Transition to wizard step (Story 1.2)
- Responses: 200, 422

### `DELETE /api/organizations/{org_id}`

- Tags: data-management
- Summary: Confirm Delete Organization
- Responses: 200, 422

### `DELETE /api/organizations/{org_id}/dry-run`

- Tags: data-management
- Summary: Preview Delete Organization
- Responses: 200, 422

### `POST /api/organizations/{org_id}/export`

- Tags: data-management
- Summary: Export Organization
- Responses: 202, 422

### `GET /api/organizations/{org_id}/exports`

- Tags: data-management
- Summary: List Organization Exports
- Responses: 200, 422

### `GET /api/plugins/marketplace`

- Tags: plugins
- Summary: List Plugin Marketplace
- Responses: 200

### `DELETE /api/plugins/marketplace/{plugin_id}/install`

- Tags: plugins
- Summary: Uninstall Plugin
- Responses: 200, 422

### `POST /api/plugins/marketplace/{plugin_id}/install`

- Tags: plugins
- Summary: Install Plugin
- Responses: 200, 422

### `GET /api/plugins/prompt-templates`

- Tags: plugins
- Summary: List Prompt Templates
- Responses: 200

### `POST /api/plugins/prompt-templates`

- Tags: plugins
- Summary: Create Prompt Template
- Responses: 200, 422

### `DELETE /api/plugins/prompt-templates/{template_id}`

- Tags: plugins
- Summary: Delete Prompt Template
- Responses: 200, 422

### `PUT /api/plugins/prompt-templates/{template_id}`

- Tags: plugins
- Summary: Update Prompt Template
- Responses: 200, 422

### `GET /api/retention/policies`

- Tags: retention
- Summary: List Retention Policies
- Responses: 200

### `PATCH /api/retention/policies/{policy_id}`

- Tags: retention
- Summary: Update Retention Policy
- Responses: 200, 422

### `POST /api/retention/run`

- Tags: retention
- Summary: Run Retention
- Responses: 202

### `GET /api/retention/runs`

- Tags: retention
- Summary: List Retention Runs
- Responses: 200

### `GET /api/sandboxes`

- Tags: sandboxes
- Summary: 查询沙箱列表
- Responses: 200

### `GET /api/sandboxes/quota/history`

- Tags: sandboxes
- Summary: 查询沙箱配额历史
- Responses: 200, 422

### `GET /api/sandboxes/quota/usage`

- Tags: sandboxes
- Summary: 查询沙箱配额用量
- Responses: 200

### `GET /api/sandboxes/warm-pool`

- Tags: sandboxes
- Summary: 查询 WarmPool 状态
- Responses: 200

### `POST /api/sandboxes/warm-pool/benchmark`

- Tags: sandboxes
- Summary: 运行 WarmPool Benchmark
- Responses: 201, 422

### `GET /api/sandboxes/warm-pool/benchmarks`

- Tags: sandboxes
- Summary: 查询 WarmPool Benchmark 记录
- Responses: 200, 422

### `GET /api/sandboxes/{sandbox_id}`

- Tags: sandboxes
- Summary: 查询沙箱详情
- Responses: 200, 422

### `POST /api/sandboxes/{sandbox_id}/terminate`

- Tags: sandboxes
- Summary: 终止沙箱
- Responses: 202, 422

### `GET /api/secrets`

- Tags: secrets
- Summary: 查询密钥库
- Responses: 200

### `PUT /api/secrets`

- Tags: secrets
- Summary: 保存密钥
- Responses: 200, 422

### `POST /api/secrets/import-env`

- Tags: secrets
- Summary: 导入环境变量业务密钥
- Responses: 200

### `DELETE /api/secrets/{secret_id}`

- Tags: secrets
- Summary: 停用密钥
- Responses: 204, 422

### `GET /api/settings/models`

- Tags: settings
- Summary: 查询模型设置
- Responses: 200

### `PUT /api/settings/models`

- Tags: settings
- Summary: 更新模型设置
- Responses: 200, 422

### `GET /api/settings/models/fallbacks`

- Tags: settings
- Summary: 查询模型 fallback 观测
- Responses: 200, 422

### `GET /api/settings/models/health`

- Tags: settings
- Summary: 查询模型健康状态
- Responses: 200

### `GET /api/settings/models/official-status`

- Tags: settings
- Summary: 查询官方模型服务状态
- Responses: 200

### `GET /api/settings/models/pricing-sources`

- Tags: settings
- Summary: 查询内置模型价格官方来源
- Responses: 200

### `GET /api/settings/policies`

- Tags: settings
- Summary: 查询策略设置
- Responses: 200

### `PUT /api/settings/policies`

- Tags: settings
- Summary: 更新策略设置
- Responses: 200, 422

### `DELETE /api/subagent-marketplace/installations/{installation_id}`

- Tags: subagent-marketplace
- Summary: 卸载已安装的市场专家
- Responses: 204, 422

### `GET /api/subagent-marketplace/listings`

- Tags: subagent-marketplace
- Summary: 浏览子 Agent 专家市场
- Responses: 200, 422

### `POST /api/subagent-marketplace/listings`

- Tags: subagent-marketplace
- Summary: 发布子 Agent 专家到市场
- Responses: 201, 422

### `GET /api/subagent-marketplace/listings/{listing_id}`

- Tags: subagent-marketplace
- Summary: 查询专家市场 listing 详情
- Responses: 200, 422

### `PATCH /api/subagent-marketplace/listings/{listing_id}`

- Tags: subagent-marketplace
- Summary: 更新专家市场 listing（不修改审核状态）
- Responses: 200, 422

### `POST /api/subagent-marketplace/listings/{listing_id}/approve`

- Tags: subagent-marketplace
- Summary: 审核专家市场 listing
- Responses: 200, 422

### `POST /api/subagent-marketplace/listings/{listing_id}/install`

- Tags: subagent-marketplace
- Summary: 安装专家市场 listing 到当前组织
- Responses: 201, 422

### `GET /api/subagent-specialists`

- Tags: subagent-specialists
- Summary: 查询子 Agent 专家模板
- Responses: 200, 422

### `POST /api/subagent-specialists`

- Tags: subagent-specialists
- Summary: 创建组织子 Agent 专家模板
- Responses: 201, 422

### `GET /api/subagent-specialists/calibration`

- Tags: subagent-specialists
- Summary: 查询专家选择校准报告
- Responses: 200, 422

### `DELETE /api/subagent-specialists/{specialist_id}`

- Tags: subagent-specialists
- Summary: 归档组织子 Agent 专家模板
- Responses: 204, 422

### `GET /api/subagent-specialists/{specialist_id}`

- Tags: subagent-specialists
- Summary: 查询子 Agent 专家模板详情
- Responses: 200, 422

### `PATCH /api/subagent-specialists/{specialist_id}`

- Tags: subagent-specialists
- Summary: 更新组织子 Agent 专家模板
- Responses: 200, 422

### `POST /api/subagent-specialists/{specialist_id}/preflight`

- Tags: subagent-specialists
- Summary: 预检专家输出契约和预算
- Responses: 200, 422

### `GET /api/subagent-specialists/{specialist_id}/stats`

- Tags: subagent-specialists
- Summary: 查询子 Agent 专家历史表现
- Responses: 200, 422

### `GET /api/subagents`

- Tags: subagents
- Summary: 查询组织子 Agent 列表
- Responses: 200, 422

### `POST /api/subagents/bulk`

- Tags: subagents
- Summary: 批量操作子 Agent
- Responses: 202, 422

### `GET /api/subagents/recovery/global-summary`

- Tags: subagents
- Summary: 查询全局子 Agent 恢复运营摘要
- Responses: 200, 422

### `GET /api/subagents/recovery/global-summary/export`

- Tags: subagents
- Summary: 导出全局子 Agent 恢复运营摘要
- Responses: 200, 422

### `GET /api/subagents/recovery/summary`

- Tags: subagents
- Summary: 查询子 Agent 恢复运营摘要
- Responses: 200, 422

### `GET /api/subagents/{subagent_id}`

- Tags: subagents
- Summary: 查询子 Agent 详情
- Responses: 200, 422

### `POST /api/subagents/{subagent_id}/cancel`

- Tags: subagents
- Summary: 取消子 Agent
- Responses: 202, 422

### `POST /api/subagents/{subagent_id}/fanout/extend`

- Tags: subagents
- Summary: 动态扩缩子 Agent fanout 批次
- Responses: 201, 422

### `POST /api/subagents/{subagent_id}/output`

- Tags: subagents
- Summary: 写入子 Agent 结构化输出
- Responses: 201, 422

### `GET /api/tasks`

- Tags: agent-run-compatibility
- Summary: 兼容层：查询 Agent Run 列表
- Responses: 200, 422

### `POST /api/tasks`

- Tags: agent-run-compatibility
- Summary: 兼容层：创建 Agent Run 记录
- Responses: 201, 422

### `GET /api/tasks/{task_id}`

- Tags: agent-run-compatibility
- Summary: 兼容层：查询 Agent Run 详情
- Responses: 200, 422

### `POST /api/tasks/{task_id}/cancel`

- Tags: agent-run-compatibility
- Summary: 兼容层：取消 Agent Run
- Responses: 202, 422

### `GET /api/tasks/{task_id}/context`

- Tags: agent-run-compatibility
- Summary: 兼容层：查询 Agent Run 记忆与模型路由
- Responses: 200, 422

### `POST /api/tasks/{task_id}/context/route`

- Tags: agent-run-compatibility
- Summary: 兼容层：刷新 Agent Run 上下文路由
- Responses: 202, 422

### `GET /api/tasks/{task_id}/events`

- Tags: agent-run-compatibility
- Summary: 兼容层：查询 Agent Run 事件
- Responses: 200, 422

### `GET /api/tasks/{task_id}/events/stream`

- Tags: agent-run-compatibility
- Summary: 兼容层：订阅 Agent Run 事件流
- Responses: 200, 422

### `GET /api/tasks/{task_id}/fanout-batches`

- Tags: subagents
- Summary: 兼容层：查询 Agent Run fanout 批次
- Responses: 200, 422

### `GET /api/tasks/{task_id}/model-calls`

- Tags: agent-run-compatibility
- Summary: 兼容层：查询模型调用
- Responses: 200, 422

### `GET /api/tasks/{task_id}/plan`

- Tags: agent-run-compatibility
- Summary: 兼容层：查询 Agent Run Plan
- Responses: 200, 422

### `GET /api/tasks/{task_id}/plans`

- Tags: agent-run-compatibility
- Summary: 兼容层：查询 Agent Run Plan 版本
- Responses: 200, 422

### `GET /api/tasks/{task_id}/plans/diff`

- Tags: agent-run-compatibility
- Summary: 兼容层：对比 Agent Run Plan 版本
- Responses: 200, 422

### `POST /api/tasks/{task_id}/replay`

- Tags: agent-run-compatibility
- Summary: 兼容层：Replay Agent Run
- Responses: 200, 422

### `GET /api/tasks/{task_id}/result`

- Tags: agent-run-compatibility
- Summary: 兼容层：查询 Agent Run 结果
- Responses: 200, 422

### `POST /api/tasks/{task_id}/resume`

- Tags: agent-run-compatibility
- Summary: 兼容层：恢复 Agent Run
- Responses: 202, 422

### `POST /api/tasks/{task_id}/start`

- Tags: agent-run-compatibility
- Summary: 兼容层：启动 Agent Run
- Responses: 202, 422

### `GET /api/tasks/{task_id}/steps`

- Tags: agent-run-compatibility
- Summary: 兼容层：查询 Agent Run 步骤
- Responses: 200, 422

### `POST /api/tasks/{task_id}/steps/resume`

- Tags: agent-run-compatibility
- Summary: 兼容层：从指定步骤续跑 Agent Run
- Responses: 202, 422

### `GET /api/tasks/{task_id}/subagents`

- Tags: subagents
- Summary: 兼容层：查询 Agent Run 子 Agent
- Responses: 200, 422

### `POST /api/tasks/{task_id}/subagents`

- Tags: subagents
- Summary: 兼容层：创建 Agent Run 子 Agent
- Responses: 201, 422

### `POST /api/tasks/{task_id}/subagents/recover`

- Tags: subagents
- Summary: 兼容层：恢复 Agent Run 子 Agent
- Responses: 202, 422

### `GET /api/tasks/{task_id}/subagents/recovery-batches`

- Tags: subagents
- Summary: 兼容层：查询 Agent Run 子 Agent 恢复批次
- Responses: 200, 422

### `GET /api/tasks/{task_id}/tool-approvals`

- Tags: agent-run-compatibility
- Summary: 兼容层：查询工具审批
- Responses: 200, 422

### `POST /api/tasks/{task_id}/tool-approvals/{approval_id}/approve`

- Tags: agent-run-compatibility
- Summary: 兼容层：批准工具审批
- Responses: 202, 422

### `POST /api/tasks/{task_id}/tool-approvals/{approval_id}/modify`

- Tags: agent-run-compatibility
- Summary: 兼容层：修改并批准工具审批
- Responses: 202, 422

### `POST /api/tasks/{task_id}/tool-approvals/{approval_id}/reject`

- Tags: agent-run-compatibility
- Summary: 兼容层：拒绝工具审批
- Responses: 202, 422

### `GET /api/tasks/{task_id}/tool-calls`

- Tags: agent-run-compatibility
- Summary: 兼容层：查询工具调用
- Responses: 200, 422

### `POST /api/tasks/{task_id}/tools/execute`

- Tags: agent-run-compatibility
- Summary: 兼容层：执行工具
- Responses: 202, 422

### `GET /api/teams`

- Tags: teams
- Summary: List Teams
- Responses: 200

### `POST /api/teams`

- Tags: teams
- Summary: Create Team
- Responses: 201, 422

### `DELETE /api/teams/{team_id}`

- Tags: teams
- Summary: Archive Team
- Responses: 200, 422

### `GET /api/teams/{team_id}`

- Tags: teams
- Summary: Get Team
- Responses: 200, 422

### `PATCH /api/teams/{team_id}`

- Tags: teams
- Summary: Rename Team
- Responses: 200, 422

### `POST /api/teams/{team_id}/agents`

- Tags: teams
- Summary: Add Team Agent
- Responses: 201, 422

### `DELETE /api/teams/{team_id}/agents/{slot_id}`

- Tags: teams
- Summary: Remove Team Agent
- Responses: 200, 422

### `PATCH /api/teams/{team_id}/agents/{slot_id}`

- Tags: teams
- Summary: Update Team Agent
- Responses: 200, 422

### `POST /api/teams/{team_id}/agents/{slot_id}/mailbox/read`

- Tags: teams
- Summary: Read Team Mailbox
- Responses: 200, 422

### `POST /api/teams/{team_id}/agents/{slot_id}/wake`

- Tags: teams
- Summary: Wake Team Agent
- Responses: 200, 422

### `POST /api/teams/{team_id}/agents/{slot_id}/wake/cancel`

- Tags: teams
- Summary: Cancel Team Agent Wake
- Responses: 200, 422

### `POST /api/teams/{team_id}/agents/{slot_id}/wake/stream`

- Tags: teams
- Summary: Stream Wake Team Agent
- Responses: 200, 422

### `GET /api/teams/{team_id}/events`

- Tags: teams
- Summary: List Team Events
- Responses: 200, 422

### `POST /api/teams/{team_id}/goals`

- Tags: teams
- Summary: Create Team Goal
- Responses: 201, 422

### `GET /api/teams/{team_id}/goals/active`

- Tags: teams
- Summary: Get Active Team Goal
- Responses: 200, 422

### `PATCH /api/teams/{team_id}/goals/{goal_id}`

- Tags: teams
- Summary: Update Team Goal
- Responses: 200, 422

### `POST /api/teams/{team_id}/goals/{goal_id}/supervise`

- Tags: teams
- Summary: Supervise Team Goal
- Responses: 200, 422

### `POST /api/teams/{team_id}/messages`

- Tags: teams
- Summary: Send Team Message
- Responses: 201, 422

### `GET /api/teams/{team_id}/stream`

- Tags: teams
- Summary: Stream Team Events
- Responses: 200, 422

### `GET /api/teams/{team_id}/tasks`

- Tags: teams
- Summary: List Team Tasks
- Responses: 200, 422

### `POST /api/teams/{team_id}/tasks`

- Tags: teams
- Summary: Create Team Task
- Responses: 201, 422

### `PATCH /api/teams/{team_id}/tasks/{task_id}`

- Tags: teams
- Summary: Update Team Task
- Responses: 200, 422

### `POST /api/teams/{team_id}/tools/{tool_name}`

- Tags: teams
- Summary: Call Team Tool
- Responses: 200, 422

### `POST /api/terminal/tokens`

- Tags: terminal
- Summary: Create Terminal Token
- Responses: 200, 422

### `GET /api/tools/adapters`

- Tags: tools
- Summary: List registered real tool adapters
- Responses: 200

### `GET /api/tools/adapters/{slug}/health`

- Tags: tools
- Summary: Probe a registered tool adapter
- Responses: 200, 422

### `POST /api/tools/capabilities/admin-validate`

- Tags: tools
- Summary: Validate capability metadata without execution
- Responses: 200, 422

### `PATCH /api/tools/capabilities/attachments/{attachment_id}`

- Tags: tools
- Summary: Enable or disable an Agent capability attachment
- Responses: 200, 422

### `GET /api/tools/capabilities/dependency-preflight`

- Tags: tools
- Summary: Report v1 capability product dependency and runtime preflight
- Responses: 200

### `POST /api/tools/capabilities/install/trusted-url`

- Tags: tools
- Summary: Install and enable a trusted allowlisted URL capability
- Responses: 201, 422

### `POST /api/tools/capabilities/install/upload`

- Tags: tools
- Summary: Install an uploaded capability package without manifest editing
- Responses: 201, 422

### `GET /api/tools/capabilities/marketplace`

- Tags: tools
- Summary: Browse MCP and Skill marketplace entries
- Responses: 200, 422

### `GET /api/tools/capabilities/packages`

- Tags: tools
- Summary: List staged and installed capability packages
- Responses: 200

### `POST /api/tools/capabilities/packages/private`

- Tags: tools
- Summary: Stage a private capability package without executing code
- Responses: 201, 422

### `POST /api/tools/capabilities/packages/public`

- Tags: tools
- Summary: Stage a public URL/Git capability package with trust controls
- Responses: 201, 422

### `POST /api/tools/capabilities/packages/{package_id}/approve`

- Tags: tools
- Summary: Approve a staged capability package and create an immutable version
- Responses: 200, 422

### `POST /api/tools/capabilities/packages/{package_id}/attachments`

- Tags: tools
- Summary: Attach an approved package capability to an Agent
- Responses: 201, 422

### `POST /api/tools/capabilities/packages/{package_id}/rollback`

- Tags: tools
- Summary: Rollback package current version without mutating historical versions
- Responses: 200, 422

### `POST /api/tools/capabilities/packages/{package_id}/uninstall`

- Tags: tools
- Summary: Uninstall a package when no enabled Agent attachments remain
- Responses: 200, 422

### `POST /api/tools/capabilities/preflight/marketplace`

- Tags: tools
- Summary: Register marketplace metadata for approval without fetching the listed URL
- Responses: 201, 422

### `POST /api/tools/capabilities/preflight/public-url`

- Tags: tools
- Summary: Download and preflight an arbitrary public URL capability without activation
- Responses: 201, 422

### `GET /api/tools/capabilities/runtime-config`

- Tags: tools
- Summary: Get installed MCP runtime configuration
- Responses: 200, 422

### `PATCH /api/tools/capabilities/runtime-config`

- Tags: tools
- Summary: Save installed MCP runtime configuration
- Responses: 200, 422

### `GET /api/tools/capabilities/runtime-configs`

- Tags: tools
- Summary: List installed MCP runtime configuration records
- Responses: 200, 422

### `POST /api/tools/capabilities/staged/{package_id}/enable`

- Tags: tools
- Summary: Enable a staged public capability after validation
- Responses: 200, 422

### `POST /api/tools/capabilities/test-invoke`

- Tags: tools
- Summary: Invoke an attached capability through an Agent-scoped test run
- Responses: 202, 422

### `GET /api/tools/mcp-servers`

- Tags: tools
- Summary: List configured MCP protocol servers
- Responses: 200, 422

### `POST /api/tools/mcp-servers/{tool_name}/discover`

- Tags: tools
- Summary: Discover MCP protocol tools and register child capabilities
- Responses: 200, 422

### `GET /api/tools/registry`

- Tags: tools
- Summary: 查询 Tool Registry
- Responses: 200, 422

### `GET /api/users`

- Tags: users
- Summary: List Users
- Responses: 200

### `POST /api/users`

- Tags: users
- Summary: Invite User
- Responses: 201, 422

### `DELETE /api/users/{user_id}`

- Tags: users
- Summary: Remove User
- Responses: 204, 422

### `PATCH /api/users/{user_id}/role`

- Tags: users
- Summary: Update User Role
- Responses: 200, 422

### `POST /api/webhook/trigger/{endpoint_path}`

- Tags: triggers
- Summary: Invoke public webhook trigger
- Responses: 200, 422

### `GET /health`

- Tags: health
- Summary: 健康检查
- Responses: 200
