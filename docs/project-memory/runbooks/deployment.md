# Deployment Runbook

本文件定义私有 Docker Compose 交付、启动、验证和后续服务器部署流程。

## Canonical Private Docker Compose Handoff

第一版私有交付体验面向懂 Docker、但不熟悉本仓库的内部工程同事。Canonical 路径是 Docker Compose 全链路启动并通过 Agent Run smoke；`systemd`、Nginx 域名部署和生产式验证是后续服务器安装路径，不是第一版 handoff 的通过条件。

### Prerequisites

```text
Docker Engine running
Docker Compose plugin available
Ports available: 8000, 5173, 3000, 8080, 9091, 3001, 3100, 3200
Local Docker socket available at /var/run/docker.sock
```

### Environment

Use the compose-specific env template for private handoff:

```bash
cp deploy/docker-compose/.env.example deploy/docker-compose/.env
```

Before starting any API container, replace the example startup secrets:

```bash
python3 scripts/generate-runtime-secrets.py
```

Write `AUTH_JWT_SECRET`, `HARNESS_SECRET_ENCRYPTION_KEY`, and
`HARNESS_SECRET_ENCRYPTION_KEY_ID` to `deploy/docker-compose/.env`. The
placeholder `replace-with-openssl-rand-hex-32` is intentionally rejected at API
startup, and production secret-vault reads/writes require
`HARNESS_SECRET_ENCRYPTION_KEY`.
For an empty database, set `HARNESS_INITIAL_ADMIN_EMAIL` and
`HARNESS_INITIAL_ADMIN_PASSWORD` for the first boot only. Remove or clear those
two bootstrap variables after the first successful login and restart the API.
Details and the CLI fallback live in
[First-Run Admin Runbook](./first-run-admin.md).

Key defaults:

```text
API: http://127.0.0.1:8000
Console: http://127.0.0.1:5173
Website: http://127.0.0.1:3000
Nginx: http://127.0.0.1:8080
Prometheus: http://127.0.0.1:9091
Grafana: http://127.0.0.1:3001
Loki: http://127.0.0.1:3100
Tempo: http://127.0.0.1:3200
```

`APP_ENV` defaults to `production` for the compose handoff so dev bearer tokens
are rejected. Set `APP_ENV=development` only for local development diagnostics.
The default model path is the platform-managed OpenAI-compatible provider:
`AI_PROVIDER_PROTOCOL=chat_completions`,
`AI_PROVIDER_BASE_URL=https://chybenzun.top/v1`, and
`AI_PROVIDER_MODEL=deepseek-v4-flash`. Set `AI_PROVIDER_API_KEY` only in the
deployment-local environment file or secret manager. It is read by backend
processes only and must never be passed as a browser build argument or exposed
through `VITE_*` / `NEXT_PUBLIC_*` variables. Legacy `MODEL_GATEWAY_*` and
`DEEPSEEK_API_KEY` values remain only for local mock compatibility. The API
refuses to start in production when `AI_PROVIDER_API_KEY` is empty or still set
to the example placeholder, so production cannot silently fall back to mock
model output. `AI_PROVIDER_PROTOCOL` is intentionally fixed to
`chat_completions`; Harness does not currently implement the reference
project's optional `responses` request and response contract.

If a default host port is already occupied, override the matching `*_HTTP_PORT` and public URL values in `deploy/docker-compose/.env` before building. Example:

```text
API_HTTP_PORT=18000
CONSOLE_HTTP_PORT=15173
WEBSITE_HTTP_PORT=13000
PUBLIC_API_BASE_URL=http://127.0.0.1:18000
PUBLIC_CONSOLE_BASE_URL=http://127.0.0.1:15173
PUBLIC_WEBSITE_BASE_URL=http://127.0.0.1:13000
```

The Console and Website images are static frontend builds. Public URL changes are build-time inputs, so rerun `docker compose ... up -d --build` after changing `PUBLIC_*` values. A stale frontend image can still point at old ports.

