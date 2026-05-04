# 07 部署与运营

## 部署形态

首个交付版部署形态固定为：

```text
Docker Compose
systemd
Nginx
PostgreSQL 16
Redis 7
Prometheus
Grafana
Loki
OpenTelemetry Collector
```

首个交付版不包含 Kubernetes。

## Docker Sandbox

Agent 高风险工具全部进入 Docker 容器。

容器约束：

```text
memory=1024m
cpus=1.0
network=none
user=non-root
timeout=per-command
workspace=/workspace
```

工作目录：

```text
/var/lib/agent-harness/workspaces/{task_id}/
├─ input/
├─ output/
├─ tmp/
└─ logs/
```

## WarmPool

WarmPool 配置：

```text
WARM_POOL_ENABLED=true
WARM_POOL_MIN_SIZE=3
WARM_POOL_MAX_SIZE=10
WARM_POOL_IDLE_TTL_SECONDS=600
WARM_POOL_CONTAINER_IMAGE=agent-runtime:latest
```

容器状态：

```text
CREATING
IDLE
BUSY
DRAINING
FAILED
DESTROYED
```

低风险任务使用 WarmPool。高风险任务使用一次性容器。

## 监控指标

任务指标：

```text
agent_tasks_total
agent_tasks_running
agent_tasks_failed_total
agent_task_duration_seconds
agent_task_resume_total
```

Subagent 指标：

```text
agent_subagents_running
agent_subagents_queued
agent_subagents_failed_total
agent_subagent_duration_seconds
```

沙箱指标：

```text
sandbox_containers_total
sandbox_containers_running
sandbox_start_duration_seconds
sandbox_command_duration_seconds
sandbox_command_timeout_total
```

WarmPool 指标：

```text
warm_pool_idle_containers
warm_pool_busy_containers
warm_pool_hit_total
warm_pool_miss_total
warm_pool_acquire_duration_seconds
```

模型指标：

```text
model_calls_total
model_call_duration_seconds
model_call_errors_total
model_tokens_input_total
model_tokens_output_total
```

## 日志

日志使用 JSON 格式写入 Loki。

```json
{
  "level": "INFO",
  "service": "agent-worker",
  "task_id": "task_123",
  "agent_run_id": "agent_456",
  "event_type": "TOOL_CALLED",
  "message": "tool called",
  "trace_id": "trace_789"
}
```

日志禁止包含密钥、完整 Prompt、用户敏感数据和未脱敏文件内容。

## 告警

告警规则：

- 任务失败率超过阈值。
- Subagent 队列积压。
- 沙箱启动失败。
- WarmPool 命中率低于阈值。
- API 错误率超过阈值。
- PostgreSQL 连接数超过阈值。
- Redis 不可用。
- 磁盘空间不足。
