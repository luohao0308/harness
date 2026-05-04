# End-To-End Demo Script

本文件定义标准端到端演示任务。该剧本用于产品演示、回归测试和 AI 执行验收。

## Demo Goal

```text
Analyze the current Python project, inspect structure, run tests in sandbox, identify failures, spawn a Subagent for dependency review, recover from an interrupted run, and produce a final report.
```

## Preconditions

```text
API Server running
PostgreSQL running
Redis running
Dramatiq worker running
Docker Engine running
WarmPool initialized
Agent Console running
```

## Step 1: Create Task

API:

```bash
curl -X POST http://127.0.0.1:8000/api/tasks \
  -H "Content-Type: application/json" \
  -d '{"title":"Repository analysis demo","goal":"Analyze the current Python project, run tests, review dependencies, and produce a final report.","model_provider":"openai-compatible","model_name":"default","max_runtime_seconds":1800,"max_subagents":5,"enable_sandbox":true,"enable_network":false}'
```

Expected events:

```text
TASK_CREATED
```

Console:

```text
Task appears in /tasks with CREATED status.
```

## Step 2: Start Task

API:

```bash
curl -X POST http://127.0.0.1:8000/api/tasks/{task_id}/start
```

Expected events:

```text
TASK_STARTED
PLAN_REQUESTED
PLAN_GENERATED
STEP_STARTED
```

Console:

```text
Task detail shows execution plan.
Event timeline starts streaming.
```

## Step 3: Planner Output

Expected plan steps:

```text
inspect_project
read_test_config
run_tests
dependency_review
produce_report
```

Expected data:

```text
execution_plans row created
task_steps rows created
PLAN_GENERATED payload includes plan summary
```

## Step 4: Executor Runs Inspection

Expected events:

```text
STEP_STARTED
TOOL_CALLED
TOOL_RESULT_RECEIVED
STEP_COMPLETED
```

Console:

```text
ExecutionPlanPanel marks inspect_project completed.
EventTimeline shows list_files and read_file calls.
```

## Step 5: Sandbox Runs Tests

Expected events:

```text
SANDBOX_REQUESTED
SANDBOX_ALLOCATED
SANDBOX_COMMAND_STARTED
TOOL_CALLED
TOOL_RESULT_RECEIVED
SANDBOX_COMMAND_COMPLETED
SANDBOX_RELEASED
STEP_COMPLETED
```

Console:

```text
SandboxPanel shows container status.
WarmPool reuse appears when container came from WarmPool.
```

## Step 6: Spawn Subagent

Expected events:

```text
SUBAGENT_SPAWNED
SUBAGENT_STARTED
SUBAGENT_PROGRESS
SUBAGENT_COMPLETED
```

Console:

```text
SubagentPanel shows PENDING, RUNNING, SUCCESS transitions.
```

## Step 7: Simulate Recovery

Action:

```text
Stop worker during run_tests step.
Restart worker.
Call POST /api/tasks/{task_id}/resume.
```

Expected events:

```text
TASK_RESUMED
```

Expected behavior:

```text
Completed steps remain completed.
Execution resumes from last stable unfinished step.
Timed-out Subagents are marked TIMEOUT.
Lost Sandbox instances are replaced.
```

## Step 8: Final Report

Expected events:

```text
STEP_COMPLETED
TASK_COMPLETED
```

Expected result:

```json
{
  "summary": "Project inspected, tests executed in sandbox, dependency review completed.",
  "findings": [],
  "artifacts": []
}
```

Console:

```text
Task status is COMPLETED.
TaskResultPanel shows final report.
EventTimeline contains full audit trail.
```

## Acceptance Criteria

```text
Task created
Plan generated
Events streamed to console
Sandbox command executed
Subagent completed
Recovery path executed
Final report generated
Audit trail complete
Metrics visible
Logs queryable by task_id
```

