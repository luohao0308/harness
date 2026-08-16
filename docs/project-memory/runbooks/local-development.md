# Local Development Runbook

本文件定义本地开发环境启动、验证和排障流程。

## Prerequisites

```text
Python 3.11
Node.js 20
Docker Engine
Docker Compose
PostgreSQL 16 container
Redis 7 container
```

## Environment Setup

```bash
cp .env.example .env
cp services/api-server/.env.example services/api-server/.env
cp apps/web-site/.env.example apps/web-site/.env.local
cp apps/agent-console/.env.example apps/agent-console/.env.local
```

The backend defaults to the platform-managed Chat Completions provider in the
two server-side templates. Put `AI_PROVIDER_API_KEY` only in `.env` or
`services/api-server/.env` when exercising a real provider call. Do not add it
to `apps/agent-console/.env.local`, website environment files, `VITE_*`, or
`NEXT_PUBLIC_*` values. `MODEL_GATEWAY_*` remains available solely for local
mock compatibility. Harness currently accepts only
`AI_PROVIDER_PROTOCOL=chat_completions`; the reference project's optional
`responses` protocol is not implemented here. In development, an empty
`AI_PROVIDER_API_KEY` keeps the existing mock path available and therefore is
not evidence of real upstream connectivity.

## Start Dependencies

```bash
cd deploy/docker-compose
docker compose up -d postgres redis
docker compose ps
```

## API Server

```bash
cd services/api-server
python -m venv .venv
source .venv/bin/activate
python -m pip install -U pip
python -m pip install -e ".[dev]"
alembic upgrade head
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Verify:

```bash
curl --noproxy '*' http://127.0.0.1:8000/health
curl --noproxy '*' http://127.0.0.1:8000/metrics
curl --noproxy '*' http://127.0.0.1:8000/api/tasks -H "Authorization: Bearer dev-engineer-token"
```

## Agent Worker

```bash
cd services/api-server
source .venv/bin/activate
dramatiq app.workers.subagent_worker
```

## Agent Assignment Worker

```bash
cd services/api-server
source .venv/bin/activate
dramatiq app.workers.agent_assignment_worker --queues agent_assignments
```

Verify:

```bash
curl --noproxy '*' http://127.0.0.1:8000/api/observability/summary -H "Authorization: Bearer dev-engineer-token"
```

The `assignment_queue` object reports queued and running multi-agent assignments.

## Subagent Recovery Worker

```bash
cd services/api-server
source .venv/bin/activate
python -m app.workers.subagent_recovery_worker
```

Metrics:

```text
http://127.0.0.1:9102/metrics
```

## Team Runtime Worker

Run this worker beside the API when testing autonomous Team Goal execution without
browser-driven wake streams:

```bash
cd services/api-server
source .venv/bin/activate
python -m app.workers.team_runtime_worker
```

Useful tuning environment variables:

```text
TEAM_RUNTIME_INTERVAL_SECONDS=5
TEAM_RUNTIME_MAX_GOALS=20
TEAM_RUNTIME_MAX_WAKES_PER_TICK=4
TEAM_RUNTIME_EXECUTION_BACKEND=inline
TEAM_RUNTIME_WORKER_POOL_SIZE=2
TEAM_RUNTIME_WORKER_TIMEOUT_SECONDS=300
```

## Website

```bash
cd apps/web-site
npm ci
npm run dev
```

URL:

```text
http://localhost:3000
```

Docker Compose 入口：

```text
Website: http://127.0.0.1:3000
Grafana: http://127.0.0.1:3001
```

## Console

```bash
cd apps/agent-console
npm ci
npm run dev
```

URL:

```text
http://localhost:5173
```

## Desktop

Desktop development requires the API server and Agent Console dev server above.
Then launch the Electron shell:

```bash
cd apps/desktop-app
npm ci
npm run build:main
NO_PROXY=localhost,127.0.0.1 ELECTRON_RUN_AS_NODE= VITE_DEV_SERVER_URL=http://127.0.0.1:5173 electron .
```

See `docs/development/desktop/README.md` for the desktop capability map, production
verification matrix, packaging notes, and common Electron pitfalls.

## Test Commands

```bash
cd services/api-server
python -m pytest
```

```bash
cd apps/web-site
npm run lint
npm run build
```

```bash
cd apps/agent-console
npm run lint
npm run build
```

```bash
cd apps/desktop-app
npm test
npm run build:main
```

## Common Failures

### PostgreSQL connection refused

Check:

```bash
docker compose -f deploy/docker-compose/docker-compose.yml ps postgres
docker compose -f deploy/docker-compose/docker-compose.yml logs postgres
```

Resolution:

```bash
docker compose -f deploy/docker-compose/docker-compose.yml up -d postgres
```

### Redis connection refused

Check:

```bash
docker compose -f deploy/docker-compose/docker-compose.yml ps redis
docker compose -f deploy/docker-compose/docker-compose.yml logs redis
```

Resolution:

```bash
docker compose -f deploy/docker-compose/docker-compose.yml up -d redis
```

### Docker permission denied

Check:

```bash
docker ps
```

Resolution:

```bash
sudo usermod -aG docker "$USER"
```

Re-login after group change.
