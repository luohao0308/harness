# 06 阶段 05：Task 与 Event Store

## 阶段目标

实现任务表、事件表、Alembic 迁移、Task API、Event API 和 append-only Event Store。

## Required Context

- [执行协议](./00-execution-protocol.md)
- [任务进度说明](./01-task-progress.md)
- [机器可读任务进度](./task-progress.yaml)
- [数据、事件与 API](./reference/data-events-api.md)

## AI 执行提示词

```text
你是本项目的后端工程执行 Agent。现在执行阶段 05：Task 与 Event Store。

必须先读取 docs/ai/00-execution-protocol.md、docs/ai/01-task-progress.md、docs/ai/task-progress.yaml 和 docs/ai/reference/data-events-api.md。
只执行阶段 05，不进入阶段 06。

执行内容：
1. 创建 SQLAlchemy 模型 tasks、execution_plans、task_steps、agent_runs、agent_events、sandbox_instances。
2. 初始化 Alembic。
3. 创建迁移文件。
4. 实现 app/events/event_store.py。
5. EventStore.append 必须在事务内分配 task-local sequence。
6. EventStore.list_by_task 必须按 sequence 升序返回。
7. 创建 app/api/tasks.py，实现 POST /api/tasks、GET /api/tasks、GET /api/tasks/{task_id}。
8. 创建 app/api/events.py，实现 GET /api/tasks/{task_id}/events 和 GET /api/tasks/{task_id}/events/stream。
9. 创建 Pydantic schemas。
10. 创建测试：创建任务时写入 TASK_CREATED，事件 sequence 从 1 开始。
11. 更新 docs/ai/task-progress.yaml，把 stage-05-task-event-store 标记为 completed。

验收标准：
- Alembic migration 通过。
- 创建任务成功。
- 创建任务写入 TASK_CREATED。
- 事件列表按 sequence 升序。
- SSE endpoint 存在。
- pytest 通过。
- task-progress.yaml 已更新。
```

## Required Files

```text
services/api-server/app/db/models.py
services/api-server/app/events/event_store.py
services/api-server/app/events/event_types.py
services/api-server/app/api/tasks.py
services/api-server/app/api/events.py
services/api-server/app/api/schemas.py
services/api-server/tests/test_tasks.py
services/api-server/tests/test_event_store.py
```

## API Request

```json
{
  "title": "Analyze repository",
  "goal": "Analyze this Python project and produce findings",
  "model_provider": "openai-compatible",
  "model_name": "default",
  "max_runtime_seconds": 1800,
  "max_subagents": 5,
  "enable_sandbox": true,
  "enable_network": false
}
```

## Verification Commands

```bash
cd services/api-server
alembic upgrade head
python -m pytest
curl -X POST http://127.0.0.1:8000/api/tasks \
  -H "Content-Type: application/json" \
  -d '{"title":"Demo","goal":"Analyze project","model_provider":"openai-compatible","model_name":"default","max_runtime_seconds":1800,"max_subagents":5,"enable_sandbox":true,"enable_network":false}'
```

## Progress Update Rule

```yaml
stage-05-task-event-store:
  status: completed
  verification_result: passed
  next_stage: stage-06-planner-executor
```

