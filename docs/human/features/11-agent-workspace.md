# 11 Agent Workspace 与 Plan 模式 Spec

## 目标

产品主入口必须是 Agent，而不是后台记录创建页。最终目标是生产级 AI Agent 平台：用户能通过 Agent Workspace 看到模型、工具、规划、执行、隔离、事件溯源和多 Agent 编排如何组合成一个可运行、可审计、可恢复的 Agent。

用户先选择或配置 Agent，再在对话工作台中选择运行模式：

```text
Agent Workspace
├─ Chat：普通协作对话
├─ Plan：只做目标分解与规划，不执行工具
├─ Execute：按已确认计划执行
└─ Auto：自动规划、执行、观察和修正
```

产品语义中不存在“主任务”。用户发起的是 `Agent Session` 和 `Agent Run`；`tasks` 表只是当前兼容存储实现，界面和 API 新增能力必须使用 Run 语义。Planner、Executor、Subagent、Sandbox、Event Sourcing 和 WarmPool 是 Agent Run 背后的运行时能力。

`Subagent` 不是完整的多 Agent 编排系统。Subagent 是 Run 中某个异步步骤派生出的工作单元；多 Agent 编排还必须包含 Agent Registry、Agent Router、Orchestrator、handoff、parallel fan-out、reduce/merge 和跨 Agent 事件关联。

## 用户可见能力

| 能力 | 入口 | 用户结果 |
|---|---|---|
| 选择 Agent | `/agents`、`/agents/:agentId/chat` | 用户看到可用 Agent 和默认模型 |
| Plan 模式 | `/agents/:agentId/chat` | 输入目标后返回结构化计划，不执行工具 |
| Execute 模式 | `/agents/:agentId/chat` | 按计划执行，展示工具调用、沙箱和结果 |
| Auto 模式 | `/agents/:agentId/chat` | 自动规划并执行，必要时派生 Subagent |
| 多 Agent 编排 | `/agents/:agentId/chat`、Run 详情 | 一个 Run 中由 Router 选择多个具名 Agent 协作，并展示交接与聚合 |
| 查看 Run 详情 | `/runs/:runId` 或兼容 `/tasks/:taskId` | 展示计划、事件、工具、Subagent、Sandbox 和产物 |
| 模型切换 | `/settings/models` | 添加预置/自定义模型并设为 Agent 默认模型 |

## 后端契约

首个 Agent Workspace 交付先复用 `tasks` 表作为 Run 存储，同时新增 Agent 语义入口：

```text
POST /api/agents/plan
POST /api/agents/runs
POST /api/agents/runs/{run_id}/execute
POST /api/agents/runs/{run_id}/orchestrate
GET  /api/agents/runs/{run_id}
GET  /api/agents/runs/{run_id}/events
GET  /api/agents
GET  /api/agents/{agent_id}
```

首个最小实现必须落地：

```text
POST /api/agents/plan
```

该接口只运行 Planner，写入当前兼容事件名 `TASK_CREATED`、`PLAN_REQUESTED`、`PLAN_GENERATED`，Run 状态保持 `PLANNED`，不会调用 Executor、Tool、Subagent 或 Sandbox。

第二个实现必须落地：

```text
POST /api/agents/runs/{run_id}/execute
```

该接口执行 Plan 模式已经生成的同一个 Run，不重新规划，不新增第二个 `PLAN_GENERATED`。

## 前端入口

| 页面 | 数据来源 | 交互 |
|---|---|---|
| `/agents` | Agent presets、Model Settings | 查看 Agent 列表和默认模型 |
| `/agents/:agentId/chat` | Agent Plan API、Run APIs、Event SSE | 选择 Chat/Plan/Execute/Auto，输入目标并查看 Agent 输出 |
| `/runs` | Run API；当前可复用 Task API 兼容层 | 历史运行记录 |
| `/runs/:runId` | Run Detail；当前可复用 Task Detail 兼容层 | 运行详情和审计 |

Plan 模式页面必须包含：

```text
顶部：Agent 名称、默认模型、模式切换
中间：用户消息与 Agent Plan 响应
右侧：结构化 Plan、风险、工具意图、是否需要 Subagent/Sandbox
底部：输入框、Plan 按钮、Execute 按钮
```

## 数据模型

首个实现复用：

| 数据 | 作用 |
|---|---|
| `tasks` | 当前实现中的 Agent Run 兼容存储 |
| `execution_plans` | Plan 模式输出 |
| `agent_events` | Plan/Run 审计事件 |
| `model_calls` | Planner 模型调用审计 |

后续正式模型：

| 数据 | 作用 |
|---|---|
| `agents` | Agent 配置、默认模型、工具权限和系统提示词 |
| `agent_sessions` | 对话会话 |
| `agent_messages` | 用户与 Agent 消息 |
| `agent_runs` | 每次执行记录 |
| `agent_assignments` | 多 Agent 编排中的 Agent 选择、角色、输入和输出 |
| `agent_handoffs` | Agent 之间的交接记录 |

## 事件模型

