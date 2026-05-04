# 06 模型与工具审计

## 目标

模型调用和工具调用必须有数据库事实源、事件审计和控制台展示。审计能力用于合规、排障、成本分析和策略复盘。

## 使用入口

| 入口 | 动作 |
|---|---|
| `/tasks/:taskId` | 查看模型调用和工具调用 |
| `/observability` | 查看模型与工具指标 |
| `/settings/models` | 管理模型网关 |
| `/settings/policies` | 管理工具策略 |

## 后端契约

```text
GET /api/tasks/{task_id}/model-calls
GET /api/tasks/{task_id}/tool-calls
```

## 数据

| 数据 | 作用 |
|---|---|
| `model_calls` | 模型请求、响应、token、耗时、fallback |
| `tool_calls` | 工具名称、输入摘要、输出摘要、耗时、策略结果 |

## 事件

```text
MODEL_CALLED
MODEL_RESPONSE_RECEIVED
MODEL_CALL_FAILED
MODEL_FALLBACK_USED
POLICY_CHECKED
TOOL_CALLED
TOOL_RESULT_RECEIVED
TOOL_FAILED
TOOL_TIMEOUT
TOOL_DENIED_BY_POLICY
```

## 联动

- Planner 和 Executor 调用 Model Gateway。
- Tool Registry 执行工具前触发 Policy Engine。
- 模型与工具事件写入 Event Store。
- 审计表提供控制台列表和指标聚合。
- Settings 改变后续模型与工具行为。

## 验收

- 每次模型调用有审计记录。
- 每次工具调用有审计记录。
- 策略拒绝有事件和审计记录。
- 控制台展示模型调用列表。
- 控制台展示工具调用列表。
