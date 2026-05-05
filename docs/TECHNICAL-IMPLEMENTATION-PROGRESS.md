# 技术实现与流程进展总览

## 定位

本文汇总当前文档体系、技术实现、后端接口、前端入口、部署基础、验证状态和未完成缺口。它是项目阶段复盘与后续实现排程的总览，不替代正式 Spec、OpenAPI 和阶段文档。

事实源优先级：

```text
docs/SPEC.md
-> docs/SPEC-INDEX.md
-> docs/human/features/*.md
-> docs/api/openapi.yaml
-> docs/ai/reference/*.md
-> docs/runbooks/*.md
-> docs/human/10-task-progress.md
-> docs/ai/task-progress.yaml
```

## 文档体系进展

| 文档域 | 位置 | 当前进展 | 用途 |
|---|---|---|---|
| 全局 Spec | `docs/SPEC.md` | 已收敛 | 定义文档层级、优先级、变更流程和交付分层 |
| 功能索引 | `docs/SPEC-INDEX.md` | 已收敛 | 功能域到 Spec、OpenAPI、参考规格、运行手册和验证入口的映射 |
| Spec 模板 | `docs/SPEC-TEMPLATE.md` | 已收敛 | 新功能文档统一格式 |
| 功能 Spec | `docs/human/features/*.md` | 已收敛 | 每个功能独立描述目标、能力、接口、数据、事件、权限、状态、缺口和验收 |
| OpenAPI | `docs/api/openapi.yaml`、`docs/api/openapi.json` | 已同步当前后端 | Swagger、Postman、Apifox 导入与后端契约 |
| 参考规格 | `docs/ai/reference/*.md`、`*.yaml` | 已覆盖主干 | 架构、数据、事件、工具、权限、前端、部署、Prompt |
| 设计规格 | `docs/design/*` | 已覆盖主干 | 官网、控制台、页面清单、Figma Brief、设计 token |
| 质量规格 | `docs/qa/*`、`docs/evals/*` | 已覆盖主干 | 后端、前端、Prompt、端到端验收 |
| 运行手册 | `docs/runbooks/*` | 已覆盖主干 | 本地开发、部署、迁移、回滚、排障 |
| 进度文档 | `docs/human/10-task-progress.md`、`docs/ai/task-progress.yaml` | 已持续记录 | 阶段状态、PR、验证和遗留说明 |

## 主流程

```text
官网
-> 控制台
-> 创建任务
-> Planner 生成计划
-> Executor 执行 sync step
-> async step 派生 Subagent
-> Tool Registry / Policy Engine
-> Docker Sandbox / WarmPool
-> Event Store 写入事件
-> Replay / Resume 恢复
-> Result 输出
-> Observability / Settings 管理运行面
-> OpenAPI 支撑外部集成
```

## 技术栈落地进展

| 技术项 | 目标 | 当前状态 | 证据 |
|---|---|---|---|
| 官网 | Next.js | 已接入基础工程 | `apps/web-site` |
| 控制台 | React + Vite | 已接入主要运行页面 | `apps/agent-console` |
| 后端 | Python 3.11 + FastAPI | 已落地 API 服务 | `services/api-server` |
| 数据库 | PostgreSQL 16 | 已接入模型和迁移 | `deploy/docker-compose`、Alembic |
| 缓存与队列 | Redis 7 | 已接入 Dramatiq Broker | `agent-worker`、Redis 服务 |
| 异步任务 | Dramatiq | 基础落地 | `services/api-server/app/workers/subagent_worker.py` |
| 沙箱 | Docker SDK for Python | 基础落地 | Docker Manager、Sandbox API |
| WarmPool | 预热容器池 | 已落地状态接口和数据库事实源 | `GET /api/sandboxes/warm-pool` |
| 事件溯源 | append-only event table | 已落地 | `agent_events`、Event Store |
| Replay | snapshot + event replay | 基础落地 | `POST /api/tasks/{task_id}/replay` |
| 模型网关 | OpenAI-compatible | 基础落地 | Model Gateway、model_calls |
| 工具治理 | Tool Registry + Policy Engine | 基础落地 | Tool Runner、tool_calls |
| 观测 | Prometheus + Grafana + Loki + OTel | 部署基础已接入，深度查询待补 | `/metrics`、Observability Summary |
| 本地化 | 默认中文，English 切换 | 基础落地 | 控制台 Shell 和部分页面 |

## 功能实现与接口进展

