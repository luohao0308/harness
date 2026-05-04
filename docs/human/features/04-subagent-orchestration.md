# 04 Subagent 编排

## 目标

Subagent 负责异步、长耗时、并发探索类任务。主 Executor 不被长任务阻塞，通过 Dramatiq 和 Redis 调度子 Agent。

## 使用入口

| 入口 | 动作 |
|---|---|
| `/tasks/:taskId` | 查看任务下的 Subagent |
| `/tasks/:taskId/subagents` | 查看 Subagent 列表 |
| `/subagents/:subagentId` | 查看单个 Subagent |

## 后端契约

```text
GET  /api/tasks/{task_id}/subagents
GET  /api/subagents/{subagent_id}
POST /api/subagents/{subagent_id}/cancel
```

## 状态

```text
PENDING
RUNNING
SUCCESS
FAILED
TIMEOUT
CANCELLED
```

## 约束

```text
最大并发：5
默认超时：900 秒
队列：Redis
worker：Dramatiq
子 Agent 不再派生子 Agent
```

## 联动

- Planner 标记 async 步骤。
- Executor 派生 Subagent。
- Subagent 写入状态事件。
- Parent Executor 聚合 Subagent 结果。
- Timeout 写入事件并进入失败处理。

## 验收

- 超过并发上限的 Subagent 保持 PENDING。
- Subagent 状态流转完整。
- 取消动作写入事件。
- 超时任务进入 TIMEOUT。
- 主任务能读取 Subagent 结果摘要。
