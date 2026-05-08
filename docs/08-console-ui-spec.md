# Console UI Spec

## Layout

```text
Left: Agent Chat / Task Input
Center: Plan DAG + Task Status
Right: Trace Timeline + Tool Calls + Guardrails
Bottom: Eval Result + Cost / Latency / Replay
```

## Required Console Pages

- Agent Workspace
- Agents Registry
- Runs
- Run Detail
- Subagents
- Sandboxes
- Observability
- Eval Harness
- Policy Settings
- Model Settings

## UI Rules

- Console pages display backend state.
- Static KPI cards are removed.
- Placeholder pages are removed from routes.
- The first screen is the usable Agent Console, not a landing page.
- Eval Harness must show datasets, cases, runs, metrics, and grader traces.
