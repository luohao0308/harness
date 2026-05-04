# 02 Planner 与 Executor

## 目标

Planner 把用户目标拆成结构化计划。Executor 按计划执行步骤，并通过 ReAct 循环驱动工具、模型和 Subagent。

## 使用入口

| 入口 | 动作 |
|---|---|
| `/tasks/new` | 输入目标、模型、策略和沙箱约束 |
| `/tasks/:taskId` | 查看执行计划和步骤状态 |

## 后端模块

```text
services/api-server/app/agents/planner.py
services/api-server/app/agents/executor.py
services/api-server/app/agents/react_engine.py
services/api-server/app/agents/model_gateway.py
services/api-server/app/tools/registry.py
```

## 执行结构

```text
User Goal
-> Planner
-> execution_plans
-> task_steps
-> Executor
-> Reason / Act / Observe
-> Tool / Model / Subagent
-> Event Store
-> Result
```

## 事件与数据

| 事件 | 含义 |
|---|---|
| `PLAN_REQUESTED` | 请求生成计划 |
| `PLAN_GENERATED` | 计划生成完成 |
| `STEP_STARTED` | 步骤开始 |
| `STEP_COMPLETED` | 步骤完成 |
| `STEP_FAILED` | 步骤失败 |

## 联动

- Planner 决定步骤是否需要 Sandbox。
- Planner 决定步骤是否允许派生 Subagent。
- Executor 执行每个步骤并写入事件。
- Executor 调用 Tool Registry 和 Policy Engine。
- Executor 结束后写入任务结果。

## 验收

- 每个任务有结构化计划。
- 每个步骤有稳定 key 和状态。
- 工具动作不绕过 Tool Registry。
- 高风险动作不绕过 Sandbox。
- 事件流能还原执行顺序。
