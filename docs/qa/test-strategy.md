# Test Strategy

本文件定义平台测试策略、覆盖范围、测试文件位置和通过标准。

## Test Layers

```text
unit
api
event_replay
subagent_concurrency
sandbox_security
warmpool_cleanup
frontend_component
frontend_e2e
deployment_smoke
prompt_eval
```

## Backend Unit Tests

Targets:

```text
EventStore.append
EventStore.list_by_task
Planner schema validation
Executor step lifecycle
Tool Registry policy lookup
Model Gateway response normalization
```

Command:

```bash
cd services/api-server
python -m pytest tests/unit
```

## API Tests

Targets:

```text
POST /api/tasks
POST /api/tasks/{task_id}/start
GET /api/tasks/{task_id}/events
GET /api/tasks/{task_id}/events/stream
GET /api/tasks/{task_id}/subagents
GET /api/sandboxes/warm-pool
```

Command:

```bash
cd services/api-server
python -m pytest tests/api
```

## Event Replay Tests

Targets:

```text
rebuild task state from events
read latest task_snapshots before scanning events
create task_snapshots every 100 events
resume from stable step
ignore completed steps during recovery
write STEP_SKIPPED for completed steps during resume
mark timed-out Subagents
replace lost Sandbox
```

Command:

```bash
cd services/api-server
python -m pytest tests/events
```

## Subagent Concurrency Tests

Targets:

```text
max running subagents equals 5
extra subagents remain PENDING
timeout writes SUBAGENT_TIMEOUT
cancel writes SUBAGENT_CANCELLED
```

Command:

```bash
cd services/api-server
python -m pytest tests/subagents
```

## Sandbox Security Tests

Targets:

```text
shell tool uses Docker SDK
host subprocess is absent from Agent shell execution
network default is none
memory limit is 1024m
cpu limit is 1.0
timeout terminates command
```

Command:

```bash
cd services/api-server
python -m pytest tests/sandbox
```

## WarmPool Cleanup Tests

Targets:

```text
workspace is cleaned before release
dirty container is destroyed
IDLE container is reused
warm_pool_hit_total increments
warm_pool_miss_total increments
```

Command:

```bash
cd services/api-server
python -m pytest tests/warmpool
```

## Frontend Tests

Targets:

```text
Workspace Pro route renders three-column layout
Conversation tree creates branch on edit and resend
Pause changes assistant node to paused and Continue preserves partial content
Pinned messages and context window affect stream payloads
Tool Cards render pending, approved, rejected, success, and failed states
Artifacts panel renders code, JSON, and diff previews
EventTimeline appends SSE events in Run Detail
SubagentPanel renders state transitions
SandboxPanel renders WarmPool status
```

Command:

```bash
cd apps/agent-console
npm run build
```

Frontend component and e2e test infrastructure is tracked as a deferred Workspace Pro gap until `apps/agent-console/package.json` defines a real `test` script.

## Deployment Smoke Tests

Targets:

```text
docker compose config
api health
metrics endpoint
postgres connectivity
redis connectivity
grafana reachable
website reachable
loki reachable
nginx health
nginx api proxy
nginx sse proxy
prometheus reachable on 9091
```

Command:

```bash
docker compose -f deploy/docker-compose/docker-compose.yml config
docker compose -f deploy/docker-compose/docker-compose.yml up -d --build
curl --noproxy '*' http://127.0.0.1:8000/health
curl --noproxy '*' http://127.0.0.1:8000/metrics
curl --noproxy '*' http://127.0.0.1:3000
curl --noproxy '*' http://127.0.0.1:8080/health
curl --noproxy '*' http://127.0.0.1:8080/api/tasks -H "Authorization: Bearer dev-engineer-token"
curl --noproxy '*' http://127.0.0.1:9091/-/healthy
curl --noproxy '*' http://127.0.0.1:3001/api/health
```

## Release Gate

Release requires:

```text
backend tests passed
frontend build passed
prompt eval passed
docker compose config passed
docs validation passed
security policy checks passed
```
