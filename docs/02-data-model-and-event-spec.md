# Data Model And Event Spec

## Core Tables

- `tasks`: Agent Run root entity.
- `execution_plans`: Planner DAG versions.
- `task_steps`: concrete executable plan steps.
- `agent_runs`: Subagent runtime records.
- `agents`: named Agent definitions.
- `agent_assignments`: multi-agent work items.
- `agent_handoffs`: inter-agent handoff edges.
- `agent_events`: append-only task event stream.
- `task_snapshots`: replay checkpoints.
- `model_calls`: model call audit records.
- `tool_calls`: tool call audit records.
- `sandbox_instances`: sandbox lifecycle records.
- `warm_pool_containers`: prewarmed container inventory.
- `eval_datasets`: eval dataset registry.
- `eval_cases`: saved run or manual eval cases.
- `eval_runs`: eval execution batches.
- `eval_results`: per-case grader outputs.
- `admin_audit_events`: non-task administrative audit stream.
- `system_settings`: model, policy, and runtime settings.

## Required Event Types

Task and plan:

```text
TASK_CREATED, TASK_STARTED, TASK_PAUSED, TASK_RESUMED, TASK_CANCELLED,
TASK_FAILED, TASK_COMPLETED, PLAN_REQUESTED, PLAN_GENERATED, PLAN_UPDATED,
PLAN_REJECTED, STEP_STARTED, STEP_COMPLETED, STEP_FAILED, STEP_RETRIED, STEP_SKIPPED
```

Model and tool:

```text
MODEL_CALLED, MODEL_RESPONSE_RECEIVED, MODEL_CALL_FAILED, MODEL_FALLBACK_USED,
TOOL_CALLED, TOOL_RESULT_RECEIVED, TOOL_FAILED, TOOL_TIMEOUT, TOOL_DENIED_BY_POLICY
```

Agent orchestration:

```text
SUBAGENT_SPAWNED, SUBAGENT_STARTED, SUBAGENT_PROGRESS, SUBAGENT_COMPLETED,
SUBAGENT_FAILED, SUBAGENT_TIMEOUT, SUBAGENT_CANCELLED,
AGENT_SELECTED, AGENT_ASSIGNMENT_CREATED, AGENT_ASSIGNMENT_QUEUED,
AGENT_ASSIGNMENT_STARTED, AGENT_ASSIGNMENT_COMPLETED, AGENT_ASSIGNMENT_FAILED,
AGENT_HANDOFF_STARTED, AGENT_HANDOFF_COMPLETED, AGENT_PARALLEL_FANOUT_STARTED,
AGENT_PARALLEL_BRANCH_COMPLETED, AGENT_REDUCE_STARTED, AGENT_REDUCE_COMPLETED
```

Policy, sandbox, eval:

```text
SANDBOX_REQUESTED, SANDBOX_ALLOCATED, SANDBOX_REUSED_FROM_WARM_POOL,
SANDBOX_COMMAND_STARTED, SANDBOX_COMMAND_COMPLETED, SANDBOX_COMMAND_FAILED,
SANDBOX_RELEASED, SANDBOX_DESTROYED, POLICY_CHECKED, POLICY_DENIED,
EVAL_DATASET_CREATED, EVAL_CASE_CREATED, EVAL_RUN_STARTED, EVAL_CASE_GRADED,
EVAL_RUN_COMPLETED, EVAL_RUN_FAILED
```

## Tool Call Record

```json
{
  "tool_name": "string",
  "input": {},
  "output": {},
  "status": "REQUESTED|APPROVED|BLOCKED|SUCCESS|FAILED",
  "latency_ms": 0
}
```

## Eval Metrics

```json
{
  "task_success_rate": 0,
  "tool_selection_accuracy": 0,
  "policy_violation_rate": 0,
  "avg_latency_ms": 0,
  "avg_cost_usd": 0,
  "retry_rate": 0,
  "human_escalation_rate": 0
}
```
