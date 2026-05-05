# Enterprise AI Agent Harness Platform

本项目是生产级企业 AI Agent Harness 平台的定稿方案与工程规范。项目采用确定技术栈、确定架构边界、确定开发顺序，文档统一收敛为正式 Spec。

核心公式：

```text
Model + Harness = Agent
```

Model 负责理解、推理和生成。Harness 负责规划、执行、隔离、恢复、审计、监控和部署。平台目标是把大模型能力工程化为企业环境中的任务执行系统。

## 产品功能范围

本平台交付的是企业 Agent 运行时和控制台，不只是任务列表页面。完整功能范围如下：

| 功能域 | 用户可见能力 | 技术实现落点 |
|---|---|---|
| 任务生命周期 | 创建任务、查看任务、启动任务、取消任务、恢复任务、查看结果 | Task API、Task 状态机、Event Store、OpenAPI |
| 计划与执行 | 将目标拆解为执行计划，按步骤执行，保留步骤状态 | Planner、Executor、execution_plans、task_steps |
| 事件流 | 实时查看任务事件、断线重连、按 sequence 继续读取 | append-only agent_events、SSE、Last-Event-ID、after_sequence |
| Replay 与恢复 | 按事件序号重放任务状态，定位失败点，生成调试摘要 | replay service、task_snapshots、Replay API |
| Subagent 并发 | 查看子 Agent、跟踪子任务、取消子 Agent | Dramatiq worker、agent_runs、Subagent API |
| 工具执行 | shell、文件、HTTP、测试、Git 等工具按策略执行 | Tool Registry、Policy Engine、Docker Sandbox |
| 模型调用审计 | 查看模型供应商、模型名、token、延迟、失败与 fallback | Model Gateway、model_calls、MODEL_* 事件 |
| 工具调用审计 | 查看工具入参、结果、耗时、策略拒绝、超时和失败 | tool_calls、TOOL_* 事件、POLICY_* 事件 |
| 沙箱治理 | 查看沙箱实例、预热池、运行状态、终止沙箱 | Sandbox API、WarmPool、Docker manager |
| 模型设置 | 管理模型网关、供应商、限流、健康状态 | Settings API、admin RBAC、控制台 settings/models |
| 策略设置 | 管理工具风险、审批规则、沙箱规则、审计要求 | Settings API、Policy Matrix、控制台 settings/policies |
| 观测与运营 | 查看任务吞吐、失败率、资源、模型与工具指标 | Prometheus、Grafana、Loki、OpenTelemetry |
| 控制台本地化 | 默认中文，顶栏切换中文/English，技术值保留原值并展示中文说明 | React Console i18n、frontend-spec、Figma brief |
| OpenAPI 导入 | 输出中文 OpenAPI YAML/JSON，支持 Swagger/Postman/Apifox 导入 | docs/api/openapi.yaml、docs/api/openapi.json、FastAPI schema |

## 实现契约

研发执行必须以契约文件为准，README 只做总入口和功能地图。

| 契约 | 事实源 |
|---|---|
| 全局 Spec 入口、优先级、变更流程 | [Harness 正式规格总入口](./docs/SPEC.md) |
| 功能域与文档映射 | [Spec 功能索引](./docs/SPEC-INDEX.md) |
| 新增功能文档格式 | [Spec 模板](./docs/SPEC-TEMPLATE.md) |
| 技术实现、接口和流程进展总览 | [技术实现与流程进展总览](./docs/TECHNICAL-IMPLEMENTATION-PROGRESS.md) |
| API 路径、请求、响应、安全方案 | [OpenAPI YAML](./docs/api/openapi.yaml) |
| API 人读说明 | [OpenAPI 契约](./docs/api/openapi-contract.md) |
| 数据表、字段、索引、关系 | [数据库 Schema YAML](./docs/ai/reference/database-schema.yaml) |
| 事件枚举、Event Store 规则 | [数据、事件与 API](./docs/ai/reference/data-events-api.md) |
| 工具列表、输入输出、风险等级 | [Tool Registry YAML](./docs/ai/reference/tool-registry.yaml) |
| 工具治理规则 | [Tool Registry 契约](./docs/ai/reference/tool-registry-spec.md) |
| 角色权限、工具策略、管理权限 | [安全策略矩阵](./docs/ai/reference/security-policy-matrix.md) |
| Planner、Executor、Subagent、Replay Prompt | [运行时 Agent Prompts](./docs/ai/reference/runtime-agent-prompts.md) |
| 前端路由、组件、中文文案规则 | [前端规格](./docs/ai/reference/frontend-spec.md) |
| 设计源与页面清单 | [Figma 生产 Brief](./docs/design/figma-production-brief.md) 与 [页面清单](./docs/design/page-inventory.md) |
| 使用流程与功能联动 | [网站使用流程](./docs/human/11-website-usage-flow.md) 与 [功能文档目录](./docs/human/features/README.md) |
| 部署、运行时目录、指标、日志 | [运行时与部署规格](./docs/ai/reference/runtime-deployment-spec.md) |
| 阶段执行状态 | [机器可读任务进度](./docs/ai/task-progress.yaml) |

## 当前实现状态

```text
当前阶段：阶段 13 Website Code Integration
当前状态：ready_for_review
当前 PR：https://github.com/luohao0308/harness/pull/11
运行时补齐：进行中
官网与控制台接入：进行中
```

