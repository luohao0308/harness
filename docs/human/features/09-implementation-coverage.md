# 09 实现覆盖与缺口 Spec

## 目标

本文件记录当前后端、前端、文档三者的覆盖关系。用途是防止页面、OpenAPI、README 与真实运行时能力脱节。

## 用户可见能力

| 能力 | 入口 | 用户结果 |
|---|---|---|
| 查看已落地功能 | 本文件 | 明确当前可用范围 |
| 查看待增强功能 | 本文件 | 明确后续实现队列 |
| 查看接口覆盖 | 本文件、OpenAPI | 确认功能对应 API |
| 查看页面覆盖 | 本文件、前端规格 | 确认功能对应页面 |

## 后端契约

本文件不新增 API，引用 [OpenAPI](../../api/openapi.yaml) 作为接口事实源。

## 前端入口

本文件不新增页面，引用控制台页面覆盖表。

## 数据模型

不涉及。

## 事件模型

不涉及。

## 权限模型

不涉及。

## 状态流转

```text
待落地 -> 基础落地 -> 已落地
已落地 -> 待增强
待增强 -> 已落地
```

## 外部服务契约

不涉及。

## 观测指标

不涉及。

## 当前实现状态

覆盖口径：

| 状态 | 含义 |
|---|---|
| 已落地 | 有后端接口、数据来源、测试和前端入口 |
| 基础落地 | 有接口和数据链路，生产级策略仍需增强 |
| 待增强 | 文档已定义，代码只覆盖部分行为 |
| 待落地 | 文档已定义，代码尚无稳定入口 |

后端接口覆盖：

| 功能 | 状态 | 接口 |
|---|---|---|
| 任务生命周期 | 已落地 | `POST /api/tasks`、`GET /api/tasks`、`GET /api/tasks/{task_id}`、`POST /api/tasks/{task_id}/start`、`POST /api/tasks/{task_id}/cancel`、`POST /api/tasks/{task_id}/resume`、`GET /api/tasks/{task_id}/result` |
| 计划与步骤 | 已落地 | `GET /api/tasks/{task_id}/plan`、`GET /api/tasks/{task_id}/plans`、`GET /api/tasks/{task_id}/plans/diff`、`GET /api/tasks/{task_id}/steps`、`POST /api/tasks/{task_id}/steps/resume` |
| 事件流 | 已落地 | `GET /api/tasks/{task_id}/events`、`GET /api/tasks/{task_id}/events/stream` |
| Replay | 基础落地 | `POST /api/tasks/{task_id}/replay` |
| Subagent | 已落地 | `GET /api/tasks/{task_id}/subagents`、`POST /api/tasks/{task_id}/subagents`、`POST /api/tasks/{task_id}/subagents/recover`、`GET /api/tasks/{task_id}/subagents/recovery-batches`、`GET /api/subagents`、`POST /api/subagents/bulk`、`GET /api/subagents/recovery/summary`、`GET /api/subagents/recovery/global-summary`、`GET /api/subagents/recovery/global-summary/export`、`GET /api/subagents/{subagent_id}`、`POST /api/subagents/{subagent_id}/cancel` |
| Subagent 结果聚合 | 已落地 | `GET /api/tasks/{task_id}/result` 返回 `subagent_results` |
| Subagent 工具链 | 基础落地 | `GET /api/tasks/{task_id}/tool-calls` 返回 worker 工具审计 |
| 工具执行 | 基础落地 | `POST /api/tasks/{task_id}/tools/execute` |
| 沙箱治理 | 已落地 | `GET /api/sandboxes`、`GET /api/sandboxes/quota/usage`、`GET /api/sandboxes/quota/history`、`GET /api/sandboxes/warm-pool`、`GET /api/sandboxes/{sandbox_id}`、`POST /api/sandboxes/{sandbox_id}/terminate`，Settings 下发 memory、cpu、workspace quota 和 network allowlist |
| 模型审计 | 已落地 | `GET /api/tasks/{task_id}/model-calls`，响应包含 `trace_id`、请求摘要、响应预览和错误信息 |
| 工具审计 | 已落地 | `GET /api/tasks/{task_id}/tool-calls`，支持工具、状态、风险、Trace 筛选和事件/Trace 深链 |
| 模型设置 | 已落地 | `GET /api/settings/models`、`PUT /api/settings/models`、`GET /api/settings/models/health`、`GET /api/settings/models/fallbacks`，覆盖 RPM、TPM、主动探测、供应商熔断和 fallback 观测 |
| 策略设置 | 已落地 | `GET /api/settings/policies`、`PUT /api/settings/policies` |
| 指标与观测 | 已落地 | `GET /api/observability/summary`、`GET /metrics`，summary 返回 `subagent_queue` 队列摘要 |
| 日志观测 | 基础落地 | `GET /api/observability/logs`、Promtail 采集 |
| Trace 观测 | 已落地 | `GET /api/observability/traces/{trace_id}`，支持服务、Span 名称和属性键值过滤 |
| Grafana 集成 | 已落地 | `GET /api/observability/grafana/dashboards`、provisioning、admin/operator RBAC |
| 观测服务健康 | 已落地 | `GET /api/observability/services/health`、admin/operator RBAC |
| 观测导出 | 已落地 | `GET /api/observability/exports`、`GET /api/observability/exports/logs`、`GET /api/observability/exports/traces/{trace_id}`、`GET /api/observability/exports/grafana/dashboards`、`GET /api/observability/exports/services/health`、`GET /api/observability/exports/history`、`GET /api/observability/exports/history/{export_id}/download` |

前端页面覆盖：

