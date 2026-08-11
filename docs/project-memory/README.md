# 项目操作记忆

_状态：长期 Runbook 导航 | 权威范围：可重复操作与排障 | 更新：2026-08-10 | 读取方式：按问题打开相关章节_

本目录是项目的长期记忆库，保存高频、可重复、已经验证的操作知识和排障经验。

> 当前任务状态以 [`docs/TASKS.md`](../TASKS.md) 为准，短期上下文以 [`docs/WORKING-CONTEXT.md`](../WORKING-CONTEXT.md) 为准；一次性验证过程和历史证据写入工作日志（如项目启用）。

## 维护规则

- 只记录能够迁移到后续任务的流程、排障路径和本地约定。
- 只写已经验证的经验；未复现的推断、临时决策和当前任务进度不写入这里。
- 不保存密钥、原始访问令牌、刷新令牌、密码、Cookie、私钥或完整签名 URL。
- 优先按问题组织内容，不重复编写宽泛的架构摘要。
- 优先链接源文件或现有文档，避免复制大段内容。
- 长文只检索与当前任务相关的章节；任何线上动态值都必须重新执行对应的 Preflight。

## Runbook 索引

| 编号 | 文档 | 内容 | 最近验证 |
|---|---|---|---|
| 01 | [local-development.md](runbooks/local-development.md) | 本地 API/Console/Compose 启动与依赖准备 | 2026-08-10 |
| 02 | [deployment.md](runbooks/deployment.md) | 私有栈部署、健康和服务拓扑 | 2026-08-10 |
| 03 | [migrations.md](runbooks/migrations.md)、[migration-conventions.md](runbooks/migration-conventions.md) | Alembic 迁移、命名、备份和恢复入口 | 2026-08-10 |
| 04 | [rollback.md](runbooks/rollback.md) | 受控回滚与数据恢复 | 2026-08-10 |
| 05 | [troubleshooting-overview.md](runbooks/troubleshooting-overview.md)、[troubleshooting.md](runbooks/troubleshooting.md) | 快速分流与完整排障目录 | 2026-08-10 |
| 06 | [release.md](runbooks/release.md)、[cicd.md](runbooks/cicd.md) | Tag、产物、CI、发布和回滚门禁 | 2026-08-10 |
| 07 | [first-run-admin.md](runbooks/first-run-admin.md)、[performance.md](runbooks/performance.md) | 首次管理员与性能验证 | 2026-08-10 |
| 08 | [sse-streaming.md](runbooks/sse-streaming.md)、[web-research.md](runbooks/web-research.md) | 实时流和外部研究排障 | 2026-08-10 |

## 新增 Runbook 规范

每份 Runbook 至少包含：适用范围、前置条件、操作步骤、Preflight、验证方式、失败处理、回滚或恢复方式、证据记录和敏感信息边界。动态值必须标注采集时间，并在再次操作前重新核验。
