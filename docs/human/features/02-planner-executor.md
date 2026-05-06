# 02 Planner 与 Executor Spec

## 目标

Planner 把用户目标拆成结构化计划。Executor 按计划执行步骤，并通过 ReAct 循环驱动工具、模型和 Subagent。任务分解与执行架构必须明确区分同步执行和异步执行。

目标架构：

```text
任务分解与执行架构
├─ Planner：任务分解与规划
├─ Executor：同步执行（ReAct Engine）
└─ Subagent：异步执行（长时间任务）
```

## 用户可见能力

| 能力 | 入口 | 用户结果 |
|---|---|---|
| 输入目标 | `/tasks/new` | 创建待规划任务 |
| 查看计划 | `/tasks/:taskId` | 查看计划版本、步骤和原始 JSON |
| 查看步骤 | `/tasks/:taskId` | 查看步骤状态、耗时和错误 |
| 执行工具 | `/tasks/:taskId` | 按策略执行工具并记录审计 |
| 查看同步执行 | `/tasks/:taskId` | 计划步骤显示 `sync`，步骤由 Executor 直接执行 |
| 查看异步执行 | `/tasks/:taskId`、`/tasks/:taskId/subagents` | 计划步骤显示 `async`，步骤派生 Subagent 并展示子 Agent 状态 |
| 查看计划版本 | `/tasks/:taskId` | 查看计划版本数量、最新版本和相邻版本差异 |

## 后端契约

```text
POST /api/tasks/{task_id}/start
GET  /api/tasks/{task_id}/result
GET  /api/tasks/{task_id}/plan
GET  /api/tasks/{task_id}/plans
GET  /api/tasks/{task_id}/plans/diff
GET  /api/tasks/{task_id}/steps
POST /api/tasks/{task_id}/tools/execute
```

## 前端入口

| 页面 | 数据来源 | 交互 |
|---|---|---|
| `/tasks/new` | Task API | 输入目标、模型、策略和沙箱约束 |
| `/tasks/:taskId` | Plan、Steps、Tool Execute、Subagent API | 查看同步步骤、异步步骤、工具执行结果和子 Agent |

同步与异步在页面上的体现：

| 类型 | 页面位置 | 页面显示 | 数据来源 |
|---|---|---|---|
| 同步执行 | 执行计划面板 | 步骤 `execution_mode=sync`、状态 `STEP_STARTED` 到 `STEP_COMPLETED` | `GET /api/tasks/{task_id}/plan`、`GET /api/tasks/{task_id}/steps` |
| 同步执行 | 事件时间线 | `STEP_STARTED`、`TOOL_CALLED`、`TOOL_RESULT_RECEIVED`、`STEP_COMPLETED` | `GET /api/tasks/{task_id}/events` |
| 异步执行 | 执行计划面板 | 步骤 `execution_mode=async`、`can_spawn_subagent=true` | `GET /api/tasks/{task_id}/plan` |
| 异步执行 | Subagent 面板 | 子 Agent `PENDING`、`RUNNING`、`SUCCESS`、`FAILED`、`TIMEOUT` | `GET /api/tasks/{task_id}/subagents` |
| 异步执行 | 事件时间线 | `SUBAGENT_SPAWNED` 与后续 Subagent 状态事件 | `GET /api/tasks/{task_id}/events` |

## 数据模型

| 数据 | 作用 |
|---|---|
| `execution_plans` | 计划版本、结构化步骤、原始 JSON |
| `task_steps` | 步骤 key、状态、执行结果和错误 |
| `tool_calls` | Executor 工具调用审计 |
| `model_calls` | Planner 与 Executor 模型调用审计 |

同步与异步字段：

| 字段 | 所在数据 | 说明 |
|---|---|---|
| `execution_mode=sync` | `execution_plans.plan_json.steps[]`、`task_steps.execution_mode` | Executor 同步执行 |
| `execution_mode=async` | `execution_plans.plan_json.steps[]`、`task_steps.execution_mode` | Executor 派生 Subagent |
| `can_spawn_subagent=true` | `execution_plans.plan_json.steps[]` | 该步骤允许异步派生 |
| `assigned_agent_id` | `task_steps` | 异步步骤绑定的 `agent_runs.id` |
| `agent_runs.status` | `agent_runs` | 子 Agent 状态 |
| `planner_source` | `execution_plans.plan_json`、Plan API | `llm`、`llm_repaired`、`deterministic` |
| `planner_attempts` | `execution_plans.plan_json`、Plan API | 计划生成尝试次数 |
| `execution_plans.version` | `execution_plans`、Plan Version API | 计划版本号 |

## 事件模型

