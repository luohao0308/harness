# API Spec

## Agent Run Console

- `GET /api/agents`
- `GET /api/agents/{agent_id}`
- `POST /api/agents/{agent_id}/sessions`
- `POST /api/agents/sessions/{session_id}/messages`
- `POST /api/agents/{agent_id}/runs`
- `POST /api/agents/{agent_id}/runs/plan/stream`
- `POST /api/agents/{agent_id}/runs/chat/stream`
- `POST /api/agents/plan`
- `POST /api/agents/auto`
- `GET /api/agents/runs`
- `GET /api/agents/runs/{run_id}/workspace`
- `POST /api/agents/runs/{run_id}/execute`
- `POST /api/agents/runs/{run_id}/orchestrate`
- `POST /api/agents/runs/{run_id}/orchestrate/execute`
- `POST /api/agents/runs/{run_id}/orchestrate/enqueue`
- `GET /api/agents/runs/{run_id}/assignments`
- `GET /api/agents/runs/{run_id}/handoffs`

## Tasks, Events, Replay

- `GET /api/tasks`
- `POST /api/tasks`
- `GET /api/tasks/{task_id}`
- `POST /api/tasks/{task_id}/start`
- `POST /api/tasks/{task_id}/cancel`
- `POST /api/tasks/{task_id}/resume`
- `POST /api/tasks/{task_id}/steps/resume`
- `GET /api/tasks/{task_id}/events`
- `GET /api/tasks/{task_id}/events/stream`
- `POST /api/tasks/{task_id}/replay`
- `GET /api/tasks/{task_id}/plan`
- `GET /api/tasks/{task_id}/plans`
- `GET /api/tasks/{task_id}/plans/diff`

## Workspace Pro Stream

`POST /api/agents/{agent_id}/runs/chat/stream` is the Workspace Pro stream entry. It keeps the current FastAPI control plane and SSE transport. It does not add Vercel AI SDK as a core dependency.

Request body:

```json
{
  "goal": "optional user goal",
  "messages": [],
  "active_leaf_id": "node-id",
  "pinned_node_ids": [],
  "context_window_turns": 8,
  "continue_from_node_id": "optional-node-id",
  "partial_assistant_content": "optional partial content",
  "tool_mentions": []
}
```

`messages` contains ConversationNode objects from the active branch and selected pinned nodes. `tool_mentions` contains structured mentions from the Tool Tray and is not parsed from plain text.

The response is `text/event-stream`. Required SSE event names:

| Event | Payload contract |
|---|---|
| `think_delta` | Collapsible planner or reasoning trace text |
| `delta` | Visible assistant text token or chunk |
| `tool_call_requested` | Tool name, risk, sandbox, input JSON, approval id when pending |
| `tool_call_result` | Tool status, output summary, duration, trace id |
| `artifact_created` | Artifact id, name, type, content or preview handle |
| `usage` | input tokens, output tokens, cost, TTFB, total duration, model call id |
| `done` | run id, assistant node id, final state |
| `error` | error code, message, recoverable flag |

The stream creates or continues an Agent Run. The durable Run projection is visible through `GET /api/agents/runs/{run_id}/workspace`. Continue requests preserve the original `run_id`, `active_branch_id`, and `continue_from_node_id`.

### Workspace Pro Public Schemas

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

type AgentChatStreamRequest = {
  goal?: string;
  messages: ConversationNode[];
  active_leaf_id: string;
  pinned_node_ids: string[];
  context_window_turns: number;
  continue_from_node_id?: string;
  partial_assistant_content?: string;
  tool_mentions?: ToolMention[];
};

type ToolApprovalModifyRequest = {
  approval_id: string;
  modified_input_json: Record<string, unknown>;
  reason: string;
};
```

## Tools And Sandboxes

- `POST /api/tasks/{task_id}/tools/execute`
- `GET /api/tasks/{task_id}/tool-calls`
- `GET /api/tasks/{task_id}/tool-approvals`
- `POST /api/tasks/{task_id}/tool-approvals/{approval_id}/approve`
- `POST /api/tasks/{task_id}/tool-approvals/{approval_id}/reject`
- `POST /api/tasks/{task_id}/tool-approvals/{approval_id}/modify`
- `GET /api/sandboxes`
- `GET /api/sandboxes/warm-pool`
- `GET /api/sandboxes/quota/usage`
- `GET /api/sandboxes/quota/history`

## Eval Harness

- `POST /api/evals/datasets`
- `GET /api/evals/datasets`
- `POST /api/evals/datasets/{dataset_id}/cases`
- `POST /api/evals/datasets/{dataset_id}/cases/from-run/{task_id}`
- `GET /api/evals/datasets/{dataset_id}/cases`
- `POST /api/evals/datasets/{dataset_id}/runs`
- `GET /api/evals/runs`
- `GET /api/evals/runs/{eval_run_id}`

## Settings And Observability

- `GET /api/settings/models`
- `PUT /api/settings/models`
- `GET /api/settings/models/health`
- `GET /api/settings/policies`
- `GET /api/observability/summary`
- `GET /api/observability/architecture`
- `GET /api/observability/logs`
- `GET /api/observability/traces/{trace_id}`
