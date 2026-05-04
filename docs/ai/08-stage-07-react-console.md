# 08 阶段 07：React 控制台

## 阶段目标

实现 React + Vite 控制台，完成任务列表、创建任务、任务详情、执行计划、事件流、Subagent 面板和 Sandbox 面板。

## Required Context

- [执行协议](./00-execution-protocol.md)
- [任务进度说明](./01-task-progress.md)
- [机器可读任务进度](./task-progress.yaml)
- [前端规格](./reference/frontend-spec.md)
- [数据、事件与 API](./reference/data-events-api.md)
- `docs/design/figma-production-brief.md`
- `docs/design/design-tokens.json`

## AI 执行提示词

```text
你是本项目的前端工程执行 Agent。现在执行阶段 07：React 控制台。

必须先读取 docs/ai/00-execution-protocol.md、docs/ai/01-task-progress.md、docs/ai/task-progress.yaml、docs/ai/reference/frontend-spec.md、docs/ai/reference/data-events-api.md、docs/design/figma-production-brief.md 和 docs/design/design-tokens.json。
只执行阶段 07，不进入阶段 08。

执行内容：
1. 初始化 apps/agent-console，技术栈为 React + Vite + TypeScript + Tailwind CSS + shadcn/ui。
2. 安装 @tanstack/react-query、zustand、react-router-dom、echarts、lucide-react。
3. 建立 src/app/routes.tsx。
4. 建立任务 API client。
5. 建立 EventSource SSE hook。
6. 实现 /tasks 页面。
7. 实现 /tasks/new 页面。
8. 实现 /tasks/:taskId 页面。
9. 实现 ExecutionPlanPanel、EventTimeline、SubagentPanel、SandboxPanel、TaskResultPanel。
10. UI 对齐 docs/design 设计源。
11. 任务详情页必须实时展示事件流。
12. 执行 npm run lint 和 npm run build。
13. 更新 docs/ai/task-progress.yaml，把 stage-07-react-console 标记为 completed。

验收标准：
- 控制台项目存在。
- npm run build 通过。
- /tasks、/tasks/new、/tasks/:taskId 路由存在。
- 任务详情展示计划、事件流、Subagent、Sandbox。
- SSE hook 使用 EventSource。
- task-progress.yaml 已更新。
```

## Required Structure

```text
apps/agent-console/
├─ src/
│  ├─ main.tsx
│  ├─ app/
│  │  └─ routes.tsx
│  ├─ features/
│  │  ├─ tasks/
│  │  │  ├─ api.ts
│  │  │  ├─ pages/TaskListPage.tsx
│  │  │  ├─ pages/TaskCreatePage.tsx
│  │  │  └─ pages/TaskDetailPage.tsx
│  │  ├─ events/
│  │  │  ├─ useTaskEventStream.ts
│  │  │  └─ components/EventTimeline.tsx
│  │  ├─ subagents/components/SubagentPanel.tsx
│  │  └─ sandboxes/components/SandboxPanel.tsx
│  ├─ lib/
│  └─ stores/
```

## Required Routes

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

## Verification Commands

```bash
cd apps/agent-console
npm run lint
npm run build
rg -n "EventSource|ExecutionPlanPanel|EventTimeline|SubagentPanel|SandboxPanel" src
```

## Progress Update Rule

```yaml
stage-07-react-console:
  status: completed
  verification_result: passed
  next_stage: stage-08-dramatiq-subagent
```