When using overrides, pass matching smoke environment variables:

```bash
HARNESS_API_BASE_URL=http://127.0.0.1:18000 \
HARNESS_CONSOLE_BASE_URL=http://127.0.0.1:15173 \
HARNESS_WEBSITE_BASE_URL=http://127.0.0.1:13000 \
HARNESS_NGINX_BASE_URL=http://127.0.0.1:18080 \
HARNESS_PROMETHEUS_BASE_URL=http://127.0.0.1:19091 \
HARNESS_GRAFANA_BASE_URL=http://127.0.0.1:13001 \
HARNESS_LOKI_BASE_URL=http://127.0.0.1:13100 \
HARNESS_TEMPO_BASE_URL=http://127.0.0.1:13200 \
python3 scripts/smoke-test-docker.py
```

### Validate Configuration

```bash
docker compose --env-file deploy/docker-compose/.env -f deploy/docker-compose/docker-compose.yml config
```

This command is the first gate. Do not start the stack until it exits 0.

### Migration Pre-flight

Before deploying a branch with new Alembic migrations, run the full migration
chain against PostgreSQL. SQLite is not a sufficient pre-flight for production
schema changes because it can miss type-width issues.

Run the migration id lint before the PostgreSQL pre-flight:

```bash
python3 scripts/check-migration-ids.py services/api-server/alembic/versions
```

Identifier-width rules are documented in
[Migration Conventions](./migration-conventions.md).

One-command local check:

```bash
bash scripts/migration-preflight.sh
```

The script defaults to `HARNESS_MIGRATION_PREFLIGHT_MODE=auto`: it uses Docker
when the daemon is available, and otherwise falls back to local PostgreSQL
`initdb` / `pg_ctl` binaries if they are installed. Set the mode to `docker` or
`local` to force one path.

Equivalent manual flow:

```bash
docker run --rm -e POSTGRES_PASSWORD=t -p 15432:5432 -d --name harness-pg postgres:16
cd services/api-server
DATABASE_URL=postgresql+psycopg://postgres:t@127.0.0.1:15432/postgres \
  .venv/bin/python -m alembic upgrade head
cd ../..
docker rm -f harness-pg
```

Always remove the temporary container after the check, including failed runs, so
the pre-flight does not leave port `15432` occupied.

### Start

```bash
docker compose --env-file deploy/docker-compose/.env -f deploy/docker-compose/docker-compose.yml up -d --build
```

### Verify Service Reachability

```bash
docker compose --env-file deploy/docker-compose/.env -f deploy/docker-compose/docker-compose.yml ps
curl --noproxy '*' http://127.0.0.1:8000/health
curl --noproxy '*' http://127.0.0.1:5173
curl --noproxy '*' http://127.0.0.1:3000
curl --noproxy '*' http://127.0.0.1:8080/health
curl --noproxy '*' http://127.0.0.1:9091/-/healthy
curl --noproxy '*' http://127.0.0.1:3001/api/health
```

With the override example above, use:

```bash
curl --noproxy '*' http://127.0.0.1:18000/health
curl --noproxy '*' http://127.0.0.1:15173
curl --noproxy '*' http://127.0.0.1:13000
curl --noproxy '*' http://127.0.0.1:18080/health
curl --noproxy '*' http://127.0.0.1:19091/-/healthy
curl --noproxy '*' http://127.0.0.1:13001/api/health
```

The Console must load from `http://127.0.0.1:5173` and be built against API base URL `http://127.0.0.1:8000`. A Console page that loads but points at the wrong API base URL is a failed handoff.

When using overrides, the same rule applies to the overridden values: Console on `http://127.0.0.1:15173` must be built against API base URL `http://127.0.0.1:18000`.

### Prove The Harness Chain

Log in and export real JWTs for production-mode smoke tests:

