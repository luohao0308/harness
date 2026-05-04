# 09 技术落地流程

本文件是人读技术落地索引。具体执行步骤由 AI 阶段文档和 Runbook 承担，避免同一流程在多处重复维护。

## 技术栈事实源

```text
docs/ai/reference/architecture-and-decisions.md
```

## 代码阶段执行

| 技术 | 执行文档 |
|---|---|
| GitHub 与 Git | [02-stage-01-git-github.md](../ai/02-stage-01-git-github.md) |
| Figma | [03-stage-02-figma-design.md](../ai/03-stage-02-figma-design.md) |
| 仓库脚手架 | [04-stage-03-repository-scaffold.md](../ai/04-stage-03-repository-scaffold.md) |
| FastAPI | [05-stage-04-backend-foundation.md](../ai/05-stage-04-backend-foundation.md) |
| Task 与 Event Store | [06-stage-05-task-event-store.md](../ai/06-stage-05-task-event-store.md) |
| Planner 与 Executor | [07-stage-06-planner-executor.md](../ai/07-stage-06-planner-executor.md) |
| React 控制台 | [08-stage-07-react-console.md](../ai/08-stage-07-react-console.md) |
| Dramatiq Subagent | [09-stage-08-dramatiq-subagent.md](../ai/09-stage-08-dramatiq-subagent.md) |
| Docker Sandbox 与 WarmPool | [10-stage-09-sandbox-warmpool.md](../ai/10-stage-09-sandbox-warmpool.md) |
| 监控、日志、部署 | [11-stage-10-observability-deployment.md](../ai/11-stage-10-observability-deployment.md) |

## 机器契约

| 契约 | 文件 |
|---|---|
| API | [openapi.yaml](../api/openapi.yaml) |
| 数据库 | [database-schema.yaml](../ai/reference/database-schema.yaml) |
| 工具注册 | [tool-registry.yaml](../ai/reference/tool-registry.yaml) |
| Prompt | [prompt-contracts.yaml](../ai/reference/prompt-contracts.yaml) |
| 任务进度 | [task-progress.yaml](../ai/task-progress.yaml) |

## 运维 Runbook

| 场景 | 文件 |
|---|---|
| 本地开发 | [local-development.md](../runbooks/local-development.md) |
| 部署 | [deployment.md](../runbooks/deployment.md) |
| 数据库迁移 | [migrations.md](../runbooks/migrations.md) |
| 回滚 | [rollback.md](../runbooks/rollback.md) |
| 排障 | [troubleshooting.md](../runbooks/troubleshooting.md) |

## 质量与安全

| 主题 | 文件 |
|---|---|
| 安全威胁模型 | [threat-model.md](../security/threat-model.md) |
| 测试策略 | [test-strategy.md](../qa/test-strategy.md) |
| 端到端演示 | [e2e-demo-script.md](../demo/e2e-demo-script.md) |
| Prompt Eval | [prompt-eval-runbook.md](../evals/prompt-eval-runbook.md) |

