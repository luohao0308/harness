# AI 执行文档入口

本目录是 AI Agent 执行项目落地的唯一任务书。AI 必须按编号读取，按阶段执行，完成一个阶段后更新 [机器可读任务进度](./task-progress.yaml)，再读取下一阶段文档。

## 强制读取顺序

0. [Master Prompt](./00-master-prompt.md)
1. [执行协议](./00-execution-protocol.md)
2. [任务进度](./01-task-progress.md)
3. [机器可读任务进度](./task-progress.yaml)
4. [阶段 01：GitHub 与 Git 初始化](./02-stage-01-git-github.md)
5. [阶段 02：Figma 设计源](./03-stage-02-figma-design.md)
6. [阶段 03：仓库脚手架](./04-stage-03-repository-scaffold.md)
7. [阶段 04：FastAPI 后端基础](./05-stage-04-backend-foundation.md)
8. [阶段 05：Task 与 Event Store](./06-stage-05-task-event-store.md)
9. [阶段 06：Planner 与 Executor](./07-stage-06-planner-executor.md)
10. [阶段 07：React 控制台](./08-stage-07-react-console.md)
11. [阶段 08：Dramatiq Subagent](./09-stage-08-dramatiq-subagent.md)
12. [阶段 09：Docker Sandbox 与 WarmPool](./10-stage-09-sandbox-warmpool.md)
13. [阶段 10：监控、日志、部署](./11-stage-10-observability-deployment.md)

## 参考规格

- [架构与技术决策](./reference/architecture-and-decisions.md)
- [数据、事件与 API](./reference/data-events-api.md)
- [前端规格](./reference/frontend-spec.md)
- [运行时与部署规格](./reference/runtime-deployment-spec.md)
- [运行时 Agent Prompts](./reference/runtime-agent-prompts.md)
- [Tool Registry 契约](./reference/tool-registry-spec.md)
- [Tool Registry YAML](./reference/tool-registry.yaml)
- [Prompt 契约 YAML](./reference/prompt-contracts.yaml)
- [安全策略矩阵](./reference/security-policy-matrix.md)
- [数据库 ERD 与迁移规则](./reference/database-erd-migrations.md)
- [数据库 Schema YAML](./reference/database-schema.yaml)
- [OpenAPI 契约](../api/openapi-contract.md)
- [OpenAPI YAML](../api/openapi.yaml)
- [Prompt Eval Cases](../evals/prompt-eval-cases.yaml)
- [Prompt Eval Runbook](../evals/prompt-eval-runbook.md)
- [安全威胁模型](../security/threat-model.md)
- [QA 测试策略](../qa/test-strategy.md)
- [端到端 Demo 剧本](../demo/e2e-demo-script.md)
- [本地开发 Runbook](../runbooks/local-development.md)
- [部署 Runbook](../runbooks/deployment.md)
- [迁移 Runbook](../runbooks/migrations.md)
- [回滚 Runbook](../runbooks/rollback.md)
- [排障 Runbook](../runbooks/troubleshooting.md)

## 执行总规则

- 固定技术栈不可替换。
- 固定目录结构不可改名。
- GitHub 与 Figma 阶段必须先完成。
- 每个阶段必须使用对应文档中的“AI 执行提示词”作为任务输入。
- 每个阶段完成后必须更新 `docs/ai/task-progress.yaml`。
- 进度未更新时禁止进入下一阶段。
- API 路径、事件枚举、数据表、状态机不可随意变更。
- Event Store 是任务状态事实源。
- 高风险工具必须进入 Docker Sandbox。
- 异步任务必须使用 Dramatiq。
- 控制台必须使用 React + Vite。
- 官网必须使用 Next.js。
- 日志必须使用 Loki JSON 日志。
- 监控必须使用 Prometheus + Grafana。
