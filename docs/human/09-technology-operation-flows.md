# 09 技术落地流程

本文件是人读技术落地索引。具体执行步骤由 AI 阶段文档和 Runbook 承担，避免同一流程在多处重复维护。

## 技术栈事实源

```text
docs/ai/reference/architecture-and-decisions.md
```

## 代码阶段执行

| 技术 | 执行文档 |
|---|---|
| Agent Workspace Console | [01-agent-workspace-console.md](../ai/stages/01-agent-workspace-console.md) |
| Agent Studio Config | [02-agent-studio-config.md](../ai/stages/02-agent-studio-config.md) |
| Harness Tool MCP | [03-harness-tool-mcp.md](../ai/stages/03-harness-tool-mcp.md) |
| Event Sourcing Replay UI | [04-event-sourcing-replay-ui.md](../ai/stages/04-event-sourcing-replay-ui.md) |
| Eval Regression | [05-eval-regression.md](../ai/stages/05-eval-regression.md) |
| WarmPool Infra | [06-warmpool-infra.md](../ai/stages/06-warmpool-infra.md) |

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
