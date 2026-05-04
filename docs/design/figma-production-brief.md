# Figma Production Brief

本文件是阶段 02 的 Figma 设计源说明。Figma 文件、设计 token、页面结构和组件状态必须对齐本文件。

## 文件结构

```text
Agent Harness Platform
├─ 00 Design Tokens
├─ 01 Website
├─ 02 Console
└─ 03 Components
```

## Website Pages

```text
Home
Product
Architecture
Security
Deployment
Docs
Contact
```

## Console Pages

```text
Task List
Task Create
Task Detail
Event Timeline
Subagent Panel
Sandbox Panel
Observability
Model Settings
Policy Settings
```

## Home Page Sections

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

## Task Detail Layout

```text
Top Bar: task status, duration, actions
Left Panel: execution plan
Center Panel: event timeline and agent output
Right Panel: subagents, sandbox, model calls, resource metrics
Bottom Panel: result and artifacts
```

## Component States

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

## Production Rule

Gemini/H5 产物只进入视觉参考层和文案参考层。生产代码由 Next.js 与 React 组件重建。

