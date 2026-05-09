# Product Spec

## Summary

AI Harness Platform is a Production Agent Harness Platform for AI Harness Engineers and Agent Infrastructure Engineers. It is not a plain chatbot, not a generic task tracker, and not a static showcase console.

The product turns a configured model into a production Agent through Harness capabilities: model routing, prompt control, tool and MCP runtime, sandbox policy, planning, execution, event sourcing, replay, eval, observability, Workspace Pro conversation control, Artifacts preview, and WarmPool.

## Target Users

| User | Need |
|---|---|
| AI Harness Engineer | Build and debug production Agent infrastructure |
| Agent Infrastructure Engineer | Operate model, tool, sandbox, event, eval, and rollout systems |
| Platform Reviewer | Audit runs, inspect policy decisions, replay failures, compare versions |

## Core Product Structure

### Agent Studio

Users create and configure Agents.

Required surfaces:

- Model selection and provider configuration
- Built-in MiniMax model preset
- System Prompt management
- Tool and MCP connection selection
- Sandbox and permission profile selection
- RAG and template entries in disabled state until backed by API
- Agent version metadata

### Agent Workspace

Users operate an Agent through Workspace Pro, a three-column IDE-style console.

Required layout:

```text
Left:  Explorer: Model, MCP Tool Tray, context window, pinned messages, file bridge status
Center: Chat Console: conversation tree, stream pause, continue, edit and resend
Right: Artifacts and Runtime: previews, Plan DAG, Event Stream, Tool Cards, Approvals, Model Calls
```

The Workspace has exactly one user-facing mode: Plan-Act. Plan generation, streamed
conversation output, tool approval, and artifact preview live inside the same surface.
Execution, orchestration, replay, and eval saving remain Run/Harness capabilities shown
around the Run and in Run Detail.

Workspace Pro required behaviors:

- Conversation state is a tree, not a flat array.
- User edits on historical messages create new branches.
- Active path controls request context.
- Pinned messages are injected into every Workspace request.
- Context window control limits recent branch turns sent with a request.
- Streaming responses support pause and continue without deleting partial output.
- Planner trace and thought-like output render collapsed by default.
- Tool calls render as cards with input JSON, output JSON, risk, status, latency, and trace.
- Side-effect tools require Approve, Reject, or Modify before execution.
- Artifacts preview supports JSON, code, diff, chart, and text outputs.
- Token, cost, first-byte latency, and total duration render on messages and the metadata panel.

### Harness Management

Users manage the runtime layer behind Agents.

Required surfaces:

- Tool Registry
- MCP Adapter state
- Tool permissions
- Tool Tray entries for Workspace mention insertion
- Sandbox policy
- DAG and pipeline controls
- Trigger entries in disabled state until backed by API

### Observability

Users inspect and replay execution.

Required surfaces:

- Event Sourcing browser
- Replay to sequence
- Model and tool calls
- Token and cost tracking
- Latency and success metrics
- Service health and alert state

### Eval & Testing

Users evaluate Agent behavior.

Required surfaces:

- Dataset management
- Eval run execution
- Regression gate status
- Agent version comparison
- Human review queue entry
- Trace grader output

### Infra

Users operate platform infrastructure.

Required surfaces:

- WarmPool status and benchmark
- Sandbox list and lifecycle
- Tenant boundary indicators
- API Gateway documentation entry
- Version and rollout state

## Primary User Journey

```text
Open Agent Studio
-> choose Agent and model
-> open Agent Workspace
-> enter goal in Chat Console
-> stream Plan-Act progress
-> create Agent Run with Plan DAG and artifact preview
-> inspect execution readiness, policy, tools, approvals, metadata, and Subagent projections
-> Event Store records every change
-> right panel shows Artifacts, live trace, tool cards, and model calls
-> user opens Run Detail to execute, replay, or save it as an Eval Case
-> Eval Harness grades regression behavior
```

## Product Rules

- `Agent Run` is the user-facing execution object.
- `Task` appears only as internal database compatibility language.
- MiniMax is the default built-in model preset.
- Console data comes from backend APIs.
- Unsupported future modules render disabled entries with backend-backed readiness state.
- Website remains as public information shell and does not define console product behavior.
- Workspace Pro UI state does not replace Event Store, Agent Run, or ToolCall audit records.
