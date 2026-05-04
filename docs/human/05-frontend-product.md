# 05 官网与控制台

## 前端项目

前端拆分为两个项目：

```text
apps/web-site
apps/agent-console
```

官网使用 Next.js + TypeScript + Tailwind CSS。控制台使用 React + Vite + TypeScript + Tailwind CSS + shadcn/ui。

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
/tasks
/tasks/new
/tasks/:taskId
/tasks/:taskId/events
/tasks/:taskId/subagents
/sandboxes
/observability
/settings/models
/settings/policies
```

## 任务详情布局

```text
顶部：任务状态、耗时、操作按钮
左侧：执行计划 Step 列表
中间：实时事件流与 Agent 输出
右侧：Subagent、Sandbox、模型调用、资源信息
底部：最终结果与产物
```

## 控制台组件

核心组件：

```text
TaskTable
TaskCreateForm
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
shadcn/ui
lucide-react
ECharts
```

交互规范：

- 图标按钮使用 lucide-react。
- 表单使用 shadcn/ui Form。
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
任务列表
任务详情
事件流与 Subagent 面板
```

Figma 是设计事实源。前端实现严格对齐 Figma 的页面结构、间距、颜色、组件状态和信息层级。

## AI 生成视觉规则

Gemini/H5 产物只进入参考层。生产代码禁止直接复制 AI 生成 H5。生产代码由 Next.js 与 React 组件重建。
