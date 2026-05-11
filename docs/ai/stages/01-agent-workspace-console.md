# Stage 1: Agent Workspace Console

> This stage captures one delivery snapshot. It describes a valid implementation shape, not the only acceptable console structure.

## Goal

Build the core Agent Workspace Pro route as the primary usage surface for AI Harness Platform by upgrading the existing `/agents/:agentId/workspace` route into a chat-first workspace with clear access to planning and runtime observations.

## Input

- User selects an Agent from Agent Studio.
- User enters a natural-language goal in the Chat Console.
- User may pin messages, adjust context window, pause a stream, continue partial output, or edit and resend a historical message.

## Output

- An Agent Run is created through Agent semantics.
- Console shows streamed assistant responses, conversation branch state, artifacts preview, plan data, event stream, subagents, tool cards, approvals, and model calls.
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

- The workspace may use left, center, right, drawer, or tabbed groupings as long as the chat experience stays primary.
- Context, tools, and model state remain easy to reach.
- Artifacts, metadata, plan data, event stream, subagents, tool cards, approvals, and model calls remain visible without forcing the user out of the chat flow.
- `/tasks/new` is deleted.
- `/tasks` redirects to `/runs` during compatibility migration.

## Tests

- Backend tests cover Agent Run creation, Workspace stream events, usage metadata, approval modify, and workspace projection.
- Frontend build covers route, store, stream control, artifact preview, and Tool Card integration.
- Manual smoke opens `/agents/default/workspace` and `/runs`.

## Acceptance

- User creates or continues an Agent Run from Workspace Pro.
- Same screen or coordinated views show streamed assistant output, conversation state, artifacts, and Harness internals.
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
