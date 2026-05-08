# System Architecture

## Service Boundaries

- `agent-console`: React console for Agent runs, DAG status, trace, tools, guardrails, evals, settings, and operations.
- `api-server`: FastAPI control plane for agents, tasks, events, tools, policies, evals, observability, and settings.
- `assignment-worker`: async multi-agent assignment executor.
- `subagent-worker`: async Subagent executor.
- `warm-pool-service`: sandbox prewarm and cleanup service.
- `postgres`: durable relational store for state, events, audit, evals, and settings.
- `redis`: queue and coordination layer.
- `prometheus/grafana`: metrics and dashboard surface.

## Runtime Flow

```text
Agent Run Console
-> /api/agents/plan
-> Planner creates ExecutionPlan DAG
-> /api/agents/runs/{run_id}/execute or /orchestrate
-> Executor handles sync ReAct steps
-> Assignment/Subagent workers handle async branches
-> Tool Runtime checks policy and executes tools
-> EventStore appends events
-> Console reads REST + SSE projections
-> Eval Harness saves and grades traces
```

## State Machines

Task:

```text
CREATED -> PLANNING -> PLANNED -> RUNNING -> WAITING_SUBAGENTS -> COMPLETED
                                         -> FAILED
                                         -> CANCELLED
FAILED/CANCELLED -> RUNNING
```

Subagent:

```text
PENDING -> QUEUED -> RUNNING -> SUCCESS
                            -> FAILED
                            -> TIMEOUT
                            -> CANCELLED
```

Eval Run:

```text
PENDING -> RUNNING -> COMPLETED
                   -> FAILED
```

## Realtime Communication

- SSE streams task events from `/api/tasks/{task_id}/events/stream`.
- Polling backs list-level operational dashboards.
- WebSocket is reserved for Stage 3 if bidirectional approvals require it.

## Approval Flow

```text
Tool call requested
-> Tool policy evaluates risk
-> low risk executes
-> high risk writes approval request
-> human approves or blocks
-> runtime writes tool status and event
```

## Recovery And Replay

- Event streams are append-only per task.
- Task snapshots are created after fixed event intervals.
- Replay reconstructs state to the requested sequence.
- Recovery resumes failed or stale work from replayed state.
