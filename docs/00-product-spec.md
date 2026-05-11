# Product Spec

## Summary

AI Harness Platform is a Production Agent Harness Platform for AI Harness Engineers and Agent Infrastructure Engineers. It is not a plain chatbot, not a generic task tracker, and not a static showcase console.

This is a living product reference, not a component lock. Equivalent UI decomposition is acceptable when the user-visible behavior, traceability, and audit records stay intact.

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

Reference surfaces:

- Model selection and provider configuration
- Built-in MiniMax model preset
- System Prompt management
- Tool and MCP connection selection
- Sandbox and permission profile selection
- RAG and template entries in disabled state until backed by API
- Agent version metadata

### Agent Workspace

Users operate an Agent through Workspace Pro, a chat-first workspace that can surface context, tools, artifacts, and run state without locking the UI to a single panel layout.

Reference layout:

```text
Workspace Pro may organize its surface around context, chat, and runtime views.
One valid shape is a left/context region, a central conversation region, and a right/runtime region.
```

The Workspace can center on auditable planning and execution behavior. Planning, streamed conversation output, tool approval, and artifact preview may share the same screen or be split across coordinated views as long as the run remains traceable. Execution, orchestration, replay, and eval saving remain Run/Harness capabilities shown around the Run and in Run Detail.

Workspace mode semantics are explicit:

- `chat` is the default conversational mode.
- `markdown_plan` is the user-facing planning mode for markdown plan output.
- `plan` is the explicit Plan-Act execution mode and should not be conflated with `markdown_plan`.

Workspace Pro reference behaviors:

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

Reference surfaces:

- Tool Registry
- MCP Adapter state
- Tool permissions
- Tool Tray entries for Workspace mention insertion
- Sandbox policy
- DAG and pipeline controls
- Trigger entries in disabled state until backed by API

### Observability

Users inspect and replay execution.

Reference surfaces:

- Event Sourcing browser
- Replay to sequence
- Model and tool calls
- Token and cost tracking
- Latency and success metrics
- Service health and alert state

### Eval & Testing

Users evaluate Agent behavior.

Reference surfaces:

- Dataset management
- Eval run execution
- Regression gate status
- Agent version comparison
- Human review queue entry
- Trace grader output

### Infra

Users operate platform infrastructure.

Reference surfaces:

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
-> stream chat or markdown_plan output
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
