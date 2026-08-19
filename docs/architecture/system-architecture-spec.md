# System Architecture

## Architecture Summary

Forge Harness is a control plane and runtime for production Agents.

```text
Agent Studio
-> Agent configuration
-> Agent Workspace
-> Conversation Tree / Context Controls
-> Agent Run
-> Planner
-> Executor / Subagent / Multi-Agent Orchestrator
-> Tool / MCP Runtime
-> Guardrail / Sandbox / WarmPool
-> Event Store
-> Projections
-> Observability / Replay / Eval
```

## Architecture Direction

The active project direction is not a generic chat UI. The product target is:

```text
Model + Harness = Agent
```

The Harness proves and productizes the full execution chain: Agent configuration, Workspace goal intake, Agent Run, planning, execution, tools/MCP, sandbox isolation, subagents, event audit, replay, eval, observability, and private deployment.

```mermaid
flowchart TD
  A["Forge Harness"] --> B["Product Target: Model + Harness = Agent"]

  B --> C["Agent Console"]
  B --> D["FastAPI Backend"]
  B --> E["Harness Runtime"]
  B --> F["Private Deployment"]

  C --> C1["Agent Workspace"]
  C --> C2["Agent Studio"]
  C --> C3["Run Detail"]
  C --> C4["Eval / Observability / Tools / Sandboxes"]

  D --> D1["Agent Run API"]
  D --> D2["Model Gateway"]
  D --> D3["Event Store"]
  D --> D4["Eval Dataset / Regression"]
  D --> D5["Settings / Config"]

  E --> E1["Planner"]
  E --> E2["Executor"]
  E --> E3["Tool / MCP Calls"]
  E --> E4["Sandbox / WarmPool"]
  E --> E5["Subagents"]
  E --> E6["Replay / Diagnosis"]

  F --> F1["Docker Compose"]
  F --> F2["Env Examples"]
  F --> F3["Runbooks"]
  F --> F4["Smoke / Validation Scripts"]
  F --> F5["Lightweight Diagnostics"]

  C1 --> D1
  C2 --> D5
  D1 --> E1
  E1 --> E2
  E2 --> E3
  E2 --> E4
  E2 --> E5
  E3 --> D3
  E4 --> D3
  E5 --> D3
  D3 --> C3
  C3 --> E6
  C3 --> D4
  D4 --> C4
  D3 --> C4

  F1 --> D
  F1 --> C
  F4 --> D1
  F4 --> C3
```

## Stage And Productization Flow

Stage 07 is closed historical context. It proved the private-deployable Harness chain. Current post-stage work should harden, package, and make that chain easier to operate without reopening Stage 07 as active product scope.

```mermaid
flowchart LR
  S1["Stage 01-06<br/>Core Platform Surfaces"] --> S7["Stage 07<br/>Private Deployable Harness Chain"]
  S7 --> H1["Post-stage Hardening<br/>Workspace Browser Smoke"]
  H1 --> H2["Complete Harness Validation Flow"]
  H2 --> H3["Navigation Resilience"]
  H3 --> H4["L3 Live Browser Validation"]
  H4 --> H5["Release Gate + Handoff Hygiene"]
  H5 --> H6["Private Deployment Experience"]

  S7 -. "closed historical context" .-> Guard["Do not reopen Stage 07"]
  H6 --> Goal["Docker Compose full chain starts<br/>Agent Run smoke passes"]
```

## Private Deployment Experience Lane

This completed productization lane is a private deployment handoff package for a Docker-literate internal tester who does not already know this repository. The first-pass acceptance signal is concrete: Docker Compose starts the full chain and the Agent Run smoke passes.

```mermaid
flowchart TD
  P["Private Deployment Experience"] --> U["Target User:<br/>Docker-literate non-core engineer"]

  P --> Pack["Product-like Handoff Package"]
  Pack --> Env[".env.example alignment"]
  Pack --> Compose["Docker Compose startup path"]
  Pack --> Runbook["Private deploy runbook"]
  Pack --> Validate["Validation scripts"]
  Pack --> Diagnose["Lightweight diagnostics"]

  Validate --> V1["docker compose config"]
  Validate --> V2["API health"]
  Validate --> V3["Agent Run smoke"]
  Validate --> V4["Frontend/docs checks"]

  Diagnose --> D1["Docker unavailable"]
  Diagnose --> D2["Port conflicts"]
  Diagnose --> D3["DB connectivity"]
  Diagnose --> D4["Console API base URL"]
  Diagnose --> D5["Model key / mock fallback"]

  P --> NonGoals["Non-goals"]
  NonGoals --> NG1["No Kubernetes"]
  NonGoals --> NG2["No full RBAC/security model"]
  NonGoals --> NG3["No installer framework"]
  NonGoals --> NG4["No cloud deployment matrix"]
  NonGoals --> NG5["No full ops platform"]
```

