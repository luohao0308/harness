# 项目摘要（AI 快速参考）

_来源：代码、配置、CI、产品规格和已记录验证证据 | 状态：ready | 更新：2026-08-10_

> 本文件只保存稳定的项目事实和路径速查，不记录实时任务、临时验证、交接过程或历史证据。当前任务状态以 `TASKS.md` 为准，短期上下文以 `WORKING-CONTEXT.md` 为准。

## 1. 项目概览

Forge Harness 是一个私有部署的企业 AI 控制面，把基础模型包装成可配置、可审计、可评估的 Agent 运行系统。Harness 是产品中的工程可靠性层；核心链路为 `Agent Studio → Agent Workspace → Planner/Executor → Tool/MCP/Knowledge/Sandbox → Events/Replay/Eval/Observability`。

公共网站只承担产品信息和演示；业务控制面是 `apps/agent-console` 与 `services/api-server`。当前 Desktop 还提供 Electron 本地工作区与本地运行时。Kubernetes、完整 SaaS 商业化和生产凭据不属于本地开发默认范围。

## 2. 仓库拓扑与所有权

| 路径 | 类型 | 责任/用途 | 独立 Git 仓库 | 变更边界 |
|---|---|---|---|---|
| `apps/agent-console` | React/TypeScript 控制台 | Agent Studio、Workspace、Runs、Tools、Knowledge、Eval、Observability | 否 | 前端变更需 lint、测试和 build |
| `apps/web-site` | Next.js 公共网站 | 产品信息和公开演示壳 | 否 | 保持网站与控制台边界 |
| `apps/desktop-app` | Electron 桌面端 | 本地工作区、终端、设置和打包运行时 | 否 | 需桌面测试、main build；签名由 CI 负责 |
| `apps/mobile-app` | React Native/Expo | 移动端离线任务与同步 | 否 | 以 `docs/operations/mobile/` 与移动测试为准 |
| `services/api-server` | FastAPI/Python 3.11 | API、Agent Runtime、数据、事件、Knowledge、Team、Worker | 否 | 后端变更需 pytest、Ruff；Schema 变更先迁移演练 |
| `services/agent-runtime` | 容器运行时 | Agent runtime 镜像/隔离执行支持 | 否 | 与 Compose/沙箱契约同步 |
| `deploy/`、`compose*.yml` | 部署与观测 | Compose、Caddy/Nginx、Helm、监控和 systemd | 否 | 配置校验、Preflight、健康与回滚 |
| `docs/`、`omx_wiki/` | 项目知识库 | 规格、Runbook、阶段证据与交接 | 否 | 按文档职责边界更新 |

## 3. 技术与运行时画像

| 层/能力 | 当前方案 | 稳定约束 |
|---|---|---|
| 语言/框架 | Python/FastAPI、React/TypeScript、Next.js、Electron | API 固定 Python 3.11；Node 工作区要求 Node 20+ |
| 数据/存储 | PostgreSQL、Redis、Alembic；Desktop 使用 profile-scoped SQLite | 迁移入口为 `services/api-server/alembic`；生产数据先备份再变更 |
| 外部依赖 | Docker、OpenAI-compatible model gateway、可选 Tavily/连接器、OTel/Prometheus/Loki/Tempo | 密钥只进服务端环境或安全存储；默认不读取真实凭据 |
| 本地运行 | `compose.production.yml` 私有栈，`deploy/docker-compose/docker-compose.yml` 完整开发栈，Electron 可运行本地 sidecar | 运行前使用 `scripts/generate-runtime-secrets.py` 或 `.env.example`，不提交生成值 |

## 4. 模块与领域

| 模块/领域 | 目录或入口 | 稳定用途 | 依赖/边界 | 备注 |
|---|---|---|---|---|
| Agent Runtime | `services/api-server/app/agents/`、`app/executor/` | 计划、执行、暂停/恢复、模型调用和子 Agent 编排 | 通过事件/审计连接工具、Run、Eval | Agent Run 是执行主入口 |
| Knowledge / Context | `services/api-server/app/knowledge/`、`app/context/` | 文档、检索、记忆、上下文 manifest 和 grounding | 证据必须带来源、策略和 Run 绑定 | 本地证据不足时不能伪造已验证结论 |
| Tools / MCP / Sandbox | `services/api-server/app/tools/`、`app/sandbox/` | Capability Registry、ToolRunner、策略、沙箱和 WarmPool | 工具执行经过 Policy、Audit、Event | 无 Agent capability attachment 时 fail closed |
| API / Data / Events | `services/api-server/app/api/`、`app/db/`、`app/events/`、`alembic/` | HTTP、SQLAlchemy、事件溯源、迁移和回放 | API/OpenAPI 与迁移必须同步验证 | PostgreSQL 是生产数据库路径 |
| Console / Desktop / Mobile | `apps/agent-console/`、`apps/desktop-app/`、`apps/mobile-app/` | 浏览器控制台、桌面工作区、移动同步 | 前端状态来自 API/本地运行时，不放静态业务数据 | 浏览器保留完整数据和观测控制台 |

