# Stage 3: Agent Run Console

## Goal

Make the console the operational cockpit for Agent execution, not a static dashboard.

## Input

Agent sessions, tasks, plans, events, tool calls, guardrails, eval records, and observability summaries.

## Output

Dynamic console layout with chat, DAG, run status, trace, tools, guardrails, replay, eval, cost, and latency.

## Modules

React console, API client, SSE stream, Run Detail, Eval page, Settings pages.

## API And Schema Changes

No static data is accepted. Each displayed operational metric must come from an API.

## Event Types

Console timeline renders event types from `agent_events`.

## Frontend Display

```text
Left: Agent Chat / Task Input
Center: Plan DAG + Task Status
Right: Trace Timeline + Tool Calls + Guardrails
Bottom: Eval Result + Cost / Latency / Replay
```

## Tests

Build passes and browser smoke validates routes: `/agents/default/chat`, `/tasks`, `/tasks/{id}`, `/evals`, `/observability`.

## Acceptance

Changing backend state changes the frontend without code changes.

## Not Doing

Marketing landing pages are not part of the console.

## Vertical Slice Demo

```text
Create and run an Agent task
-> observe realtime events
-> save it as eval case
-> run eval
```
