# 07 Settings 与 Observability Spec

## 目标

Settings 管理运行规则。Observability 展示运行结果。两者共同构成平台运行面。

## 用户可见能力

| 能力 | 入口 | 用户结果 |
|---|---|---|
| 管理模型设置 | `/settings/models` | 设置供应商、模型、限流、健康状态 |
| 管理策略设置 | `/settings/policies` | 设置工具风险、审批、沙箱、审计要求 |
| 查看运营摘要 | `/observability` | 查看任务、模型、工具、沙箱和队列指标 |
| 查看 Prometheus 指标 | `/metrics` | 获取 Prometheus exposition 格式指标 |

## 后端契约

```text
GET /api/settings/models
PUT /api/settings/models
GET /api/settings/models/health
GET /api/settings/policies
PUT /api/settings/policies
GET /api/observability/summary
GET /metrics
```

深度观测契约：

```text
GET /api/observability/grafana/dashboards
GET /api/observability/logs
GET /api/observability/traces/{trace_id}
GET /api/observability/services/health
```

详细规格见 [Observability 与本地化规格](./10-observability-localization-spec.md)。

## 前端入口

| 页面 | 数据来源 | 交互 |
|---|---|---|
| `/settings/models` | Settings Models API | 查看、编辑、保存模型设置 |
| `/settings/policies` | Settings Policies API | 查看、编辑、保存策略设置 |
| `/observability` | Observability Summary、Metrics | 查看摘要、指标和运行状态 |

## 数据模型

| 数据表 | 作用 |
|---|---|
| `system_settings` | 保存组织级模型设置与策略设置 |
| `admin_audit_events` | 保存设置变更审计 |
| `tasks` | 观测任务状态 |
| `model_calls` | 观测模型调用 |
| `tool_calls` | 观测工具调用 |
| `sandbox_instances` | 观测沙箱运行状态 |

## 事件模型

```text
ADMIN_ACTION
POLICY_CHECKED
POLICY_DENIED
MODEL_CALLED
TOOL_CALLED
SANDBOX_ALLOCATED
```

## 权限模型

| 能力 | 角色 |
|---|---|
| settings read | admin、engineer |
| settings write | admin |
| observability read | admin、operator |
| task metrics read | project member |

## 状态流转

```text
读取设置 -> 修改设置 -> 写入 system_settings -> 写入 ADMIN_ACTION -> 后续运行读取新设置
运行数据 -> 事件与审计表 -> 聚合接口 -> 控制台观测页面
```

## 外部服务契约

| 服务 | 用途 |
|---|---|
| Prometheus | 指标抓取与查询 |
| Grafana | 仪表盘展示 |
| Loki | 结构化日志查询 |
| OpenTelemetry | trace 采集与查询 |

## 观测指标

```text
agent_tasks_total
agent_tasks_running
agent_tasks_failed_total
agent_task_duration_seconds
agent_subagents_running
sandbox_containers_running
warm_pool_idle_containers
warm_pool_hit_total
model_calls_total
model_call_errors_total
```

## 当前实现状态

| 能力 | 状态 | 证据 |
|---|---|---|
| 模型设置读取 | 已落地 | `GET /api/settings/models` |
| 模型设置写入 | 已落地 | `PUT /api/settings/models` |
| 模型设置生效 | 已落地 | Model Gateway 读取组织级默认模型、供应商和限流 |
| 模型健康状态 | 已落地 | `GET /api/settings/models/health` |
| 策略设置读取 | 已落地 | `GET /api/settings/policies` |
| 策略设置写入 | 已落地 | `PUT /api/settings/policies` |
| 策略设置生效 | 已落地 | Tool Runner 读取组织级风险、角色、审批和沙箱要求 |
| 沙箱设置生效 | 已落地 | Sandbox Manager 读取默认网络和默认超时 |
| Observability 聚合 API | 已落地 | `GET /api/observability/summary` |
| 设置变更审计 | 已落地 | `admin_audit_events` |
| Model Gateway 读取设置 | 已落地 | Model Gateway |
| Policy Engine 读取设置 | 已落地 | Policy Engine |
| Grafana / Loki 控制台入口 | 基础落地 | `/observability` 已展示日志、Trace、Dashboard 和服务健康 |

## 缺口

| 缺口 | 影响 | 目标 |
|---|---|---|
| Loki 真实采集链路 | 当前接口已按 Event Store 回退，外部采集仍需增强 | JSON 日志进入 Loki 并按标签查询 |
| Grafana 鉴权和 provisioning | 当前接口有 Grafana 查询和配置回退 | 后端代理 Grafana dashboard 元数据和权限 |
| Trace 后端集成 | 当前接口已按 Event Store 合成 span | 后端查询真实 OTel Trace 并返回 span 列表 |

## 实现顺序

```text
1. 保持 Settings API 与 OpenAPI 同步
2. 保持 Settings 生效链路测试
3. 增加 Loki、Grafana、Trace 代理接口
4. 前端补日志页、Trace 页和 dashboard 深链
5. 更新部署 Runbook 和排障 Runbook
```

## 验收标准

- 非 admin 修改设置返回 403。
- admin 修改设置返回 200。
- 设置变更写入审计。
- 设置变更重新读取后保持最新值。
- 策略变更影响后续工具调用。
- 沙箱策略变更影响后续沙箱创建和命令执行。
- Observability 聚合结果按组织隔离。
- Observability 展示任务、模型、工具、沙箱指标。
- 控制台 settings 页面不使用占位页。
