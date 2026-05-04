# 11 阶段 10：监控、日志、部署

## 阶段目标

实现 Prometheus 指标、Grafana 看板、Loki JSON 日志、OpenTelemetry trace、Docker Compose、systemd 和 Nginx 部署配置。

## Required Context

- [执行协议](./00-execution-protocol.md)
- [任务进度说明](./01-task-progress.md)
- [机器可读任务进度](./task-progress.yaml)
- [运行时与部署规格](./reference/runtime-deployment-spec.md)

## AI 执行提示词

```text
你是本项目的 DevOps 执行 Agent。现在执行阶段 10：监控、日志、部署。

必须先读取 docs/ai/00-execution-protocol.md、docs/ai/01-task-progress.md、docs/ai/task-progress.yaml 和 docs/ai/reference/runtime-deployment-spec.md。
只执行阶段 10。
阶段开始前必须创建阶段分支，验证通过后 commit、push 并创建 PR。

执行内容：
1. API Server 暴露 /metrics。
2. 注册任务、Subagent、Sandbox、WarmPool、模型调用指标。
3. JSON 日志输出到 stdout，字段包含 level、service、message、trace_id、task_id、agent_run_id、event_type、created_at。
4. 日志禁止输出 secret_value、raw_api_key、full_prompt、raw_sensitive_file_content。
5. FastAPI 接入 OpenTelemetry middleware。
6. trace_id 写入 agent_events 和 JSON 日志。
7. 创建 deploy/docker-compose/docker-compose.yml。
8. docker compose 服务包含 nginx、api-server、agent-worker、sandbox-worker、postgres、redis、prometheus、grafana、loki、otel-collector。
9. 创建 deploy/monitoring/prometheus.yml。
10. 创建 deploy/monitoring/loki.yml。
11. 创建 deploy/monitoring/otel-collector.yml。
12. 创建 deploy/monitoring/grafana-dashboard-agent-harness.json。
13. 创建 deploy/systemd/agent-api.service、agent-worker.service、agent-sandbox-worker.service、agent-warm-pool.service。
14. 创建 deploy/nginx/agent-harness.conf。
15. Nginx 必须支持 SSE，事件流路径关闭 proxy buffering。
16. 验证 docker compose config。
17. 更新 docs/ai/task-progress.yaml，把 stage-10-observability-deployment 标记为 completed。

PR 与进度要求：
- 阶段分支必须推送到 origin。
- 阶段变更必须创建 Pull Request。
- branch、commit_sha、pr_url 写入 docs/ai/task-progress.yaml。
- 人读进度 docs/human/10-task-progress.md 必须同步更新。

验收标准：
- /metrics 存在。
- JSON 日志字段完整。
- Docker Compose 配置有效。
- Prometheus 配置存在。
- Grafana dashboard JSON 存在。
- Loki 配置存在。
- systemd service 文件存在。
- Nginx 配置存在并支持 SSE。
- task-progress.yaml 已更新。
```

## Required Files

```text
deploy/docker-compose/docker-compose.yml
deploy/monitoring/prometheus.yml
deploy/monitoring/loki.yml
deploy/monitoring/otel-collector.yml
deploy/monitoring/grafana-dashboard-agent-harness.json
deploy/systemd/agent-api.service
deploy/systemd/agent-worker.service
deploy/systemd/agent-sandbox-worker.service
deploy/systemd/agent-warm-pool.service
deploy/nginx/agent-harness.conf
```

## Required Metrics

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

## Verification Commands

```bash
curl http://127.0.0.1:8000/metrics
cd deploy/docker-compose
docker compose config
test -f ../monitoring/prometheus.yml
test -f ../monitoring/loki.yml
test -f ../monitoring/otel-collector.yml
test -f ../monitoring/grafana-dashboard-agent-harness.json
test -f ../nginx/agent-harness.conf
test -f ../systemd/agent-api.service
test -f ../systemd/agent-worker.service
test -f ../systemd/agent-sandbox-worker.service
test -f ../systemd/agent-warm-pool.service
```

## Progress Update Rule

```yaml
stage-10-observability-deployment:
  status: completed
  verification_result: passed
  next_stage: completed
```

