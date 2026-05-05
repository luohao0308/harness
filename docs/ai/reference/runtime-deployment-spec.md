# 运行时与部署规格参考

## Docker Sandbox 默认值

```yaml
image: agent-runtime:latest
memory: 1024m
cpus: "1.0"
network: none
user: non-root
workspace_mount: /workspace
command_timeout_required: true
```

## Workspace

```text
/var/lib/agent-harness/workspaces/{task_id}/
├─ input/
├─ output/
├─ tmp/
└─ logs/
```

## WarmPool

```yaml
WARM_POOL_ENABLED: "true"
WARM_POOL_MIN_SIZE: "3"
WARM_POOL_MAX_SIZE: "10"
WARM_POOL_IDLE_TTL_SECONDS: "600"
WARM_POOL_CONTAINER_IMAGE: "agent-runtime:latest"
```

## 指标

```text
agent_tasks_total
agent_tasks_running
agent_tasks_failed_total
agent_task_duration_seconds
agent_task_resume_total
agent_subagents_running
agent_subagents_queued
agent_subagents_failed_total
agent_subagent_duration_seconds
sandbox_containers_total
sandbox_containers_running
sandbox_start_duration_seconds
sandbox_command_duration_seconds
sandbox_command_timeout_total
warm_pool_idle_containers
warm_pool_busy_containers
warm_pool_hit_total
warm_pool_miss_total
warm_pool_acquire_duration_seconds
model_calls_total
model_call_duration_seconds
model_call_errors_total
model_tokens_input_total
model_tokens_output_total
```

## 服务

```text
nginx
api-server
agent-worker
sandbox-worker
postgres
redis
prometheus
grafana
loki
otel-collector
```

## 外部观测服务入口

```text
Prometheus: http://127.0.0.1:9091
Grafana: http://127.0.0.1:3001
Loki: http://127.0.0.1:3100
OTel gRPC: http://127.0.0.1:4317
OTel HTTP: http://127.0.0.1:4318
```

## 目标后端代理接口

```text
GET /api/observability/grafana/dashboards
GET /api/observability/logs
GET /api/observability/traces/{trace_id}
GET /api/observability/services/health
```

## systemd

```text
agent-api.service
agent-worker.service
agent-sandbox-worker.service
agent-warm-pool.service
```

## 日志

JSON 日志必须包含：

```text
level
service
message
trace_id
task_id
agent_run_id
event_type
created_at
```

JSON 日志禁止包含：

```text
secret_value
raw_api_key
full_prompt
raw_sensitive_file_content
```
