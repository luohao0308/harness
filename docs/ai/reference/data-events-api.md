# 数据、事件与 API 参考

本文件只保留事件、Event Store 和 API 契约指引。数据表字段以 [database-schema.yaml](./database-schema.yaml) 为唯一机器契约，API 以 [openapi.yaml](../../api/openapi.yaml) 为唯一机器契约。

## 数据契约

```text
机器契约：docs/ai/reference/database-schema.yaml
说明文档：docs/ai/reference/database-erd-migrations.md
```

## API 契约

```text
机器契约：docs/api/openapi.yaml
说明文档：docs/api/openapi-contract.md
```

## 当前接口分组

```text
Tasks: create, list, detail, start, cancel, resume, step resume, result
Events: list, stream
Replay: replay
Subagents: list, create, detail, cancel
Sandboxes: list, warm-pool, detail, terminate
Settings: models read/write, model health, policies read/write
Audit: model-calls, tool-calls
Observability: summary
Metrics: /metrics
```

## 事件类型

```text
TASK_CREATED
TASK_STARTED
TASK_PAUSED
TASK_RESUMED
TASK_CANCELLED
TASK_FAILED
TASK_COMPLETED
PLAN_REQUESTED
PLAN_GENERATED
PLAN_UPDATED
PLAN_REJECTED
STEP_STARTED
STEP_COMPLETED
STEP_FAILED
STEP_RETRIED
STEP_SKIPPED
MODEL_CALLED
MODEL_RESPONSE_RECEIVED
MODEL_CALL_FAILED
MODEL_FALLBACK_USED
TOOL_CALLED
TOOL_RESULT_RECEIVED
TOOL_FAILED
TOOL_TIMEOUT
TOOL_DENIED_BY_POLICY
SUBAGENT_SPAWNED
SUBAGENT_STARTED
SUBAGENT_PROGRESS
SUBAGENT_COMPLETED
SUBAGENT_FAILED
SUBAGENT_TIMEOUT
SUBAGENT_CANCELLED
SANDBOX_REQUESTED
SANDBOX_ALLOCATED
SANDBOX_REUSED_FROM_WARM_POOL
SANDBOX_COMMAND_STARTED
SANDBOX_COMMAND_COMPLETED
SANDBOX_COMMAND_FAILED
SANDBOX_RELEASED
SANDBOX_DESTROYED
POLICY_CHECKED
POLICY_DENIED
SECRET_ACCESSED
USER_ACTION
ADMIN_ACTION
```

## Event Store 规则

- `agent_events` 只追加。
- `agent_events` 禁止 update。
- `agent_events` 禁止 delete。
- 同一个 `task_id` 的 `sequence` 单调递增。
- 唯一索引固定为 `task_id + sequence`。
- 任务状态从事件流重建。
- 每 100 个事件生成一次 snapshot。
- Replay 会读取最近的 `task_snapshots`，再继续扫描后续事件。
- Snapshot 内容包含状态、步骤、工具、模型、子 Agent、沙箱、失败点和最后事件序号。
