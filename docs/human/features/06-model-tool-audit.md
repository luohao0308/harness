# 06 模型与工具审计 Spec

## 目标

模型调用和工具调用必须有数据库事实源、事件审计和控制台展示。审计能力用于合规、排障、成本分析和策略复盘。

## 用户可见能力

| 能力 | 入口 | 用户结果 |
|---|---|---|
| 查看模型调用 | `/tasks/:taskId` | 查看供应商、模型、token、耗时和失败 |
| 查看工具调用 | `/tasks/:taskId` | 查看工具、入参摘要、结果摘要、耗时和策略 |
| 筛选工具审计 | `/tasks/:taskId` | 按工具、状态、风险和 Trace 定位工具调用 |
| 执行工具 | `/tasks/:taskId` | 按策略执行工具并写入审计 |
| 查看指标 | `/observability` | 查看模型和工具汇总指标 |
| 管理策略 | `/settings/models`、`/settings/policies` | 调整模型网关和工具策略 |

## 后端契约

```text
GET  /api/tasks/{task_id}/model-calls
GET  /api/tasks/{task_id}/tool-calls?tool_name=&status=&risk_level=&trace_id=&limit=
POST /api/tasks/{task_id}/tools/execute
```

## 前端入口

| 页面 | 数据来源 | 交互 |
|---|---|---|
| `/tasks/:taskId` | Model Calls、Tool Calls、Tool Execute | 审计列表、工具筛选、Trace 深链和工具执行 |
| `/observability?trace_id=` | Observability Trace | 从工具审计跳转 Trace 链路 |
| `/observability` | Observability Summary | 模型与工具指标 |
| `/settings/models` | Settings API | 模型供应商、模型、限流、健康状态 |
| `/settings/policies` | Settings API | 工具风险、审批、沙箱、审计要求 |

## 数据模型

| 数据 | 作用 |
|---|---|
| `model_calls` | 模型请求、响应、token、耗时、fallback |
| `tool_calls` | 工具名称、输入摘要、输出摘要、耗时、策略结果 |
| `system_settings` | 模型与工具策略 |
| `agent_events` | 模型、工具和策略事件 |

## 事件模型

```text
MODEL_CALLED
MODEL_RESPONSE_RECEIVED
MODEL_CALL_FAILED
MODEL_FALLBACK_USED
POLICY_CHECKED
POLICY_DENIED
TOOL_CALLED
TOOL_RESULT_RECEIVED
TOOL_FAILED
TOOL_TIMEOUT
TOOL_DENIED_BY_POLICY
```

## 权限模型

| 能力 | 角色 |
|---|---|
| 查看模型审计 | admin、engineer、operator |
| 查看工具审计 | admin、engineer、operator |
| 执行低风险工具 | admin、engineer |
| 执行高风险工具 | admin、engineer，且策略允许 |
| 修改模型和工具策略 | admin |

## 状态流转

```text
MODEL_CALLED -> MODEL_RESPONSE_RECEIVED
MODEL_CALLED -> MODEL_CALL_FAILED -> MODEL_FALLBACK_USED
POLICY_CHECKED -> TOOL_CALLED -> TOOL_RESULT_RECEIVED
POLICY_CHECKED -> POLICY_DENIED
TOOL_CALLED -> TOOL_FAILED
TOOL_CALLED -> TOOL_TIMEOUT
```

## 外部服务契约

| 服务 | 用途 |
|---|---|
| OpenAI-compatible Provider | 模型调用 |
| Docker Sandbox | 高风险工具隔离 |
| Prometheus | 模型与工具指标 |

## 观测指标

```text
model_calls_total
model_call_duration_seconds
model_call_errors_total
model_tokens_input_total
model_tokens_output_total
tool_calls_total
tool_call_duration_seconds
tool_call_errors_total
tool_policy_denied_total
```

## 当前实现状态

| 能力 | 状态 | 证据 |
|---|---|---|
| `model_calls` 表 | 已落地 | 数据库模型 |
| `tool_calls` 表 | 已落地 | 数据库模型 |
| 模型审计查询 | 已落地 | `GET /api/tasks/{task_id}/model-calls` |
| 工具审计查询 | 已落地 | `GET /api/tasks/{task_id}/tool-calls` |
| 任务级工具执行接口 | 已落地 | `POST /api/tasks/{task_id}/tools/execute` |
| Tool Registry 元数据 | 已落地 | `tool-registry.yaml` |
| Tool Runner 策略入口 | 已落地 | `runner.py` |
| Policy Engine 读取 Settings | 已落地 | Policy Engine |
| 低风险文件工具真实执行 | 已落地 | Tool Runner |
| 高风险工具无沙箱拒绝 | 已落地 | Policy Engine |
| 角色策略拒绝 | 已落地 | Policy Engine |
| 高风险工具沙箱真实执行 | 基础落地 | Docker Sandbox 路径 |
| Model Gateway OpenAI-compatible 调用 | 基础落地 | Model Gateway |
| Model Gateway 读取 Settings | 已落地 | Model Gateway |
| 模型 RPM 限流 | 已落地 | Model Gateway |
| 模型 TPM 限流 | 已落地 | Model Gateway 按组织、供应商和模型估算 prompt token |
| 模型健康主动探测 | 已落地 | `GET /api/settings/models/health` 探测真实供应商并写回健康快照 |
| 供应商级熔断 | 已落地 | Model Gateway 连续失败达到阈值后快速拒绝并触发 fallback 流程 |
| 模型健康状态接口 | 已落地 | `GET /api/settings/models/health` 返回探测模式、熔断状态和连续失败次数 |
| 模型调用成功审计 | 已落地 | `model_calls` |
| 模型调用失败审计 | 已落地 | `model_calls` |
| 模型 fallback 事件 | 已落地 | `MODEL_FALLBACK_USED` |
| 工具产物摘要 | 基础落地 | Result API 从工具结果派生 Subagent `artifacts[]` |
| 工具结果解析 | 基础落地 | Tool Call API 返回 `output_kind`、`output_summary` 和 `timeout_category` |
| 控制台工具审计详情 | 基础落地 | 控制台展示工具输出类型、输出摘要、沙箱标记、风险等级和超时分类 |
| 工具审计筛选和深链 | 已落地 | `GET /api/tasks/{task_id}/tool-calls` 支持 `tool_name`、`status`、`risk_level`、`trace_id` 和 `limit`；响应返回 `trace_id`；控制台可跳转任务事件和观测 Trace |

## 缺口

| 缺口 | 影响 | 目标 |
|---|---|---|
| 控制台审计详情验收测试 | 页面能力已有实现，自动验收仍需增强 | 覆盖模型审计、工具审计和策略拒绝展示 |

## 实现顺序

```text
1. 保持审计表与 OpenAPI 同步
2. 补控制台审计详情验收测试
```

## 验收标准

- 每次模型调用有审计记录。
- 每次工具调用有审计记录。
- 策略拒绝有事件和审计记录。
- 控制台展示模型调用列表。
- 控制台展示工具调用列表。
- 控制台展示工具输出类型、摘要和超时分类。
- 工具审计 API 必须支持按 `tool_name`、`status`、`risk_level` 和 `trace_id` 筛选。
- 工具审计响应必须返回关联 `trace_id`。
- 控制台工具审计必须能跳转任务事件和观测 Trace。
- 控制台展示模型 TPM、健康探测和供应商熔断状态。
- 高风险工具必须经过策略检查和沙箱路径。
