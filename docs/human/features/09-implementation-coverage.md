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
| 计划与步骤 | 基础落地 | `GET /api/tasks/{task_id}/plan`、`GET /api/tasks/{task_id}/plans`、`GET /api/tasks/{task_id}/plans/diff`、`GET /api/tasks/{task_id}/steps` |
| 事件流 | 已落地 | `GET /api/tasks/{task_id}/events`、`GET /api/tasks/{task_id}/events/stream` |
| Replay | 基础落地 | `POST /api/tasks/{task_id}/replay` |
| Subagent | 已落地 | `GET /api/tasks/{task_id}/subagents`、`POST /api/tasks/{task_id}/subagents`、`POST /api/tasks/{task_id}/subagents/recover`、`GET /api/subagents/{subagent_id}`、`POST /api/subagents/{subagent_id}/cancel` |
| Subagent 结果聚合 | 已落地 | `GET /api/tasks/{task_id}/result` 返回 `subagent_results` |
| Subagent 工具链 | 基础落地 | `GET /api/tasks/{task_id}/tool-calls` 返回 worker 工具审计 |
| 工具执行 | 基础落地 | `POST /api/tasks/{task_id}/tools/execute` |
| 沙箱治理 | 已落地 | `GET /api/sandboxes`、`GET /api/sandboxes/warm-pool`、`GET /api/sandboxes/{sandbox_id}`、`POST /api/sandboxes/{sandbox_id}/terminate` |
| 模型审计 | 基础落地 | `GET /api/tasks/{task_id}/model-calls` |
| 工具审计 | 基础落地 | `GET /api/tasks/{task_id}/tool-calls` |
| 模型设置 | 已落地 | `GET /api/settings/models`、`PUT /api/settings/models`、`GET /api/settings/models/health` |
| 策略设置 | 已落地 | `GET /api/settings/policies`、`PUT /api/settings/policies` |
| 指标与观测 | 已落地 | `GET /api/observability/summary`、`GET /metrics` |
| 日志观测 | 基础落地 | `GET /api/observability/logs`、Promtail 采集 |
| Trace 观测 | 基础落地 | `GET /api/observability/traces/{trace_id}` |
| Grafana 集成 | 基础落地 | `GET /api/observability/grafana/dashboards`、provisioning |
| 观测服务健康 | 基础落地 | `GET /api/observability/services/health` |

前端页面覆盖：

| 页面 | 数据来源 | 状态 |
|---|---|---|
| `/tasks` | Task API | 已接入 |
| `/tasks/new` | Task API | 已接入 |
| `/tasks/:taskId` | Task、Result、Events、Replay、Audit、Subagent、Subagent Result | 已接入 |
| `/subagents` | Subagent API | 已接入 |
| `/sandboxes` | Sandbox API | 已接入 |
| `/observability` | `GET /api/observability/summary` 与 `/metrics` | 已接入 |
| `/observability` 日志区 | `GET /api/observability/logs` | 基础接入 |
| `/observability` Trace 区 | `GET /api/observability/traces/{trace_id}` | 基础接入 |
| `/settings/models` | Settings API | 已接入 |
| `/settings/policies` | Settings API | 已接入 |

## 缺口

| 能力 | 当前缺口 | 目标结果 |
|---|---|---|
| Planner | 已接入 Prompt 1.1、模型 JSON 计划解析、一次结构修复、确定性回退、计划来源展示、计划版本对比和差异可视化 | 增强步骤级断点续跑 |
| Executor | 同步执行、异步步骤派生 Subagent、恢复时跳过已完成步骤已落地 | 增强 Worker 恢复批次历史查询 |
| Worker 恢复 | 手动恢复、巡检函数、service loop、跨节点恢复锁、批次详情、Compose 服务、Prometheus 指标、Grafana 面板和 Prometheus 告警规则已基础落地 | 增强恢复批次历史查询 |
| 同步与异步可视化 | 执行计划已显示中文标签、assigned_agent_id、Subagent 状态链路和时间线并行执行拓扑 | 增强批量状态展示 |
| Subagent Worker | assignment 工具执行、工具审计、结果回写、多轮 `next_tools` ReAct 执行、产物摘要和长上下文压缩已基础落地 | 增强恢复批次历史查询 |
| Model Gateway | OpenAI-compatible 调用、审计、失败、fallback、RPM 限流和健康状态已基础落地 | 补齐 TPM 限流、外部主动探测和供应商级熔断 |
| Tool Runner | 统一入口和任务级公开执行接口已落地，支持 Settings 策略、低风险工具真实执行和策略拒绝审计 | 补齐更多沙箱工具结果解析、超时分类和控制台细节 |
| Replay Snapshot | 每 100 个事件自动生成，Replay 从最近 snapshot 续扫 | 增强恢复批次查询 |
| Observability | 聚合 API、深度观测接口、控制台摘要、Prometheus 指标和 Grafana Basic Auth 代理已落地 | 补齐队列图表与 Grafana 权限模型 |
| Loki | 日志接口、Event Store 回退、Loki 容器、Promtail 采集和标签查询已落地 | 增强日志检索深链 |
| OpenTelemetry | trace_id 响应头、Trace 查询接口和 Event Store 合成 span 已落地 | 接入真实 OTel Trace 后端 |
| 控制台本地化 | 顶栏语言切换基础落地，全页面字典化待落地 | 所有页面表头、按钮、空状态和错误状态双语 |
| Settings 生效链路 | 模型设置已被 Model Gateway 读取，策略设置已被 Policy Engine 和 Sandbox Manager 读取 | 资源规格、网络 allowlist 和供应商熔断增强 |

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