```bash
LOGIN_JSON="$(curl --noproxy '*' -sS http://127.0.0.1:8000/api/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"email":"admin@example.com","password":"replace-with-bootstrap-password"}')"
export HARNESS_AUTH_TOKEN="$(python3 -c 'import json,sys; print(json.load(sys.stdin)["access_token"])' <<<"$LOGIN_JSON")"
export HARNESS_ADMIN_TOKEN="$HARNESS_AUTH_TOKEN"
export HARNESS_OPERATOR_TOKEN="$HARNESS_AUTH_TOKEN"
```

```bash
python3 scripts/smoke-test-docker.py
python3 scripts/smoke-test-agent-run.py
```

`scripts/smoke-test-docker.py` validates the compose-level service chain.
`scripts/smoke-test-agent-run.py` is the canonical product smoke: it must prove
the Agent Run path and required run/task/event/tool/sandbox/subagent/eval/
observability correlation. In `APP_ENV=development` only, these scripts fall
back to the legacy dev tokens when `HARNESS_*_TOKEN` variables are absent.

### P7 Knowledge Demo And Restore Smoke

P7 adds deterministic Knowledge/RAG demo hardening without widening the private handoff into a new installer or full operations profile.

Seed demo knowledge through public APIs only:

```bash
python3 scripts/seed-knowledge-demo.py --print-plan

HARNESS_API_BASE_URL=http://127.0.0.1:8000 \
HARNESS_DEMO_AGENT_ID=default \
HARNESS_ADMIN_TOKEN="$HARNESS_ADMIN_TOKEN" \
python3 scripts/seed-knowledge-demo.py --verify-readback --check-idempotent
```

The seed writes agent-scoped and org-scoped Markdown sources using the same API path as Agent Studio. Fixture origin is carried by deterministic names, `idempotency_key`, and `seed-fixture://...` document URIs. It is local fixture evidence, not provider-backed web verification.

Run the default service-level migration/restore smoke before claiming release readiness:

```bash
python3 scripts/smoke-test-knowledge-migration-restore.py
```

To point the smoke at a specific service database instead of temporary SQLite:

```bash
HARNESS_P7_DATABASE_URL="$DATABASE_URL" \
python3 scripts/smoke-test-knowledge-migration-restore.py --allow-service-db-mutation
```

This smoke checks the Knowledge/RAG migration surface and selector continuity for retrieval hits and citations after engine reopen. It does not require full Docker Compose. Full Compose startup remains the private handoff path above, and a full Compose migration/restore profile should stay manual or nightly unless a later release plan changes that boundary.

### P1 Production Deployment Hardening

P1 adds the first production deployment profile without changing the product boundary:

- `compose.production.yml` wraps the API behind Caddy with HTTPS and long-lived SSE proxying.
- `GET /api/health/liveness` is the process-only probe.
- `GET /api/health/readiness` checks Postgres, Redis, and LLM provider health.
- `scripts/backup-postgres.sh` and `scripts/restore-postgres.sh` cover daily backup and restore.
- `deploy/helm/harness/` provides a minimal Helm chart with ingress, migration job, HPA, and PDB.

The production profile expects explicit secrets for `POSTGRES_PASSWORD`,
`REDIS_PASSWORD`, `AUTH_JWT_SECRET`, `HARNESS_SECRET_ENCRYPTION_KEY`, and
`HARNESS_DOMAIN`. It is intentionally
narrower than the dev compose path and keeps graceful shutdown plus frontend
reconnect as the user-facing fallback for SSE interruption. Console production
builds do not embed dev bearer tokens unless `CONSOLE_DEV_TOKEN` or
`CONSOLE_DEV_ADMIN_TOKEN` is explicitly set for a development-only diagnostic.

The browser release gate includes a mocked P7 Knowledge demo projection:

```bash
cd apps/agent-console && npm run e2e:smoke:release
```

