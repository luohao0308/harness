# AI Harness Platform

AI Harness Platform turns a base model into an operational Agent system. The
product combines model routing, Agent Studio, Workspace execution, tools, MCP,
sandbox policy, knowledge grounding, Eval contracts, Specialists, observability,
RBAC, retention, and deployment hardening into one private control plane.

```text
Model + Harness = Agent
```

```text
Operator
  |
  v
Agent Console  ->  FastAPI Control Plane  ->  Postgres / Redis
  |                      |                         |
  |                      v                         v
  |                Planner / Executor       Events / Audit / Cache
  |                      |
  v                      v
Workspace Run  ->  Tools / MCP / Sandbox / Knowledge / Eval / Trace
```

## Product Demos

The repository includes durable capture targets for product media:

| Demo | Asset target | What it proves |
|---|---|---|
| 30 second private deploy | [docs/gifs/docker-compose-up.gif](docs/gifs/README.md) | Compose config, services, health checks |
| 30 second first Agent Run | [docs/gifs/first-agent-run.gif](docs/gifs/README.md) | Workspace Plan, events, tools, sandbox, Eval evidence |
| 30 second cost dashboard | [docs/gifs/cost-dashboard.gif](docs/gifs/README.md) | Model calls, token cost, cached rollups |

Screenshot capture targets live in [docs/screenshots/](docs/screenshots/README.md)
for Dashboard, onboarding, Agent Studio, Workspace, Run Detail, Eval,
Observability, Specialist Marketplace, and data management.

## For Users

Start the private stack:

```bash
eval "$(python3 scripts/generate-runtime-secrets.py)"
export AUTH_JWT_SECRET HARNESS_SECRET_ENCRYPTION_KEY HARNESS_SECRET_ENCRYPTION_KEY_ID
HARNESS_INITIAL_ADMIN_EMAIL=admin@example.com \
HARNESS_INITIAL_ADMIN_PASSWORD=change-me-strong-password \
POSTGRES_PASSWORD=change-me \
REDIS_PASSWORD=change-me \
HARNESS_DOMAIN=localhost \
docker compose -f compose.production.yml up -d --build
```

Open the Console and log in with the initial admin email/password. After the
first successful login, remove `HARNESS_INITIAL_ADMIN_EMAIL` and
`HARNESS_INITIAL_ADMIN_PASSWORD` from the runtime environment and restart the
API. Keep `AUTH_JWT_SECRET` stable. Then finish onboarding, configure the model
provider, load demo data, and run the first task from Agent Workspace. A
successful first pass creates a Run with a Plan, event stream, tool-call record,
sandbox boundary, grounding or context manifest, Eval evidence, and cost data.
Keep `HARNESS_SECRET_ENCRYPTION_KEY` stable as well; it decrypts stored
business integration secrets and is generated server-side, never in the
frontend.

See [First-Run Admin Runbook](docs/runbooks/first-run-admin.md) for JWT login,
smoke-test token exports, and the `scripts/create-admin.py` fallback.

Primary Console routes:

| Route | Purpose |
|---|---|
| `/` | Dashboard with active Agents, Runs, cost, alerts, quick actions |
| `/agents` | Agent Studio for model, prompt, tools, knowledge, and optimizer setup |
| `/agents/default/workspace` | Agent Workspace with the single Plan execution surface |
| `/runs` | Run History with virtualized rows and cursor-backed API data |
| `/runs/:runId` | Run Detail with replay, events, tools, model calls, Eval, trace |
| `/tools` | Tool Registry, adapters, MCP, capability packages, approvals |
| `/knowledge` | Knowledge sources, connectors, indexing state, grounding setup |
| `/evals` | Datasets, cases, Eval Runs, contracts, regression evidence |
| `/subagent-specialists` | Specialist templates, stats, calibration, fanout behavior |
| `/subagent-marketplace` | Signed Specialist sharing and installation |
| `/observability` | Health, trace, cost, alerts, notifications |
| `/settings/data-management` | Retention policy, exports, dry-run deletion, deletion audit |
| `/help` | In-app Help Center with search and feedback |
| `/help/troubleshooting` | 50+ searchable troubleshooting cases |

## Feature Matrix

| Area | Current surface |
|---|---|
| Agent lifecycle | Create, clone, configure, attach capabilities, run Workspace Plans |
| Model routing | Built-in provider defaults, DeepSeek-compatible gateway path, fallback metadata |
| Tool adapters | 27+ real adapter operations across filesystem, shell, tests, network, GitHub, Slack, Notion, Linear, Code Interpreter, sandbox file, and MCP |
| MCP | Protocol discovery, stdio/http/sse runtime config, sandboxed execution path |
| Knowledge/RAG | Local sources, connector sync, chunking, grounding citations, context manifest |
| Eval contracts | 9 contract categories across exact match, schema, grounding, safety, tool usage, Specialist output, regression, calibration, and trace evidence |
| Specialists | System and org Specialists, selector decisions, calibration, dynamic fanout |
| Marketplace | Signed listing validation, admin review, install, uninstall, archived history |
| Observability | Events, replay, traces, spans, model calls, tool calls, cost rollups, alerts |
| Security | JWT/API-key auth, organization RBAC, audit logs, verified notification URLs |
| Data lifecycle | Retention policies, archived records, export ZIP, dry-run counts, confirmed deletion |
| Performance | Redis-first query cache, cursor pagination, lazy routes, hashed assets, N+1 detector, k6 load scripts |
| Deployment | Production Compose, Caddy, Nginx assets, Helm scaffold, backup/restore, CI release gates |

