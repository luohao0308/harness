# 09 技术落地流程

本文件是人读技术落地索引。具体执行步骤由 AI 阶段文档和 Runbook 承担，避免同一流程在多处重复维护。

## 技术栈事实源

```text
docs/development/ai/reference/architecture-and-decisions.md
```

## 代码阶段执行

| 技术 | 执行文档 |
|---|---|
| Agent Workspace Console | [01-agent-workspace-console.md](../development/ai/stages/01-agent-workspace-console.md) |
| Agent Studio Config | [02-agent-studio-config.md](../development/ai/stages/02-agent-studio-config.md) |
| Harness Tool MCP | [03-harness-tool-mcp.md](../development/ai/stages/03-harness-tool-mcp.md) |
| Event Sourcing Replay UI | [04-event-sourcing-replay-ui.md](../development/ai/stages/04-event-sourcing-replay-ui.md) |
| Eval Regression | [05-eval-regression.md](../development/ai/stages/05-eval-regression.md) |
| WarmPool Infra | [06-warmpool-infra.md](../development/ai/stages/06-warmpool-infra.md) |

## 机器契约

| 契约 | 文件 |
|---|---|
| API | [openapi.yaml](../contracts/api/openapi.yaml) |
| 数据库 | [database-schema.yaml](../development/ai/reference/database-schema.yaml) |
| 工具注册 | [tool-registry.yaml](../development/ai/reference/tool-registry.yaml) |
| Prompt | [prompt-contracts.yaml](../development/ai/reference/prompt-contracts.yaml) |
| 任务进度 | [task-progress.yaml](../development/ai/task-progress.yaml) |

## 运维 Runbook

| 场景 | 文件 |
|---|---|
| 本地开发 | [local-development.md](../project-memory/runbooks/local-development.md) |
| 部署 | [deployment.md](../project-memory/runbooks/deployment.md) |
| 数据库迁移 | [migrations.md](../project-memory/runbooks/migrations.md) |
| 回滚 | [rollback.md](../project-memory/runbooks/rollback.md) |
| 排障 | [troubleshooting.md](../project-memory/runbooks/troubleshooting.md) |

## 质量与安全

| 主题 | 文件 |
|---|---|
| 安全威胁模型 | [threat-model.md](../architecture/security/threat-model.md) |
| 测试策略 | [test-strategy.md](../testing/qa/test-strategy.md) |
| 端到端演示 | [e2e-demo-script.md](../design/media/demo/e2e-demo-script.md) |
| Prompt Eval | [prompt-eval-runbook.md](../testing/evals/prompt-eval-runbook.md) |
