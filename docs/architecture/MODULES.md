# 模块与依赖边界

_状态：active | 更新：2026-08-10_

## 模块清单

| 模块 | 路径/入口 | 职责 | 允许依赖 | 禁止依赖 | 所有权 |
|---|---|---|---|---|---|
| API/control plane | `services/api-server/app/api/` | FastAPI 路由、输入校验和响应投影 | 依赖 services/domain/db；被 Console、Desktop、CI 消费 | 不直接读取前端状态或绕过 service/policy | API team |
| Agent runtime | `services/api-server/app/agents/`、`app/executor/`、`app/teams/` | Plan、Run、模型调用、任务、Team 和 Subagent | 依赖 model gateway、events、tools、knowledge | 不绕过事件/审计执行副作用 | Runtime team |
| Data and events | `services/api-server/app/db/`、`app/events/`、`alembic/` | SQLAlchemy 模型、事件溯源、迁移和 replay | 被 API、workers、observability 使用 | 迁移不得绕过备份/兼容门禁 | Data team |
| Capability execution | `services/api-server/app/tools/`、`app/sandbox/` | Capability Registry、ToolRunner、MCP、Policy、Sandbox/WarmPool | 由 Agent runtime 调用，写 ToolCall/Event | 无 attachment 或策略拒绝时必须 fail closed | Platform team |
| Knowledge and Eval | `services/api-server/app/knowledge/`、`app/evals/` | Memory/RAG/context grounding、Eval contract 和 regression | 依赖 run/model/event 数据；投影到 Run Detail | 不把 fixture/未验证 web 结果标成 verified | Knowledge team |
| Background workers | `services/api-server/app/workers/`、`app/runtime_jobs/` | 异步 assignment、recovery、Team、WarmPool 和 runtime jobs | 依赖 DB/Redis/Event；通过队列与 API 解耦 | 不在 worker 内复制 API 权威规则 | Runtime team |
| Browser console | `apps/agent-console/` | React operator UI 和用户工作流 | 通过 API/client/store 获取状态 | 不内置静态生产数据或服务端密钥 | Console team |
| Desktop/mobile | `apps/desktop-app/`、`apps/mobile-app/` | 本地运行时、同步、终端和设备体验 | Desktop 通过受控 IPC/loopback；Mobile 复用同步协议 | 不暴露 renderer secrets 或绕过 auth | Client team |
| Public website | `apps/web-site/` | 对外信息壳与演示 | 独立 Next.js 构建 | 不承担控制台数据面 | Website team |
| Deployment/observability | `deploy/`、`compose*.yml`、`.github/workflows/` | Compose、Helm、代理、监控和发布 CI | 依赖应用镜像和运行契约 | 不把生产秘密写入仓库或镜像 | Release team |

## 依赖原则

- 依赖方向：`Console/Desktop/Mobile → API/IPC → services → DB/Redis/Events/Workers`；Website 是独立公共壳。
- 跨模块通信：HTTP/OpenAPI、内部 service 调用、append-only Event Store、WebSocket/SSE、Desktop IPC 和离线同步协议。
- 公共基础设施：`core/`、auth、policy、audit、observability、DB session；业务模块不得反向依赖 UI 或部署实现。
- 数据所有权：API/services 是业务数据唯一写入入口；Alembic 是 Schema 变更入口；Console/客户端只保存受控本地状态。

## 新增或拆分模块检查

- [ ] 职责可用一句话说明，且没有与现有模块重复。
- [ ] 入口、依赖方向和数据所有权已明确。
- [ ] 对外契约、权限和错误语义已确定。
- [ ] 测试、迁移、观测和回滚入口已确定。
- [ ] `PROJECT-SUMMARY.md` 与本模块表已同步。

## 受保护区域

| 路径/能力 | 风险 | 修改条件 | 验证要求 |
|---|---|---|---|
| `services/api-server/alembic/versions/` | 破坏性或不可逆数据变更 | 迁移 owner；生产发布需授权 | migration ID、upgrade/restore、数据断言 |
| `services/api-server/app/security/`、`.env*`、CI secrets | 身份、密钥和租户数据风险 | Security/release owner | 定向安全测试、Ruff、无密钥 diff |
| `compose*.yml`、`deploy/`、`.github/workflows/` | 发布拓扑、健康和产物风险 | Release owner | config/lint、smoke、rollback/runbook |
| `apps/desktop-app/src/main.ts`、native/runtime | 本地权限、IPC、数据和打包风险 | Desktop owner | focused Vitest、main build、package smoke |
