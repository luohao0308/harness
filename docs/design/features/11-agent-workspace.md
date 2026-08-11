# 11 Agent Workspace 与 Plan 模式 Spec

## 目标

Agent Workspace 是 AI Harness Platform 的主使用入口。下一代形态是 Workspace Pro：在现有 `/agents/:agentId/workspace` 路由上提供 chat-first 的 Agent 对话、规划、工具、产物和运行观察能力，而不是另起独立产品。

产品语义中不存在“主任务”。用户发起的是 `Agent Run`；`tasks` 表只是当前兼容存储实现。Conversation Tree 是 Workspace UI 状态与审计输入，不替代 Agent Run、Event Store、ModelCall、ToolCall 或 ToolApproval。
本文件描述目标能力和验收边界，不锁死具体组件名、面板数量、宽度或请求辅助函数。

## Workspace Pro 组织方式

```text
Agent Workspace Pro
├─ 对话主区域：真实模型回复、规划回复、暂停/继续、编辑重发、结构化 @ mention
├─ 上下文与工具区域：模型、MCP 工具、Tool Tray、上下文窗口、Pinned 消息、文件桥接状态
└─ 产物与运行观察区域：代码、JSON、Diff、图表、Tool Call、Plan DAG、事件、模型调用、审批
```

这些区域可以是侧栏、抽屉、标签页、浮层或响应式分组。主要求是：中间体验像正常大模型对话窗口，Plan / Tool / Runtime 信息不抢占默认对话体验。执行、编排、回放和保存 Eval 仍然是 Run/Harness 能力。

## 现有基础与取舍

| 需求 | 当前项目基础 | 决策 |
|---|---|---|
| chat-first Workspace | 已有 `/agents/:agentId/workspace` | 原路由升级 |
| Zustand | 已安装 | 扩展为 conversation tree store |
| Tailwind + Lucide | 已有 | 继续使用 |
| shadcn/ui | 未正式引入 | 保持本地 UI 组件风格 |
| 图表 | 当前使用 ECharts | 图表 artifact 继续用 ECharts |
| Vercel AI SDK | 未使用，后端是 FastAPI | 不作为核心依赖；复用 SSE / Model Gateway |
| MCP / Tool Runtime | 已有 Tool Registry / MCP Adapter / ToolCall audit | 展示工具入口和调用状态 |
| Tool Approval | 已有审批模型 | 增加 Modify 和挂起恢复体验 |
| Artifacts | 有 artifact 数据结构 | 提供可达的 Artifacts Preview |
| Token / latency | ModelCall 记录 tokens / duration | 展示到消息或运行观察区域 |

## 用户可见能力

| 能力 | 入口 | 用户结果 |
|---|---|---|
| 选择 Agent | `/agents`、`/agents/:agentId/workspace` | 用户看到可用 Agent 和默认模型 |
| 正常对话 | `/agents/:agentId/workspace` | 输入消息后返回真实模型回复 |
| 规划模式 | `/agents/:agentId/workspace` | 用户显式选择规划时生成规划回复，不自动进入执行 |
| 显式 Plan-Act | `/agents/:agentId/workspace` | 用户显式创建可执行 Run 后进入计划、工具意图和产物流 |
| Conversation Tree | `/agents/:agentId/workspace` | 编辑历史消息生成新分支，旧分支保留 |
| Pause / Continue | `/agents/:agentId/workspace` | 暂停只中断 stream，继续携带 partial content 恢复 |
| Context 控制 | `/agents/:agentId/workspace` | 最近 N 轮、Pinned 消息、上下文预览和 token 估算可见 |
| Tool Approval | Workspace Tool Card | 副作用工具进入 Approve / Reject / Modify |
| Artifacts Preview | 可达的预览区域 | 预览 code、JSON、diff、chart、text |
| 查看 Run 详情 | `/runs/:runId` | 展示计划、事件、工具、Subagent、Sandbox 和产物 |
| 多 Agent 编排 | Workspace、Run 详情 | 展示 Agent 选择、交接、并行分支和聚合结果 |

