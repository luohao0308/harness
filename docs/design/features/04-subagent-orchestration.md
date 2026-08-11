# 04 Subagent 编排 Spec

## 目标

Subagent 负责异步、长耗时、并发探索类任务。主 Executor 不被长任务阻塞，通过 Dramatiq 和 Redis 调度子 Agent。Subagent 是异步执行在产品上的主要体现。

## 用户可见能力

| 能力 | 入口 | 用户结果 |
|---|---|---|
| 查看 Run 子 Agent | `/runs/:runId` | 查看子 Agent 数量、状态和摘要 |
| 查看子 Agent 列表 | `/runs/:runId/subagents` | 查看 Run 下全部子 Agent |
| 查看单个子 Agent | `/subagents/:subagentId` | 查看 assignment、状态、结果和错误 |
| 取消子 Agent | `/subagents/:subagentId` | 子 Agent 进入 `CANCELLED` |
| 查看异步派生关系 | `/runs/:runId` | 从 async step 看到对应子 Agent |
| 查看恢复运营摘要 | `/observability` | 查看组织级和全局恢复批次、扫描数、恢复数和动作统计 |
| 导出全局恢复摘要 | `/observability` | 下载跨组织恢复运营 JSON |
| 批量取消子 Agent | `/subagents` | 选择多个 `PENDING`、`RUNNING` 子 Agent 后统一取消 |
| 查看 Worker 接管 | `/observability`、`/subagents/:subagentId` | 查看卡住 worker 被接管的代次、执行者和恢复批次 |

## 后端契约

```text
GET  /api/tasks/{task_id}/subagents
POST /api/tasks/{task_id}/subagents
POST /api/tasks/{task_id}/subagents/recover
GET  /api/subagents
POST /api/subagents/bulk
GET  /api/subagents/recovery/summary
GET  /api/subagents/recovery/global-summary
GET  /api/subagents/recovery/global-summary/export
GET  /api/subagents/{subagent_id}
POST /api/subagents/{subagent_id}/cancel
```

## 前端入口

| 页面 | 数据来源 | 交互 |
|---|---|---|
| `/runs/:runId` | Subagent API | 展示 Run 相关子 Agent |
| `/runs/:runId/subagents` | Subagent API | 展示列表和状态 |
| `/subagents` | Subagent API | 展示组织级批量状态、状态筛选、任务跳转和详情跳转 |
| `/subagents` | Bulk Subagent API | 选择多个子 Agent 后批量取消 |
| `/subagents/:subagentId` | Subagent API | 展示详情并取消 |
| `/observability` | Recovery Summary API | 展示组织级恢复运营摘要、全局恢复摘要和导出入口 |

异步执行在页面上的体现：

| 页面位置 | 页面显示 | 数据来源 |
|---|---|---|
| 执行计划面板 | `execution_mode=async`、`can_spawn_subagent=true` | Plan API |
| Subagent 面板 | 子 Agent 数量、状态、assignment 摘要 | Subagent API |
| Subagent 列表页 | `PENDING`、`RUNNING`、`SUCCESS`、`FAILED`、`TIMEOUT`、`CANCELLED` | Subagent API |
| 事件时间线 | `SUBAGENT_SPAWNED`、`SUBAGENT_STARTED`、`SUBAGENT_COMPLETED` | Events API |
| 任务结果面板 | 聚合展示子 Agent 状态和结果摘要 | Result API |

## 数据模型

| 数据 | 作用 |
|---|---|
| `agent_runs` | 子 Agent 事实表 |
| `agent_events` | 子 Agent 状态事件 |
| `tasks` | 父任务 |

异步派生字段：

| 字段 | 所在数据 | 说明 |
|---|---|---|
| `agent_runs.task_id` | `agent_runs` | 所属父任务 |
| `agent_runs.parent_agent_id` | `agent_runs` | 父 Agent |
| `agent_runs.context_json.assignment` | `agent_runs` | 子 Agent 任务说明 |
| `agent_runs.status` | `agent_runs` | 子 Agent 当前状态 |
| `task_steps.assigned_agent_id` | `task_steps` | async step 绑定的子 Agent |
| `agent_runs.context_json.result` | `agent_runs` | worker 写回的子 Agent 结果摘要 |
| `agent_runs.context_json.tools[]` | `agent_runs` | 子 Agent assignment 内的工具执行声明 |
| `agent_runs.context_json.result.tool_results[]` | `agent_runs` | 子 Agent 工具执行结果 |
| `agent_runs.context_json.result.artifacts[]` | API 派生 | 子 Agent 工具结果产物摘要 |
| `agent_runs.context_json.result.react_trace[]` | `agent_runs` | 子 Agent 多轮工具规划轨迹 |
| `agent_runs.context_json.result.context_summary` | `agent_runs` | 子 Agent 长上下文压缩摘要 |
| `agent_runs.context_json.max_tool_rounds` | `agent_runs` | 子 Agent ReAct 工具轮次上限，最大 5 |
| `agent_runs.context_json.takeover_generation` | `agent_runs` | Worker 接管代次 |
| `agent_runs.context_json.last_takeover_owner` | `agent_runs` | 最近接管执行者 |
| `agent_runs.context_json.last_takeover_at` | `agent_runs` | 最近接管时间 |
| `subagent_recovery_batches` | 恢复批次 | 手动恢复、自动巡检、跨组织汇总和导出数据源 |

