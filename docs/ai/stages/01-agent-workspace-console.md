# Stage 1: Agent Workspace Three-Column Console

## Goal

Build the core Agent Workspace Pro route as the primary usage surface for AI Harness Platform by upgrading the existing `/agents/:agentId/workspace` route.

## Input

- User selects an Agent from Agent Studio.
- User enters a natural-language goal in the Chat Console.
- User may pin messages, adjust context window, pause a stream, continue partial output, or edit and resend a historical message.

## Output

- An Agent Run is created through Agent semantics.
- Console shows streamed Plan-Act response, conversation tree branch, Artifacts preview, Plan DAG, Event Stream, Subagents, Tool Cards, Approvals, and Model Calls.
- Old task creation route is absent from primary navigation.

## Modules

- Agent Workspace
- Conversation Tree Store
- Agent Run
- Planner
- Executor
- Subagent projection
- Tool and Model call projection

## API And Schema Changes

- Add `POST /api/agents/{agent_id}/runs`.
- Add `POST /api/agents/{agent_id}/runs/chat/stream`.
- Add `GET /api/agents/runs`.
- Add `GET /api/agents/runs/{run_id}/workspace`.
- Add or expose `POST /api/tasks/{task_id}/tool-approvals/{approval_id}/modify`.
- Keep `/api/tasks/*` as internal compatibility until migration completes.

## Event Types

- `TASK_CREATED` as internal compatibility event for Run creation
- `PLAN_REQUESTED`
- `MODEL_CALLED`
- `MODEL_RESPONSE_RECEIVED`
- `PLAN_GENERATED`
- `TASK_STARTED`
- `STEP_STARTED`
- `STEP_COMPLETED`
- `STEP_FAILED`
- `TASK_COMPLETED`
- `TASK_FAILED`

## Frontend Display

- Left column: Explorer with model, Tool Tray, MCP tools, context slider, pinned messages, file bridge state.
- Center column: Chat Console with active conversation branch, streamed Plan-Act output, Pause, Continue, Edit and Resend, and structured `@` mentions.
- Right column: Artifacts Preview, metadata, Plan DAG, Event Stream, Subagents, Tool Cards, Approvals, Model Calls.
- `/tasks/new` is deleted.
- `/tasks` redirects to `/runs` during compatibility migration.

## Tests

- Backend tests cover Agent Run creation, Workspace stream events, usage metadata, approval modify, and workspace projection.
- Frontend build covers route, store, stream control, artifact preview, and Tool Card integration.
- Manual smoke opens `/agents/default/workspace` and `/runs`.

## Acceptance

- User creates or continues an Agent Run from Workspace Pro.
- Same screen shows streamed Plan-Act output, Conversation Tree state, Artifacts, and Harness internals.
- Historical message edits create a branch and do not overwrite existing nodes.
- Pause keeps partial content; Continue resumes from the paused node.
- Pinned messages remain in request payloads.
- Data comes from API responses.
- No fake Run state is displayed.

## Not Doing

- No marketplace implementation.
- No RAG ingestion implementation.
- No trigger editor implementation.

## Vertical Slice Demo

```text
Open /agents/default/workspace
-> enter goal
-> stream Plan-Act response
-> pause and continue partial assistant output
-> edit an earlier user message and create a new branch
-> Agent Run appears
-> Artifacts Preview, Plan DAG, Event Stream, Tool Cards, Model Calls, Approvals, and Subagents stay visible as Harness projections
```
