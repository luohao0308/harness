<!-- AUTO-GENERATED from docs/architecture/module-map.json — do not hand-edit -->
<!-- Regenerate: python3 scripts/agent-context-brief.py --gen-module-index -->

# Module Index

Code module → owning docs. For feature→spec mapping see [SPEC-INDEX](../contracts/SPEC-INDEX.md).

| Module | Path | Summary | Docs |
| --- | --- | --- | --- |
| `agent-console` | `apps/agent-console` | React 18 + TypeScript operator UI: workspace, studio, tools, evals, observability. | [console-ui-spec.md](../design/console-ui-spec.md) |
| `agents` | `services/api-server/app/agents` | Agent lifecycle management: create, clone, configure, run workspace plans. | [agent-runtime-spec.md](agent-runtime-spec.md) |
| `api` | `services/api-server/app/api` | FastAPI route definitions, request/response models, OpenAPI spec. | [api-spec.md](../contracts/api/api-spec.md) |
| `core` | `services/api-server/app/core` | Shared utilities, base classes, cross-cutting concerns. | [system-architecture-spec.md](system-architecture-spec.md) |
| `db` | `services/api-server/app/db` | SQLAlchemy models, Alembic migrations, database session management. | [data-model-and-event-spec.md](../contracts/data-model-and-event-spec.md) |
| `events` | `services/api-server/app/events` | Event sourcing, append-only event log, replay infrastructure. | [data-model-and-event-spec.md](../contracts/data-model-and-event-spec.md) |
| `knowledge` | `services/api-server/app/knowledge` | RAG pipeline: local sources, connector sync, chunking, grounding citations. | [eval-harness-spec.md](../testing/eval-harness-spec.md) |
| `observability` | `services/api-server/app/observability` | OpenTelemetry traces, spans, model calls, tool calls, cost rollups, alerts. | [benchmark-spec.md](../testing/benchmark-spec.md) |
| `sandbox` | `services/api-server/app/sandbox` | Docker sandbox warmpool, sandboxed code execution, resource isolation. | [tool-mcp-runtime-spec.md](../contracts/tool-mcp-runtime-spec.md) |
| `security` | `services/api-server/app/security` | JWT/API-key auth, org RBAC, audit logs, encrypted secrets. | [system-architecture-spec.md](system-architecture-spec.md), [guardrail-policy-spec.md](../contracts/guardrail-policy-spec.md) |
| `teams` | `services/api-server/app/teams` | Multi-agent team coordination, specialist routing, dynamic fanout. | [agent-runtime-spec.md](agent-runtime-spec.md) |
| `tools` | `services/api-server/app/tools` | 27+ tool adapters (filesystem, shell, GitHub, Slack, MCP), registry, policy. | [tool-mcp-runtime-spec.md](../contracts/tool-mcp-runtime-spec.md) |
| `web-site` | `apps/web-site` | Public-facing website and portfolio demo flows. | [portfolio-demo-spec.md](../design/portfolio-demo-spec.md) |
| `workers` | `services/api-server/app/workers` | Dramatiq background job queue, async task execution, warmpool workers. | [agent-runtime-spec.md](agent-runtime-spec.md) |
