# 02 Planner 与 Executor Spec

## 目标

Planner 把用户目标拆成结构化计划。Executor 按计划执行步骤，并通过 ReAct 循环驱动工具、模型和 Subagent。目标分解与执行架构必须明确区分同步执行和异步执行。

目标架构：

```text
目标分解与执行架构
├─ Planner：目标分解与规划
├─ Executor：同步执行（ReAct Engine）
└─ Subagent：异步执行（长时间任务）
```

## 用户可见能力

| 能力 | 入口 | 用户结果 |
|---|---|---|
| 输入目标 | `/agents/:agentId/workspace` | 在 Workspace 中输入目标 |
| 只规划不执行 | `/agents/:agentId/workspace` | 生成结构化计划和 Agent Run 投影，Run 状态为 `PLANNED` |
| 查看计划 | `/runs/:runId` | 查看计划版本、步骤和原始 JSON |
| 查看步骤 | `/runs/:runId` | 查看步骤状态、耗时和错误 |
| 执行工具 | `/runs/:runId` 或 Workspace Tool Card | 按策略执行工具并记录审计 |
| 查看同步执行 | `/runs/:runId` | 计划步骤显示 `sync`，步骤由 Executor 直接执行 |
| 查看异步执行 | `/runs/:runId`、`/runs/:runId/subagents` | 计划步骤显示 `async`，步骤派生 Subagent 并展示子 Agent 状态 |
| 查看计划版本 | `/runs/:runId` | 查看计划版本数量、最新版本和相邻版本差异 |
| 从步骤断点续跑 | `/runs/:runId` | 选择步骤作为断点，从该步骤继续执行后续未完成步骤 |

## 后端契约

```text
POST /api/agents/plan
POST /api/agents/runs/{run_id}/execute
POST /api/tasks/{task_id}/start
GET  /api/tasks/{task_id}/result
GET  /api/tasks/{task_id}/plan
GET  /api/tasks/{task_id}/plans
GET  /api/tasks/{task_id}/plans/diff
GET  /api/tasks/{task_id}/steps
POST /api/tasks/{task_id}/steps/resume
POST /api/tasks/{task_id}/tools/execute
```

## 前端入口

| 页面 | 数据来源 | 交互 |
|---|---|---|
| `/agents/:agentId/workspace` | Workspace Pro stream API | workspace surface 创建 Agent Run、展示计划、工具意图和产物 |
| `/runs/:runId` | Agent Run Workspace projection | 执行同一个已规划 Run、查看计划、事件、工具、Subagent 和 Replay |
| deprecated `/api/tasks/*` compatibility | Task compatibility API | 兼容内部存储和旧 API，不作为当前产品入口 |

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

步骤断点续跑契约：

| 字段 | 所在数据 | 说明 |
|---|---|---|
| `step_keys` | Step Resume Request | 人工选择的断点步骤键列表 |
| `resume_mode=from_first_selected` | Step Resume Request | 从计划顺序中最靠前的步骤键续跑 |
| `resume_from_step_key` | Step Resume Response | 实际续跑断点 |
| `resumed_step_keys` | Step Resume Response | 本次实际执行的步骤 |
| `skipped_step_keys` | Step Resume Response | 本次跳过的已完成步骤 |
| `pending_step_keys` | Step Resume Response | 重放后仍未完成的步骤 |

## 事件模型