## 后端契约

Workspace Pro 当前参考接口：

```text
POST /api/agents/{agent_id}/runs/chat/stream
GET  /api/agents/runs/{run_id}/workspace
POST /api/tasks/{task_id}/tool-approvals/{approval_id}/approve
POST /api/tasks/{task_id}/tool-approvals/{approval_id}/reject
POST /api/tasks/{task_id}/tool-approvals/{approval_id}/modify
```

`POST /api/agents/{agent_id}/runs/chat/stream` 请求体当前包含：

```text
goal?
messages
active_leaf_id
pinned_node_ids
context_window_turns
continue_from_node_id?
partial_assistant_content?
tool_mentions?
```

SSE 事件类型参考：

```text
think_delta
delta
tool_call_requested
tool_call_result
artifact_created
usage
done
error
```

## 前端状态

Zustand store 的当前参考状态：

```text
nodesById
rootNodeId
activeLeafId
pinnedNodeIds
contextWindowTurns
activeStream
```

ConversationNode 的当前参考字段：

```text
id
parent_id
children_ids
role: user | assistant | system | tool
content
state: draft | streaming | paused | done | error
run_id?
metadata: input_tokens, output_tokens, cost_usd, ttfb_ms, duration_ms
tool_calls
artifacts
```

## 权限模型

| 能力 | 角色 |
|---|---|
| 使用 Agent Workspace Pro | admin、engineer |
| 查看 Run 详情 | admin、engineer、operator |
| Approve / Reject 副作用工具 | admin、engineer |
| Modify 工具输入并批准 | admin |
| 修改 Agent 默认模型 | admin |

## 事件模型

Workspace stream 事件：

```text
WORKSPACE_STREAM_STARTED
WORKSPACE_DELTA_EMITTED
WORKSPACE_THINK_DELTA_EMITTED
WORKSPACE_STREAM_PAUSED
WORKSPACE_STREAM_CONTINUED
WORKSPACE_STREAM_COMPLETED
WORKSPACE_ARTIFACT_CREATED
WORKSPACE_USAGE_RECORDED
```

工具审批事件：

```text
TOOL_APPROVAL_REQUESTED
TOOL_APPROVAL_APPROVED
TOOL_APPROVAL_REJECTED
TOOL_APPROVAL_MODIFIED_APPROVED
```

## 分期

| Phase | 范围 |
|---|---|
| P0 | Conversation Tree Store、Abort / Continue、Edit & Resend、usage 展示、Artifacts 初版、Tool Card 初版 |
| P1 | Approve / Reject / Modify、副作用工具挂起 stream、审批后恢复 Run、`@` 工具与上下文菜单 |
| P2 | 最近 N 轮滑动条、Pin 消息、Context Preview、对齐 RunContextRouter |
| P3 | Diff 增强、大型 artifact 懒加载、图表 artifact、文件树与本地文件桥接 |

## 验收标准

- 用户能从 `/agents/default/workspace` 发起 Workspace Pro 对话流。
- 编辑历史消息生成新分支，不覆盖旧分支。
- Abort 后消息状态变为 `paused`，Continue 从 partial content 继续。
- Pin 消息始终进入请求 payload。
- Context slider 正确影响 active path 中携带的最近轮数。
- Tool Card 正确展示 pending、approved、rejected、success、failed。
- Artifacts 面板能渲染 code、json、diff 三类内容。
- Chat stream 返回标准 SSE 事件。
- usage 事件能写入 ModelCall 并返回前端。
- 副作用 tool call 会创建 approval，不直接执行。
- Modify approval 使用修改后的 input_json 执行工具。
- Continue 请求关联原 runId 和 branch id。
- OpenAPI 与 docs 校验通过。
