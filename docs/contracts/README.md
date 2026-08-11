# 契约治理入口

_状态：active | 权威范围：对外可观察的 API、事件、Schema、CLI 和文件格式 | 更新：2026-08-10_

## 权威顺序

1. 已验证的运行中行为和机器可解析契约；
2. 生成机器契约的源代码或 Schema；
3. 契约测试与消费者测试；
4. 人工使用指南和示例；
5. 历史快照与归档。

人工指南不能悄悄覆盖机器契约。出现冲突时先验证当前实现，再同步修正文档和生成物。

## 契约索引

| 契约 | 类型 | 生产者 | 消费者 | 权威源 | 生成/验证入口 | 兼容策略 |
|---|---|---|---|---|---|---|
| FastAPI/OpenAPI | HTTP | `services/api-server/app/api/` | Console、Desktop、Mobile、CI | 路由/Pydantic + `docs/contracts/api/openapi.yaml` | `python3 scripts/generate-api-docs.py`; API tests | 兼容优先，旧路由显式标 deprecated |
| Run/Event/Replay | event | `app/events/`、runtime services | Console Run Detail、Eval、Observability | Event Store models/spec | event/replay/observability tests | append-only；事件类型变更需消费者回归 |
| DB/Alembic | schema/migration | `services/api-server/alembic/versions/` | API、workers、部署 | SQLAlchemy models + Alembic | `alembic upgrade head`; migration checks | 单 head、可恢复、生产前备份 |
| Tool/MCP/Capability | HTTP/event/JSON | Tool Registry/ToolRunner | Agent runtime、Console、Eval | capability models、policy、ToolCall | tool registry/runner/approval tests | 附件/策略拒绝时 fail closed |
| Desktop sync/IPC | JSON/IPC | `apps/desktop-app/src/`、desktop sync API | Electron renderer、loopback runtime、Mobile | types + preload/native bridge | Desktop Vitest、main build、smoke | auth-bound、redacted、versioned |
| CLI/smoke | CLI/file | `scripts/`、`app/cli/` | CI、operators、release docs | argparse/CLI output contracts | `scripts/smoke-*`, `check-*.py` | 不输出凭据；退出码可判定 |

## 生成物规则

- 机器使用的固定文件名保持稳定，不复制出 `final`、`new`、`latest` 等并行版本。
- 生成物写明来源、生成时间和版本/提交身份；无法验证来源时不伪造更新日期。
- 自动生成文件不手工修补；修改源定义后重新生成并检查差异。
- 历史快照进入归档并标注日期，不继续作为当前导入源。
- 示例只使用占位符或环境变量，不包含真实凭据、Cookie、Token 或签名 URL。
- 功能到规格的映射见 [SPEC-INDEX.md](SPEC-INDEX.md)；本目录不复制设计或架构正文。

## 文件地图

| 路径 | 权威范围 |
|---|---|
| [api/openapi.yaml](api/openapi.yaml)、[api/openapi.json](api/openapi.json) | 当前 OpenAPI 机器契约 |
| [api/api-spec.md](api/api-spec.md)、[api/openapi-contract.md](api/openapi-contract.md) | API 行为说明与生成规则 |
| [api-reference/](api-reference/) | 由 FastAPI 元数据生成的参考快照 |
| [data-model-and-event-spec.md](data-model-and-event-spec.md) | 数据模型、事件和 Workspace 状态 |
| [tool-mcp-runtime-spec.md](tool-mcp-runtime-spec.md) | Tool/MCP/Approval 契约 |
| [guardrail-policy-spec.md](guardrail-policy-spec.md) | Policy、审批和 Guardrail 契约 |
| [SPEC-INDEX.md](SPEC-INDEX.md) | 功能到规格、设计和验证入口的总映射 |

## 变更流程

契约变更先使用 [CHANGE-CHECKLIST.md](CHANGE-CHECKLIST.md) 判断兼容性。新增契约从 [CONTRACT-TEMPLATE.md](CONTRACT-TEMPLATE.md) 建立；涉及数据 Schema 或回填时同时使用 [MIGRATION-TEMPLATE.md](MIGRATION-TEMPLATE.md)。