| 功能域 | 用户能力 | 已落地接口 | 当前状态 |
|---|---|---|---|
| 任务生命周期 | 创建、查看、启动、取消、恢复、结果 | `POST /api/tasks`、`GET /api/tasks`、`GET /api/tasks/{task_id}`、`POST /api/tasks/{task_id}/start`、`POST /api/tasks/{task_id}/cancel`、`POST /api/tasks/{task_id}/resume`、`GET /api/tasks/{task_id}/result` | 已落地 |
| 计划与执行 | 查看计划、步骤、同步执行、异步派生 | `GET /api/tasks/{task_id}/plan`、`GET /api/tasks/{task_id}/steps`、`POST /api/tasks/{task_id}/start` | 基础落地，已支持模型 JSON 计划解析 |
| 同步执行 | Executor 直接执行 step | `GET /api/tasks/{task_id}/steps`、`GET /api/tasks/{task_id}/events` | 基础落地 |
| 异步执行 | async step 派生 Subagent | `GET /api/tasks/{task_id}/plan`、`GET /api/tasks/{task_id}/subagents`、`POST /api/tasks/{task_id}/subagents` | 基础落地，已请求 Dramatiq 入队 |
| 事件流 | 事件查询、SSE、断线续读 | `GET /api/tasks/{task_id}/events`、`GET /api/tasks/{task_id}/events/stream` | 已落地 |
| Replay 与恢复 | 重放状态、定位失败点、恢复执行 | `POST /api/tasks/{task_id}/replay`、`POST /api/tasks/{task_id}/resume` | 基础落地 |
| Subagent 并发 | 查询、创建、取消、状态追踪 | `GET /api/tasks/{task_id}/subagents`、`POST /api/tasks/{task_id}/subagents`、`GET /api/subagents/{subagent_id}`、`POST /api/subagents/{subagent_id}/cancel` | 已落地 |
| 工具执行 | 按策略执行工具 | `POST /api/tasks/{task_id}/tools/execute` | 基础落地 |
| 模型调用审计 | 查询供应商、模型、token、延迟、失败 | `GET /api/tasks/{task_id}/model-calls` | 基础落地 |
| 工具调用审计 | 查询入参、结果、耗时、拒绝、失败 | `GET /api/tasks/{task_id}/tool-calls` | 基础落地 |
| 沙箱治理 | 沙箱列表、详情、终止 | `GET /api/sandboxes`、`GET /api/sandboxes/{sandbox_id}`、`POST /api/sandboxes/{sandbox_id}/terminate` | 已落地 |
| WarmPool | 查看预热池状态 | `GET /api/sandboxes/warm-pool` | 已落地 |
| 模型设置 | 供应商、模型、限流、健康状态 | `GET /api/settings/models`、`PUT /api/settings/models`、`GET /api/settings/models/health` | 已落地 |
| 策略设置 | 工具风险、审批、沙箱、审计要求 | `GET /api/settings/policies`、`PUT /api/settings/policies` | 已落地 |
| 观测摘要 | 任务、模型、工具、沙箱、WarmPool 汇总 | `GET /api/observability/summary`、`GET /metrics` | 已落地 |
| OpenAPI 导入 | 中文 JSON/YAML 导入 | `GET /openapi.json`、`docs/api/openapi.json`、`docs/api/openapi.yaml` | 已落地 |

## 同步执行与异步执行体现

| 执行类型 | 后端体现 | 前端体现 | 数据体现 | 当前状态 |
|---|---|---|---|---|
| 同步执行 | Executor 执行 `execution_mode=sync` 的 step | 任务详情执行计划展示“同步执行”和步骤状态 | `task_steps.execution_mode=sync`、`STEP_STARTED`、`STEP_COMPLETED` | 基础落地 |
| 异步执行 | Executor 对 `execution_mode=async` 且 `can_spawn_subagent=true` 的 step 派生 Subagent | 任务详情执行计划展示“异步执行”，Subagent 面板展示子 Agent | `task_steps.assigned_agent_id`、`agent_runs.status`、`SUBAGENT_SPAWNED` | 基础落地 |
| 并发控制 | Subagent 上限固定 5 | 页面展示任务最大子 Agent 数 | `tasks.max_subagents`、`agent_runs` | 已落地 |
| 超时保护 | worker 使用 timeout | 子 Agent 列表展示 timeout 时间 | `agent_runs.timeout_at`、`SUBAGENT_TIMEOUT` | 基础落地 |

## 页面进展

| 页面 | 能力 | 数据来源 | 当前状态 |
|---|---|---|---|
| `/tasks` | 任务列表 | Task API | 已接入 |
| `/tasks/new` | 创建任务、配置模型和 max_subagents | Task API | 已接入 |
| `/tasks/:taskId` | 详情、计划、事件、Replay、结果、Subagent、审计 | Task、Plan、Steps、Events、Replay、Audit、Subagent API | 已接入 |
| `/tasks/:taskId/events` | 事件流聚焦 | Events API、SSE | 已接入 |
| `/tasks/:taskId/subagents` | 子 Agent 聚焦 | Subagent API | 已接入 |
| `/subagents` | 子 Agent 列表 | Task API、Subagent API | 已接入 |
| `/sandboxes` | 沙箱和 WarmPool | Sandbox API、WarmPool API | 已接入 |
| `/observability` | 运行摘要 | Observability Summary、Metrics | 基础接入 |
| `/settings/models` | 模型设置 | Settings Models API | 已接入 |
| `/settings/policies` | 策略设置 | Settings Policies API | 已接入 |
| 官网 | 产品展示、文档、OpenAPI 下载 | Next.js、公开 OpenAPI 文件 | 基础接入，最终官网代码待整合 |

