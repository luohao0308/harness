# 07 阶段 06：Planner 与 Executor

## 阶段目标

实现结构化 Planner、执行计划持久化、Executor 执行循环、Tool Registry、Model Gateway 接口和基础 ReAct 流程。

## Required Context

- [执行协议](./00-execution-protocol.md)
- [任务进度说明](./01-task-progress.md)
- [机器可读任务进度](./task-progress.yaml)
- [架构与技术决策](./reference/architecture-and-decisions.md)
- [数据、事件与 API](./reference/data-events-api.md)

## AI 执行提示词

```text
你是本项目的 Agent Harness 后端执行 Agent。现在执行阶段 06：Planner 与 Executor。

必须先读取 docs/ai/00-execution-protocol.md、docs/ai/01-task-progress.md、docs/ai/task-progress.yaml、docs/ai/reference/architecture-and-decisions.md 和 docs/ai/reference/data-events-api.md。
只执行阶段 06，不进入阶段 07。
阶段开始前必须创建阶段分支，验证通过后 commit、push 并创建 PR。

执行内容：
1. 创建 app/agents/schemas.py，定义 PlanStep 和 ExecutionPlan。
2. 创建 app/agents/planner.py，生成结构化计划。
3. 开发闭环阶段使用 deterministic mock Planner。
4. 创建 app/agents/model_gateway.py，定义 OpenAI-compatible 统一接口，不接业务直接 SDK。
5. 创建 app/tools/registry.py，注册工具元数据和风险等级。
6. 创建 app/agents/react_engine.py，定义 Reason、Act、Observe 数据结构。
7. 创建 app/agents/executor.py，执行计划步骤。
8. POST /api/tasks/{task_id}/start 必须触发 PLAN_REQUESTED、PLAN_GENERATED、STEP_STARTED、STEP_COMPLETED、TASK_COMPLETED。
9. Planner 输出必须经 Pydantic 校验。
10. 校验失败写入 PLAN_REJECTED。
11. 创建测试覆盖 start task、plan generated、step events、task completed。
12. 更新 docs/ai/task-progress.yaml，把 stage-06-planner-executor 标记为 completed。

PR 与进度要求：
- 阶段分支必须推送到 origin。
- 阶段变更必须创建 Pull Request。
- branch、commit_sha、pr_url 写入 docs/ai/task-progress.yaml。
- 人读进度 docs/human/10-task-progress.md 必须同步更新。

验收标准：
- start task API 可执行。
- execution_plans 表写入 plan_json。
- task_steps 表写入步骤。
- 事件流包含计划和步骤事件。
- pytest 通过。
- task-progress.yaml 已更新。
```

## Required Plan Shape

```json
{
  "summary": "Analyze project and produce report",
  "steps": [
    {
      "key": "inspect_project",
      "description": "Inspect project structure",
      "execution_mode": "sync",
      "requires_sandbox": false,
      "can_spawn_subagent": false
    },
    {
      "key": "produce_report",
      "description": "Produce final report",
      "execution_mode": "sync",
      "requires_sandbox": false,
      "can_spawn_subagent": false
    }
  ]
}
```

## Required Events

```text
PLAN_REQUESTED
PLAN_GENERATED
STEP_STARTED
STEP_COMPLETED
TASK_COMPLETED
PLAN_REJECTED
STEP_FAILED
TASK_FAILED
```

## Verification Commands

```bash
cd services/api-server
python -m pytest
curl -X POST http://127.0.0.1:8000/api/tasks/{task_id}/start
curl http://127.0.0.1:8000/api/tasks/{task_id}/events
```

## Progress Update Rule

```yaml
stage-06-planner-executor:
  status: completed
  verification_result: passed
  next_stage: stage-07-react-console
```

