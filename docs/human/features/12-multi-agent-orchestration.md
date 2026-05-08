# 12 多 Agent 编排 Spec

## 目标

多 Agent 编排不是简单派生 Subagent。用户发起的是一次 Agent Session 或 Agent Run；Subagent 是 Run 中某个异步步骤派生出的工作单元。多 Agent 编排是 Agent Router 根据目标、上下文、工具权限和专长，选择多个具名 Agent 协作，并由 Orchestrator 管理交接、并行分支、聚合和事件溯源。

目标架构：

```text
Multi-agent Orchestration
├─ Agent Registry：Agent 定义、模型、工具、权限、系统提示词
├─ Agent Router：选择参与 Agent 和编排策略
├─ Orchestrator：handoff / parallel fan-out / reduce
├─ Agent Runner：每个 Agent 的生命周期
└─ Event Store：跨 Agent 审计、恢复和回放
```

## 用户可见能力

| 能力 | 入口 | 用户结果 |
|---|---|---|
| 查看 Agent 列表 | `/agents` | 看到 Researcher、Coder、Reviewer、Operator 等具名 Agent |
| 选择入口 Agent | `/agents/:agentId/chat` | 以某个 Agent 开始会话和运行 |
| 自动路由 | `/agents/:agentId/chat` Auto 模式 | Router 选择参与 Agent |
| 手动选择协作 Agent | `/agents/:agentId/chat` Advanced | 用户指定参与 Agent |
| 查看编排图 | Run 详情 | 展示 handoff、parallel fan-out、reduce 的拓扑 |
| 查看跨 Agent 事件 | Event Timeline | 每个事件绑定 agent_id、assignment_id 和 run_id |

## 后端契约

```text
GET  /api/agents
GET  /api/agents/{agent_id}
POST /api/agents/runs
POST /api/agents/runs/{run_id}/orchestrate
GET  /api/agents/runs/{run_id}/assignments
GET  /api/agents/runs/{run_id}/handoffs
GET  /api/agents/runs/{run_id}/events
GET  /api/observability/summary
```

## 前端入口

| 页面 | 数据来源 | 交互 |
|---|---|---|
| `/agents` | Agent Registry API | Agent 列表、默认模型、工具权限、状态 |
| `/agents/:agentId/chat` | Agent Run API | Chat/Plan/Execute/Auto、协作 Agent 选择 |
| `/runs/:runId` | Assignment、Handoff、Events API | 编排拓扑、事件、产物和错误 |
| `/observability` | Observability Summary API | Assignment 状态分布和队列状态 |

## 数据模型

| 数据 | 作用 |
|---|---|
| `agents` | 具名 Agent 配置：角色、模型、工具权限、系统提示词 |
| `agent_sessions` | 对话会话 |
| `agent_messages` | 用户和 Agent 消息 |
| `agent_runs` | 会话运行记录 |
| `agent_assignments` | 某个 Run 中被分配给 Agent 的工作 |
| `agent_handoffs` | Agent 到 Agent 的交接 |
| `agent_events` | 全量事件流 |

`agent_assignments` 最少字段：

```text
id
run_id
agent_id
parent_assignment_id
step_key
role
status
input_json
output_json
started_at
completed_at
```

## 事件模型

```text
AGENT_SELECTED
AGENT_ASSIGNMENT_CREATED
AGENT_ASSIGNMENT_STARTED
AGENT_ASSIGNMENT_COMPLETED
AGENT_ASSIGNMENT_FAILED
AGENT_HANDOFF_STARTED
AGENT_HANDOFF_COMPLETED
AGENT_PARALLEL_FANOUT_STARTED
AGENT_PARALLEL_BRANCH_COMPLETED
AGENT_REDUCE_STARTED
AGENT_REDUCE_COMPLETED
```

所有事件必须包含：

```text
run_id
agent_id
assignment_id
parent_assignment_id
trace_id
payload_json
sequence
created_at
```

## 权限模型

| 能力 | 角色 |
|---|---|
| 查看 Agent | admin、engineer、operator |
| 创建或修改 Agent | admin |
| 启动多 Agent 编排 | admin、engineer |
| 查看编排审计 | admin、engineer、operator |

## 状态流转

Assignment：

```text
PENDING -> QUEUED -> RUNNING -> SUCCESS
PENDING -> QUEUED -> RUNNING -> FAILED
PENDING -> QUEUED -> RUNNING -> TIMEOUT
PENDING -> CANCELLED
```

Orchestration：

```text
ROUTING -> ASSIGNED -> RUNNING -> REDUCING -> COMPLETED
ROUTING -> ASSIGNED -> RUNNING -> FAILED
```

## 编排策略

| 策略 | 场景 | 行为 |
|---|---|---|
| handoff | 需要专长切换 | A Agent 输出作为 B Agent 输入 |
| parallel fan-out | 可并行分析、验证、搜索 | Router 同时创建多个 assignment |
| reduce | 多个 Agent 输出需要汇总 | Reducer Agent 聚合结果并写最终产物 |
| supervisor | 长任务需要监控 | Supervisor 观察分支状态并处理失败 |

## 外部服务契约

