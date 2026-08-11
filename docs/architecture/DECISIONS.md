# 架构决策记录（ADR 索引）

_状态：active | 更新：2026-08-10_

## 决策索引

| ID | 决策 | 状态 | 日期 | 影响范围 | 替代/关联 |
|---|---|---|---|---|---|
| ADR-0001 | 记录架构决策 | accepted | 2026-05-01 | 全仓库 | [原始 ADR 索引](adr/ADR-INDEX.md) |
| ADR-0002 | Python/FastAPI 后端 | accepted | 2026-05-01 | API、Runtime | [原始 ADR](adr/0002-use-python-fastapi.md) |
| ADR-0003 | Event Sourcing 与 Replay | accepted | 2026-05-01 | Events、Run、Observability | [原始 ADR](adr/0003-use-event-sourcing.md) |
| ADR-0004 | Docker Sandbox 与 WarmPool | accepted | 2026-05-01 | Tools、Sandbox、Deploy | [原始 ADR](adr/0004-use-docker-sandbox-warmpool.md) |
| ADR-0005 | React/Next.js 客户端 | accepted | 2026-05-01 | Console、Website | [原始 ADR](adr/0005-use-react-nextjs.md) |
| ADR-0006 | AI-native 文档架构 | accepted | 2026-05-01 | AGENTS、docs/development/ai、workflow docs | [原始 ADR](adr/0006-ai-native-docs-architecture.md) |

## ADR 模板

### ADR-XXXX：<!-- 标题 -->

- 状态：proposed / accepted / superseded
- 日期：YYYY-MM-DD
- 背景与证据：
- 决策驱动因素：
- 采用方案：
- 考虑过的替代方案：
- 结果与代价：
- 兼容、迁移和回滚影响：
- 验证方式：
- 后续复审触发条件：

> 不删除已经生效的历史决策。方案被替代时，把状态改为 `superseded` 并链接新 ADR。详细背景以 `docs/architecture/adr/` 为准，本索引不复制全文。
