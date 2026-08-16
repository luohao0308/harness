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
components: local UI primitives compatible with current console style
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

核心组件：

```text
AgentWorkspacePro
ConversationTree
ContextExplorer
ToolTray
ToolCallingCard
ArtifactPreview
MetadataPanel
RunHistory
RunDetail
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

Workspace Pro 状态：

```yaml
store: Zustand
shape:
  nodesById: ConversationNode map
  rootNodeId: string
  activeLeafId: string
  pinnedNodeIds: string array
  contextWindowTurns: number
  activeStream: AbortController metadata
conversation_node:
  id: string
  parent_id: string | null
  children_ids: string array
  role: user | assistant | system | tool
  content: string
  state: draft | streaming | paused | done | error
  run_id: string | null
  metadata: token, cost, ttfb, duration
  tool_calls: object array
  artifacts: object array
```


技术取舍：

- 不迁移到 Next.js App Router；控制台继续使用 React 18 + Vite。
- 不引入 Node.js 作为核心后端；MCP 与文件桥接接入现有 FastAPI Tool Runtime。
- 不引入 Vercel AI SDK 作为核心依赖；继续使用现有 SSE 与 Model Gateway。
- 不新增 Recharts；图表类 artifact 使用现有 ECharts。
- 不绕过 Sandbox 增加本地文件写入能力；文件副作用仍走 Tool Policy、Approval、Sandbox。
- Conversation Tree 是 Workspace UI 状态与审计输入；不替代 Agent Run 或 Event Store。
- 本文件描述的是当前前端参考合同，不是永久不变的组件清单；等价实现只要保留行为、数据覆盖和审计链路即可。

Workspace Pro 数据流：

```text
Chat Console submit
-> build active path, pinned nodes, context window, tool mentions
-> POST /api/agents/{agent_id}/runs/chat/stream
-> SSE: think_delta, delta, tool_call_requested, artifact_created, usage, done
-> update conversation node, metadata, tool cards, artifacts, active Run
-> query /api/agents/runs/{run_id}/workspace for durable projection
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

- 控制台保持当前本地 UI 组件风格；不强制引入 shadcn/ui。
- lucide-react 用于图标。
- ECharts 用于监控图表。
- 控制台默认偏向密集企业工具布局，但具体结构可按页面类型调整。
- 控制台默认语言为中文，顶栏提供中文/English 切换。
- 控制台所有页面文案、按钮、表头、空状态、加载状态、状态说明默认使用中文。
- 运行时代码值、API 路径、事件类型、指标名、镜像名、模型名、ID、枚举值等技术字段必须保留原值，并在相邻位置提供中文说明或中文标签。
- 英文模式用于交付和联调兜底，必须覆盖同一组页面文案，不允许只翻译部分主导航。
- 官网首屏必须出现产品名。
- 控制台页面禁止使用营销型大 Hero。
- 生产代码禁止复制 AI 生成 H5。
- 实现应保留 Figma Brief 的视觉意图和信息层级；如与产品行为冲突，以活跃产品规格为准。
