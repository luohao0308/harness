# Stage 7: Private Deployable Harness Chain

## Goal

Close the private deployable Agent Harness chain with Agent Run-first evidence.

## Input

- Stage 01-06 completed platform slices.
- Agent Run APIs and compatibility task APIs.
- Docker/private deployment topology and observability stack.

## Output

- Canonical smoke script `scripts/smoke-test-agent-run.py`.
- Correlated evidence for `run_id` with task/replay/tool/sandbox/subagent/eval/observability.
- Stage progress records updated with pass/fail evidence.

## Modules

- Agent Run APIs (`/api/agents/{agent_id}/runs`, `/api/agents/runs/*`)
- Task compatibility APIs (`/api/tasks/*`) for replay/tool/subagent/event linkage
- Eval APIs
- Observability APIs

## API And Schema Changes

- No API contract expansion in this pass.
- Add Stage 07 canonical smoke script to validate existing contracts.

## Event Types

- Planning: `PLAN_REQUESTED`, `PLAN_GENERATED`
- Execution: `STEP_STARTED`, `STEP_COMPLETED`, `STEP_FAILED`
- Tool: `TOOL_CALLED`, `TOOL_RESULT_RECEIVED`, `TOOL_APPROVAL_REQUESTED`
- Sandbox/WarmPool: `SANDBOX_REQUESTED`, `SANDBOX_ALLOCATED`, `SANDBOX_REUSED_FROM_WARM_POOL`, `SANDBOX_RELEASED`
- Subagent: `SUBAGENT_SPAWNED`
- Eval: `EVAL_CASE_CREATED`, `EVAL_RUN_STARTED`, `EVAL_RUN_COMPLETED`

## Tests

- `python3 -m py_compile scripts/smoke-test-agent-run.py`
- `python3 scripts/smoke-test-agent-run.py`

## Acceptance

- Smoke script exits `0`.
- Evidence summary includes canonical `run_id`, compatibility `task_id`, `trace_id`, event/replay sequence, tool call id, sandbox id, subagent id, eval case/run id, warm-pool lifecycle marker.
- Missing required correlation exits non-zero.

## Current Status

- `completed`
- Canonical smoke passed on `2026-05-11T16:44:58Z`.
- Canonical Stage 07 smoke now starts from primary `POST /api/agents/default/runs`
  without Agent Workspace chat-stream fallback.
- Primary Agent Run planning now repairs invalid model plan output when possible and
  falls back to an auditable deterministic plan when repair output is still invalid.
- Evidence run:
  - `run_id`: `3a310efa-dcbd-4216-b78c-c49241e97245`
  - compatibility `task_id`: `3a310efa-dcbd-4216-b78c-c49241e97245`
  - `trace_id`: `7f988c30-0b40-4fc2-90a7-e21d014b23d7`
  - event/replay sequence: `25`
  - `tool_call_id`: `73238497-f794-4a2d-b050-4165645aaefd`
  - `sandbox_id`: `f37faf5a-076d-4a7a-a75e-5d13f86902ea`
  - warm-pool marker: `SANDBOX_ALLOCATED`
  - `subagent_id`: `d722d9b4-6cc9-4e96-b445-94f237dac6f5`
  - `eval_case_id`: `9cbffa92-e818-4554-9370-dc2e7db602e7`
  - `eval_run_id`: `dd10ffb5-4386-450f-b5a9-8bf7c367b2a5`

## Vertical Slice Demo

```text
Run scripts/smoke-test-agent-run.py
-> create canonical Agent Run
-> execute plan + runtime chain
-> collect correlated evidence summary
-> fail fast on missing links
```