The mocked browser smoke proves Agent Studio knowledge projection, Workspace local grounding indicator, Run Detail retrieval/citation/manifest evidence, Eval grounding metrics, and Observability grounding quality without consuming live seeded backend rows.

For the full Phase 0b vertical spine gate, the release flow also accepts an OMX-independent evidence JSON under the validation report directory at:

```text
.omx/reports/complete-harness-validation-flow/phase0b-release-spine-evidence.json
```

`scripts/validate-harness-flow.sh --full-infra` requires that file and validates it with `scripts/check-release-spine-evidence.py` before the handoff is considered complete. Local partial runs may use `--local-dev`, which writes the matching template to `.omx/reports/complete-harness-validation-flow/phase0b-release-spine-evidence.template.json` and explicitly reports the Phase 0b evidence as skipped until a real JSON is supplied.

### Phase 0b Complete Capability Spine Evidence

The complete Agent capability product release gate must not close from browser fixture projection alone. Record one concrete Phase 0b evidence JSON after the integrated lanes are available, then validate it with the OMX-independent checker:

```bash
python3 scripts/check-release-spine-evidence.py --write-template .omx/reports/complete-harness-validation-flow/phase0b-release-spine-evidence.template.json
python3 scripts/check-release-spine-evidence.py .omx/reports/complete-harness-validation-flow/phase0b-release-spine-evidence.json
```

The evidence JSON must prove the single operator path: private package staging, public URL/Git package staging with no package-code execution during validation, Agent creation or clone, MCP/Skill/Tool/knowledge connector attachments, usable connector sync or reindex, Workspace multi-agent orchestration, inspectable subagent run, Run Detail capability snapshot, orchestration evidence, knowledge evidence, context manifest, and token/cost panel. Keep this checker independent of OMX state, tmux panes, and worker mailboxes so it can run in local release CI or during a private handoff.

### Shutdown / Cleanup

```bash
docker compose --env-file deploy/docker-compose/.env -f deploy/docker-compose/docker-compose.yml down
```

Record this cleanup command in the handoff evidence. If the stack is intentionally kept running for diagnosis, record the reason, failing service, relevant command, log pointer, recovery note, and which acceptance criteria remain unproven.

### Common Failure Entry Points

Use [Troubleshooting Runbook](./troubleshooting.md) for narrow local diagnostics:

- Docker daemon or socket unavailable.
- Occupied host ports.
- PostgreSQL or Redis unhealthy.
- API health check failing.
- Console API base URL mismatch.
- Platform provider key or legacy mock-model fallback.

Do not turn this path into a new installer, doctor framework, Kubernetes deployment, cloud matrix, or full operations platform.

## Deployment Layout

```text
/opt/agent-harness
├─ current
├─ releases
├─ shared
│  ├─ .env
│  ├─ logs
│  ├─ workspaces
│  └─ observability-exports
└─ backups
```

## First Deployment

This section is the server layout variant. For first-pass private handoff, prefer the canonical Docker Compose path above.

```bash
sudo mkdir -p /opt/agent-harness/{current,releases,shared/logs,shared/workspaces,shared/observability-exports,backups}
sudo chown -R "$USER":"$USER" /opt/agent-harness
```

Clone:

```bash
git clone git@github.com:<org>/agent-harness.git /opt/agent-harness/current
cd /opt/agent-harness/current
git checkout main
```

Environment:

```bash
cp .env.example /opt/agent-harness/shared/.env
```

Replace `AUTH_JWT_SECRET` and `HARNESS_SECRET_ENCRYPTION_KEY`, and for an empty
database, set the first-run admin bootstrap variables in
`/opt/agent-harness/shared/.env` before startup. The API will reject the JWT
placeholder secret, and production secret-vault reads/writes require the
encryption key.

Start:

```bash
docker compose --env-file /opt/agent-harness/shared/.env -f deploy/docker-compose/docker-compose.yml up -d --build
```