| 页面 | 数据来源 | 状态 |
|---|---|---|
| `/tasks` | Task API | 已接入 |
| `/tasks/new` | Task API | 已接入 |
| `/tasks/:taskId` | Task、Result、Events、Replay、Step Resume、Audit、Subagent、Subagent Result | 已接入，执行计划面板支持从指定步骤续跑 |
| `/subagents` | Subagent API | 已接入，展示组织级批量状态、状态筛选、任务跳转、详情跳转和批量取消 |
| `/subagents/:subagentId` | Subagent API、Task Result API | 已接入，展示单个子 Agent assignment、状态、取消、产物、工具结果、ReAct 轨迹和上下文压缩 |
| `/sandboxes` | Sandbox API、Quota API | 已接入，展示 WarmPool、资源配额摘要和历史审计 |
| `/observability` | `GET /api/observability/summary`、`GET /api/subagents/recovery/summary`、`GET /api/subagents/recovery/global-summary` 与 `/metrics` | 已接入，展示运行摘要、队列摘要、组织级恢复运营摘要、全局恢复摘要、导出入口和指标入口 |
| `/observability` 日志区 | `GET /api/observability/logs` | 已接入，支持任务、Trace、服务和事件类型筛选 |
| `/observability` Trace 区 | `GET /api/observability/traces/{trace_id}` | 已接入，支持手动 Trace 查询、日志行跳转和 Span 属性筛选 |
| `/observability` 导出区 | `GET /api/observability/exports`、`GET /api/observability/exports/history` 与下载接口 | 已接入，支持导出日志、Trace、Grafana dashboard、服务健康快照和历史文件 |
| `/settings/models` | Settings API、Model Health API、Model Fallback API | 已接入，展示 RPM、TPM、探测模式、熔断状态和 fallback 观测 |
| `/settings/policies` | Settings API | 已接入 |

## 缺口

| 能力 | 当前缺口 | 目标结果 |
|---|---|---|
| Planner | 已接入 Prompt 1.1、模型 JSON 计划解析、一次结构修复、确定性回退、计划来源展示、计划版本对比、差异可视化和步骤断点续跑契约 | 保持计划回归 |
| Executor | 同步执行、异步步骤派生 Subagent、恢复时跳过已完成步骤、从指定步骤续跑后续未完成步骤已落地 | 保持执行回归 |
| Worker 恢复 | 手动恢复、巡检函数、service loop、跨节点恢复锁、批次详情、批次历史、跨任务恢复运营摘要、跨组织恢复摘要、全局恢复导出、Compose 服务、Prometheus 指标、Grafana 面板和 Prometheus 告警规则已落地 | 保持恢复导出权限和运营页面验证 |
| 同步与异步可视化 | 执行计划已显示中文标签、assigned_agent_id、Subagent 状态链路、步骤续跑动作、组织级批量状态、批量取消和时间线并行执行拓扑 | 保持页面回归 |
| Subagent Worker | assignment 工具执行、工具审计、结果回写、多轮 `next_tools` ReAct 执行、产物摘要、长上下文压缩、组织级批量状态、批量取消、接管元数据、单个子 Agent 详情页和跨任务恢复运营摘要已落地 | 保持恢复回归 |
| Model Gateway | OpenAI-compatible 调用、审计、失败、fallback、fallback 观测、RPM 限流、TPM 限流、主动探测和供应商级熔断已落地 | 保持多供应商回归 |
| Tool Runner | 统一入口和任务级公开执行接口已落地，支持 Settings 策略、低风险工具真实执行、策略拒绝审计、工具结果解析、超时分类、控制台细节、工具审计筛选、Trace 深链和审计详情验收测试 | 保持策略拒绝回归 |
| Replay Snapshot | 每 100 个事件自动生成，Replay 从最近 snapshot 续扫，并发写入和 SSE 断线重连测试已落地 | 保持并发回归 |
| Observability | 聚合 API、深度观测接口、控制台摘要、Prometheus 指标、Grafana Basic Auth 代理、Grafana admin/operator RBAC、服务健康 RBAC、观测导出、导出留存、下载历史、队列图表、配额指标、fallback 指标和 Tempo Trace 查询已落地 | 保持 dashboard 指标覆盖 |
| Loki | 日志接口、Event Store 回退、Loki 容器、Promtail 采集、标签查询和控制台深链筛选已落地 | 增强日志导出 |
| OpenTelemetry | trace_id 响应头、OTLP exporter、OTel Collector、Tempo 存储、Trace 查询接口、Event Store 回退、控制台 Trace 深链和 span 属性检索已落地 | 增强跨服务 Trace 视图 |
| 控制台本地化 | 顶栏语言切换、默认中文、任务、详情、事件、Subagent、子 Agent 详情、沙箱、观测、模型设置和策略设置页面双语已落地 | 持续巡检新增页面表头、按钮、空状态和错误状态 |
| Settings 生效链路 | 模型设置已被 Model Gateway 读取，策略设置已被 Policy Engine、Sandbox Manager 和网络请求策略读取，模型健康探测写回设置快照，沙箱资源规格、network allowlist、配额用量统计和历史审计已落地 | 保持设置回归 |

## 实现顺序

```text
1. 设置持久化与 Subagent 创建接口
2. Planner 异步步骤与 Executor 派生链路
3. Tool Runner 统一入口与策略拒绝审计
4. Model Gateway 真实供应商调用、失败审计、fallback、限流与健康状态
5. Snapshot 自动生成与断点恢复
6. Observability 聚合查询
7. Plan / Step 查询与任务级工具执行接口
8. Observability 外部服务代理与本地化字典化
```

## 验收标准

- README 的已实现说明必须来自本文件和 OpenAPI。
- 前端页面上线前必须有对应后端数据来源。
- 后端接口新增后必须同步 OpenAPI。
- 待落地接口不得写成已落地。
