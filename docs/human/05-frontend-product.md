# 05 官网与控制台

## 前端项目

前端拆分为两个项目：

```text
apps/web-site
apps/agent-console
```

官网使用 Next.js + TypeScript + Tailwind CSS。控制台使用 React + Vite + TypeScript + Tailwind CSS、本地 UI primitives、lucide-react 和 ECharts；shadcn/ui 仅作为历史设计目标参考，不是当前实现依赖。

## 官网页面

路由：

```text
/                     首页
/product              产品能力
/architecture         架构说明
/solutions            场景方案
/security             安全与合规
/deployment           私有化部署
/docs                 文档入口
/contact              联系入口
```

首页结构：

```text
Hero
Model + Harness = Agent
核心模块
架构图
控制台预览
企业场景
安全与部署
联系入口
```

首屏文案：

```text
生产级企业 AI Agent Harness 平台
```

```text
通过 Planner、Executor、Subagent、Event Sourcing、Docker Sandbox 和 WarmPool，将大模型转化为企业级任务执行系统。
```

## 控制台路由

```text
/agents
/agents/:agentId/workspace
/runs
/runs/:runId
/runs/:runId/events
/runs/:runId/subagents
/sandboxes
/observability
/settings/models
/settings/policies
/tools
/evals
/subagents
```

`/agents/:agentId/workspace` 是当前主入口。`/tasks` 是 deprecated 兼容入口并跳转到 `/runs`；历史 `/tasks/new` 创建页不是当前产品路由。

## Agent Workspace 布局

```text
左侧 Explorer：Agent 模型、Tool Tray、上下文窗口、Pinned 消息、文件桥接状态
中列 Chat Console：Conversation Tree、流式 Plan-Act 输出、暂停/继续、编辑重发、结构化 @ mention
右侧 Artifacts / Runtime：Artifacts、Metadata、Plan DAG、Events、Tool Cards、Approvals、Model Calls
底部输入区：目标输入、发送、暂停、Continue
```

Workspace Pro 要求：

- 不再提供历史 Chat / Plan / Execute / Auto 多 Tab 作为当前主交互。
- 单一 Plan-Act surface 创建或继续 Agent Run。
- 中列展示树状对话、流式输出和折叠的规划/思考轨迹。
- 右侧展示 Plan、Events、Tools、Subagents、Sandbox、Artifacts、Approvals 和 Model Calls。
- 用户可从 Workspace 跳转到 Run Detail 执行、编排、Replay 或保存 Eval。

## Run 详情布局

```text
顶部：任务状态、耗时、操作按钮
左侧：执行计划 Step 列表
中间：实时事件流与 Agent 输出
右侧：Subagent、Sandbox、模型调用、资源信息
底部：最终结果与产物
```

Run 详情必须展示多 Agent 编排面板：

- `agent_assignments` 节点状态。
- `agent_handoffs` 交接边。
- Reducer 汇总输出。
- QUEUED 或 RUNNING assignment 存在时自动刷新。

## 观测页动态数据

`/observability` 必须读取后端动态摘要，不使用静态状态。页面展示：

- Task、Subagent、Agent Assignment、Model Call、Tool Call 状态分布。
- Subagent 队列和 Agent Assignment 队列。
- WarmPool、Sandbox、日志、Trace、导出和服务健康。

## 控制台组件

核心组件：

```text
AgentWorkspace
AgentModeSwitch
AgentMessageList
AgentPlanCard
RunHistory
RunDetail
AgentWorkspacePro
ConversationTree
ContextExplorer
ToolTray
ToolCallingCard
ArtifactPreview
TaskStatusBadge
ExecutionPlanPanel
EventTimeline
SubagentPanel
SandboxPanel
ModelCallPanel
ResourceUsageChart
TaskResultPanel
PolicyBadge
```

## 设计系统

固定使用：

```text
Tailwind CSS
local UI primitives
lucide-react
ECharts
```

交互规范：

- 图标按钮使用 lucide-react。
- 表单使用当前控制台本地 UI primitives；shadcn/ui 只保留为历史设计目标参考。
- 表格使用密集型布局。
- 状态使用 Badge。
- 时间线用于事件流。
- 图表使用 ECharts。
- 页面信息密度按企业控制台标准设计。

## Figma 产物

Figma 文件包含：

```text
官网首页
产品架构页
Agent Workspace Pro
Run History
Run Detail
事件流与 Subagent 面板
```

Figma 是设计事实源。前端实现严格对齐 Figma 的页面结构、间距、颜色、组件状态和信息层级。

## AI 生成视觉规则

Gemini/H5 产物只进入参考层。生产代码禁止直接复制 AI 生成 H5。生产代码由 Next.js 与 React 组件重建。
