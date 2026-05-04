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
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8000/metrics
```

## Agent Worker

```bash
cd services/api-server
source .venv/bin/activate
dramatiq app.workers.subagent_worker
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

