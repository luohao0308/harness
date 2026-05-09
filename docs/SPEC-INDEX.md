# Spec 功能索引

## 定位

本索引用于把功能域、产品规格、API 规格、参考规格、运行手册和验证入口连成一张表。任何代码变更进入实现前，必须先定位对应 Spec。

## 功能索引

| 功能域 | 功能规格 | API 规格 | 参考规格 | 前端与设计 | 运行与验证 | 当前状态 |
|---|---|---|---|---|---|---|
| Agent Workspace Pro | [11 Agent Workspace](./human/features/11-agent-workspace.md)、[产品规格](./00-product-spec.md) | [API 规格](./03-api-spec.md)、[OpenAPI](./api/openapi.yaml) | [Tool MCP Runtime](./05-tool-mcp-runtime-spec.md)、[前端规格](./ai/reference/frontend-spec.md) | [Console UI Spec](./08-console-ui-spec.md)、[Stage 01](./ai/stages/01-agent-workspace-console.md) | [QA 策略](./qa/test-strategy.md)、[Gap Register](./workspace-pro-gap-register.md) | 垂直切片已落地；full-spec gap 已追踪 |
| 任务生命周期 | [01 任务生命周期](./human/features/01-task-lifecycle.md) | [OpenAPI](./api/openapi.yaml) | [数据、事件与 API](./ai/reference/data-events-api.md)、[数据库 Schema](./ai/reference/database-schema.yaml) | [前端规格](./ai/reference/frontend-spec.md)、[页面清单](./design/page-inventory.md) | [QA 策略](./qa/test-strategy.md)、[本地开发](./runbooks/local-development.md) | 已落地 |
| 计划与执行 | [02 Planner 与 Executor](./human/features/02-planner-executor.md) | [OpenAPI](./api/openapi.yaml) | [运行时 Agent Prompts](./ai/reference/runtime-agent-prompts.md)、[Tool Registry](./ai/reference/tool-registry-spec.md) | [前端规格](./ai/reference/frontend-spec.md) | [QA 策略](./qa/test-strategy.md) | 已落地 |
| 事件流 | [03 Event Sourcing 与 Replay](./human/features/03-event-sourcing-replay.md) | [OpenAPI](./api/openapi.yaml) | [数据、事件与 API](./ai/reference/data-events-api.md) | [前端规格](./ai/reference/frontend-spec.md) | [QA 策略](./qa/test-strategy.md) | 已落地 |
| Replay 与恢复 | [03 Event Sourcing 与 Replay](./human/features/03-event-sourcing-replay.md) | [OpenAPI](./api/openapi.yaml) | [数据库 ERD 与迁移规则](./ai/reference/database-erd-migrations.md) | [前端规格](./ai/reference/frontend-spec.md) | [QA 策略](./qa/test-strategy.md) | 已落地 |
| Subagent 并发 | [04 Subagent 编排](./human/features/04-subagent-orchestration.md) | [OpenAPI](./api/openapi.yaml) | [运行时 Agent Prompts](./ai/reference/runtime-agent-prompts.md)、[运行时与部署规格](./ai/reference/runtime-deployment-spec.md) | [前端规格](./ai/reference/frontend-spec.md) | [部署 Runbook](./runbooks/deployment.md) | 已落地 |
| 工具执行 | [06 模型与工具审计](./human/features/06-model-tool-audit.md) | [OpenAPI](./api/openapi.yaml) | [Tool Registry YAML](./ai/reference/tool-registry.yaml)、[安全策略矩阵](./ai/reference/security-policy-matrix.md) | [前端规格](./ai/reference/frontend-spec.md) | [安全威胁模型](./security/threat-model.md) | 已落地 |
| 模型调用审计 | [06 模型与工具审计](./human/features/06-model-tool-audit.md) | [OpenAPI](./api/openapi.yaml) | [运行时 Agent Prompts](./ai/reference/runtime-agent-prompts.md)、[数据库 Schema](./ai/reference/database-schema.yaml) | [前端规格](./ai/reference/frontend-spec.md) | [QA 策略](./qa/test-strategy.md) | 已落地 |
| 工具调用审计 | [06 模型与工具审计](./human/features/06-model-tool-audit.md) | [OpenAPI](./api/openapi.yaml) | [Tool Registry](./ai/reference/tool-registry-spec.md)、[安全策略矩阵](./ai/reference/security-policy-matrix.md) | [前端规格](./ai/reference/frontend-spec.md) | [安全威胁模型](./security/threat-model.md) | 已落地 |
| 沙箱治理 | [05 Docker Sandbox 与 WarmPool](./human/features/05-sandbox-warmpool.md) | [OpenAPI](./api/openapi.yaml) | [运行时与部署规格](./ai/reference/runtime-deployment-spec.md)、[安全策略矩阵](./ai/reference/security-policy-matrix.md) | [前端规格](./ai/reference/frontend-spec.md) | [部署 Runbook](./runbooks/deployment.md)、[排障 Runbook](./runbooks/troubleshooting.md) | 已落地 |
| 模型设置 | [07 Settings 与 Observability](./human/features/07-settings-observability.md) | [OpenAPI](./api/openapi.yaml) | [安全策略矩阵](./ai/reference/security-policy-matrix.md) | [前端规格](./ai/reference/frontend-spec.md) | [QA 策略](./qa/test-strategy.md) | 已落地 |
| 策略设置 | [07 Settings 与 Observability](./human/features/07-settings-observability.md) | [OpenAPI](./api/openapi.yaml) | [Tool Registry](./ai/reference/tool-registry-spec.md)、[安全策略矩阵](./ai/reference/security-policy-matrix.md) | [前端规格](./ai/reference/frontend-spec.md) | [安全威胁模型](./security/threat-model.md) | 已落地 |
| 观测与运营 | [10 Observability 与本地化规格](./human/features/10-observability-localization-spec.md) | [OpenAPI](./api/openapi.yaml) | [运行时与部署规格](./ai/reference/runtime-deployment-spec.md) | [前端规格](./ai/reference/frontend-spec.md)、[Figma Brief](./design/figma-production-brief.md) | [部署 Runbook](./runbooks/deployment.md)、[排障 Runbook](./runbooks/troubleshooting.md) | 已落地 |
| 控制台本地化 | [10 Observability 与本地化规格](./human/features/10-observability-localization-spec.md) | 不涉及 | [前端规格](./ai/reference/frontend-spec.md) | [Figma Brief](./design/figma-production-brief.md)、[页面清单](./design/page-inventory.md) | [QA 策略](./qa/test-strategy.md) | 已落地 |
| 官网与 OpenAPI | [08 官网、控制台与 OpenAPI 入口](./human/features/08-website-console-openapi.md) | [OpenAPI 契约](./api/openapi-contract.md) | [架构与技术决策](./ai/reference/architecture-and-decisions.md) | [Figma Brief](./design/figma-production-brief.md) | [端到端 Demo 剧本](./demo/e2e-demo-script.md) | 已落地 |

## 变更检查

```text
1. 查本索引定位功能规格。
2. 按功能规格改 OpenAPI、后端、前端和测试。
3. 同步参考规格、运行手册和覆盖文档。
4. 执行 docs、backend、frontend 验证命令。
5. 更新进度文档和当前状态。
```
