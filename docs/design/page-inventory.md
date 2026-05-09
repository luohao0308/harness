# Page Inventory

本清单定义 Figma 页面与前端路由的交付边界。官网由 Next.js 实现，控制台由 React + Vite 实现。

## Website

| Figma Page | Route | Owner | Implementation | Required Modules |
|---|---|---|---|---|
| Home | `/` | web-site | Next.js | Hero, Model + Harness, Core Modules, Console Preview |
| Product | `/product` | web-site | Next.js | Planner, Executor, Subagent, Sandbox, Event Store |
| Architecture | `/architecture` | web-site | Next.js | Architecture diagram, Event Timeline, data flow |
| Solutions | `/solutions` | web-site | Next.js | Enterprise scenarios, private deployment |
| Security | `/security` | web-site | Next.js | Sandbox policy, audit, secret boundary |
| Deployment | `/deployment` | web-site | Next.js | Docker Compose, systemd, Nginx, observability |
| Docs | `/docs` | web-site | Next.js | AI docs, runbooks, API contract links |
| Contact | `/contact` | web-site | Next.js | Enterprise contact entry |

## Console

| Figma Page | Route | Owner | Implementation | Required Modules |
|---|---|---|---|---|
| Agent Workspace Pro | `/agents/:agentId/workspace` | agent-console | React | ConversationTree, ContextExplorer, ToolTray, ToolCallingCard, ArtifactPreview |
| Run History | `/runs` | agent-console | React | Run table, status badges, filters |
| Run Detail | `/runs/:runId` | agent-console | React | ExecutionPlanPanel, EventTimeline, TaskResultPanel |
| Event Timeline | `/runs/:runId/events` | agent-console | React | SSE stream, event payload, replay position |
| Subagent Panel | `/runs/:runId/subagents` | agent-console | React | SubagentPanel, assignment state, result summary |
| Sandbox Panel | `/sandboxes` | agent-console | React | SandboxPanel, Docker Sandbox, WarmPool, resource usage |
| Observability | `/observability` | agent-console | React | ResourceUsageChart, model calls, task throughput |
| Model Settings | `/settings/models` | agent-console | React | ModelCallPanel, gateway status, limits |
| Policy Settings | `/settings/policies` | agent-console | React | PolicyBadge, risk levels, approval rules |

## Console Language

| Item | Required Value |
|---|---|
| Default locale | `zh-CN` |
| Fallback locale | `en-US` |
| Switch labels | `中文` / `English` |
| Switch location | Console top bar |
| Required behavior | 默认展示中文，切换后同一组页面文案展示英文 |

技术字段保留原值：

```text
任务 ID
事件类型
接口路径
枚举值
指标名
镜像名
模型名
容器 ID
```

技术字段展示规则：

```text
原始值必须保留。
中文模式必须附带中文含义、描述或标签。
英文模式必须保留同等信息量。
```

## Component Inventory

| Component | Figma Source | Frontend Target | States |
|---|---|---|---|
| Button | `03 Components/Button` | Local Button primitive | default, hover, active, focus, disabled, loading |
| Input | `03 Components/Input` | Local Input/Textarea primitives | default, focus, disabled, error |
| Select | `03 Components/Select` | Local select/control primitive | default, open, selected, disabled, error |
| Table | `03 Components/Table` | Local Table primitive | loading, empty, sorted, selected |
| Badge | `03 Components/Badge` | Local Badge primitive | CREATED, PLANNING, RUNNING, FAILED, COMPLETED |
| Tabs | `03 Components/Tabs` | Local tabs/segmented control primitive | default, active, disabled |
| Dialog | `03 Components/Dialog` | Local dialog primitive | confirm, form, destructive |
| Timeline | `03 Components/Timeline` | EventTimeline | running, success, failed, selected |
| Status Card | `03 Components/Status Card` | StatusCard | pending, success, timeout, failed |

## Delivery Constraints

- Figma is the design source of truth.
- Website implementation must use Next.js.
- Console implementation must use React + Vite.
- Gemini/H5 output is reference material only.
- Run Detail, Event Timeline, Subagent, Sandbox, and WarmPool must remain explicit user-facing concepts.
