# 03 阶段 02：Figma 设计源

## 阶段目标

建立 Figma 设计源的生产级说明、页面清单、设计 token、组件规范和前端交付约束。此阶段在代码脚手架之前完成。

## Required Context

- [执行协议](./00-execution-protocol.md)
- [任务进度说明](./01-task-progress.md)
- [机器可读任务进度](./task-progress.yaml)
- [前端规格](./reference/frontend-spec.md)

## AI 执行提示词

```text
你是本项目的产品设计执行 Agent。现在执行阶段 02：Figma 设计源。

必须先读取 docs/ai/00-execution-protocol.md、docs/ai/01-task-progress.md、docs/ai/task-progress.yaml 和 docs/ai/reference/frontend-spec.md。
只执行阶段 02，不进入阶段 03。

执行内容：
1. 创建 docs/design/figma-production-brief.md。
2. 创建 docs/design/design-tokens.json。
3. 创建 docs/design/page-inventory.md。
4. 在 Figma Brief 中写清楚文件结构、页面、组件、设计 token、控制台布局、官网首屏、状态色、交互状态和交付规则。
5. 明确 Gemini/H5 产物只进入参考层，生产前端由 Next.js 和 React 重建。
6. 明确 Figma 是设计事实源，前端实现对齐 Figma。
7. 更新 docs/ai/task-progress.yaml，把 stage-02-figma-design 标记为 completed。

验收标准：
- docs/design/figma-production-brief.md 存在。
- docs/design/design-tokens.json 存在。
- docs/design/page-inventory.md 存在。
- Brief 包含官网首页、架构页、任务列表、任务详情、事件流、Subagent、Sandbox。
- task-progress.yaml 已更新。
```

## Required Design Files

```text
docs/design/
├─ figma-production-brief.md
├─ design-tokens.json
└─ page-inventory.md
```

## Figma 文件结构

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
│  ├─ Task List
│  ├─ Task Create
│  ├─ Task Detail
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

## Design Token Requirements

`design-tokens.json` 必须包含：

```json
{
  "color": {
    "background": {},
    "surface": {},
    "text": {},
    "border": {},
    "status": {}
  },
  "spacing": {},
  "radius": {},
  "shadow": {},
  "font": {},
  "layout": {}
}
```

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

## Verification Commands

```bash
test -f docs/design/figma-production-brief.md
test -f docs/design/design-tokens.json
test -f docs/design/page-inventory.md
rg -n "Task Detail|Event Timeline|Subagent|Sandbox|WarmPool|Next.js|React" docs/design
```

## Progress Update Rule

完成后更新 [机器可读任务进度](./task-progress.yaml)：

```yaml
stage-02-figma-design:
  status: completed
  verification_result: passed
  next_stage: stage-03-repository-scaffold
```