| 服务 | 用途 |
|---|---|
| LLM Provider | Router 决策、Agent 推理、Reducer 汇总 |
| Redis / Dramatiq | 多 Agent 异步执行队列 |
| Event Store | 编排状态事实源 |
| Sandbox | 每个 Agent assignment 的隔离工具执行 |

## 观测指标

```text
agent_orchestration_runs_total
agent_assignments_total
agent_assignment_duration_seconds
agent_handoffs_total
agent_parallel_branches_running
agent_reduce_duration_seconds
```

## 当前实现状态

| 能力 | 状态 | 证据 |
|---|---|---|
| Subagent 派生 | 已落地 | async step 通过 `SubagentManager.spawn` 写入子运行记录 |
| Subagent 状态追踪 | 已落地 | PENDING、RUNNING、SUCCESS、FAILED、TIMEOUT、CANCELLED |
| Agent Workspace | 基础落地 | `/agents/:agentId/chat` |
| Agent Plan/Execute | 基础落地 | Plan-only 和 execute existing plan |
| Agent Registry | 基础落地 | `agents` 表、默认 preset、`GET /api/agents` |
| Agent Router | 基础落地 | `orchestrate` 根据目标、工具意图和风险选择具名 Agent |
| Orchestrator | 基础落地 | 创建并执行 `agent_assignments`、`agent_handoffs` 和编排事件 |
| Agent Runner | 基础落地 | assignment 通过 ToolRunner 执行并写入 `output_json` |
| Reducer | 基础落地 | reviewer assignment 聚合分支摘要并写入 `AGENT_REDUCE_COMPLETED` |
| Workspace 编排入口 | 基础落地 | Plan 后可编排 Agent、运行编排、入队运行并展示 assignments |
| Worker 队列入口 | 基础落地 | `POST /api/agents/runs/{run_id}/orchestrate/enqueue` 投递 assignments |
| Assignment Worker | 基础落地 | `agent_assignment_worker` 可执行单个 assignment 并触发 reduce |
| Worker 部署入口 | 已落地 | Docker Compose 和 systemd 均包含 `agent-assignment-worker` |
| Assignment 观测 | 已落地 | `/api/observability/summary` 返回 `agent_assignments_by_status` 和 `assignment_queue` |
| Run 详情编排视图 | 基础落地 | Run 详情展示 assignments、handoff 边、分支输出和 reduce 输出 |
| Run 详情拓扑 UI | 已落地 | Run 详情按 Entry、Parallel Branches、Reducer 展示 fan-out/reduce 拓扑 |
| Run 详情异步刷新 | 已落地 | QUEUED/RUNNING assignments 存在时自动轮询刷新 assignments、handoffs、events 和 tool calls |
| 事件重放覆盖 | 已落地 | Replay 状态包含 `agent_assignments`、`agent_handoffs` 和 `agent_reduce` |
| 分支耗时视图 | 已落地 | Assignment 节点展示 queue/run/total 耗时并标记瓶颈分支 |
| Prometheus 编排指标 | 已落地 | `/metrics` 输出 assignment、handoff、parallel branch 和 reduce 指标 |
| LLM Router | 已落地 | Router 先请求模型输出 `selected_agent_ids`、`strategy`、`reasoning`，失败时回落确定性规则 |
| Agent 工具权限边界 | 已落地 | assignment 执行前按 `agent.tools_json` 校验工具 allowlist，输出记录 `permission_boundary` 和 `allowed_tools` |

## 缺口

| 缺口 | 影响 | 目标 |
|---|---|---|
| RBAC 仍按平台角色执行 | Agent 工具 allowlist 已生效，但 ToolRunner roles 仍使用平台 engineer 角色 | 将 Agent role、组织 RBAC 和人工审批合成为 assignment execution principal |

## 实现顺序

```text
1. 新增 Agent Registry 数据模型和 preset
2. 新增 GET /api/agents 与 Agent 列表页
3. 新增 Agent Router，输出参与 Agent 与编排策略
4. 新增 agent_assignments 和 agent_handoffs
5. 新增 Orchestrator，先支持 handoff 和 parallel fan-out
6. 接入 Agent Runner，执行每个 assignment
7. 新增 Reducer Agent 聚合结果
8. Run 详情新增多 Agent 编排拓扑
9. Worker 异步化和队列化
10. Worker 部署、运行手册和观测摘要接入
11. Run 详情节点/边拓扑视图
12. 事件流、Replay 和测试覆盖跨 Agent 回放
```

## 验收标准

- 用户能看到多个具名 Agent，而不是只看到 Subagent ID。
- Auto 模式能由 Router 选择至少两个参与 Agent。
- 并行编排必须生成多个 `agent_assignments`。
- handoff 必须记录来源 Agent、目标 Agent、输入和输出。
- reduce 必须把多个 Agent 输出聚合为最终结果。
- Run 详情必须展示多 Agent 拓扑和事件时间线。
- `/observability` 必须展示 assignment 状态和 worker 队列状态。
- Docker Compose 或 systemd 启动后必须存在 `agent-assignment-worker`。
- 事件重放必须能还原每个 Agent assignment 的状态。
