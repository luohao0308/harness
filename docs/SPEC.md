# AI Harness Platform Spec

## Positioning

AI Harness Platform is a production Agent infrastructure product built around this invariant:

```text
Model + Harness = Agent
```

A model provides reasoning and generation. Harness provides model configuration, prompt control, tool and MCP access, sandbox policy, planning, execution, event sourcing, replay, evaluation, WarmPool acceleration, and release operations. The product exists to create, run, observe, constrain, evaluate, and ship Agents.

The public website remains in the repository as a public information shell. The product console is the implementation center.

This is a living reference, not a frozen component contract. Equivalent decompositions are acceptable when they preserve visible behavior, traceability, and audit coverage.

## Product Pillars

| Pillar | Product Surface | Required Capability |
|---|---|---|
| Agent Studio | `/agents`, `/settings/models` | Reference surface for building Agents from model, prompt, tools, MCP, RAG settings, templates, versions |
| Agent Workspace | `/agents/:agentId/workspace` | Reference surface for using an Agent through a chat-first workspace: conversation, planning, context controls, tools, artifacts, run state, and audit views |
| Harness Management | `/tools`, `/sandboxes` | Reference surface for registering tools, connecting MCP, enforcing permissions, sandbox actions, DAG and trigger controls |
| Observability | `/observability`, `/runs/:runId` | Reference surface for event browser, replay, cost, latency, success rate, alerts, audit exports |
| Eval & Testing | `/evals` | Reference surface for dataset, eval run, regression gate, A/B comparison, human review queue |
| Infra | `/sandboxes`, `/settings/models` | Reference surface for WarmPool, multi-tenant isolation, API Gateway surface, version and rollout state |

## Product Concepts

| Concept | Meaning |
|---|---|
| Agent | A named runtime made from Model plus Harness configuration |
| Agent Session | Internal compatibility conversation context; not the primary product mode |
| Agent Run | A durable execution attempt created from Agent Workspace |
| Conversation Tree | Branch-preserving Workspace UI graph for user, assistant, system, and tool messages |
| Active Path | Current branch path used to assemble Workspace context |
| Pinned Message | Conversation node forced into each Workspace Pro request context |
| Artifact | Previewable output derived from plan JSON, code block, tool result, diff, chart, or subagent output |
| Plan DAG | Planner output for an Agent Run |
| Executor Step | Synchronous ReAct execution unit |
| Subagent | Async worker for long-running branch execution |
| Assignment | Multi-Agent orchestration branch assigned to a named Agent |
| Event | Append-only audit fact for replay and recovery |
| Eval Case | Reusable test case derived from a Run or written dataset row |

The database table named `tasks` remains an internal compatibility detail during migration. Product copy, console navigation, new API entry points, and specs use `Agent Run`.

## Workspace Mode Semantics

Workspace stream modes are intentionally separate:

- `chat` is the default conversational mode and returns displayable model text.
- `markdown_plan` returns markdown planning text for the user to review. It does not create an `ExecutionPlan`, tool call, approval, or artifact event by itself.
- `plan` is the explicit Plan-Act path. It can create a Plan DAG, runtime artifacts, tool-call audit records, and approval state.

Future UI layouts can rename buttons, regroup panels, or move runtime details into drawers, but they should preserve this semantic split.

## Active Console Routes

| Route | Role |
|---|---|
| `/agents` | Agent Studio registry and entry |
| `/agents/:agentId/workspace` | Agent Workspace Pro workspace |
| `/runs` | Agent Run audit history |
| `/runs/:runId` | Run detail with Plan, Trace, Replay, Tool Calls, Model Calls, Approvals |
| `/settings/models` | Model configuration with built-in MiniMax preset |
| `/tools` | Tool and MCP registry |
| `/observability` | Event, metric, latency, cost, service health |
| `/evals` | Eval datasets, runs, regression results |
| `/sandboxes` | Sandbox and WarmPool operations |
| `/subagents` | Async Subagent monitoring |

`/agents/:agentId/chat` and `/tasks` are compatibility redirects. `/tasks/new` is not a product route.

## Data Source Rule

Console state comes from APIs. Static fake metrics, fake models, fake tool statuses, fake run statuses, and fake eval results are prohibited. Future surfaces such as template marketplace, trigger editor, and RAG setup render as disabled entries until backed by API state.

## Workspace Pro Rules

- Workspace Pro uses a tree-shaped conversation graph rather than a flat message list.
- Editing a historical user message creates a new branch and keeps the previous branch intact.
- The active path, pinned nodes, and context window determine request context.
- Streaming output supports pause and continue through client-side abort control.
- `markdown_plan` planning text renders as normal assistant content; explicit `plan` traces and thought-like text render as collapsible trace blocks when returned.
- Side-effect tools enter the Tool Approval path before execution.
- Tool Cards show tool name, risk, sandbox requirement, input JSON, output JSON, latency, status, and trace.
- Artifacts render in the right preview surface and never bypass Tool Policy or Sandbox.
- Per-message metadata shows input tokens, output tokens, cost, first-byte latency, and total duration when returned by the API.

These rules describe the current behavioral contract, not a frozen component map. Equivalent layouts, component names, and request assembly helpers are acceptable if they preserve the same user-visible behavior and audit guarantees.

## Current Implementation Focus

The current implementation focus is the active AI Harness Platform path. Old task-management UX, marketing-like console pages, static dashboard cards, and unrelated historical stages are treated as non-primary references unless a later plan explicitly revives them. Website code stays present.
