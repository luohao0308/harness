# Enterprise AI Agent Harness Platform

本项目是生产级企业 AI Agent Harness 平台的定稿方案与工程规范。项目采用确定技术栈、确定架构边界、确定开发顺序，文档拆分为人读文档和 AI 读文档。

核心公式：

```text
Model + Harness = Agent
```

Model 负责理解、推理和生成。Harness 负责规划、执行、隔离、恢复、审计、监控和部署。平台目标是把大模型能力工程化为企业环境中的任务执行系统。

## 固定技术栈

```text
后端语言：Python 3.11
API 框架：FastAPI
数据校验：Pydantic v2
ORM：SQLAlchemy 2.0
数据库迁移：Alembic
数据库：PostgreSQL 16
缓存与队列：Redis 7
异步任务：Dramatiq + Redis Broker
容器沙箱：Docker SDK for Python
事件溯源：PostgreSQL append-only event table
日志系统：Loki
指标系统：Prometheus + Grafana
链路追踪：OpenTelemetry
官网：Next.js + TypeScript + Tailwind CSS
控制台：React + Vite + TypeScript + Tailwind CSS + shadcn/ui
状态与请求：Zustand + TanStack Query
图表：ECharts
部署：Docker Compose + systemd + Nginx
设计：Figma
```

## 文档结构

人读文档面向产品、研发、设计、交付和管理人员，强调业务理解、系统边界、研发流程和验收标准。

- [人读文档入口](./docs/human/README.md)
- [GitHub 与 Git 工作流](./docs/human/00-git-github-workflow.md)
- [Figma 设计工作流](./docs/human/01-figma-design-workflow.md)
- [产品定位](./docs/human/02-product-positioning.md)
- [总体架构](./docs/human/03-system-architecture.md)
- [研发流程](./docs/human/04-development-flow.md)
- [官网与控制台](./docs/human/05-frontend-product.md)
- [后端与运行时](./docs/human/06-backend-runtime.md)
- [部署与运营](./docs/human/07-deployment-operations.md)
- [路线图与验收](./docs/human/08-roadmap-acceptance.md)
- [技术落地流程](./docs/human/09-technology-operation-flows.md)
- [任务进度看板](./docs/human/10-task-progress.md)

AI 读文档面向代码代理、自动化实现工具和工程执行 Agent，强调唯一事实源、固定目录、接口契约、事件枚举、任务顺序和禁止事项。

- [AI 读文档入口](./docs/ai/README.md)
- [AI Master Prompt](./docs/ai/00-master-prompt.md)
- [执行协议](./docs/ai/00-execution-protocol.md)
- [任务进度](./docs/ai/01-task-progress.md)
- [机器可读任务进度](./docs/ai/task-progress.yaml)
- [人读任务进度看板](./docs/human/10-task-progress.md)
- [阶段 01：GitHub 与 Git 初始化](./docs/ai/02-stage-01-git-github.md)
- [阶段 02：Figma 设计源](./docs/ai/03-stage-02-figma-design.md)
- [阶段 03：仓库脚手架](./docs/ai/04-stage-03-repository-scaffold.md)
- [阶段 04：FastAPI 后端基础](./docs/ai/05-stage-04-backend-foundation.md)
- [阶段 05：Task 与 Event Store](./docs/ai/06-stage-05-task-event-store.md)
- [阶段 06：Planner 与 Executor](./docs/ai/07-stage-06-planner-executor.md)
- [阶段 07：React 控制台](./docs/ai/08-stage-07-react-console.md)
- [阶段 08：Dramatiq Subagent](./docs/ai/09-stage-08-dramatiq-subagent.md)
- [阶段 09：Docker Sandbox 与 WarmPool](./docs/ai/10-stage-09-sandbox-warmpool.md)
- [阶段 10：监控、日志、部署](./docs/ai/11-stage-10-observability-deployment.md)
- [运行时 Agent Prompts](./docs/ai/reference/runtime-agent-prompts.md)
- [Tool Registry 契约](./docs/ai/reference/tool-registry-spec.md)
- [Tool Registry YAML](./docs/ai/reference/tool-registry.yaml)
- [Prompt 契约 YAML](./docs/ai/reference/prompt-contracts.yaml)
- [安全策略矩阵](./docs/ai/reference/security-policy-matrix.md)
- [数据库 ERD 与迁移规则](./docs/ai/reference/database-erd-migrations.md)
- [数据库 Schema YAML](./docs/ai/reference/database-schema.yaml)
- [OpenAPI 契约](./docs/api/openapi-contract.md)
- [OpenAPI YAML](./docs/api/openapi.yaml)
- [Prompt Eval Cases](./docs/evals/prompt-eval-cases.yaml)
- [Prompt Eval Runbook](./docs/evals/prompt-eval-runbook.md)
- [安全威胁模型](./docs/security/threat-model.md)
- [QA 测试策略](./docs/qa/test-strategy.md)
- [端到端 Demo 剧本](./docs/demo/e2e-demo-script.md)
- [本地开发 Runbook](./docs/runbooks/local-development.md)
- [部署 Runbook](./docs/runbooks/deployment.md)
- [迁移 Runbook](./docs/runbooks/migrations.md)
- [回滚 Runbook](./docs/runbooks/rollback.md)
- [排障 Runbook](./docs/runbooks/troubleshooting.md)
- [ADR 目录](./docs/adr/0001-record-architecture-decisions.md)

## 项目结构

```text
harness/
├─ README.md
├─ .env.example
├─ docs/
│  ├─ ai/
│  ├─ human/
│  ├─ design/
│  ├─ api/
│  ├─ evals/
│  ├─ security/
│  ├─ qa/
│  ├─ demo/
│  ├─ runbooks/
│  └─ adr/
├─ apps/
│  ├─ web-site/
│  │  └─ .env.example
│  └─ agent-console/
│     └─ .env.example
├─ services/
│  ├─ api-server/
│  │  └─ .env.example
│  └─ sandbox-worker/
├─ deploy/
│  ├─ docker-compose/
│  │  └─ .env.example
│  ├─ systemd/
│  ├─ nginx/
│  └─ monitoring/
└─ scripts/
   ├─ check-docs.sh
   ├─ check-env.sh
   └─ validate-docs.py
```

## 执行顺序

```text
阶段 01：GitHub 与 Git 初始化
阶段 02：Figma 设计源
阶段 03：仓库脚手架
阶段 04：FastAPI 后端基础
阶段 05：Task 与 Event Store
阶段 06：Planner 与 Executor
阶段 07：React 控制台
阶段 08：Dramatiq Subagent
阶段 09：Docker Sandbox 与 WarmPool
阶段 10：监控、日志、部署
```

## 对外表述

正式官网使用以下表述：

```text
生产级企业 AI Agent Harness 平台
```

```text
将大模型能力工程化为具备审计、恢复、隔离、并发编排和私有化部署能力的企业任务执行系统。
```

正式材料禁止把“复现 Claude Code”作为主宣传语。内部技术材料使用“参考现代 Agentic Coding 产品的 Planner、Executor、Subagent、事件流和工具执行范式”描述来源。
