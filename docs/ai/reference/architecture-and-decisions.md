# 架构与技术决策参考

本文件是阶段执行文档的参考规格。AI 执行阶段任务时，不得修改本文件中的固定决策。

## 固定技术栈

```yaml
backend_language: Python 3.11
api_framework: FastAPI
validation: Pydantic v2
orm: SQLAlchemy 2.0
migrations: Alembic
database: PostgreSQL 16
cache: Redis 7
queue: Dramatiq with Redis Broker
sandbox: Docker SDK for Python
event_store: PostgreSQL append-only table
logs: Loki
metrics: Prometheus
dashboards: Grafana
tracing: OpenTelemetry
website: Next.js + TypeScript + Tailwind CSS
console: React + Vite + TypeScript + Tailwind CSS + local UI primitives + lucide-react + ECharts
client_state: Zustand
server_state: TanStack Query
charts: ECharts
deployment: Docker Compose + systemd + Nginx
design_source: Figma
model_access: OpenAI-compatible Model Gateway
```

## 固定架构

```text
Model + Harness = Agent
```

Harness 层固定包含：

```text
Planner
Executor
ReAct Engine
Subagent Manager
Tool Registry
Policy Engine
Event Store
Sandbox Manager
WarmPool Manager
Model Gateway
Observability
Deployment
```

## 固定仓库结构

```text
harness/
├─ README.md
├─ docs/
│  ├─ ai/
│  ├─ human/
│  └─ design/
├─ apps/
│  ├─ web-site/
│  └─ agent-console/
├─ services/
│  ├─ api-server/
│  └─ sandbox-worker/
├─ deploy/
│  ├─ docker-compose/
│  ├─ systemd/
│  ├─ nginx/
│  └─ monitoring/
└─ scripts/
```

## 固定状态机

Task：

```text
CREATED
PLANNING
RUNNING
WAITING_SUBAGENTS
FAILED
COMPLETED
CANCELLED
```

Subagent：

```text
PENDING
RUNNING
SUCCESS
FAILED
TIMEOUT
CANCELLED
```

Sandbox：

```text
IDLE
BUSY
DESTROYED
FAILED
```

## 固定约束

```yaml
subagent_concurrency_limit: 5
default_subagent_timeout_seconds: 900
warm_pool_target_acquire_ms: 50
sandbox_default_network: none
sandbox_default_memory: 1024m
sandbox_default_cpus: 1.0
sandbox_default_workspace_quota_mb: 1024
sandbox_network_allowlist_default: []
kubernetes_in_initial_delivery: false
direct_host_command_execution: forbidden
direct_model_sdk_usage_in_business_code: forbidden
ai_generated_h5_as_production_code: forbidden
delivery_stage_terms_required: true
```
