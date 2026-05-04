# 09 阶段 08：Dramatiq Subagent

## 阶段目标

实现 Dramatiq + Redis 的异步 Subagent 系统，包含派生、队列、并发控制、超时、状态追踪和事件写入。

## Required Context

- [执行协议](./00-execution-protocol.md)
- [任务进度说明](./01-task-progress.md)
- [机器可读任务进度](./task-progress.yaml)
- [架构与技术决策](./reference/architecture-and-decisions.md)
- [数据、事件与 API](./reference/data-events-api.md)

## AI 执行提示词

```text
你是本项目的后端异步执行 Agent。现在执行阶段 08：Dramatiq Subagent。

必须先读取 docs/ai/00-execution-protocol.md、docs/ai/01-task-progress.md、docs/ai/task-progress.yaml、docs/ai/reference/architecture-and-decisions.md 和 docs/ai/reference/data-events-api.md。
只执行阶段 08，不进入阶段 09。
阶段开始前必须创建阶段分支，验证通过后 commit、push 并创建 PR。

执行内容：
1. 创建 app/workers/broker.py，配置 RedisBroker。
2. 创建 app/workers/subagent_worker.py，定义 Dramatiq actor。
3. 创建 app/agents/subagent_manager.py。
4. SubagentManager.spawn 创建 agent_runs 记录，初始状态 PENDING。
5. SubagentManager.spawn 写入 SUBAGENT_SPAWNED。
6. worker 开始执行时写入 SUBAGENT_STARTED。
7. worker 成功时写入 SUBAGENT_COMPLETED。
8. worker 失败时写入 SUBAGENT_FAILED。
9. worker 超时时写入 SUBAGENT_TIMEOUT。
10. 并发限制固定为 5。
11. 默认超时固定为 900 秒。
12. GET /api/tasks/{task_id}/subagents 返回子 Agent 列表。
13. GET /api/subagents/{subagent_id} 返回子 Agent 详情。
14. POST /api/subagents/{subagent_id}/cancel 取消子 Agent。
15. 创建测试覆盖派生、状态流转、超时事件。
16. 更新 docs/ai/task-progress.yaml，把 stage-08-dramatiq-subagent 标记为 completed。

PR 与进度要求：
- 阶段分支必须推送到 origin。
- 阶段变更必须创建 Pull Request。
- branch、commit_sha、pr_url 写入 docs/ai/task-progress.yaml。
- 人读进度 docs/human/10-task-progress.md 必须同步更新。

验收标准：
- Dramatiq broker 存在。
- Subagent worker 存在。
- agent_runs 状态正确流转。
- 并发限制为 5。
- 超时为 900 秒。
- Subagent API 存在。
- pytest 通过。
- task-progress.yaml 已更新。
```

## Required Files

```text
services/api-server/app/workers/broker.py
services/api-server/app/workers/subagent_worker.py
services/api-server/app/agents/subagent_manager.py
services/api-server/app/api/subagents.py
services/api-server/tests/test_subagents.py
```

## Required State Flow

```text
PENDING -> RUNNING -> SUCCESS
PENDING -> RUNNING -> FAILED
PENDING -> RUNNING -> TIMEOUT
PENDING -> CANCELLED
```

## Verification Commands

```bash
cd services/api-server
python -m pytest
dramatiq app.workers.subagent_worker
curl http://127.0.0.1:8000/api/tasks/{task_id}/subagents
```

## Progress Update Rule

```yaml
stage-08-dramatiq-subagent:
  status: completed
  verification_result: passed
  next_stage: stage-09-sandbox-warmpool
```