## 观测与运行进展

| 能力 | 当前状态 | 已有入口 | 待补目标 |
|---|---|---|---|
| Prometheus 指标 | 已落地 | `GET /metrics` | 增强 dashboard 指标覆盖 |
| 观测摘要 | 已落地 | `GET /api/observability/summary` | 增加队列、耗时分位和深链 |
| Grafana | 部署基础已接入 | Grafana 服务 | `GET /api/observability/grafana/dashboards` |
| Loki | 部署基础已接入 | Loki 服务 | `GET /api/observability/logs` |
| OpenTelemetry | trace_id 基础已接入 | 响应头与 collector | `GET /api/observability/traces/{trace_id}` |
| 服务健康 | API 健康已接入 | `GET /health` | `GET /api/observability/services/health` |

## 当前未完成缺口

| 缺口 | 影响 | 目标文档 |
|---|---|---|
| LLM Planner 增强 | 已解析模型 JSON 计划，Prompt 重试和版本对比仍需增强 | `docs/human/features/02-planner-executor.md` |
| Worker 级恢复 | 长任务跨进程恢复仍需增强 | `docs/human/features/03-event-sourcing-replay.md` |
| Subagent 工具链执行 | worker 已回写 assignment 摘要，模型、工具、沙箱组合执行仍需增强 | `docs/human/features/04-subagent-orchestration.md` |
| 父任务聚合子 Agent 结果 | 任务结果摘要对异步输出聚合不足 | `docs/human/features/04-subagent-orchestration.md` |
| 工具结果解析 | 工具审计详情和产物解析不足 | `docs/human/features/06-model-tool-audit.md` |
| TPM 限流与供应商熔断 | 模型成本和稳定性治理仍需增强 | `docs/human/features/06-model-tool-audit.md` |
| Loki 日志查询 | 控制台无法按 task_id、trace_id 查结构化日志 | `docs/human/features/10-observability-localization-spec.md` |
| Grafana 代理 | 控制台无法读取 dashboard 元数据 | `docs/human/features/10-observability-localization-spec.md` |
| Trace 查询 | 控制台无法按 trace_id 查看链路 | `docs/human/features/10-observability-localization-spec.md` |
| 控制台全量 i18n | 部分旧页面仍有英文原始文案 | `docs/human/features/10-observability-localization-spec.md` |
| 官网最终接入 | 用户提供的官网代码还需整合 | `docs/human/features/08-website-console-openapi.md` |

## 流程进展

| 阶段 | 文档 | 当前状态 |
|---|---|---|
| 阶段 01 | `docs/ai/02-stage-01-git-github.md` | 已完成 |
| 阶段 02 | `docs/ai/03-stage-02-figma-design.md` | 已完成 |
| 阶段 03 | `docs/ai/04-stage-03-repository-scaffold.md` | 已完成 |
| 阶段 04 | `docs/ai/05-stage-04-backend-foundation.md` | 已完成 |
| 阶段 05 | `docs/ai/06-stage-05-task-event-store.md` | 已完成 |
| 阶段 06 | `docs/ai/07-stage-06-planner-executor.md` | 已完成，运行时增强仍在功能 Spec 缺口中 |
| 阶段 07 | `docs/ai/08-stage-07-react-console.md` | 已完成，页面细节仍按功能 Spec 增强 |
| 阶段 08 | `docs/ai/09-stage-08-dramatiq-subagent.md` | 已完成，真实长任务执行仍需增强 |
| 阶段 09 | `docs/ai/10-stage-09-sandbox-warmpool.md` | 已完成，资源治理仍需增强 |
| 阶段 10 | `docs/ai/11-stage-10-observability-deployment.md` | 已完成基础部署，深度查询接口待补 |
| 阶段 11 | `docs/ai/12-stage-11-review-p1-hardening.md` | 已完成 |
| 阶段 12 | `docs/ai/13-stage-12-runtime-product-completion.md` | 基础能力已补齐，增强项转入功能 Spec |
| 阶段 13 | `docs/ai/14-stage-13-website-code-integration.md` | 进行中，等待最终官网代码整合 |

## 后续执行顺序

```text
1. 完成同步执行 / 异步执行派生关系展示
2. 补 LLM Planner 结构重试和计划版本对比
3. 补 Subagent worker 工具链执行和父任务结果聚合
4. 补 Worker 级恢复编排
5. 补 Loki logs、Grafana dashboards、Trace 查询和观测服务健康接口
6. 补控制台全量 i18n
7. 整合用户提供的官网代码
8. 同步 OpenAPI、测试、Runbook 和覆盖文档
```

## 验证命令

```bash
python3 scripts/validate-docs.py
bash scripts/check-docs.sh
cd services/api-server && .venv/bin/python -m pytest
cd services/api-server && .venv/bin/python -m ruff check app tests
cd apps/agent-console && npm run lint
cd apps/agent-console && npm run build
cd apps/web-site && npm run lint
cd apps/web-site && npm run build
```
