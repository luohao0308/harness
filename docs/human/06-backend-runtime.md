# 06 后端与运行时

## 后端技术栈

```text
Python 3.11
FastAPI
Pydantic v2
SQLAlchemy 2.0
Alembic
PostgreSQL 16
Redis 7
Dramatiq
Docker SDK for Python
OpenTelemetry
prometheus-client
```

## 服务目录

```text
services/api-server/
├─ app/
│  ├─ main.py
│  ├─ api/
│  │  ├─ tasks.py
│  │  ├─ events.py
│  │  ├─ subagents.py
│  │  ├─ sandboxes.py
│  │  └─ settings.py
│  ├─ core/
│  │  ├─ config.py
│  │  ├─ auth.py
│  │  ├─ logging.py
│  │  └─ telemetry.py
│  ├─ agents/
│  │  ├─ planner.py
│  │  ├─ executor.py
│  │  ├─ react_engine.py
│  │  ├─ subagent_manager.py
│  │  └─ model_gateway.py
│  ├─ events/
│  │  ├─ event_store.py
│  │  ├─ event_types.py
│  │  └─ replay.py
│  ├─ sandbox/
│  │  ├─ docker_manager.py
│  │  ├─ warm_pool.py
│  │  └─ policies.py
│  ├─ tools/
│  │  ├─ registry.py
│  │  ├─ shell.py
│  │  ├─ filesystem.py
│  │  └─ http.py
│  ├─ db/
│  │  ├─ session.py
│  │  ├─ models.py
│  │  └─ migrations/
│  └─ workers/
│     ├─ broker.py
│     ├─ subagent_worker.py
│     └─ sandbox_worker.py
```

## 数据模型

核心表：

```text
tasks
execution_plans
task_steps
agent_runs
agent_events
sandbox_instances
model_calls
tool_calls
```

Event Store 使用 PostgreSQL append-only 表。事件禁止 update，禁止 delete。合规清理通过归档表完成。

## API

任务：

```text
POST   /api/tasks
GET    /api/tasks
GET    /api/tasks/{task_id}
POST   /api/tasks/{task_id}/start
POST   /api/tasks/{task_id}/cancel
POST   /api/tasks/{task_id}/resume
POST   /api/tasks/{task_id}/steps/resume
GET    /api/tasks/{task_id}/result
```

事件：

```text
GET    /api/tasks/{task_id}/events
GET    /api/tasks/{task_id}/events/stream
POST   /api/tasks/{task_id}/replay
```

Subagent：

```text
GET    /api/tasks/{task_id}/subagents
GET    /api/subagents
GET    /api/subagents/recovery/summary
GET    /api/subagents/recovery/global-summary
GET    /api/subagents/recovery/global-summary/export
GET    /api/subagents/{subagent_id}
POST   /api/subagents/{subagent_id}/cancel
```

Sandbox：

```text
GET    /api/sandboxes
GET    /api/sandboxes/{sandbox_id}
POST   /api/sandboxes/{sandbox_id}/terminate
GET    /api/sandboxes/warm-pool
```

## Planner

Planner 输入：

```text
goal
context
available_tools
policy
model_config
previous_events
```

Planner 输出：

```json
{
  "summary": "Analyze and fix failing tests",
  "steps": [
    {
      "key": "inspect_project",
      "description": "Inspect project structure and test configuration",
      "execution_mode": "sync",
      "requires_sandbox": false
    },
    {
      "key": "run_tests",
      "description": "Run test suite in sandbox",
      "execution_mode": "async",
      "requires_sandbox": true,
      "can_spawn_subagent": true
    }
  ]
}
```

## Executor

Executor 使用 ReAct 循环：

```text
Reason
Act
Observe
Write Event
Update State
Continue / Stop
```

所有工具调用经过 Tool Registry 和 Policy Engine。高风险工具全部进入 Docker Sandbox。

## Model Gateway

首个交付版使用 OpenAI-compatible endpoint。业务代码只调用 Model Gateway，禁止直接调用模型供应商 SDK。

Model Gateway 负责：

- 统一请求格式
- 统一响应格式
- token 统计
- fallback 策略
- 敏感信息脱敏
- MODEL_CALLED 事件
- MODEL_RESPONSE_RECEIVED 事件
- MODEL_CALL_FAILED 事件
- MODEL_FALLBACK_USED 事件

当前后端已提供 OpenAI-compatible HTTP 调用路径、本地 mock 路径、模型调用审计、失败审计、fallback 事件、组织级 Settings 读取、RPM 限流和模型健康状态接口。TPM 限流、外部主动探测和供应商级熔断属于企业版增强项。