## For Developers

Read [docs/CONTRIBUTING.md](docs/CONTRIBUTING.md) for contribution flow when
available, and use these stable entry points for local work:

```bash
cd services/api-server && .venv/bin/python -m pytest
cd services/api-server && .venv/bin/python -m ruff check app tests
cd apps/agent-console && npm test -- --run --pool forks --poolOptions.forks.singleFork
cd apps/agent-console && npm run build
python3 scripts/validate-docs.py
```

New AI agent sessions use the low-token startup contract:

```text
docs/ai/agent-startup-context.md
docs/ai/task-progress.yaml
python3 scripts/agent-context-brief.py --task "<user task>"
```

Completion write-back targets are `docs/ai/task-progress.yaml` and a relevant
`omx_wiki/` session or handoff page.

Core spec map:

| Area | Document |
|---|---|
| Product | [docs/00-product-spec.md](docs/00-product-spec.md) |
| Architecture | [docs/01-system-architecture.md](docs/01-system-architecture.md) |
| Data and events | [docs/02-data-model-and-event-spec.md](docs/02-data-model-and-event-spec.md) |
| API | [docs/03-api-spec.md](docs/03-api-spec.md) |
| Agent runtime | [docs/04-agent-runtime-spec.md](docs/04-agent-runtime-spec.md) |
| Tool and MCP runtime | [docs/05-tool-mcp-runtime-spec.md](docs/05-tool-mcp-runtime-spec.md) |
| Guardrail policy | [docs/06-guardrail-policy-spec.md](docs/06-guardrail-policy-spec.md) |
| Eval harness | [docs/07-eval-harness-spec.md](docs/07-eval-harness-spec.md) |
| Console UI | [docs/08-console-ui-spec.md](docs/08-console-ui-spec.md) |
| Benchmark | [docs/09-benchmark-spec.md](docs/09-benchmark-spec.md) |
| Portfolio demo | [docs/10-portfolio-demo-spec.md](docs/10-portfolio-demo-spec.md) |
| Progress | [docs/task-progress.md](docs/task-progress.md) |

Stage docs:

| Stage | Document |
|---|---|
| 01 | [docs/ai/stages/01-agent-workspace-console.md](docs/ai/stages/01-agent-workspace-console.md) |
| 02 | [docs/ai/stages/02-agent-studio-config.md](docs/ai/stages/02-agent-studio-config.md) |
| 03 | [docs/ai/stages/03-harness-tool-mcp.md](docs/ai/stages/03-harness-tool-mcp.md) |
| 04 | [docs/ai/stages/04-event-sourcing-replay-ui.md](docs/ai/stages/04-event-sourcing-replay-ui.md) |
| 05 | [docs/ai/stages/05-eval-regression.md](docs/ai/stages/05-eval-regression.md) |
| 06 | [docs/ai/stages/06-warmpool-infra.md](docs/ai/stages/06-warmpool-infra.md) |

## API Reference

FastAPI exposes OpenAPI at `/openapi.json` and interactive docs at `/docs`.
Generated API reference output lives in [docs/api-reference/](docs/api-reference/).

Regenerate it with:

```bash
python3 scripts/generate-api-docs.py
```

## Load And Scale

Performance guidance lives in [docs/runbooks/performance.md](docs/runbooks/performance.md).
The baseline scripts under [tests/load/](tests/load/) cover mixed user traffic,
spike traffic, and soak traffic through k6. The Console build emits hashed
`assets/` files with immutable cache headers through the production Nginx asset
service.

## Project Layout

```text
harness/
├─ apps/
│  ├─ agent-console/
│  └─ web-site/
├─ services/
│  └─ api-server/
├─ docs/
│  ├─ api-reference/
│  ├─ gifs/
│  ├─ runbooks/
│  └─ screenshots/
├─ deploy/
├─ scripts/
├─ tests/load/
└─ omx_wiki/
```

## Roadmap And Community

Current roadmap source: [.omx/plans/roadmap-production-readiness.md](.omx/plans/roadmap-production-readiness.md).

Community links are operator-owned placeholders for the private distribution:

- Slack: `https://example.invalid/harness-slack`
- Discord: `https://example.invalid/harness-discord`
