# 04 Subagent 编排 Spec

## 目标

Subagent 负责异步、长耗时、并发探索类任务。主 Executor 不被长任务阻塞，通过 Dramatiq 和 Redis 调度子 Agent。Subagent 是异步执行在产品上的主要体现。

## 用户可见能力

| 能力 | 入口 | 用户结果 |
|---|---|---|
| 查看任务子 Agent | `/tasks/:taskId` | 查看子 Agent 数量、状态和摘要 |
| 查看子 Agent 列表 | `/tasks/:taskId/subagents` | 查看任务下全部子 Agent |
| 查看单个子 Agent | `/subagents/:subagentId` | 查看 assignment、状态、结果和错误 |
| 取消子 Agent | `/subagents/:subagentId` | 子 Agent 进入 `CANCELLED` |
| 查看异步派生关系 | `/tasks/:taskId` | 从 async step 看到对应子 Agent |

## 后端契约

```text
GET  /api/tasks/{task_id}/subagents
POST /api/tasks/{task_id}/subagents
POST /api/tasks/{task_id}/subagents/recover
GET  /api/subagents/{subagent_id}
POST /api/subagents/{subagent_id}/cancel
```

## 前端入口

| 页面 | 数据来源 | 交互 |
|---|---|---|
| `/tasks/:taskId` | Subagent API | 展示任务相关子 Agent |
| `/tasks/:taskId/subagents` | Subagent API | 展示列表和状态 |
| `/subagents/:subagentId` | Subagent API | 展示详情并取消 |

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
```

## 权限模型

| 能力 | 角色 |
|---|---|
| 查看子 Agent | admin、engineer、operator |
| 创建子 Agent | admin、engineer |
| 取消子 Agent | admin、engineer |

## 状态流转

```text
PENDING -> RUNNING -> SUCCESS
PENDING -> RUNNING -> FAILED
PENDING -> RUNNING -> TIMEOUT
PENDING -> CANCELLED
RUNNING -> CANCELLED
```

异步非阻塞流转：

```text
Executor 发现 async step
-> SubagentManager.spawn
-> agent_runs.PENDING
-> 主 Executor 继续后续步骤
-> Dramatiq worker 执行子 Agent
-> Tool Runner 执行 assignment.tools
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
| 子 Agent 详情 | 已落地 | `GET /api/subagents/{subagent_id}` |
| 子 Agent 取消 | 已落地 | `POST /api/subagents/{subagent_id}/cancel` |
| 子 Agent 恢复 | 基础落地 | `POST /api/tasks/{task_id}/subagents/recover` |
| 自动恢复巡检 | 基础落地 | `subagent_recovery_worker` 扫描 `PENDING`、`RUNNING` 子 Agent |
| 恢复观测指标 | 已落地 | `/metrics` 与 Grafana 默认 Dashboard 展示恢复动作 |
| 并发上限 | 已落地 | 固定 5 |
| Dramatiq worker | 基础落地 | `agent-worker` |
| 异步派生可见性 | 基础落地 | 任务详情页 Subagent 面板和 `/subagents` 页面 |
| worker 结果写回 | 基础落地 | worker 写入 `SUBAGENT_PROGRESS`、`SUBAGENT_COMPLETED` 和 `context_json.result` |
| 主任务聚合子 Agent 结果 | 已落地 | `GET /api/tasks/{task_id}/result` 返回 `subagent_results` 和 `subagent-results.json` |
| Subagent 工具链执行 | 基础落地 | worker 执行 `assignment.tools[]`，写入 `tool_calls` 和 `result.tool_results[]` |

## 缺口

| 缺口 | 影响 | 目标 |
|---|---|---|
| 子 Agent 长任务执行增强 | 当前 worker 已接入 assignment 工具链，复杂多轮工具规划仍需增强 | worker 按 ReAct 循环组织模型、工具和沙箱并回写结构化结果 |
| 自动恢复巡检告警 | 当前已有巡检函数、service loop、Compose 服务和指标 | 接入告警规则 |
| 派生关系展示 | 基础落地，执行计划和 Subagent 面板已展示 step key、assigned_agent_id 和状态 | 增强时间线中的并行执行拓扑 |

## 实现顺序

```text
1. 固化 agent_runs 字段和状态机
2. 增强 Dramatiq worker 多轮 ReAct 工具链
3. 增强父任务结果聚合产物详情
4. 增加超时和取消测试
5. 前端补详情页和批量状态展示
```

## 验收标准

- 超过并发上限的 Subagent 保持 `PENDING`。
- Subagent 状态流转完整。
- 取消动作写入事件。
- 超时任务进入 `TIMEOUT`。
- async step 必须生成 Subagent 记录。
- 任务详情页必须展示异步派生出的 Subagent。
- 执行计划面板必须展示异步步骤关联的子 Agent ID 和状态。
- 主任务能读取 Subagent 结果摘要。
