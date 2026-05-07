# 01 任务生命周期 Spec

## 目标

任务生命周期负责把用户目标从创建、启动、执行、取消、恢复到结果输出串成闭环。任务是控制台、事件、Subagent、Sandbox、模型调用和工具调用的主线对象。

## 用户可见能力

| 能力 | 入口 | 用户结果 |
|---|---|---|
| 创建任务 | `/tasks/new` | 生成任务并进入 `CREATED` |
| 查看任务 | `/tasks`、`/tasks/:taskId` | 查看任务状态、目标、事件和结果 |
| 启动任务 | `/tasks/:taskId` | 触发 Planner 与 Executor |
| 取消任务 | `/tasks/:taskId` | 任务进入 `CANCELLED` |
| 恢复任务 | `/tasks/:taskId` | 从 Replay 状态继续执行 |
| 从步骤续跑 | `/tasks/:taskId` | 从指定步骤继续执行后续未完成步骤 |
| 查看结果 | `/tasks/:taskId` | 查看摘要、产物和最后事件序号 |

## 后端契约

```text
POST /api/tasks
GET  /api/tasks
GET  /api/tasks/{task_id}
POST /api/tasks/{task_id}/start
POST /api/tasks/{task_id}/cancel
POST /api/tasks/{task_id}/resume
POST /api/tasks/{task_id}/steps/resume
GET  /api/tasks/{task_id}/result
```

## 前端入口

| 页面 | 数据来源 | 交互 |
|---|---|---|
| `/tasks` | Task API | 列表、状态筛选、进入详情 |
| `/tasks/new` | Task API | 输入目标并创建任务 |
| `/tasks/:taskId` | Task、Result、Events、Replay、Step Resume | 启动、取消、恢复、步骤续跑、查看结果 |

## 数据模型

| 数据 | 作用 |
|---|---|
| `tasks` | 任务事实表 |
| `execution_plans` | Planner 输出计划 |
| `task_steps` | 步骤执行状态 |
| `agent_events` | 任务全量事件流 |

## 事件模型

```text
TASK_CREATED
TASK_STARTED
TASK_CANCELLED
TASK_RESUMED
TASK_FAILED
TASK_COMPLETED
STEP_SKIPPED
STEP_RETRIED
```

## 权限模型

| 能力 | 角色 |
|---|---|
| 创建任务 | admin、engineer |
| 查看任务 | admin、engineer、operator |
| 启动任务 | admin、engineer |
| 取消任务 | admin、engineer |
| 恢复任务 | admin、engineer |
| 步骤续跑 | admin、engineer |

## 状态流转

```text
CREATED -> PLANNING -> RUNNING -> COMPLETED
CREATED -> PLANNING -> RUNNING -> FAILED
RUNNING -> WAITING_SUBAGENTS -> RUNNING
RUNNING -> CANCELLED
FAILED -> RUNNING
FAILED -> TASK_RESUMED -> STEP_RETRIED -> RUNNING
```

## 外部服务契约

不涉及。

## 观测指标

```text
agent_tasks_total
agent_tasks_running
agent_tasks_failed_total
agent_task_duration_seconds
agent_task_resume_total
```

## 当前实现状态

| 能力 | 状态 | 证据 |
|---|---|---|
| 创建任务 | 已落地 | `POST /api/tasks` |
| 启动任务 | 已落地 | `POST /api/tasks/{task_id}/start` |
| 取消任务 | 已落地 | `POST /api/tasks/{task_id}/cancel` |
| 恢复任务 | 已落地 | `POST /api/tasks/{task_id}/resume` |
| 步骤续跑 | 已落地 | `POST /api/tasks/{task_id}/steps/resume` |
| result 查询 | 已落地 | `GET /api/tasks/{task_id}/result` |
| 恢复时复用计划 | 已落地 | Executor 恢复链路 |
| 恢复时跳过已完成步骤 | 已落地 | `STEP_SKIPPED` |
| 恢复时继续失败步骤 | 已落地 | Replay state |
| 步骤续跑返回执行结果 | 已落地 | Step Resume Response |
| 分布式 Worker 级断点续跑 | 已落地 | `POST /api/tasks/{task_id}/subagents/recover`、恢复批次、Worker 接管事件和恢复运营摘要 |

## 缺口

| 缺口 | 影响 | 目标 |
|---|---|---|
| 无当前缺口 | 任务生命周期 API、状态机、步骤续跑、事件和 Worker 恢复链路已落地 | 保持任务恢复、步骤续跑和恢复运营回归 |

## 实现顺序

```text
1. 保持 Task API 与 OpenAPI 同步
2. 保持 Task 状态机与 Event Store 同步
3. 前端详情页读取 result、events、replay 和 audit 数据
4. 保持 Worker 级恢复编排回归
5. 更新覆盖文档和测试
```

## 验收标准

- 未认证请求返回 401。
- 跨组织读取返回 404。
- 启动任务后生成计划与事件。
- 完成任务后 result 返回摘要和产物。
- 取消和恢复动作在事件流中可见。
- 恢复任务不重复生成已有计划。
- 恢复任务不重复执行已完成步骤。
- 步骤续跑必须写入 `TASK_RESUMED`、`STEP_RETRIED` 和 `STEP_SKIPPED`。
