# Portfolio Demo Guide

## Positioning

This demo presents AI Harness as a Production Agent Harness Platform for creating, running, observing, constraining, recovering, and evaluating AI Agents.

## Demo Scenario

```text
GitHub Issue
-> Agent Workspace input
-> Planner generates DAG
-> Multi-Agent orchestration fans out assignments
-> Executor runs synchronous steps
-> Subagent handles long running work
-> Tool Runtime records tool calls
-> Guardrail routes high risk calls to approval
-> Event Sourcing records the full trace
-> Replay inspects a sequence
-> Eval Harness saves the run as a regression case
-> WarmPool Benchmark proves reserve latency
```

## Local URLs

```text
Console: http://127.0.0.1:5173
API: http://127.0.0.1:8000
OpenAPI: http://127.0.0.1:8000/openapi.json
Metrics: http://127.0.0.1:8000/metrics
```

## Demo Steps

1. Open `/agents` and select the default Agent.
2. Open Chat, enter a GitHub issue style goal, then use Plan mode.
3. Confirm the plan and execute the Agent Run.
4. Open the Run Detail page and show Plan DAG, Event Timeline, Subagents, Multi-Agent topology, Guardrails, Tool Calls, Context Router, Replay, and Eval Regression.
5. Trigger Route Context and point to `CONTEXT_COMPRESSED` plus `MODEL_ROUTED` events.
6. Save the successful Run as an Eval Case and run the Dataset Eval.
7. Open `/tools` and show builtin plus MCP-shaped tools from one registry.
8. Open `/sandboxes` and run WarmPool Benchmark.
9. Open `/observability` and show backend-driven runtime totals.

## Evidence To Show

```text
Backend tests: 123 passed
Frontend tests: 30 files / 148 tests passed
Frontend build: passed
Docs validation: passed
Diff whitespace check: passed
OpenAPI export: docs/contracts/api/openapi.yaml and docs/contracts/api/openapi.json
```

## Demo Narrative

The user sees one Agent Run Console, while the system underneath provides planner, executor, subagents, multi-agent orchestration, tool runtime, guardrails, event sourcing, replay, eval, context routing, and WarmPool benchmarking.
