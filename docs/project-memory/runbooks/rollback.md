# Rollback Runbook

本文件定义应用、数据库和配置回滚流程。

## Application Rollback

Identify previous tag:

```bash
git tag --sort=-creatordate | head
```

Rollback:

```bash
cd /opt/agent-harness/current
git fetch origin --tags
git checkout <previous_tag>
docker compose -f deploy/docker-compose/docker-compose.yml up -d --build
```

Verify:

```bash
curl http://127.0.0.1:8000/health
docker compose -f deploy/docker-compose/docker-compose.yml ps
```

## Database Rollback

Rollback only when migration downgrade is verified.

```bash
cd services/api-server
alembic current
alembic downgrade -1
```

Verify:

```bash
alembic current
python -m pytest
```

## Configuration Rollback

```bash
cp /opt/agent-harness/backups/.env.previous /opt/agent-harness/shared/.env
sudo systemctl restart agent-api agent-worker agent-assignment-worker agent-sandbox-worker agent-warm-pool
```

## Rollback Completion Criteria

```text
health endpoint returns ok
workers consume queue
new task creation works
event stream works
Grafana error rate returns to normal
Loki logs have no repeated fatal errors
```
