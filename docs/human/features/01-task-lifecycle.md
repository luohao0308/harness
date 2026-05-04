# 01 任务生命周期

## 目标

任务生命周期负责把用户目标从创建、启动、执行、取消、恢复到结果输出串成闭环。任务是控制台、事件、Subagent、Sandbox、模型调用和工具调用的主线对象。

## 使用入口

| 入口 | 动作 |
|---|---|
| `/tasks` | 查看任务列表、状态、最近事件 |
| `/tasks/new` | 创建任务 |
| `/tasks/:taskId` | 查看任务详情、启动、取消、恢复、查看结果 |

## 后端契约

```text
POST /api/tasks
GET  /api/tasks
GET  /api/tasks/{task_id}
POST /api/tasks/{task_id}/start
POST /api/tasks/{task_id}/cancel
POST /api/tasks/{task_id}/resume
GET  /api/tasks/{task_id}/result
```

## 状态

```text
CREATED
PLANNING
RUNNING
WAITING_SUBAGENTS
FAILED
COMPLETED
CANCELLED
```

## 事件与数据

| 数据 | 作用 |
|---|---|
| `tasks` | 任务事实表 |
| `execution_plans` | Planner 输出计划 |
| `task_steps` | 步骤执行状态 |
| `agent_events` | 任务全量事件流 |

## 联动

- 创建任务写入 `TASK_CREATED`。
- 启动任务触发 Planner 和 Executor。
- 取消任务写入 `TASK_CANCELLED`。
- 恢复任务写入 `TASK_RESUMED`。
- 结果接口聚合任务状态、摘要、产物、最后事件序号。

## 验收

- 未认证请求返回 401。
- 跨组织读取返回 404。
- 启动任务后生成计划与事件。
- 完成任务后 result 返回摘要和产物。
- 取消和恢复动作在事件流中可见。
