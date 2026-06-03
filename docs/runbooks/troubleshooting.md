# Troubleshooting Runbook

本文件定义常见故障定位流程。

## Private Docker Compose Handoff Triage

第一版私有部署体验只做轻量诊断。优先使用既有 smoke 输出和本 runbook，不新增 installer、doctor framework、Kubernetes/cloud topology 或完整运维平台。

When full verification cannot complete, record:

```text
blocker:
failing service:
command:
log pointer:
recovery note:
unproven acceptance criteria:
```

### Docker unavailable

Check:

```bash
docker version
docker compose version
docker ps
```

Action:

```text
start Docker Desktop or Docker Engine
verify /var/run/docker.sock exists when sandbox services need it
rerun docker compose config before starting services
```

### Port conflict

Check:

```bash
lsof -nP -iTCP:8000 -sTCP:LISTEN
lsof -nP -iTCP:5173 -sTCP:LISTEN
lsof -nP -iTCP:3000 -sTCP:LISTEN
lsof -nP -iTCP:8080 -sTCP:LISTEN
lsof -nP -iTCP:9091 -sTCP:LISTEN
lsof -nP -iTCP:3001 -sTCP:LISTEN
```

Action:

```text
stop the conflicting local service, or change the compose env port override before build
when overriding API/Console ports, also update PUBLIC_API_BASE_URL / PUBLIC_CONSOLE_BASE_URL and HARNESS_* smoke env vars
record any changed port in the handoff evidence
```

### Compose config failure

Check:

```bash
docker compose --env-file deploy/docker-compose/.env -f deploy/docker-compose/docker-compose.yml config
```

Action:

```text
fix env syntax or missing variables before running application smoke
do not claim deployment readiness while compose config fails
```

### API health failure

Check:

```bash
docker compose --env-file deploy/docker-compose/.env -f deploy/docker-compose/docker-compose.yml ps
docker compose --env-file deploy/docker-compose/.env -f deploy/docker-compose/docker-compose.yml logs --tail=100 api-server
curl --noproxy '*' http://127.0.0.1:8000/health
```

Action:

```text
inspect db-migrate, postgres, redis, and api-server service status first
verify DATABASE_URL and REDIS_URL use compose service names inside compose
```

### Console API base URL mismatch

Check:

```bash
curl --noproxy '*' http://127.0.0.1:5173
grep -n "VITE_API_BASE_URL" deploy/docker-compose/docker-compose.yml apps/agent-console/.env.example
```

Action:

```text
compose console builds should target http://127.0.0.1:8000
if the Console loads but cannot reach API, fix build args/env docs before runtime code
```

### Model key vs mock fallback

Check:

```bash
grep -n "DEEPSEEK_API_KEY\\|MODEL_GATEWAY_BASE_URL" deploy/docker-compose/.env.example .env.example services/api-server/.env.example
```

Action:

```text
empty DEEPSEEK_API_KEY is acceptable for local mock-model fallback validation
real provider validation requires a deployment-local secret, never a committed key
```

### P7 knowledge demo seed failure

Check the payload plan without touching the API:

```bash
python3 scripts/seed-knowledge-demo.py --print-plan
```

Check API reachability and auth:

```bash
curl --noproxy '*' http://127.0.0.1:8000/health
HARNESS_API_BASE_URL=http://127.0.0.1:8000 \
HARNESS_ADMIN_TOKEN=dev-admin-token \
python3 scripts/seed-knowledge-demo.py --verify-readback --check-idempotent
```

Action:

```text
verify the API server is running on the same HARNESS_API_BASE_URL used by the seed
verify HARNESS_ADMIN_TOKEN matches the local admin token
inspect the failing POST /api/agents/{agent_id}/knowledge/sources response body
rerun with --check-idempotent to prove existing seed rows are reused rather than duplicated
do not repair the seed by writing directly to database tables
```

Expected seed markers:

```text
P7 Demo Agent Runbook
P7 Demo Org Handoff
p7-seed-fixture:agent:agent-runbook
p7-seed-fixture:org:org-handoff
seed-fixture://agent-knowledge-harness/p7/
```

### P7 knowledge migration/restore smoke failure

Check the default service-level smoke first:

```bash
python3 scripts/smoke-test-knowledge-migration-restore.py
```

Check a specific service database only when the target URL is intentional:

```bash
HARNESS_P7_DATABASE_URL="$DATABASE_URL" \
python3 scripts/smoke-test-knowledge-migration-restore.py --allow-service-db-mutation
```

Action:

```text
remember bare DATABASE_URL is ignored by the smoke; use HARNESS_P7_DATABASE_URL or --database-url explicitly
confirm Alembic reaches head before reading selector continuity output
inspect missing table names reported by the smoke before changing application code
rerun against temporary SQLite to separate migration breakage from service database state
use --keep-db only when a local temp database needs manual inspection
do not promote full Docker Compose restore to the default release smoke without a new plan
```

## API 5xx

Check:

```bash
journalctl -u agent-api -n 200
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8000/metrics
```

Inspect:

```text
trace_id
request_id
task_id
event_type
```

## Task stuck in RUNNING

Check events:

```bash
curl http://127.0.0.1:8000/api/tasks/{task_id}/events
```

Check workers:

```bash
systemctl status agent-worker
journalctl -u agent-worker -n 200
```

Action:

```text
replay event stream
identify last sequence
mark timed-out Subagents
resume task from stable step
```

## Subagent queue backlog

Check Redis:

```bash
redis-cli LLEN dramatiq:default
```

Check metrics:

```text
agent_subagents_queued
agent_subagents_running
agent_subagents_failed_total
```

Action:

```text
scale agent-worker
inspect failing Subagent logs
check Redis availability
```

Check console:

```text
/observability subagent_queue pending
/observability subagent_queue running
/observability subagent_queue available_slots
```

## Sandbox creation failure

Check:

```bash
docker ps
docker images
journalctl -u agent-sandbox-worker -n 200
```

Metrics:

```text
sandbox_containers_total
sandbox_start_duration_seconds
sandbox_command_timeout_total
```

Action:

```text
verify Docker socket access
verify agent-runtime image exists
verify memory and CPU limits
drain failed WarmPool containers
```

## Observability export missing

Check API:

```bash
curl http://127.0.0.1:8000/api/observability/exports/history
```

Check storage:

```text
OBSERVABILITY_EXPORT_DIR
observability-exports docker volume
observability_export_records table
```

Action:

```text
verify api-server volume mount
verify export record organization_id
verify retained file path exists
```

## SSE disconnected

Check Nginx:

```bash
sudo nginx -t
sudo tail -n 200 /var/log/nginx/error.log
```

Required Nginx behavior:

```text
proxy_buffering off
connection keep-alive
read timeout supports long-running event stream
```