Verify:

```bash
docker compose -f deploy/docker-compose/docker-compose.yml ps
curl --noproxy '*' http://127.0.0.1:8000/health
curl --noproxy '*' http://127.0.0.1:8000/metrics
curl --noproxy '*' http://127.0.0.1:3000
curl --noproxy '*' http://127.0.0.1:8080/health
curl --noproxy '*' http://127.0.0.1:9091/-/healthy
curl --noproxy '*' http://127.0.0.1:3001/api/health
```

Default local endpoints:

```text
API: http://127.0.0.1:8000
Website: http://127.0.0.1:3000
Console: http://127.0.0.1:5173
Nginx: http://127.0.0.1:8080
Prometheus: http://127.0.0.1:9091
Grafana: http://127.0.0.1:3001
```

## systemd Install

`systemd` is a server-install path for later operations work. It is not required for the first-pass private Docker Compose handoff.

```bash
sudo cp deploy/systemd/*.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable agent-api agent-worker agent-assignment-worker agent-team-runtime agent-sandbox-worker agent-warm-pool
sudo systemctl start agent-api agent-worker agent-assignment-worker agent-team-runtime agent-sandbox-worker agent-warm-pool
```

Verify:

```bash
systemctl status agent-api
systemctl status agent-assignment-worker
systemctl status agent-team-runtime
journalctl -u agent-api -n 100
journalctl -u agent-assignment-worker -n 100
journalctl -u agent-team-runtime -n 100
```

## Nginx Install

Nginx domain deployment is a server-install path for later operations work. It is not required for the first-pass private Docker Compose handoff.

```bash
sudo cp deploy/nginx/agent-harness.conf /etc/nginx/sites-available/agent-harness.conf
sudo ln -s /etc/nginx/sites-available/agent-harness.conf /etc/nginx/sites-enabled/agent-harness.conf
sudo nginx -t
sudo systemctl reload nginx
```

## Release Deployment

```bash
cd /opt/agent-harness/current
git fetch origin
git checkout main
git pull --ff-only origin main
docker compose -f deploy/docker-compose/docker-compose.yml up -d --build
```

Docker Compose 执行 `db-migrate` 一次性服务，迁移完成后 API、Subagent worker、Agent Assignment worker、Team Runtime worker、Subagent 恢复巡检和 WarmPool 服务启动。
`TEAM_RUNTIME_EXECUTION_BACKEND=process_pool` 会把 Team Runtime 的具体 wake 执行切换到子进程池；默认值仍然是 `inline`，便于本地开发和诊断。

## Post Deployment Verification

This section applies to server/domain deployments. For the canonical private Docker Compose handoff, use the local smoke commands above.

```bash
curl https://<domain>/health
curl https://<domain>/metrics
docker compose -f deploy/docker-compose/docker-compose.yml ps
docker compose -f deploy/docker-compose/docker-compose.yml logs --tail=100 agent-assignment-worker
docker compose -f deploy/docker-compose/docker-compose.yml logs --tail=100 team-runtime
curl https://<domain>/api/observability/summary -H "Authorization: Bearer <token>"
```

Grafana verification:

```text
agent_tasks_total visible
warm_pool_hit_total visible
sandbox_command_duration_seconds visible
agent_subagent_recovery_total visible
assignment_queue returned by /api/observability/summary
```

Prometheus alert rule verification:

```text
HarnessSubagentRecoveryServiceDown loaded
HarnessSubagentRecoverySweepMissing loaded
HarnessSubagentRecoveryMarkedTimeout loaded
HarnessSubagentRecoveryRepeatedReset loaded
```

Loki verification:

```text
query by service="api-server"
query by task_id
```

Observability export verification:

```text
GET /api/observability/exports/history
GET /api/observability/exports/history/{export_id}/download
OBSERVABILITY_EXPORT_DIR mounted on observability-exports volume
```
