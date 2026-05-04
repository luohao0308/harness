# 前端规格参考

## 官网

```yaml
framework: Next.js
language: TypeScript
styling: Tailwind CSS
icons: lucide-react
design_source: docs/design/figma-production-brief.md
```

路由：

```text
/
/product
/architecture
/solutions
/security
/deployment
/docs
/contact
```

## 控制台

```yaml
framework: React
build_tool: Vite
language: TypeScript
styling: Tailwind CSS
components: shadcn/ui
icons: lucide-react
server_state: TanStack Query
client_state: Zustand
charts: ECharts
routing: React Router
event_stream: SSE
design_source: docs/design/figma-production-brief.md
```

路由：

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

前端规则：

- shadcn/ui 用于 Button、Dialog、Form、Input、Select、Tabs、Table、Badge、Sheet。
- lucide-react 用于图标。
- ECharts 用于监控图表。
- 控制台使用密集企业工具布局。
- 官网首屏必须出现产品名。
- 控制台页面禁止使用营销型大 Hero。
- 生产代码禁止复制 AI 生成 H5。
- 实现严格对齐 Figma Brief。

