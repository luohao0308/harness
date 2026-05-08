# Stage 1: Agent Graph Runtime

## Goal

Deliver the Agent runtime loop: user task input, Planner DAG, Executor sync work, Subagent async work, multi-agent assignments, and frontend status display.

## Input

- User natural-language goal
- Agent identity
- Model settings
- Sandbox settings

## Output

- Task Run
- ExecutionPlan DAG
- TaskStep records
- Assignment/Subagent records
- Event stream
- Console-visible status

## Modules

Planner, Executor, ReAct Engine, Subagent Orchestrator, Agent Registry, Agent Run Console.

## API And Schema Changes

Use `/api/agents/plan`, `/api/agents/auto`, `/api/agents/runs/{run_id}/execute`, `/api/agents/runs/{run_id}/orchestrate`, `/api/tasks/{task_id}/plan`, `/api/tasks/{task_id}/events`.

## Event Types

`TASK_CREATED`, `PLAN_REQUESTED`, `PLAN_GENERATED`, `TASK_STARTED`, `STEP_STARTED`, `STEP_COMPLETED`, `SUBAGENT_SPAWNED`, `AGENT_ASSIGNMENT_CREATED`, `AGENT_REDUCE_COMPLETED`, `TASK_COMPLETED`.

## Frontend Display

Agent Workspace shows chat input, plan output, execute controls, orchestration controls, and run status. Run Detail shows plan, assignments, subagents, handoffs, reducer output, and timeline.

## Tests

Backend tests cover plan-only, execute existing plan, orchestration creation, assignment worker execution, and event persistence.

## Acceptance

A user can create a run from Agent Chat, generate a plan, execute it, fan out to agents, and inspect state changes in the console.

## Not Doing

Full Eval Harness, full MCP adapter, and full budget guardrails are out of this stage.

## Vertical Slice Demo

```text
Open /agents/default/chat
-> enter task
-> click Plan
-> click Run
-> inspect /tasks/{run_id}
```
