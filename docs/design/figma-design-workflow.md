# 01 Forge Harness Figma 设计工作流

本文件定义 Figma 在项目中的执行顺序、设计产物和交付规则。Figma 阶段在仓库脚手架和代码实现之前完成。

## 阶段目标

Figma 是官网和控制台的设计参考。前端实现应对齐 Figma 的页面结构、组件状态、设计 token、布局密度和信息层级；如果与活跃产品规格冲突，以活跃产品规格为准。

## 固定产物

```text
docs/design/
├─ figma-production-brief.md
├─ design-tokens.json
└─ page-inventory.md
```

## Figma 文件结构

```text
Forge Harness
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

## 设计 Token

`design-tokens.json` 固定包含：

```text
color.background
color.surface
color.text
color.border
color.status
spacing
radius
shadow
font
layout
```

状态色覆盖：

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

## 页面交付

官网首页包含：

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

控制台任务详情包含：

```text
任务状态
执行计划
实时事件流
Subagent 面板
Sandbox 面板
模型调用信息
资源指标
最终结果
```

## AI/H5 规则

Gemini/H5 产物只进入视觉参考层和文案参考层。生产代码由 Next.js 与 React 组件重建。前端代码不得复制 AI 生成 H5。

## 验收

- `docs/design/figma-production-brief.md` 存在。
- `docs/design/design-tokens.json` 存在。
- `docs/design/page-inventory.md` 存在。
- Brief 覆盖官网、控制台、组件、状态、交互和交付规则。