```text
PLAN_REQUESTED
PLAN_GENERATED
STEP_STARTED
STEP_COMPLETED
STEP_FAILED
TOOL_CALLED
TOOL_RESULT_RECEIVED
TOOL_FAILED
SUBAGENT_SPAWNED
```

同步执行事件：

```text
STEP_STARTED
TOOL_CALLED
TOOL_RESULT_RECEIVED
STEP_COMPLETED
```

异步执行事件：

```text
STEP_STARTED
SUBAGENT_SPAWNED
STEP_COMPLETED
SUBAGENT_STARTED
SUBAGENT_COMPLETED
SUBAGENT_FAILED
SUBAGENT_TIMEOUT
```

## 权限模型

| 能力 | 角色 |
|---|---|
| 启动计划 | admin、engineer |
| 查看计划 | admin、engineer、operator |
| 执行工具 | admin、engineer |

## 状态流转

```text
TASK_CREATED -> PLANNING -> RUNNING
STEP_PENDING -> STEP_RUNNING -> STEP_COMPLETED
STEP_PENDING -> STEP_RUNNING -> STEP_FAILED
STEP_RUNNING -> SUBAGENT_SPAWNED -> WAITING_SUBAGENTS
```

执行模式流转：

```text
sync step -> Executor -> Tool / Model -> STEP_COMPLETED
async step -> Executor -> SubagentManager.spawn -> agent_runs.PENDING -> Dramatiq worker -> SUCCESS/FAILED/TIMEOUT
```

## 外部服务契约

| 服务 | 用途 |
|---|---|
| LLM Provider | 真实 Planner 与 ReAct 推理 |
| Docker Sandbox | 高风险工具隔离执行 |
| Redis / Dramatiq | 异步步骤派生 Subagent |

## 观测指标

```text
agent_task_duration_seconds
model_calls_total
model_call_duration_seconds
tool_calls_total
tool_call_duration_seconds
agent_subagents_running
```

## 当前实现状态

| 能力 | 状态 | 证据 |
|---|---|---|
| 结构化计划 | 已落地 | `planner.py` 先解析模型 JSON，失败时回退确定性计划 |
| 计划查询接口 | 已落地 | `GET /api/tasks/{task_id}/plan` |
| 计划版本接口 | 已落地 | `GET /api/tasks/{task_id}/plans` |
| 计划版本对比 | 已落地 | `GET /api/tasks/{task_id}/plans/diff` |
| 步骤查询接口 | 已落地 | `GET /api/tasks/{task_id}/steps` |
| LLM Planner | 基础落地 | Model Gateway 返回结构化 JSON 时直接作为计划来源 |
| LLM Planner 结构重试 | 基础落地 | 第一次模型计划非法时，自动请求修复一次 |
| 计划来源展示 | 基础落地 | Plan API 和控制台展示 `planner_source`、`planner_attempts` |
| 异步步骤识别 | 基础落地 | 模型 JSON 或关键词触发 async 步骤 |
| Executor 步骤执行 | 基础落地 | 同步步骤写入工具审计与事件 |
| Subagent 派生 | 基础落地 | async 步骤写入 `agent_runs` 并请求 Dramatiq 入队 |
| 真实 Tool Runner | 基础落地 | 低风险文件工具真实执行，高风险工具进入沙箱路径 |
| 工具公开执行接口 | 已落地 | `POST /api/tasks/{task_id}/tools/execute` |

## 缺口

| 缺口 | 影响 | 目标 |
|---|---|---|
| LLM Planner 增强 | 当前已解析模型 JSON，并支持一次结构修复与版本对比 | 增强 Prompt |
| 步骤级断点续跑 | Worker 崩溃后的执行恢复仍需增强 | 以 Replay state 驱动 Worker 恢复 |
| 异步执行可视化 | 基础落地，已展示中文标签、派生子 Agent ID 和状态 | 增强时间线中的并行执行拓扑 |

## 实现顺序

```text
1. 固化 Plan / Step schema
2. 增强 LLM Planner Prompt
3. 增强计划版本差异可视化
4. 增强 Executor ReAct 循环
5. 补 Worker 级恢复与验收测试
6. 增强时间线中的并行执行拓扑
```

## 验收标准

- 每个任务有结构化计划。
- 每个步骤有稳定 key 和状态。
- 同步步骤在计划和步骤接口中显示 `execution_mode=sync`。
- 异步步骤在计划和步骤接口中显示 `execution_mode=async`。
- 异步步骤必须生成 `agent_runs` 记录，并在 Subagent 面板展示。
- 异步步骤在执行计划面板展示关联子 Agent ID 和状态。
- Plan API 返回计划来源和尝试次数。
- Plan Version API 返回版本列表和版本差异。
- 工具动作不绕过 Tool Registry。
- 高风险动作不绕过 Sandbox。
- 事件流能还原执行顺序。
