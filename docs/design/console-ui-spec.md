# Console UI Spec

## Product Frame

The console is the Forge Harness workspace, not a task management app. Its top-level navigation groups Agent construction, Agent usage, Harness management, Observability, Eval, and Infra.
This document is a current reference, not a frozen component contract. Equivalent panel decomposition is acceptable if the same behavior and data coverage remain visible.

## Reference Routes

| Route | Page | Status |
|---|---|---|
| `/agents` | Agent Studio registry | Active |
| `/agents/:agentId/workspace` | Agent Workspace Pro | Active |
| `/runs` | Agent Run history | Active |
| `/runs/:runId` | Agent Run detail | Active |
| `/settings/models` | Model settings with DeepSeek presets | Active |
| `/tools` | Tool and MCP registry | Active |
| `/observability` | Event, latency, cost, health | Active |
| `/evals` | Eval Harness | Active |
| `/sandboxes` | Sandbox and WarmPool | Active |
| `/subagents` | Subagent monitor | Active |

`/tasks/new` is not part of the primary product routes. `/tasks` redirects to `/runs` during compatibility migration.

## Agent Workspace Pro Layout

```text
┌──────────────┬────────────────────────────┬──────────────────────┐
│ Explorer     │ Chat Console                │ Artifacts / Runtime  │
│              │                            │                      │
│ Model        │ Conversation Tree          │ Metadata             │
│ Tool Tray    │ Streamed assistant output   │ Artifacts Preview    │
│ Context      │ Pause / Continue           │ Plan DAG             │
│ Pinned       │ Edit and Resend            │ Tool Cards           │
│ Files        │ @ tool mentions            │ Approvals            │
│              │                            │ Model Calls          │
└──────────────┴────────────────────────────┴──────────────────────┘
```

This layout is a reference composition, not a component lock.


## Workspace Pro Integration Decisions

Workspace Pro upgrades the existing `/agents/:agentId/workspace` route. It is not a new product and it does not move the console to a new framework.

| Requirement | Current project base | Decision |
|---|---|---|
| Chat-first workspace surface | Existing Agent Workspace route | Upgrade in place |
| Client state | Zustand already present | Extend with conversation graph store |
| Styling and icons | Tailwind and Lucide already present | Continue current stack |
| UI primitives | Local UI components already present | Keep local component style; no forced shadcn adoption |
| Charts | ECharts already present | Use ECharts for chart artifacts |
| Streaming | FastAPI and SSE already present | Reuse SSE and Model Gateway; no Vercel AI SDK core dependency |
| Tool runtime | Tool Registry, MCP Adapter, ToolCall audit | Surface through Tool Tray and Tool Cards |
| Tool approval | Existing approval model | Add Modify input approval and resumable Run UX |
| Artifacts | Artifact-shaped data exists | Add right-side preview panel as first-class surface |
| Token and latency | ModelCall records tokens and duration | Render per-message and run metadata |

## Workspace Mode Semantics

- `chat` is the default mode for normal conversation.
- `markdown_plan` is the visible planning mode and should return markdown plan text only.
- `plan` is the explicit Plan-Act mode and should remain separate from `markdown_plan`.

## Context Assembly

The request context is assembled from three sets:

1. Active path nodes from root to `activeLeafId`.
2. Pinned nodes listed in `pinnedNodeIds`.
3. Recent turns from the active path limited by `contextWindowTurns`.

Before sending a request, the left Explorer shows the context preview: message count, pinned count, estimated tokens, and compression state. Pinned nodes are expected to remain in the request payload.

## Stream Control

Pause uses `AbortController` on the client stream. A paused assistant node keeps partial content and changes state to `paused`. Continue sends `continue_from_node_id`, `partial_assistant_content`, current active path, and pinned messages. Pause never deletes streamed content.

## Public Frontend Types

```ts
type ConversationNode = {
  id: string;
  parent_id: string | null;
  children_ids: string[];
  role: "user" | "assistant" | "system" | "tool";
  content: string;
  state: "draft" | "streaming" | "paused" | "done" | "error";
  run_id?: string;
  metadata: {
    input_tokens?: number;
    output_tokens?: number;
    cost_usd?: string;
    ttfb_ms?: number;
    duration_ms?: number;
  };
  tool_calls: unknown[];
  artifacts: unknown[];
};
```

## Left Column

Shows Explorer state:

