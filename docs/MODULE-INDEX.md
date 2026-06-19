<!-- AUTO-GENERATED from docs/module-map.json — do not hand-edit -->
<!-- Regenerate: python3 scripts/agent-context-brief.py --gen-module-index -->

# Module Index

Code module → owning docs. For feature→spec mapping see [SPEC-INDEX](./SPEC-INDEX.md).

| Module | Path | Summary | Docs |
| --- | --- | --- | --- |
| `agent-console` | `apps/agent-console` | React 18 + TypeScript operator UI: workspace, studio, tools, evals, observability. | [08-console-ui-spec.md](./08-console-ui-spec.md) |
| `agents` | `services/api-server/app/agents` | Agent lifecycle management: create, clone, configure, run workspace plans. | [04-agent-runtime-spec.md](./04-agent-runtime-spec.md) |
| `api` | `services/api-server/app/api` | FastAPI route definitions, request/response models, OpenAPI spec. | [03-api-spec.md](./03-api-spec.md) |
| `core` | `services/api-server/app/core` | Shared utilities, base classes, cross-cutting concerns. | [01-system-architecture.md](./01-system-architecture.md) |
| `db` | `services/api-server/app/db` | SQLAlchemy models, Alembic migrations, database session management. | [02-data-model-and-event-spec.md](./02-data-model-and-event-spec.md) |
| `events` | `services/api-server/app/events` | Event sourcing, append-only event log, replay infrastructure. | [02-data-model-and-event-spec.md](./02-data-model-and-event-spec.md) |
| `knowledge` | `services/api-server/app/knowledge` | RAG pipeline: local sources, connector sync, chunking, grounding citations. | [07-eval-harness-spec.md](./07-eval-harness-spec.md) |
| `observability` | `services/api-server/app/observability` | OpenTelemetry traces, spans, model calls, tool calls, cost rollups, alerts. | [09-benchmark-spec.md](./09-benchmark-spec.md) |
| `sandbox` | `services/api-server/app/sandbox` | Docker sandbox warmpool, sandboxed code execution, resource isolation. | [05-tool-mcp-runtime-spec.md](./05-tool-mcp-runtime-spec.md) |
| `security` | `services/api-server/app/security` | JWT/API-key auth, org RBAC, audit logs, encrypted secrets. | [01-system-architecture.md](./01-system-architecture.md), [06-guardrail-policy-spec.md](./06-guardrail-policy-spec.md) |
| `teams` | `services/api-server/app/teams` | Multi-agent team coordination, specialist routing, dynamic fanout. | [04-agent-runtime-spec.md](./04-agent-runtime-spec.md) |
| `tools` | `services/api-server/app/tools` | 27+ tool adapters (filesystem, shell, GitHub, Slack, MCP), registry, policy. | [05-tool-mcp-runtime-spec.md](./05-tool-mcp-runtime-spec.md) |
| `web-site` | `apps/web-site` | Public-facing website and portfolio demo flows. | [10-portfolio-demo-spec.md](./10-portfolio-demo-spec.md) |
| `workers` | `services/api-server/app/workers` | Dramatiq background job queue, async task execution, warmpool workers. | [04-agent-runtime-spec.md](./04-agent-runtime-spec.md) |