当前已补齐认证、租户隔离、Docker Compose migration、事件序号并发安全、SSE 恢复、WarmPool 数据库事实源、任务生命周期、Replay、模型与工具审计查询、Settings 持久化、Subagent 创建与查询、中文 OpenAPI JSON/YAML 和官网公开下载入口。

当前运行时接口：

```text
POST /api/tasks
GET  /api/tasks
GET  /api/tasks/{task_id}
POST /api/tasks/{task_id}/start
POST /api/tasks/{task_id}/cancel
POST /api/tasks/{task_id}/resume
GET  /api/tasks/{task_id}/result
GET  /api/tasks/{task_id}/plan
GET  /api/tasks/{task_id}/steps
POST /api/tasks/{task_id}/replay
GET  /api/tasks/{task_id}/events
GET  /api/tasks/{task_id}/events/stream
GET  /api/tasks/{task_id}/subagents
POST /api/tasks/{task_id}/subagents
GET  /api/subagents/{subagent_id}
POST /api/subagents/{subagent_id}/cancel
GET  /api/tasks/{task_id}/model-calls
GET  /api/tasks/{task_id}/tool-calls
POST /api/tasks/{task_id}/tools/execute
GET  /api/sandboxes
GET  /api/sandboxes/warm-pool
GET  /api/sandboxes/{sandbox_id}
POST /api/sandboxes/{sandbox_id}/terminate
GET  /api/observability/summary
GET  /api/observability/logs
GET  /api/observability/traces/{trace_id}
GET  /api/observability/grafana/dashboards
GET  /api/observability/services/health
GET  /api/settings/models
PUT  /api/settings/models
GET  /api/settings/models/health
GET  /api/settings/policies
PUT  /api/settings/policies
GET  /health
GET  /metrics
```

当前代码落地状态：

| 要求 | 当前状态 | 证据 |
|---|---|---|
| 官网使用 Next.js | 已实现 | `apps/web-site/package.json`、`app/`、`components/`、公开 OpenAPI 文件 |
| 控制台使用 React + Vite | 已实现 | `apps/agent-console/package.json` 使用 Vite、React、TypeScript、Tailwind CSS |
| 后端使用 Python 3.11 + FastAPI | 已实现 | `services/api-server/pyproject.toml` 固定 `requires-python ==3.11.*` 并依赖 FastAPI |
| 异步任务使用 Dramatiq | 基础落地 | `services/api-server/app/workers/subagent_worker.py` 和 Docker Compose `agent-worker` 使用 Dramatiq |
| 数据库使用 PostgreSQL 16 | 已接入 | Docker Compose 使用 `postgres:16-alpine`，后端使用 SQLAlchemy 与 Alembic |
| 缓存与队列使用 Redis 7 | 已接入 | Docker Compose 使用 `redis:7-alpine`，后端依赖 Redis 与 Dramatiq broker |
| 容器沙箱使用 Docker SDK for Python | 已实现基础能力 | 后端依赖 `docker`，存在 Docker manager、WarmPool、shell 工具沙箱路径 |
| 日志使用 Loki | 已接入部署配置 | Docker Compose 包含 Loki，监控目录包含 `loki.yml` |
| 监控使用 Prometheus + Grafana | 已接入 | Docker Compose 包含 Prometheus 和 Grafana，后端提供 `/metrics` |
| 设计稿使用 Figma | 文档已约束，外部设计源未纳入仓库 | `docs/design` 中有 Figma production brief、page inventory、design tokens |
| Gemini/H5 产物只作为视觉参考和文案参考 | 文档已约束 | 生产前端必须由 React/Next.js 组件实现，不复制 AI 生成 H5 |
| 文档统一使用阶段、首个交付版、集成演示版和企业版 | 已覆盖 | README 与阶段文档统一使用固定术语 |

生产级增强项记录在 [实现覆盖与缺口](./docs/human/features/09-implementation-coverage.md)。README、OpenAPI、控制台页面只表述真实代码已有能力。

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

正式 Spec 面向产品、研发、设计、交付、管理人员和 AI 执行 Agent。所有变更先进入 Spec，再同步 OpenAPI、后端、前端、部署和验证。

- [Harness 正式规格总入口](./docs/SPEC.md)
- [Spec 功能索引](./docs/SPEC-INDEX.md)
- [Spec 模板](./docs/SPEC-TEMPLATE.md)
- [技术实现与流程进展总览](./docs/TECHNICAL-IMPLEMENTATION-PROGRESS.md)

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
- [网站使用流程](./docs/human/11-website-usage-flow.md)
- [功能文档目录](./docs/human/features/README.md)

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
- [阶段 11：Review P1 Production Hardening](./docs/ai/12-stage-11-review-p1-hardening.md)
- [阶段 12：Runtime Product Completion](./docs/ai/13-stage-12-runtime-product-completion.md)
- [阶段 13：Website Code Integration](./docs/ai/14-stage-13-website-code-integration.md)
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
阶段 11：Review P1 Production Hardening
阶段 12：Runtime Product Completion
阶段 13：Website Code Integration
```

## 交付版本术语

```text
阶段：工程执行顺序，必须按 docs/ai/task-progress.yaml 推进。
首个交付版：Docker Compose + systemd + Nginx + PostgreSQL + Redis + Prometheus + Grafana + Loki 的单环境交付形态。
集成演示版：接入 OpenAI-compatible Model Gateway、完整控制台演示、端到端任务链路和观测演示。
企业版：多组织、多用户、完整 RBAC、API Key 管理、审计导出、私有模型接入、Webhook、成本统计、备份与恢复。
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
