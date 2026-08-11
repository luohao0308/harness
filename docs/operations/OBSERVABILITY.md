# 可观测性与健康信号

_状态：active | 更新：2026-08-10_

## 信号地图

| 能力/服务 | 健康检查 | 关键日志 | 指标/SLO | 追踪 | 告警 |
|---|---|---|---|---|---|
| API/Workers | `/api/health/live`、`/api/health/readiness`、Agent Run smoke | structured app logs + run/task/trace IDs | Prometheus app/runtime metrics | OpenTelemetry spans/model/tool calls | service health/worker alerts |
| PostgreSQL/Redis | `pg_isready`、`redis-cli ping` | container logs and migration output | exporter/queue/cache metrics | DB/queue spans where enabled | dependency readiness |
| Console/Desktop | browser/native smoke、startup budget | renderer/main logs with redaction | desktop telemetry/startup report | IPC/request correlation | renderer/native error boundaries |
| Sandbox/WarmPool | sandbox lifecycle tests and worker health | ToolCall/Event/job logs | warm pool/quota/sandbox metrics | tool/model/run spans | policy/worker alerts |
| OTel/Prometheus/Loki/Tempo/Grafana | component readiness | collector/agent logs | scrape/retention dashboards | trace search | observability pipeline alerts |

## 语义约定

- Liveness 只证明进程是否需要重启；Readiness 证明是否可接收流量；业务冒烟证明关键用户路径。
- 健康端点不返回凭据、连接串、内部主机或原始异常。
- 日志必须具备请求/任务关联、结构化字段、敏感信息脱敏和明确错误码。
- 指标和告警应对应可执行的 Runbook，避免只有阈值没有处理入口。

## 发布观测窗口

- 发布前基线：CI tests/build、Compose/Helm config、migration preflight、健康端点和 smoke。
- 发布后重点指标：readiness、5xx、Run success/failure、ModelCall latency/cost、ToolCall denial、queue lag、DB/Redis health、desktop startup budget。
- 观察时长：按发布 Runbook 和当前环境风险设定；动态值操作前重新确认。
- 回滚触发条件：健康不达标、核心 Agent Run 失败、迁移/队列不可恢复、错误率或延迟超过已批准门槛。

## 常用排障入口

| 问题 | 第一证据 | 下一步 | Runbook |
|---|---|---|---|
| API 不可用 | readiness + container logs | `docker compose ps`、依赖健康、migration head | [troubleshooting](../project-memory/runbooks/troubleshooting.md) |
| Agent Run 失败 | Run/Event/ModelCall/ToolCall trace | 按 run_id 查 replay、policy、provider 错误 | [sse-streaming](../project-memory/runbooks/sse-streaming.md) |
| 迁移失败 | Alembic output + DB health | 记录 revision、备份和当前 schema | [migrations](../project-memory/runbooks/migrations.md)、[rollback](../project-memory/runbooks/rollback.md) |
| Desktop 启动慢/空白 | startup report + native/renderer logs | 运行 focused startup tests 和 isolated package smoke | [desktop](../development/desktop/README.md) |
