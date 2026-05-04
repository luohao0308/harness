# Troubleshooting Runbook

本文件定义常见故障定位流程。

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

