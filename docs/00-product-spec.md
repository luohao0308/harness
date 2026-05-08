# Product Spec

## Product Positioning

AI Harness is a Production Agent Harness Platform. It creates, runs, observes, constrains, recovers, replays, and evaluates AI Agents.

It is not a normal chatbot. The chat surface is the Agent Run Console entry point. The product value is the execution infrastructure behind each run: task decomposition, async execution, event sourcing, tool policy, trace, replay, eval, memory, model routing, and WarmPool performance.

## Target User

The primary user is an AI Harness Engineer or Agent Infrastructure Engineer building production Agent systems that must be auditable, recoverable, policy-controlled, and regression-tested.

## Core Scenario

```text
User opens Agent Run Console
-> enters a natural-language task
-> Agent clarifies or creates a plan
-> Planner produces a DAG
-> Executor runs short ReAct steps
-> Subagent Orchestrator runs long and parallel work
-> Tool Runtime executes approved tools in policy-controlled sandboxes
-> Event Store records every state transition
-> Console shows plan, trace, tool calls, guardrails, cost, latency
-> User saves a run as an Eval Case
-> Eval Harness runs regression grading and reports metrics
-> Replay reconstructs the run from events
```

## Core Modules

- Agent Run Console
- Planner
- Executor
- Subagent Orchestrator
- Event Sourcing
- Tool / MCP Runtime
- Guardrail / Policy Engine
- Eval Harness
- Memory / Context / Model Router
- WarmPool

## Product Non-Negotiables

- Every stage ships a runnable vertical slice.
- Backend dynamic state drives frontend views.
- Every operation that changes run state writes an event or audit record.
- Eval Harness is a first-class product module.
- PostgreSQL is the production database path.
- Static showcase pages are removed from the product console.
