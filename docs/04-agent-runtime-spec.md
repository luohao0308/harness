# Agent Runtime Spec

## Planner

Planner receives the user goal, model settings, sandbox settings, and Agent identity. It outputs a versioned DAG with step keys, dependencies, execution mode, risk level, tool hints, expected artifacts, and acceptance criteria.

## Executor

Executor performs short synchronous steps with a ReAct loop:

```text
Thought -> Action -> Observation -> Step Result
```

Every model call, tool call, step transition, and final result is persisted.

## Subagent Orchestrator

Subagent Orchestrator handles long and parallel steps. The concurrency limit is 5 active Subagents per organization.

## Multi-Agent Orchestration

Named Agents route work by role:

- default
- researcher
- coder
- reviewer
- operator

The orchestration graph contains entry assignment, parallel branches, handoff edges, and reducer output.

## Required Controls

- timeout
- retry
- cancel
- pause
- resume
- state projection
- event replay
