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
default_locale: zh-CN
supported_locales:
  - zh-CN
  - en-US
locale_switch: top_bar_segmented_control
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
ObservabilityExportHistory
TraceSpanFilterPanel
SubagentQueueChart
```

语言与文案：

```yaml
default_locale: zh-CN
fallback_locale: en-US
switch_labels:
  zh-CN: 中文
  en-US: English
copy_scope:
  - navigation
  - page_titles
  - buttons
  - filters
  - table_headers
  - loading_states
  - empty_states
  - error_states
  - status_descriptions
technical_values_keep_original:
  - task_id
  - event_type
  - api_path
  - metric_name
  - image_name
  - model_name
  - container_id
  - enum_value
technical_values_need_chinese_description: true
```

前端规则：

- shadcn/ui 用于 Button、Dialog、Form、Input、Select、Tabs、Table、Badge、Sheet。
- lucide-react 用于图标。
- ECharts 用于监控图表。
- 控制台使用密集企业工具布局。
- 控制台默认语言为中文，顶栏提供中文/English 切换。
- 控制台所有页面文案、按钮、表头、空状态、加载状态、状态说明默认使用中文。
- 运行时代码值、API 路径、事件类型、指标名、镜像名、模型名、ID、枚举值等技术字段必须保留原值，并在相邻位置提供中文说明或中文标签。
- 英文模式用于交付和联调兜底，必须覆盖同一组页面文案，不允许只翻译部分主导航。
- 官网首屏必须出现产品名。
- 控制台页面禁止使用营销型大 Hero。
- 生产代码禁止复制 AI 生成 H5。
- 实现严格对齐 Figma Brief。
