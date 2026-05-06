# Deployment Runbook

本文件定义服务器部署、启动、验证和发布流程。

## Deployment Layout

```text
/opt/agent-harness
├─ current
├─ releases
├─ shared
│  ├─ .env
│  ├─ logs
│  └─ workspaces
└─ backups
```

## First Deployment

```bash
sudo mkdir -p /opt/agent-harness/{current,releases,shared/logs,shared/workspaces,backups}
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

```bash
sudo cp deploy/systemd/*.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable agent-api agent-worker agent-sandbox-worker agent-warm-pool
sudo systemctl start agent-api agent-worker agent-sandbox-worker agent-warm-pool
```

Verify:

```bash
systemctl status agent-api
journalctl -u agent-api -n 100
```

## Nginx Install

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

Docker Compose 执行 `db-migrate` 一次性服务，迁移完成后 API、worker、Subagent 恢复巡检和 WarmPool 服务启动。

## Post Deployment Verification

```bash
curl https://<domain>/health
curl https://<domain>/metrics
docker compose -f deploy/docker-compose/docker-compose.yml ps
```

Grafana verification:

```text
agent_tasks_total visible
warm_pool_hit_total visible
sandbox_command_duration_seconds visible
agent_subagent_recovery_total visible
```

Loki verification:

```text
query by service="api-server"
query by task_id
```