## Services

| Service | Boundary |
|---|---|
| `agent-console` | React console for Studio, Workspace, Runs, Tools, Observability, Eval, Sandboxes, Settings |
| `api-server` | FastAPI control plane for Agents, Runs, Events, Tools, Policies, Evals, Settings |
| `assignment-worker` | Async multi-Agent assignment execution |
| `subagent-worker` | Async Subagent execution and recovery |
| `warm-pool-service` | Sandbox prewarm and lifecycle management |
| `postgres` | Durable state, append-only events, audit, settings, eval records |
| `redis` | Queue and coordination layer |
| `prometheus/grafana/loki` | Metrics, dashboards, logs |
| `web-site` | Public information shell retained outside console core |

## API Boundary

Primary product API uses Agent and Run semantics.

| API | Purpose |
|---|---|
| `POST /api/agents/{agent_id}/runs` | Create an Agent Run from Workspace |
| `POST /api/agents/{agent_id}/runs/chat/stream` | Stream Workspace Pro output |
| `GET /api/agents/runs` | List Agent Run history |
| `GET /api/agents/runs/{run_id}/workspace` | Aggregate Workspace projection |
| `POST /api/agents/runs/{run_id}/execute` | Execute existing Plan |
| `POST /api/agents/runs/{run_id}/orchestrate` | Create multi-Agent assignments |
| `POST /api/agents/runs/{run_id}/orchestrate/execute` | Execute assignments and reduce |

Legacy `/api/tasks/*` endpoints remain internal compatibility until migration completes. OpenAPI descriptions mark them as compatibility surfaces rather than the product entry.

## State Machines

### Conversation Node

```text
draft -> streaming -> done
                  -> paused -> streaming -> done
                  -> error
```

Historical edit creates a new child branch under the edited node parent. The previous
branch stays addressable through its leaf node.

### Agent Run

```text
CREATED -> PLANNING -> PLANNED -> RUNNING -> COMPLETED
                                      -> FAILED
                                      -> CANCELLED
PLANNED -> WAITING_APPROVAL -> RUNNING
FAILED -> RUNNING
```

### Subagent

```text
PENDING -> QUEUED -> RUNNING -> SUCCESS
                            -> FAILED
                            -> TIMEOUT
                            -> CANCELLED
```

### Assignment

```text
PENDING -> QUEUED -> RUNNING -> SUCCESS
                            -> FAILED
```

### Tool Call

```text
REQUESTED -> APPROVED -> RUNNING -> SUCCESS
          -> BLOCKED
          -> PENDING_APPROVAL -> APPROVED -> RUNNING -> SUCCESS
                              -> MODIFIED -> APPROVED -> RUNNING -> SUCCESS
                              -> REJECTED
          -> FAILED
          -> TIMEOUT
```

## Event Sourcing

Every meaningful state transition appends an event.

Required event categories:

- Run lifecycle
- Plan requested/generated/rejected
- Step started/completed/failed
- Model called/response/failure
- Tool policy checked/called/result/failed/approval
- Workspace stream delta, usage, artifact, and tool preview events when persisted
- Subagent spawned/heartbeat/success/failure/timeout
- Assignment selected/created/started/completed/failed/reduced
- Sandbox requested/allocated/released/destroyed
- Eval case/run/grader result
- Replay and recovery actions

Projection APIs read current SQL state plus event history. Replay reconstructs Run state to a sequence number.

## Runtime Execution

- Planner emits Plan DAG and does not execute tools.
- Workspace Pro streams workspace output over SSE and creates durable Agent Runs.
- Conversation Tree, active path, pinned nodes, and context window assemble request context.
- Executor runs short synchronous ReAct steps.
- Subagent handles long-running async branches.
- Multi-Agent Orchestrator assigns branches to named Agents and performs reduce.
- Tool Runner enforces registry, permissions, policy, sandbox, approval, audit, and trace.
- Tool Approval supports approve, reject, and modify-input approval decisions.
- WarmPool supplies sandbox instances for low-latency execution.

## Frontend State

Workspace Pro keeps UI-only conversation graph state in Zustand:

```text
nodesById
rootNodeId
activeLeafId
pinnedNodeIds
contextWindowTurns
activeStream
```

This state drives branch navigation and request assembly. Durable execution truth remains in
Agent Run, Event Store, ModelCall, ToolCall, ToolApproval, and Artifact projections.

## Frontend Data Rule

Frontend pages call API projections. No console metric or run status may be hard-coded. Disabled future modules must be visibly disabled and must not fabricate data.
