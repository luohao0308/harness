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
| 沙箱 | Docker SDK for Python | 已落地 Settings 动态资源和 network allowlist | Docker Manager、Sandbox API、Policy Engine |
| WarmPool | 预热容器池 | 已落地状态接口和数据库事实源 | `GET /api/sandboxes/warm-pool` |
| 事件溯源 | append-only event table | 已落地 | `agent_events`、Event Store |
| Replay | snapshot + event replay | 基础落地 | `POST /api/tasks/{task_id}/replay` |
| 模型网关 | OpenAI-compatible | 基础落地 | Model Gateway、model_calls |
| 工具治理 | Tool Registry + Policy Engine | 基础落地 | Tool Runner、tool_calls |
| 观测 | Prometheus + Grafana + Loki + OTel | 深度观测接口、Grafana provisioning、Grafana admin/operator RBAC、Promtail 采集和 Loki 标签检索已落地 | `/metrics`、Observability Summary、Logs、Trace、Dashboard、Health |
| 本地化 | 默认中文，English 切换 | 已落地 | 控制台 Shell、任务、详情、事件、Subagent、沙箱、观测、模型设置和策略设置页面 |

## 功能实现与接口进展

| 功能域 | 用户能力 | 已落地接口 | 当前状态 |
|---|---|---|---|
| 任务生命周期 | 创建、查看、启动、取消、恢复、结果 | `POST /api/tasks`、`GET /api/tasks`、`GET /api/tasks/{task_id}`、`POST /api/tasks/{task_id}/start`、`POST /api/tasks/{task_id}/cancel`、`POST /api/tasks/{task_id}/resume`、`GET /api/tasks/{task_id}/result` | 已落地 |
| 计划与执行 | 查看计划、步骤、同步执行、异步派生、版本对比、步骤断点续跑 | `GET /api/tasks/{task_id}/plan`、`GET /api/tasks/{task_id}/plans`、`GET /api/tasks/{task_id}/plans/diff`、`GET /api/tasks/{task_id}/steps`、`POST /api/tasks/{task_id}/steps/resume`、`POST /api/tasks/{task_id}/start` | 已落地，已支持 Planner Prompt 1.1、模型 JSON 计划解析、一次修复、来源展示、步骤元数据、版本对比和步骤断点续跑 |
| 同步执行 | Executor 直接执行 step | `GET /api/tasks/{task_id}/steps`、`GET /api/tasks/{task_id}/events` | 基础落地 |
| 异步执行 | async step 派生 Subagent | `GET /api/tasks/{task_id}/plan`、`GET /api/tasks/{task_id}/subagents`、`POST /api/tasks/{task_id}/subagents` | 基础落地，已请求 Dramatiq 入队 |
| 事件流 | 事件查询、SSE、断线续读 | `GET /api/tasks/{task_id}/events`、`GET /api/tasks/{task_id}/events/stream` | 已落地 |
| Replay 与恢复 | 重放状态、定位失败点、恢复执行、恢复卡住的子 Agent、恢复批次历史 | `POST /api/tasks/{task_id}/replay`、`POST /api/tasks/{task_id}/resume`、`POST /api/tasks/{task_id}/subagents/recover`、`GET /api/tasks/{task_id}/subagents/recovery-batches` | 已落地 |
| Subagent 并发 | 查询、创建、取消、状态追踪、组织级批量状态筛选 | `GET /api/tasks/{task_id}/subagents`、`POST /api/tasks/{task_id}/subagents`、`GET /api/subagents`、`GET /api/subagents/{subagent_id}`、`POST /api/subagents/{subagent_id}/cancel` | 已落地 |
| Subagent 恢复运营 | 跨任务查看恢复批次、扫描数、恢复数、动作统计和任务聚合 | `GET /api/subagents/recovery/summary`、`GET /api/tasks/{task_id}/subagents/recovery-batches` | 已落地 |
| Subagent 结果聚合 | 在父任务结果中查看异步摘要 | `GET /api/tasks/{task_id}/result` | 已落地 |
| Subagent 工具链 | worker 执行 assignment 内工具并审计 | `GET /api/tasks/{task_id}/tool-calls`、`GET /api/tasks/{task_id}/result` | 基础落地 |
| 工具执行 | 按策略执行工具 | `POST /api/tasks/{task_id}/tools/execute` | 基础落地 |
| 模型调用审计 | 查询供应商、模型、token、延迟、失败 | `GET /api/tasks/{task_id}/model-calls` | 基础落地 |
| 工具调用审计 | 查询入参、结果、耗时、拒绝、失败、Trace 深链 | `GET /api/tasks/{task_id}/tool-calls` | 已落地，支持工具、状态、风险和 Trace 筛选 |
| 沙箱治理 | 沙箱列表、详情、终止、资源规格和网络白名单 | `GET /api/sandboxes`、`GET /api/sandboxes/{sandbox_id}`、`POST /api/sandboxes/{sandbox_id}/terminate`、`GET/PUT /api/settings/policies` | 已落地 |
| WarmPool | 查看预热池状态，自定义资源绕过默认池 | `GET /api/sandboxes/warm-pool` | 已落地 |
| 模型设置 | 供应商、模型、RPM、TPM、主动探测、熔断状态 | `GET /api/settings/models`、`PUT /api/settings/models`、`GET /api/settings/models/health` | 已落地 |
| 策略设置 | 工具风险、审批、沙箱、审计要求 | `GET /api/settings/policies`、`PUT /api/settings/policies` | 已落地 |
| 观测摘要 | 任务、模型、工具、沙箱、WarmPool 与 Subagent 队列汇总 | `GET /api/observability/summary`、`GET /metrics` | 已落地 |
| 观测导出留存 | 查询导出入口、导出文件、查看历史、下载历史文件 | `GET /api/observability/exports`、`GET /api/observability/exports/logs`、`GET /api/observability/exports/traces/{trace_id}`、`GET /api/observability/exports/grafana/dashboards`、`GET /api/observability/exports/services/health`、`GET /api/observability/exports/history`、`GET /api/observability/exports/history/{export_id}/download` | 已落地 |
| OpenAPI 导入 | 中文 JSON/YAML 导入 | `GET /openapi.json`、`docs/api/openapi.json`、`docs/api/openapi.yaml` | 已落地 |

