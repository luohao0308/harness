# Forge Harness

Forge Harness is a private-deployable enterprise AI control plane. It turns a
model into an operational Agent system with explicit context, tools, policy,
execution, evaluation, and audit boundaries.

```text
Model + Harness = Agent
```

The product is built for teams that need AI work to be runnable, observable,
recoverable, and reviewable. It is not a generic chatbot or a static demo UI.

## What It Provides

| Capability | What Forge Harness does |
|---|---|
| Agent Studio | Configure models, prompts, capabilities, knowledge, and orchestration |
| Agent Workspace | Turn a user goal into a visible, resumable Run |
| Runtime | Plan, execute, pause, resume, cancel, replay, and delegate work |
| Tools and MCP | Register capabilities and run them through policy, approval, audit, and sandbox boundaries |
| Knowledge and context | Ingest sources, retrieve evidence, manage memory, assemble bounded context, and preserve citations |
| Eval | Save Runs as cases and measure grounding, safety, tool use, regression, and trace contracts |
| Observability | Connect model calls, tool calls, events, costs, policy decisions, and replay evidence |
| Private deployment | Run the control plane with Docker Compose, systemd, Nginx/Caddy, and the documented recovery path |

## The Runtime Loop

```text
Operator
  |
  v
Agent Studio -> Agent Workspace -> Agent Run
                                    |
                                    v
                    Planner -> Executor -> Tools / MCP / Sandbox
                                    |
                                    v
                   Events -> Replay -> Eval -> Observability
```

Every meaningful step has a server-side record. A successful Run exposes the
plan, event stream, tool calls, sandbox boundary, context or grounding
evidence, evaluation result, and cost data in one traceable surface.

## Run The Private Stack

Requirements: Docker with Compose, Python 3.11 for helper scripts, and a
server-side model provider configuration.

```bash
git clone https://github.com/luohao0308/forge-harness.git
cd forge-harness

eval "$(python3 scripts/generate-runtime-secrets.py)"
export AUTH_JWT_SECRET HARNESS_SECRET_ENCRYPTION_KEY HARNESS_SECRET_ENCRYPTION_KEY_ID
HARNESS_INITIAL_ADMIN_EMAIL=admin@example.com \
HARNESS_INITIAL_ADMIN_PASSWORD=change-me-strong-password \
POSTGRES_PASSWORD=change-me \
REDIS_PASSWORD=change-me \
HARNESS_DOMAIN=localhost \
docker compose -f compose.production.yml up -d --build
```

Open the Console, sign in with the initial admin account, configure the model
provider, and run the first task from Agent Workspace. Remove the initial
admin variables after the first successful login. Keep `AUTH_JWT_SECRET` and
`HARNESS_SECRET_ENCRYPTION_KEY` stable; they protect sessions and stored
integration secrets.

The [first-run admin runbook](docs/project-memory/runbooks/first-run-admin.md)
covers login, smoke-test tokens, and the local admin fallback.

## Console Surfaces

| Route | Purpose |
|---|---|
| `/` | Dashboard with active Agents, Runs, cost, and alerts |
| `/agents` | Agent Studio for model, prompt, capabilities, knowledge, and optimizer setup |
| `/agents/default/workspace` | Chat-first Workspace and Plan execution surface |
| `/runs` | Cursor-backed Run history |
| `/runs/:runId` | Run detail, replay, events, tools, model calls, Eval, and trace evidence |
| `/tools` | Tool Registry, adapters, MCP, capability packages, and approvals |
| `/knowledge` | Knowledge sources, connectors, indexing, and grounding setup |
| `/evals` | Datasets, cases, Eval Runs, contracts, and regression evidence |
| `/observability` | Health, traces, costs, alerts, and notifications |
| `/settings/data-management` | Retention, exports, dry-run deletion, and deletion audit |

## Develop And Verify

Use the repository's scoped entry points for local work:

```bash
cd services/api-server && .venv/bin/python -m pytest tests
cd services/api-server && .venv/bin/python -m ruff check app tests
cd apps/agent-console && npm test -- --run --pool forks --poolOptions.forks.singleFork
cd apps/agent-console && npm run lint && npm run build
python3 scripts/validate-docs.py
git diff --check
```

AI-assisted development starts from [the startup context](docs/development/ai/agent-startup-context.md),
then runs:

```bash
python3 scripts/agent-context-brief.py --task "<task>"
```

The execution contract is [docs/development/ai/00-execution-protocol.md](docs/development/ai/00-execution-protocol.md),
the machine progress source is [docs/development/ai/task-progress.yaml](docs/development/ai/task-progress.yaml),
and the current handoff is [omx_wiki/project-handoff-current-state.md](omx_wiki/project-handoff-current-state.md).

The Electron desktop surface has its own [development and release guide](docs/development/desktop/README.md).
The API reference is generated from FastAPI:

```bash
python3 scripts/generate-api-docs.py
```

## Repository Layout

```text
forge-harness/
├─ apps/
│  ├─ agent-console/     # Browser control plane UI
│  ├─ desktop-app/       # Native local workspace and runtime
│  └─ web-site/          # Public product and documentation shell
├─ services/
│  └─ api-server/        # FastAPI API, runtime, workers, data, and events
├─ deploy/               # Compose, Helm scaffold, proxies, systemd, monitoring
├─ docs/                 # Product, architecture, contracts, runbooks, and plans
├─ scripts/              # Smoke, docs, API, and release checks
└─ omx_wiki/             # Handoffs and validated project memory
```

## Read Next

- [Product positioning](docs/design/product-positioning.md)
- [Product specification](docs/design/product-spec.md)
- [System architecture](docs/architecture/system-architecture-spec.md)
- [Agent runtime](docs/architecture/agent-runtime-spec.md)
- [Data and events](docs/contracts/data-model-and-event-spec.md)
- [API contract](docs/contracts/api/api-spec.md)
- [Tool and MCP runtime](docs/contracts/tool-mcp-runtime-spec.md)
- [Guardrail policy](docs/contracts/guardrail-policy-spec.md)
- [Eval harness](docs/testing/eval-harness-spec.md)
- [Console UI](docs/design/console-ui-spec.md)
- [Benchmark](docs/testing/benchmark-spec.md)
- [Portfolio demo](docs/design/portfolio-demo-spec.md)
- [API reference](docs/contracts/api-reference/README.md)
- [Deployment runbook](docs/project-memory/runbooks/deployment.md)
- [Current tasks](docs/TASKS.md)
- [AI startup context](docs/development/ai/agent-startup-context.md)

Stage references:

- [01 Agent Workspace](docs/development/ai/stages/01-agent-workspace-console.md)
- [02 Agent Studio](docs/development/ai/stages/02-agent-studio-config.md)
- [03 Tools and MCP](docs/development/ai/stages/03-harness-tool-mcp.md)
- [04 Event sourcing and replay](docs/development/ai/stages/04-event-sourcing-replay-ui.md)
- [05 Eval regression](docs/development/ai/stages/05-eval-regression.md)
- [06 WarmPool infrastructure](docs/development/ai/stages/06-warmpool-infra.md)

## Product Boundary

Forge Harness targets private enterprise deployment and internal validation.
Kubernetes topology, full SaaS commercialization, and production credentials
are outside the default local-development scope. Secrets stay server-side and
are never committed to the repository.