## 5. 开发、验证与交付入口

| 目的 | 命令或入口 | 适用范围 | 证据/备注 |
|---|---|---|---|
| 本地启动 | `docker compose -f compose.production.yml up -d --build`；桌面 `cd apps/desktop-app && npm run start` | 私有栈/桌面 | 详见 [runbooks/local-development.md](project-memory/runbooks/local-development.md)；动态端口先查配置 |
| 定向测试 | `cd services/api-server && .venv/bin/python -m pytest tests/<target>.py`；`cd apps/agent-console && npm test -- <pattern>` | API/Console 局部变更 | 证据写入 `docs/工作日志/` 或当前会话 wiki |
| 全量验证 | `cd services/api-server && .venv/bin/python -m pytest tests`；Console `npm run lint && npm run build` | 发布、高风险或跨模块变更 | 需要 PostgreSQL/Redis 的测试按 CI 或本地容器执行 |
| 构建/打包 | `cd apps/agent-console && npm run build`；`cd apps/desktop-app && npm run build`；`python3 scripts/generate-api-docs.py` | 前端、桌面和 OpenAPI 产物 | 产物身份使用 commit/tag；签名/发布仅由受控 CI 执行 |
| 迁移/回滚 | `cd services/api-server && .venv/bin/alembic upgrade head`；[migrations](project-memory/runbooks/migrations.md)、[rollback](project-memory/runbooks/rollback.md) | 数据模型或部署变更 | 先备份，验证升级、恢复和兼容窗口 |

## 6. 契约、数据和运行边界

- 对外契约权威源：运行中的 FastAPI 路由与 Pydantic 模型、`docs/contracts/api/openapi.yaml`、事件/数据库规格；生成入口为 `scripts/generate-api-docs.py`。
- 生成物与人工指南：`docs/contracts/api-reference/` 是生成快照，`docs/project-memory/runbooks/` 是操作指南；生成文件不手工修补。
- Schema/数据变更门禁：Alembic 单头、迁移 ID 检查、PostgreSQL 升级、备份/恢复与 `scripts/validate-docs.py`。
- 发布与运行边界：Compose/Helm/CI 配置、`/api/health/readiness`、Agent Run smoke 和可观测栈；生产发布需授权。
- 敏感信息边界：不读取或提交 `.env`、API key、JWT、密码、Cookie、私钥和完整签名 URL；模型密钥只由服务端/安全存储持有。

## 7. 技术决策

| 决策 | 当前方案 | 原因/证据 | 影响范围 | 状态 |
|---|---|---|---|---|
| PostgreSQL 生产路径 | PostgreSQL + Alembic | [ADR-0002](architecture/adr/0002-use-python-fastapi.md)、迁移与 CI 配置 | API、Workers、Deploy | active |
| 事件溯源 | Run/Event Store + replay | [ADR-0003](architecture/adr/0003-use-event-sourcing.md)、Run Detail 证据 | Runtime、Console、Eval | active |
| Docker Sandbox/WarmPool | Policy-backed sandbox workers | [ADR-0004](architecture/adr/0004-use-docker-sandbox-warmpool.md) | Tools、Sandbox、Deploy | active |
| AI 任务启动路由 | `AGENTS.md` → `docs/development/ai/` → task brief | [ADR-0006](architecture/adr/0006-ai-native-docs-architecture.md) | 全仓库文档 | active |

## 8. 已知风险与技术债

| 项目 | 风险等级 | 当前影响 | 触发条件 | 后续方向 |
|---|---|---|---|---|
| 本工作树已有大量用户改动 | 高 | 当前文件可能混合历史/进行中变更 | 每次任务开始和交付前 | 只修改任务拥有的文件，禁止 reset/checkout 覆盖 |
| 外部生产凭据与签名材料 | 高 | 本地无法代表 CI 签名、真实发布或第三方授权 | 发布/联调前 | 使用 `.env.example`、CI secrets 和 runbook 边界 |
| 动态部署拓扑 | 中 | 历史端口、镜像和健康状态可能过期 | 每次部署前 | 重新运行 Compose/Helm/健康 Preflight |

## 9. 路径速查

| 需要查找的内容 | 路径 |
|---|---|
| 项目规则 | `AGENTS.md` |
| 项目入口 | `README.md`、`docs/development/ai/agent-startup-context.md` |
| 测试入口 | `services/api-server/tests/`、`apps/agent-console/src/**/__tests__/`、`apps/desktop-app/src/**/__tests__/` |
| 配置说明 | `.env.example`、`services/api-server/.env.example`、`deploy/docker-compose/.env.example`、`docs/project-memory/runbooks/local-development.md` |
| 架构文档 | `docs/architecture/`（如启用） |
| 设计文档 | `docs/design/` 或 `DESIGN.md`（如启用） |
| 长期操作记忆 | `docs/project-memory/` |
| 任务状态 | `docs/TASKS.md` |
| 当前任务上下文 | `docs/WORKING-CONTEXT.md` |

---

_更新方式：只在稳定事实、仓库拓扑、模块边界、技术决策、命令或路径发生变化并完成验证后更新。_