## 同步执行与异步执行体现

| 执行类型 | 后端体现 | 前端体现 | 数据体现 | 当前状态 |
|---|---|---|---|---|
| 同步执行 | Executor 执行 `execution_mode=sync` 的 step | 任务详情执行计划展示“同步执行”和步骤状态 | `task_steps.execution_mode=sync`、`STEP_STARTED`、`STEP_COMPLETED` | 基础落地 |
| 异步执行 | Executor 对 `execution_mode=async` 且 `can_spawn_subagent=true` 的 step 派生 Subagent | 执行计划展示“异步执行”、子 Agent ID 和状态，Subagent 面板展示来源 step | `task_steps.assigned_agent_id`、`agent_runs.status`、`SUBAGENT_SPAWNED` | 基础落地 |
| 并发控制 | Subagent 上限固定 5 | 页面展示任务最大子 Agent 数 | `tasks.max_subagents`、`agent_runs` | 已落地 |
| 超时保护 | worker 使用 timeout | 子 Agent 列表展示 timeout 时间 | `agent_runs.timeout_at`、`SUBAGENT_TIMEOUT` | 基础落地 |

## 页面进展

| 页面 | 能力 | 数据来源 | 当前状态 |
|---|---|---|---|
| `/tasks` | 任务列表 | Task API | 已接入 |
| `/tasks/new` | 创建任务、配置模型和 max_subagents | Task API | 已接入 |
| `/tasks/:taskId` | 详情、计划、事件、Replay、步骤续跑、结果、Subagent、审计 | Task、Plan、Steps、Step Resume、Events、Replay、Audit、Subagent API | 已接入，执行计划面板支持从指定步骤续跑，工具审计支持筛选和 Trace 深链 |
| `/tasks/:taskId/events` | 事件流聚焦 | Events API、SSE | 已接入 |
| `/tasks/:taskId/subagents` | 子 Agent 聚焦 | Subagent API | 已接入 |
| `/subagents` | 组织级子 Agent 批量状态、状态筛选、任务跳转和详情跳转 | Subagent API | 已接入 |
| `/subagents/:subagentId` | 子 Agent 详情、取消、结果产物、工具结果、ReAct 轨迹、上下文压缩 | Subagent API、Task Result API | 已接入 |
| `/sandboxes` | 沙箱和 WarmPool | Sandbox API、WarmPool API | 已接入 |
| `/observability` | 运行摘要 | Observability Summary、Metrics | 基础接入 |
| `/observability` 恢复运营区 | 跨任务子 Agent 恢复批次、动作统计和任务聚合 | Subagent Recovery Summary API | 已接入 |
| `/settings/models` | 模型设置 | Settings Models API、Model Health API | 已接入，展示 RPM、TPM、探测模式和熔断状态 |
| `/settings/policies` | 策略设置 | Settings Policies API | 已接入 |
| 官网 | 产品展示、文档、OpenAPI 下载 | Next.js、公开 OpenAPI 文件 | 已接入，首页、产品、架构、方案、安全、部署、文档和联系页已接通 |