- Active model provider and model name
- DeepSeek built-in preset state
- Tool Tray from API registry
- MCP-shaped tools with source labels
- Context window slider
- Estimated context message count and tokens
- Pinned messages
- File bridge state through Tool Runtime and Sandbox

## Center Column

Shows Chat Console:

- Conversation graph active path
- User and assistant messages
- Streamed assistant output
- Pause through `AbortController`
- Continue from paused assistant output
- Edit and Resend for historical user messages
- Collapsed Planner trace and thought-like blocks
- `@` tool mention menu backed by Tool Registry

Workspace Pro can omit Chat, Execute, or Auto tabs from the primary experience. The main surface creates an Agent Run and streams assistant output. Run execution, orchestration, replay, and eval saving remain Run/Harness actions outside the default chat experience.

## Right Column

Shows Artifacts and Runtime internals:

- Message and Run metadata: input tokens, output tokens, cost, first-byte latency, duration
- Artifacts Preview for JSON, code, diff, chart, and text
- Plan DAG and step state
- Event Stream ordered by sequence
- Subagent state
- Tool Calls with input, output, status, latency
- Tool Calling Cards with JSON input and output
- Tool approvals with approve, reject, and modify actions for admin
- Model Calls with provider, model, token, latency, status
- Replay entry for selected Run

The named panels above are current reference surfaces; if a later implementation uses different component names or grouping, it only needs to preserve the same user-visible behavior and traceability.

## Conversation Tree

Conversation state is a tree:

- Each node has id, parent id, children ids, role, content, state, run id, metadata, tool calls, and artifacts.
- Editing a historical message creates a branch from that message parent.
- The active leaf defines the visible path.
- Pinned nodes join the request context even when outside the recent turn window.
- Paused assistant nodes keep partial content and resume through Continue.

## Artifacts

Artifacts render in the right panel:

- `json` renders formatted JSON.
- `code` renders in a code preview surface.
- `diff` renders as a diff preview surface.
- `chart` renders through the chart runtime.
- `text` renders as plain preview.

Artifact content comes from stream events, plan JSON, tool results, and subagent outputs.


## Delivery Phases

### P0 Workspace Pro Base

- Conversation Tree Store
- Abort and Continue
- Edit and Resend branching
- SSE usage, first-byte latency, and duration display
- Initial Artifacts panel
- Initial Tool Card view

### P1 Human-in-the-loop

- Approve, Reject, and Modify
- Stream pause while side-effect tool approval is pending
- Run resume after approval decision
- `@` tool and context menu

### P2 Context and Memory UX

- Recent turns slider
- Pin message injection
- Context Preview
- Alignment with `RunContextRouter`

### P3 Advanced Preview

- Enhanced diff comparison
- Lazy loading for large artifacts
- Chart artifact rendering through ECharts
- File tree and local file bridge through Tool Runtime

## Workspace Pro Test Plan

Frontend checks:

- Editing a historical message creates a new branch and keeps the old branch.
- Abort changes the assistant node to `paused`; Continue resumes from partial content.
- Pinned messages are present in every stream request payload.
- Context slider changes the active-path messages sent to the API.
- Tool Cards render pending, approved, rejected, success, and failed states.
- Artifacts panel renders code, JSON, and diff preview types.

Backend checks:

- Chat stream emits standard SSE events.
- Usage events persist ModelCall metadata and return to the frontend.
- Side-effect tool calls create approvals before execution.
- Modify approval executes with modified input JSON.
- Continue request links to original `run_id` and branch id.
- OpenAPI and docs validation pass.

Regression commands:

```bash
services/api-server/.venv/bin/python -m pytest services/api-server/tests
services/api-server/.venv/bin/python -m ruff check services/api-server/app services/api-server/tests
cd apps/agent-console && npm run build
python3 scripts/validate-docs.py
```

## Run History

`/runs` displays Agent Run audit history. It should use `GET /api/agents/runs` and observability summary APIs. It should not show fake KPI cards.

## Run Detail

`/runs/:runId` uses `GET /api/agents/runs/{run_id}/workspace` as the primary projection. Page copy uses Run, Plan, Trace, Replay, Tool Calls, Model Calls, Approvals, Assignments, and Subagents.

## Disabled Future Surfaces

Template marketplace, RAG setup, trigger editor, API Gateway publishing, version rollout, and human review queue can stay visible as disabled product entries until backed by API state.
