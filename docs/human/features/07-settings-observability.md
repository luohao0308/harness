# 07 Settings 与 Observability

## 目标

Settings 管理运行规则。Observability 展示运行结果。两者共同构成平台运行面。

## 使用入口

| 页面 | 动作 |
|---|---|
| `/settings/models` | 管理模型供应商、模型、限流、健康状态 |
| `/settings/policies` | 管理工具风险、审批、沙箱、审计要求 |
| `/observability` | 查看任务、模型、工具、沙箱和队列指标 |

## 后端契约

```text
GET /api/settings/models
PUT /api/settings/models
GET /api/settings/policies
PUT /api/settings/policies
GET /metrics
```

## 权限

```text
settings read: admin
settings write: admin
observability read: admin / operator
task metrics read: project member
```

## 指标

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

## 联动

- Settings 写入 ADMIN_ACTION。
- 模型设置影响 Model Gateway。
- 策略设置影响 Tool Registry 和 Sandbox。
- Observability 从 Prometheus、事件和审计表汇总运行状态。
- 告警用于提示任务失败、队列积压、沙箱失败和 WarmPool 命中率异常。

## 验收

- 非 admin 修改设置返回 403。
- admin 修改设置返回 200。
- 设置变更写入事件。
- Observability 展示任务、模型、工具、沙箱指标。
- 控制台 settings 页面不使用占位页。
