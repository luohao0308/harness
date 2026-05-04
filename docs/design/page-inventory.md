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
| Task List | `/tasks` | agent-console | React | TaskTable, TaskStatusBadge, filters, create action |
| Task Create | `/tasks/new` | agent-console | React | TaskCreateForm, model selector, policy selector |
| Task Detail | `/tasks/:taskId` | agent-console | React | ExecutionPlanPanel, EventTimeline, TaskResultPanel |
| Event Timeline | `/tasks/:taskId/events` | agent-console | React | SSE stream, event payload, replay position |
| Subagent Panel | `/tasks/:taskId/subagents` | agent-console | React | SubagentPanel, assignment state, result summary |
| Sandbox Panel | `/sandboxes` | agent-console | React | SandboxPanel, Docker Sandbox, WarmPool, resource usage |
| Observability | `/observability` | agent-console | React | ResourceUsageChart, model calls, task throughput |
| Model Settings | `/settings/models` | agent-console | React | ModelCallPanel, gateway status, limits |
| Policy Settings | `/settings/policies` | agent-console | React | PolicyBadge, risk levels, approval rules |

## Component Inventory

| Component | Figma Source | Frontend Target | States |
|---|---|---|---|
| Button | `03 Components/Button` | shadcn/ui Button | default, hover, active, focus, disabled, loading |
| Input | `03 Components/Input` | shadcn/ui Input/Form | default, focus, disabled, error |
| Select | `03 Components/Select` | shadcn/ui Select | default, open, selected, disabled, error |
| Table | `03 Components/Table` | shadcn/ui Table | loading, empty, sorted, selected |
| Badge | `03 Components/Badge` | shadcn/ui Badge | CREATED, PLANNING, RUNNING, FAILED, COMPLETED |
| Tabs | `03 Components/Tabs` | shadcn/ui Tabs | default, active, disabled |
| Dialog | `03 Components/Dialog` | shadcn/ui Dialog | confirm, form, destructive |
| Timeline | `03 Components/Timeline` | EventTimeline | running, success, failed, selected |
| Status Card | `03 Components/Status Card` | StatusCard | pending, success, timeout, failed |

## Delivery Constraints

- Figma is the design source of truth.
- Website implementation must use Next.js.
- Console implementation must use React + Vite.
- Gemini/H5 output is reference material only.
- Task Detail, Event Timeline, Subagent, Sandbox, and WarmPool must remain explicit user-facing concepts.