assignment 工具声明：

```json
{
  "step_key": "tool_review",
  "tools": [
    {
      "tool_name": "read_file",
      "input_json": {
        "path": "README.md"
      }
    }
  ]
}
```

## 事件模型

```text
SUBAGENT_SPAWNED
SUBAGENT_STARTED
SUBAGENT_COMPLETED
SUBAGENT_FAILED
SUBAGENT_TIMEOUT
SUBAGENT_CANCELLED
SUBAGENT_PROGRESS stage=worker_takeover
```

## 权限模型

| 能力 | 角色 |
|---|---|
| 查看子 Agent | admin、engineer、operator |
| 创建子 Agent | admin、engineer |
| 取消子 Agent | admin、engineer |
| 批量取消子 Agent | admin、engineer |
| 查看组织恢复摘要 | admin、engineer、operator |
| 查看全局恢复摘要 | admin |
| 导出全局恢复摘要 | admin |

## 状态流转

```text
PENDING -> RUNNING -> SUCCESS
PENDING -> RUNNING -> FAILED
PENDING -> RUNNING -> TIMEOUT
PENDING -> CANCELLED
RUNNING -> CANCELLED
RUNNING -> PENDING 由 Worker 接管触发
```

异步非阻塞流转：

```text
Executor 发现 async step
-> SubagentManager.spawn
-> agent_runs.PENDING
-> 主 Executor 继续后续步骤
-> Dramatiq worker 执行子 Agent
-> Tool Runner 执行 assignment.tools
-> Model Gateway 基于工具结果返回 summary / done / next_tools
-> worker 按 max_tool_rounds 执行下一轮工具
-> tool_calls 写入审计
-> agent_runs.SUCCESS / FAILED / TIMEOUT
-> 父任务聚合结果
```

## 外部服务契约

| 服务 | 用途 |
|---|---|
| Redis 7 | Dramatiq Broker |
| Dramatiq worker | 异步子 Agent 执行 |

## 观测指标

```text
agent_subagents_running
agent_subagents_queued
agent_subagents_failed_total
agent_subagent_duration_seconds
agent_subagent_recovery_total
agent_subagent_recovery_sweeps_total
agent_subagent_recovery_last_recovered
```

## 当前实现状态