```text
PLAN_REQUESTED
PLAN_GENERATED
TASK_STARTED
STEP_STARTED
STEP_COMPLETED
STEP_FAILED
STEP_RETRIED
STEP_SKIPPED
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
| 步骤断点续跑 | admin、engineer |

## 状态流转

```text
PLAN_MODE_REQUESTED -> TASK_CREATED -> PLAN_REQUESTED -> PLAN_GENERATED -> PLANNED
TASK_CREATED -> PLANNING -> RUNNING
STEP_PENDING -> STEP_RUNNING -> STEP_COMPLETED
STEP_PENDING -> STEP_RUNNING -> STEP_FAILED
STEP_RUNNING -> SUBAGENT_SPAWNED -> WAITING_SUBAGENTS
TASK_FAILED -> TASK_RESUMED -> STEP_RETRIED -> STEP_COMPLETED
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
| Agent Plan-Act Workspace | 基础落地 | `POST /api/agents/{agent_id}/runs/chat/stream` 和 `/agents/:agentId/workspace` |
| Agent Execute 已确认计划 | 基础落地 | `POST /api/agents/runs/{run_id}/execute` 复用最新计划 |
| 计划查询接口 | 已落地 | `GET /api/tasks/{task_id}/plan` |
| 计划版本接口 | 已落地 | `GET /api/tasks/{task_id}/plans` |
| 计划版本对比 | 已落地 | `GET /api/tasks/{task_id}/plans/diff` |
| 计划版本差异可视化 | 已落地 | 控制台执行计划面板展示新增、变更和移除步骤清单 |
| 步骤查询接口 | 已落地 | `GET /api/tasks/{task_id}/steps` |
| 步骤断点续跑接口 | 已落地 | `POST /api/tasks/{task_id}/steps/resume` |
| 步骤断点续跑控制台动作 | 已落地 | 执行计划面板展示“从此续跑” |
| 步骤重试事件 | 已落地 | `STEP_RETRIED` |
| 步骤跳过事件 | 已落地 | `STEP_SKIPPED` |
| LLM Planner | 已落地 | Model Gateway 返回结构化 JSON 时直接作为计划来源 |
| LLM Planner Prompt 1.1 | 已落地 | Prompt 要求工具意图、验收标准、风险等级和预期产物 |
| LLM Planner 结构重试 | 已落地 | 第一次模型计划非法时，自动请求修复一次 |
| LLM Planner 质量治理 | 已落地 | Plan API 返回 `quality_score`、`quality_gates`、`validation_warnings` 和 `planner_prompt_version` |
| 计划来源展示 | 已落地 | Plan API 和控制台展示 `planner_source`、`planner_attempts` 和步骤元数据 |
| 异步步骤识别 | 已落地 | 模型 JSON 或关键词触发 async 步骤 |
| Executor 步骤执行 | 已落地 | 同步步骤写入工具审计与事件 |
| Executor ReAct 轨迹细节 | 已落地 | Plan API 每个步骤返回 `trace_summary`、`last_event_sequence` 和 `execution_trace` |
| Subagent 派生 | 已落地 | async 步骤写入 `agent_runs` 并请求 Dramatiq 入队 |
| 真实 Tool Runner | 已落地 | 低风险文件工具真实执行，高风险工具进入沙箱路径 |
| 工具公开执行接口 | 已落地 | `POST /api/tasks/{task_id}/tools/execute` |
| 并行执行拓扑 | 已落地 | 控制台事件时间线展示异步步骤到子 Agent 的拓扑链路 |
| Worker 跨进程接管 | 已落地 | `SubagentManager.recover_for_task`、`SUBAGENT_PROGRESS stage=worker_takeover`、恢复批次和接管元数据 |

## 缺口

| 缺口 | 影响 | 目标 |
|---|---|---|
| Full-spec Workspace Pro gaps | Workspace Pro 垂直切片已落地，但 tool_call_result、continue run/branch 语义、Artifacts 抽取和前端测试基础设施仍需追踪 | 在 Workspace Pro gap register 中逐项验证和实现 |
| deprecated `/api/tasks/*` 兼容层仍存在 | 文档若混用 Task 当前入口会误导用户 | 产品概念统一为 Agent Run，Task 仅作为兼容实现细节 |
| Execute 不能复用 Plan-only Run | 用户确认计划后无法在同一个 Run 继续执行 | `POST /api/agents/runs/{run_id}/execute` 执行现有计划且不重新规划 |
| 只有 Subagent 派生 | 只能表达单个 Run 内的异步分工，不是多 Agent 编排 | 引入 Agent Router、Orchestrator、handoff、parallel fan-out、reduce |

## 实现顺序

```text
1. 固化 Plan / Step schema
2. 新增 Agent Plan-only API
3. 通过 Agent Workspace 创建 Agent Run
4. 新增 Agent Execute existing-plan API
5. 保持 Executor ReAct 循环轨迹回归
6. 保持 Worker 跨进程接管回归
7. 新增多 Agent 编排层
```

## 验收标准

- 每个 Agent Run 有结构化计划。
- 每个步骤有稳定 key 和状态。
- 同步步骤在计划和步骤接口中显示 `execution_mode=sync`。
- 异步步骤在计划和步骤接口中显示 `execution_mode=async`。
- 异步步骤必须生成 `agent_runs` 记录，并在 Subagent 面板展示。
- Agent Execute API 必须执行已确认计划，不新增第二个 `PLAN_GENERATED`。
- 异步步骤在执行计划面板展示关联子 Agent ID 和状态。
- Plan API 返回计划来源和尝试次数。
- Plan API 返回步骤工具意图、验收标准、风险等级和预期产物。
- Plan Version API 返回版本列表和版本差异。
- 控制台必须展示计划版本新增、变更和移除步骤清单。
- 控制台必须在 Run 失败或取消后展示步骤级“从此续跑”动作。
- Step Resume API 必须写入 `TASK_RESUMED`、`STEP_RETRIED` 和 `STEP_SKIPPED`。
- Step Resume API 必须从最靠前的请求步骤继续执行后续未完成步骤。
- Step Resume API 必须返回实际断点、执行步骤、跳过步骤和剩余步骤。
- 事件时间线必须展示异步步骤到子 Agent 的并行执行拓扑。
- 工具动作不绕过 Tool Registry。
- 高风险动作不绕过 Sandbox。
- 事件流能还原执行顺序。