Plan 模式事件：

```text
TASK_CREATED
PLAN_REQUESTED
MODEL_CALLED
MODEL_RESPONSE_RECEIVED
PLAN_GENERATED
```

Execute/Auto 模式继续使用：

```text
TASK_STARTED
STEP_STARTED
TOOL_CALLED
TOOL_RESULT_RECEIVED
SUBAGENT_SPAWNED
SANDBOX_ALLOCATED
TASK_COMPLETED
```

多 Agent 编排需要新增：

```text
AGENT_SELECTED
AGENT_HANDOFF_STARTED
AGENT_HANDOFF_COMPLETED
AGENT_PARALLEL_FANOUT_STARTED
AGENT_PARALLEL_BRANCH_COMPLETED
AGENT_REDUCE_COMPLETED
```

## 权限模型

| 能力 | 角色 |
|---|---|
| 使用 Agent Plan/Chat/Execute | admin、engineer |
| 查看 Run 详情 | admin、engineer、operator |
| 修改 Agent 默认模型 | admin |

## 状态流转

Plan-only：

```text
CREATED -> PLANNING -> PLANNED
```

Execute：

```text
PLANNED -> RUNNING -> COMPLETED
PLANNED -> RUNNING -> FAILED
```

Auto：

```text
CREATED -> PLANNING -> RUNNING -> WAITING_SUBAGENTS -> COMPLETED
```

## 当前实现状态

| 能力 | 状态 | 证据 |
|---|---|---|
| Run 兼容存储 | 已落地 | `/api/tasks`、`/api/tasks/{id}/start` 当前作为兼容实现 |
| Planner 引擎 | 已落地 | `DeterministicPlanner`、`Executor.start_task` |
| Plan 面板 | 已落地但入口错误 | `/tasks/:taskId` 中的 `ExecutionPlanPanel` |
| Agent 对话工作台 | 基础落地 | `/agents/:agentId/chat` |
| Chat Session | 基础落地 | `agent_sessions`、`agent_messages`、Chat 模式发送消息 |
| Plan 模式 | 基础落地 | `POST /api/agents/plan` |
| Execute 已确认计划 | 基础落地 | `POST /api/agents/runs/{run_id}/execute` |
| Auto 模式 | 基础落地 | `POST /api/agents/auto` 自动 Plan、编排、执行 |
| 模型切换 | 基础落地 | `/settings/models` 支持预置、自定义和默认切换 |
| Agent 注册表 | 基础落地 | `GET /api/agents`、`GET /api/agents/{agent_id}`、`/agents` |
| 多 Agent 编排 | 基础落地 | 创建并执行 assignments，Reducer 聚合输出 |
| 编排入队运行 | 基础落地 | Workspace 可将 assignments 投递到 Dramatiq worker 队列 |
| Run 详情编排视图 | 基础落地 | Run 详情展示 assignments、handoff 边和 reduce 输出 |

## 缺口

| 缺口 | 影响 | 目标 |
|---|---|---|
| 用户看不到 Agent | 产品像后台运行记录系统 | 新增 Agent Workspace |
| Plan 模式不是显式交互 | 用户不知道目标分解在哪里 | 模式切换中提供 Plan |
| Sandbox/Subagent 暴露为后台概念 | 用户不知道何时使用 | 作为 Execute/Auto 的运行细节自动出现 |
| 模型配置不可操作 | 无法像 `cc switch` 一样切换模型 | 模型页支持预置、自定义和默认切换 |
| Run 详情拓扑仍偏基础 | 用户能看到节点/边列表但不是可交互图 | 增加可交互拓扑和分支耗时 |

## 实现顺序

```text
1. 新增 Agent Workspace Spec 和路由定义
2. 新增 POST /api/agents/plan
3. 新增 /agents/:agentId/chat Plan 模式页面
4. 新增 POST /api/agents/runs/{run_id}/execute，执行已确认计划
5. 将 /tasks 文案逐步迁移为 /runs
6. 新增 Agent Registry 与 Agent Router
7. 新增 Multi-agent Orchestrator，支持 handoff、parallel fan-out、reduce
8. 增加 agent/session/message 正式数据模型
9. Run 详情新增多 Agent 编排拓扑
```

## 验收标准

- 用户必须能从 `/agents/default/chat` 输入目标并选择 Plan 模式。
- Plan 模式只生成计划，不执行工具、Subagent 或 Sandbox。
- Plan 响应必须展示步骤、同步/异步、工具意图、风险、验收标准和产物预期。
- Plan 模式必须写入事件流和模型调用审计。
- 用户必须能从 Plan 结果跳转到 Run 详情。
- 用户必须能从 Plan 结果确认执行同一个 Run，且不会重新生成计划。
- 模型设置页必须支持添加预置模型、自定义 OpenAI-compatible 模型、设为默认和删除。
- 新创建 Agent Run 默认使用模型设置页当前默认模型。
- 多 Agent 编排必须展示被选中的 Agent、交接关系、并行分支、聚合结果和完整事件流。
