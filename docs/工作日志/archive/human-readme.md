# 已归档：原人读文档入口

> 2026-08-10 按 dev-workflow 重组后，本页只保留历史阅读顺序。当前入口见 [docs 索引](../../README.md)。

本目录面向产品、研发、设计、交付和管理人员。文档采用正式 Spec 口径，所有技术选型、模块边界、执行顺序和验收标准均为项目定稿。

全局入口：

- [Harness 正式规格总入口](../../design/product-spec.md)
- [Spec 功能索引](../../contracts/SPEC-INDEX.md)
- [Spec 模板](../../contracts/SPEC-TEMPLATE.md)
- [技术实现与流程进展总览](technical-implementation-progress.md)

## 阅读顺序

1. [GitHub 与 Git 工作流](../../development/git-github-workflow.md)
2. [Figma 设计工作流](../../design/figma-design-workflow.md)
3. [产品定位](../../design/product-positioning.md)
4. [总体架构](../../architecture/system-architecture-spec.md)
5. [研发流程](../../development/development-flow.md)
6. [官网与控制台](../../design/frontend-product.md)
7. [后端与运行时](../../architecture/backend-runtime.md)
8. [部署与运营](../../operations/deployment-operations.md)
9. [路线图与验收](../../plans/roadmap-acceptance.md)
10. [技术落地流程](../../development/technology-operation-flows.md)
11. [任务进度看板](task-progress-human.md)
12. [网站使用流程](../../design/website-usage-flow.md)
13. [功能文档目录](../../design/features/README.md)
14. [技术实现与流程进展总览](technical-implementation-progress.md)

## Spec 执行规则

- 功能变更先修改 `docs/design/features/*.md`。
- 接口变更同步 `docs/contracts/api/openapi.yaml` 和 `docs/contracts/api/openapi.json`。
- 数据、事件、工具、权限和部署变更同步 `docs/development/ai/reference`。
- 页面变更同步 `docs/development/ai/reference/frontend-spec.md`、`docs/design/page-inventory.md` 和对应功能 Spec。
- 验证结果同步 `docs/design/features/09-implementation-coverage.md` 与进度文档。

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