| 能力 | 状态 | 证据 |
|---|---|---|
| 子 Agent 创建 | 已落地 | `POST /api/tasks/{task_id}/subagents` |
| 子 Agent 查询 | 已落地 | `GET /api/tasks/{task_id}/subagents` |
| 组织子 Agent 批量查询 | 已落地 | `GET /api/subagents` 支持 `status` 和 `limit` |
| 子 Agent 详情 | 已落地 | `GET /api/subagents/{subagent_id}` |
| 子 Agent 取消 | 已落地 | `POST /api/subagents/{subagent_id}/cancel` |
| 子 Agent 恢复 | 已落地 | `POST /api/tasks/{task_id}/subagents/recover` |
| 自动恢复巡检 | 已落地 | `subagent_recovery_worker` 扫描 `PENDING`、`RUNNING` 子 Agent |
| 恢复批次详情 | 已落地 | 手动恢复和自动巡检返回批次 ID、扫描数量、恢复数量、动作统计和完成时间 |
| 恢复批次历史 | 已落地 | `subagent_recovery_batches` 与 `GET /api/tasks/{task_id}/subagents/recovery-batches` |
| 跨任务恢复运营摘要 | 已落地 | `GET /api/subagents/recovery/summary` 按组织聚合批次数、涉及任务、扫描数、恢复数、锁跳过次数、动作统计和最近批次 |
| 跨组织恢复运营摘要 | 已落地 | `GET /api/subagents/recovery/global-summary` 按组织聚合恢复运营数据，限定 admin |
| 跨组织恢复导出 | 已落地 | `GET /api/subagents/recovery/global-summary/export` 导出 JSON，限定 admin |
| 恢复观测指标 | 已落地 | `/metrics` 与 Grafana 默认 Dashboard 展示恢复动作 |
| 恢复告警规则 | 已落地 | Prometheus 加载 `deploy/monitoring/alert-rules.yml` |
| Worker 崩溃接管 | 已落地 | 卡住 `RUNNING` 子 Agent 重置为 `PENDING`，写入 `takeover_generation`、`last_takeover_owner`、`last_takeover_at` 和 `SUBAGENT_PROGRESS stage=worker_takeover` |
| 子 Agent 批量取消 | 已落地 | `POST /api/subagents/bulk` 与控制台 `/subagents` 选择框、批量取消按钮 |
| 并发上限 | 已落地 | 固定 5 |
| Dramatiq worker | 已落地 | `agent-worker` |
| 异步派生可见性 | 已落地 | 任务详情页 Subagent 面板和 `/subagents` 页面 |
| worker 结果写回 | 已落地 | worker 写入 `SUBAGENT_PROGRESS`、`SUBAGENT_COMPLETED` 和 `context_json.result` |
| 主任务聚合子 Agent 结果 | 已落地 | `GET /api/tasks/{task_id}/result` 返回 `subagent_results` 和 `subagent-results.json` |
| Subagent 工具链执行 | 已落地 | worker 执行 `assignment.tools[]`，写入 `tool_calls` 和 `result.tool_results[]` |
| 多轮 ReAct 工具规划 | 已落地 | worker 支持模型返回 `next_tools`，按 `max_tool_rounds` 继续执行并写入 `react_trace` |
| Subagent 产物详情 | 已落地 | Result API 从工具结果生成 `artifacts[]`；控制台 `/subagents/:subagentId` 展示结果摘要、产物、工具结果、ReAct 轨迹和上下文压缩 |
| 长上下文压缩 | 已落地 | worker 保留完整 `tool_results` 审计记录，模型侧使用 `context_summary.recent_tool_results` 和聚合计数继续规划 |

## 缺口

| 缺口 | 影响 | 目标 |
|---|---|---|
| 派生关系展示 | 已落地，执行计划、Subagent 面板、组织级批量状态页和事件时间线已展示 step key、assigned_agent_id、状态和并行执行拓扑 | 保持页面验收 |
| 批量操作 | 已落地，组织级列表支持选择和批量取消 | 保持权限与审计测试 |
| Worker 接管 | 已落地，恢复批次保存接管代次、执行者和时间 | 保持恢复巡检测试 |

## 实现顺序

```text
1. 固化 agent_runs 字段和状态机
2. 固化批量取消接口和页面
3. 增加超时、接管和批量取消测试
```

## 验收标准

- 超过并发上限的 Subagent 保持 `PENDING`。
- Subagent 状态流转完整。
- 取消动作写入事件。
- 超时任务进入 `TIMEOUT`。
- async step 必须生成 Subagent 记录。
- 任务详情页必须展示异步派生出的 Subagent。
- `/subagents` 必须展示组织级子 Agent 批量状态并支持状态筛选。
- 执行计划面板必须展示异步步骤关联的子 Agent ID 和状态。
- 主任务能读取 Subagent 结果摘要。
- 多轮 ReAct 执行必须写入 `react_trace`。
- 模型返回 `next_tools` 后 worker 必须继续执行下一轮工具。
- Result API 必须返回 Subagent 产物摘要。
- 任务产物列表必须包含 Subagent 产物入口。
- 长上下文执行必须保存完整 `tool_results`，模型请求必须使用压缩后的 `tool_context`。
- 任务结果页和子 Agent 页面必须展示上下文压缩摘要。
- 手动恢复必须在任务详情页展示最近恢复批次摘要。
- 观测页必须展示跨任务恢复运营摘要。
- 观测页必须展示跨组织恢复运营摘要。
- 全局恢复摘要必须限定 admin 访问。
- 全局恢复导出必须返回 JSON 文件。
- 事件时间线必须展示异步步骤到子 Agent 的并行执行拓扑。
- Worker 接管必须写入 `takeover_generation`、`last_takeover_owner` 和 `last_takeover_at`。
- 批量取消必须返回逐条成功、失败和跳过状态。
- `/subagents` 必须展示批量选择和批量取消入口。