## 观测与运行进展

| 能力 | 当前状态 | 已有入口 | 待补目标 |
|---|---|---|---|
| Prometheus 指标 | 已落地 | `GET /metrics` | 增强 dashboard 指标覆盖 |
| 观测摘要 | 已落地 | `GET /api/observability/summary` | 已返回子 Agent 队列容量、等待、运行、剩余槽位和使用率 |
| Grafana | 已落地 | `GET /api/observability/grafana/dashboards`、Basic Auth 代理、provisioning、admin/operator RBAC | 增强 dashboard 指标覆盖 |
| Loki | 基础落地 | `GET /api/observability/logs`、Promtail 采集、标签检索 | 增强日志检索深链 |
| OpenTelemetry | 已落地 | `GET /api/observability/traces/{trace_id}`、Tempo、OTel Collector | 已支持服务、Span 名称和属性键值检索 |
| 日志与 Trace 深链 | 已落地 | `GET /api/observability/logs`、`GET /api/observability/traces/{trace_id}`、控制台筛选查询台、观测导出接口、导出历史接口 | 已支持导出留存和 span 属性检索 |
| 服务健康 | 已落地 | `GET /health`、`GET /api/observability/services/health`、admin/operator RBAC | 增强告警联动 |

## 本轮完成收口

| 收口项 | 当前结果 | 证据 |
|---|---|---|
| Subagent 结果产物详情 | 已新增单个子 Agent 详情页，可查看 assignment、状态、取消动作、结果摘要、产物、工具结果、ReAct 轨迹和上下文压缩摘要 | `/subagents/:subagentId`、`GET /api/subagents/{subagent_id}`、`GET /api/tasks/{task_id}/result` |
| 控制台边缘文案巡检 | 新增详情页按默认中文、English 切换接入；列表、任务结果和详情入口均使用双语文案 | `apps/agent-console/src/features/subagents/pages/SubagentDetailPage.tsx` |
| 官网最终接入 | 官网首页能力文案中文优先，控制台页面清单已链接真实控制台路径，产品页补充子 Agent 详情入口 | `apps/web-site/components/Homepage.tsx`、`apps/web-site/components/Product.tsx` |
| 企业级观测运营 | 已新增导出文件留存、历史下载、子 Agent 队列摘要和 Trace span 属性检索 | `GET /api/observability/exports/history`、`GET /api/observability/summary`、`GET /api/observability/traces/{trace_id}` |

## 后续增强队列

| 增强项 | 说明 | 目标文档 |
|---|---|---|
| Worker 级恢复跨任务汇总 | 已落地组织级恢复运营摘要；后续增强跨组织汇总和导出 | `docs/human/features/04-subagent-orchestration.md` |
| 观测深链 | Loki 与 Tempo 控制台深链筛选已落地，Grafana 与服务健康 RBAC 已落地，观测导出入口、导出留存、队列图表和 Span 属性检索已落地 | `docs/human/features/10-observability-localization-spec.md` |
| Worker 跨进程接管 | 步骤级断点续跑已落地，后续增强 Worker 崩溃后的自动接管 | `docs/human/features/02-planner-executor.md` |

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
| 阶段 13 | `docs/ai/14-stage-13-website-code-integration.md` | 已完成本轮官网与控制台收口 |

## 后续执行顺序

```text
1. 持续增强 Worker 级恢复跨任务汇总
2. 增强观测深链、队列图表和导出留存
3. 增强 Worker 跨进程接管与批量操作
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
