# 系统架构

_状态：active | 更新：2026-08-10 | 证据来源：README、Compose/CI、代码模块索引、阶段规格和已记录 smoke_

## 1. 系统定位与边界

- 解决的问题：把模型调用、计划执行、工具能力、知识 grounding、隔离、评估和审计组装成可操作的 Agent。
- 主要用户/调用方：企业内部操作员、Agent Console/Desktop、CI smoke、受控 API/Worker。
- 系统负责：身份/策略、Agent Run 生命周期、模型/工具/知识/事件/评估、部署健康与观测。
- 系统不负责：公开 SaaS 商业化、Kubernetes 拓扑、未经授权的生产操作和伪造外部证据。

## 2. 仓库与代码组织

| 仓库/路径 | 类型 | 主要职责 | 所有权 | 集成方式 |
|---|---|---|---|---|
| `apps/agent-console` | browser application | 完整控制台和 Workspace | Console | API/OpenAPI；独立 npm build |
| `apps/desktop-app` | Electron application | Codex-style task workspace、本地 sidecar、IPC | Desktop | console assets + local runtime；按平台打包 |
| `apps/mobile-app` | React Native/Expo | 离线任务、同步和设备能力 | Mobile | desktop sync contract；商店材料 |
| `services/api-server` | Python service/workers | Control plane、runtime、DB、events、workers | Backend | PostgreSQL/Redis/Docker；Alembic |
| `apps/web-site` | Next.js site | 公共信息与演示壳 | Website | 独立 build |
| `deploy/` + Compose | deployment | 代理、镜像、Helm、监控、systemd | Release | CI、健康端点、runbooks |

## 3. 系统上下文

<!-- 可使用 Mermaid C4 风格图；同时列出参与者、外部系统和信任边界。 -->

| 参与者/系统 | 与本系统关系 | 协议/入口 | 信任边界 |
|---|---|---|---|
| Operator | 发起 Agent 配置、任务和审批 | Browser/Electron UI → API/IPC | authenticated internal |
| Agent Console/Desktop | 展示 Run、事件、工具、Eval、观测 | HTTP, SSE/WebSocket, IPC | authenticated |
| API/Workers | 执行计划、工具、知识、任务和审计 | HTTP, DB, Redis, Event Store | privileged service |
| PostgreSQL/Redis | 持久化业务状态和队列/缓存 | SQL, Redis protocol | private network |
| Model/Connector providers | 受策略控制的外部能力 | OpenAI-compatible HTTP, provider APIs | outbound restricted |
| Docker sandbox/observability | 隔离执行与 telemetry | Docker API, OTLP, Prometheus/Loki/Tempo | host/service boundary |

## 4. 运行时拓扑

| 组件 | 进程/部署单元 | 依赖 | 健康信号 | 失败影响 |
|---|---|---|---|---|
| Caddy/Nginx/static assets | proxy/static services | console/site/API | HTTP proxy and asset checks | external entry |
| API server | FastAPI process | PostgreSQL, Redis, model gateway | `/api/health/readiness` | control plane |
| Workers | Dramatiq/runtime workers | API DB, Redis, Docker | queue/job state and logs | async execution |
| PostgreSQL | database service | persistent volume | `pg_isready`, migration head | all business state |
| Redis | queue/cache service | persistent/ephemeral volume | `redis-cli ping` | cache/worker paths |
| Desktop harnessd | profile-scoped loopback sidecar | SQLite, local IPC | native runtime tests/readiness | local profile |
| OTel/Prometheus/Loki/Tempo/Grafana | observability stack | app telemetry | scrape/readiness | diagnostics only |

## 5. 关键端到端流程

### 流程 A：一次 Agent Run

1. Operator 在 Workspace 提交目标；API 校验 Agent、权限和模型配置并创建 Run/Plan。
2. Planner/Executor 按 DAG 执行，ModelCall、ToolCall、Policy、Event 和 grounding/context manifest 持久化。
3. 工具、MCP、Knowledge、Connector、Sandbox、Subagent 和 workers 按各自策略/队列边界运行。
4. Console/Desktop 通过事件流投影状态；Run Detail 提供 replay、诊断、Eval Case 与 Observability 关联；失败按 pause/cancel/recovery 语义处理。

## 6. 数据与状态

| 数据/状态 | 权威来源 | 生命周期 | 一致性/迁移约束 |
|---|---|---|---|
| Agent/Run/Task/Team | PostgreSQL via API/services | API/service lifecycle | org/user scope、audit 和 retention |
| Event/ModelCall/ToolCall | Event Store + observability tables | append-only event/audit paths | replay、trace correlation、redaction |
| Knowledge/Memory/Context manifest | Knowledge/Context services | versioned ingestion/assembly | source/citation/policy binding、expiry |
| Queue/cache/session | Redis + runtime job tables | workers and lease state | bounded retries、fencing、recovery |
| Desktop profile/offline queue | profile SQLite | native sidecar/sync runtime | auth-bound sync、backup/candidate migration |

## 7. 安全与信任边界

- 身份认证与授权：JWT/API key、组织 RBAC、能力策略和审批；Desktop/Terminal 通过受控 IPC/token。
- 凭据和密钥存放边界：服务端环境或加密 secret store；renderer、URL、日志和文档不保存真实密钥。
- 网络与数据访问边界：私有 Compose 网络、策略控制的外连和 Docker sandbox；外部 URL 先做 provider/domain/IP policy。
- 审计、脱敏和数据保留：Event/ToolCall/ModelCall/Policy audit、OTel correlation、retention/export/delete；敏感值 redaction。

## 8. 可用性与故障模式

| 故障 | 检测方式 | 降级/重试 | 恢复入口 |
|---|---|---|---|
| API/DB/Redis 未就绪 | readiness、容器日志、CI health loop | 阻止流量或 worker 启动，按 Compose/迁移顺序恢复 | [deployment](../project-memory/runbooks/deployment.md)、[troubleshooting](../project-memory/runbooks/troubleshooting.md) |
| 模型/外部 provider 失败 | ModelCall 状态、错误分类、gateway logs | 保留失败证据；按允许策略重试/降级，不伪造 grounding | [web-research](../project-memory/runbooks/web-research.md) |
| 工具/沙箱/worker 失败 | ToolCall/Event/job lease | fail closed、重试或 recovery worker；保留审计 | [migrations](../project-memory/runbooks/migrations.md)、[troubleshooting](../project-memory/runbooks/troubleshooting.md) |
| Desktop sidecar/IPC 失败 | native tests、renderer error boundary、startup report | 停止本地执行，保留 profile 数据并提示恢复 | [desktop](../development/desktop/README.md) |

## 9. 证据与未知项

- 代码入口：`services/api-server/app/`、`apps/agent-console/src/`、`apps/desktop-app/src/`。
- 配置/测试/契约：`compose*.yml`、`.github/workflows/`、`services/api-server/tests/`、`docs/contracts/api/`、`docs/contracts/SPEC-INDEX.md`。
- 运行证据：`scripts/smoke-test-agent-run.py`、`scripts/smoke-test-docker.py`、`docs/development/ai/task-progress.yaml`、`omx_wiki/session-*.md`。
- Unknown：当前工作树未代表正式生产拓扑、实时第三方配额或签名凭据；发布前必须按 Runbook/CI 重新验证。
