# Figma Production Brief

本文件是阶段 02 的 Figma 设计事实源说明。Figma 文件、设计 token、页面结构、组件状态和前端交付物必须对齐本文件。前端实现不得把 Gemini/H5 产物直接作为生产代码；Gemini/H5 产物只进入视觉参考层和文案参考层，生产官网由 Next.js 重建，生产控制台由 React + Vite 重建。

## 文件结构

```text
Agent Harness Platform
├─ 00 Design Tokens
├─ 01 Website
│  ├─ Home
│  ├─ Product
│  ├─ Architecture
│  ├─ Security
│  └─ Deployment
├─ 02 Console
│  ├─ Agent Workspace Pro
│  ├─ Run History
│  ├─ Run Detail
│  ├─ Event Timeline
│  ├─ Subagent Panel
│  ├─ Sandbox Panel
│  └─ Observability
└─ 03 Components
   ├─ Button
   ├─ Input
   ├─ Select
   ├─ Table
   ├─ Badge
   ├─ Tabs
   ├─ Dialog
   ├─ Timeline
   └─ Status Card
```

## Design Tokens

Figma token 页面必须映射到 `docs/design/design-tokens.json`。Token 分组固定为 color、spacing、radius、shadow、font、layout。

颜色分组：

- background：页面、面板、反色背景。
- surface：主表面、次级表面、悬浮表面。
- text：主文本、次级文本、弱化文本、反色文本。
- border：默认边框、强调边框、焦点边框。
- status：任务状态、工具状态、运行状态。

状态色必须覆盖：

```text
CREATED
PLANNING
RUNNING
WAITING_SUBAGENTS
FAILED
COMPLETED
CANCELLED
PENDING
SUCCESS
TIMEOUT
```

## Website Pages

官网使用 Next.js + TypeScript + Tailwind CSS。官网首屏必须出现产品名 `Enterprise AI Agent Harness Platform` 和正式表述 `生产级企业 AI Agent Harness 平台`。

页面：

| Figma Page | Route | Required Content |
|---|---|---|
| Home | `/` | 首屏、核心公式、平台能力、控制台预览、企业部署入口 |
| Product | `/product` | Planner、Executor、Subagent、Sandbox、Event Store、Model Gateway |
| Architecture | `/architecture` | 系统架构图、事件流、服务边界、数据流 |
| Security | `/security` | Docker Sandbox、权限策略、审计、密钥边界 |
| Deployment | `/deployment` | Docker Compose、systemd、Nginx、PostgreSQL、Redis、Loki、Prometheus、Grafana |
| Docs | `/docs` | 文档入口和运行手册入口 |
| Contact | `/contact` | 企业交付沟通入口 |

## Website Home

首屏：

- 产品名作为第一视觉信号。
- 描述 `Model + Harness = Agent`。
- 主操作入口指向产品说明和部署说明。
- 首屏必须露出下一屏内容线索。

主要区块：

```text
Hero
Model + Harness = Agent
Core Modules
Architecture Diagram
Console Preview
Enterprise Scenarios
Security And Deployment
Contact
```

## Console Layout

控制台使用 React + Vite + TypeScript + Tailwind CSS、本地 UI primitives、lucide-react 和 ECharts。历史设计中出现的 shadcn/ui 名称只代表设计系统目标，不是当前实现依赖。布局必须是密集企业工具界面，不使用营销型大 Hero。

全局布局：

- 左侧导航宽度 248px。
- 顶栏包含环境、模型网关状态、当前用户、告警入口。
- 顶栏包含中文/English 语言切换，默认中文。
- 主内容最大宽度 1440px。
- 数据密集页面使用表格、筛选、分段控制、状态 badge、详情抽屉。
- 图表使用 ECharts，事件流使用 SSE 展示实时追加。
- 页面文案、按钮、表头、空状态、加载状态、状态说明默认使用中文。
- 不能翻译的运行时技术值必须保留原始值，并在相邻位置提供中文说明。

语言文案规范：

```text
中文模式：
- 所有页面文案默认中文。
- 技术字段保留原值，旁边显示中文说明。
- 状态 badge 与空状态使用中文优先表达。

英文模式：
- 保留同一组信息密度。
- 技术字段保持原值。
- 中文说明替换为英文说明，不减少信息量。
```

## Console Pages

| Figma Page | Route | Required Content |
|---|---|---|
| Agent Workspace Pro | `/agents/:agentId/workspace` | 三栏 Plan-Act surface、Conversation Tree、Tool Tray、Artifacts、Approvals |
| Run History | `/runs` | Agent Run 表格、状态筛选、模型筛选、最近事件摘要 |
| Run Detail | `/runs/:runId` | 状态、Execution Plan、Event Timeline、Executor 输出、结果产物 |
| Event Timeline | `/runs/:runId/events` | 事件流、事件类型、payload 摘要、重放定位 |
| Subagent Panel | `/runs/:runId/subagents` | Subagent 状态、分配任务、结果摘要、失败原因 |
| Sandbox Panel | `/sandboxes` | Docker Sandbox 实例、WarmPool、资源占用、回收状态 |
| Observability | `/observability` | 任务吞吐、失败率、模型调用、工具执行、资源指标 |
| Model Settings | `/settings/models` | Model Gateway 配置、供应商、限流、健康状态 |
| Policy Settings | `/settings/policies` | 工具风险等级、审批策略、沙箱策略、审计要求 |

## Run Detail Layout

```text
Top Bar: run id, run status, duration, retry/cancel actions
Left Panel: ExecutionPlanPanel
Center Panel: EventTimeline and Executor output
Right Panel: SubagentPanel, SandboxPanel, ModelCallPanel, ResourceUsageChart
Bottom Panel: Run result and artifacts
```

## Components

组件必须在 Figma 的 `03 Components` 中维护变体，并在前端通过本地 UI primitives、lucide-react、Tailwind CSS 重建。shadcn/ui 是历史设计目标引用，不是当前控制台依赖。

组件清单：

- Button：primary、secondary、destructive、ghost、icon。
- Input：text、textarea、error、disabled、with helper text。
- Select：single、searchable、disabled、error。
- Table：loading、empty、sorted、selected、with filters。
- Badge：status、policy、risk、model、sandbox。
- Tabs：page tabs、panel tabs、segmented mode tabs。
- Dialog：confirm、form、danger action。
- Timeline：event node、error node、running node、selected node。
- Status Card：task status、resource metric、model health、sandbox health。

交互状态：

```text
default
hover
active
focus
disabled
loading
error
success
warning
```

## Delivery Rules

- Figma 是设计事实源，前端实现必须对齐 Figma。
- `docs/design/design-tokens.json` 是 token 交付契约。
- `docs/design/page-inventory.md` 是页面交付清单。
- 官网生产实现使用 Next.js；控制台生产实现使用 React + Vite。
- Gemini/H5 产物不得直接复制进生产代码。
- 控制台必须保留 Run Detail、Event Timeline、Subagent、Sandbox、WarmPool 等运行时概念。
- 状态 badge 必须使用固定状态枚举和状态色。
- 所有复杂运行状态必须有 loading、empty、error、success 展示。
