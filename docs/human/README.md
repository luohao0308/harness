# 人读文档入口

本目录面向产品、研发、设计、交付和管理人员。文档采用确定口径，所有技术选型、模块边界、执行顺序和验收标准均为项目定稿。

## 阅读顺序

1. [GitHub 与 Git 工作流](./00-git-github-workflow.md)
2. [Figma 设计工作流](./01-figma-design-workflow.md)
3. [产品定位](./02-product-positioning.md)
4. [总体架构](./03-system-architecture.md)
5. [研发流程](./04-development-flow.md)
6. [官网与控制台](./05-frontend-product.md)
7. [后端与运行时](./06-backend-runtime.md)
8. [部署与运营](./07-deployment-operations.md)
9. [路线图与验收](./08-roadmap-acceptance.md)
10. [技术落地流程](./09-technology-operation-flows.md)
11. [任务进度看板](./10-task-progress.md)

## 项目主线

```text
Model + Harness = Agent
```

平台围绕 Harness 层构建。大模型只提供推理能力，Harness 层提供任务规划、工具约束、沙箱隔离、事件溯源、断点恢复、子 Agent 编排、监控告警和私有化部署能力。

## 固定结论

- 官网使用 Next.js。
- 控制台使用 React + Vite。
- 后端使用 Python 3.11 + FastAPI。
- 异步任务使用 Dramatiq。
- 数据库使用 PostgreSQL 16。
- 缓存与队列使用 Redis 7。
- 容器沙箱使用 Docker SDK for Python。
- 日志使用 Loki。
- 监控使用 Prometheus + Grafana。
- 设计稿使用 Figma。
- Gemini/H5 产物只作为视觉参考和文案参考，生产前端由 React/Next.js 组件实现。
- 文档统一使用阶段、首个交付版、集成演示版和企业版。
