# AI Harness Engineer Capability Map

## Target Role

AI Harness Engineer / Agent Infrastructure Engineer.

## Capability Evidence

| Capability | Project Evidence |
|---|---|
| Agent runtime architecture | Planner, Executor, ReAct trace, Subagent runtime, Multi-Agent orchestration |
| Harness Engineering | Event Sourcing, Replay, Guardrails, Eval Harness, Tool Runtime, WarmPool |
| Safety isolation | Docker Sandbox, policy settings, network control, tool approval |
| Observability | Event timeline, model calls, tool calls, logs, metrics, traces, exports |
| Recovery | task snapshots, replay, step resume, subagent recovery |
| Eval | datasets, cases, eval runs, trace grader, metrics |
| Model operations | model settings, fallback events, health checks, Context Router |
| Performance | WarmPool status, reserve path benchmark, cold baseline |
| API design | FastAPI, Pydantic schemas, OpenAPI JSON/YAML export |
| Frontend operations console | Agent Workspace, Run Detail, Eval page, Tools page, Sandboxes page, Observability page |

## Interview Narrative

```text
I did not build a chatbot.
I built the harness around Agents:
planning, execution, isolation, approval, audit, replay, eval, routing, and benchmark.
```

## Proof Points

```text
Backend test suite: 123 passed
Frontend production build: passed
Docs validation: passed
OpenAPI export: generated from FastAPI app
```
