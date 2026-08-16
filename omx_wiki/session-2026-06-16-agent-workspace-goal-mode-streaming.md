# Agent Workspace Goal Mode Streaming

Category: `session-log`

Tags: `agent-workspace`, `goal-mode`, `streaming`, `sse`, `run-execution`

## Summary

Agent Workspace `追踪目标模式` now preserves `mode=goal` end to end instead of downgrading to plan mode and returning a `plan.json` artifact. The backend creates or continues a workspace Run with `mode="goal"`, drives it through the executor loop, streams visible progress deltas, and finishes with Run status evidence.

Assistant replies now stream incremental SSE `delta` chunks when the model output can be safely shown immediately. Grounded answers that may need citation/rewrite handling still buffer until the final corrected answer is known.

## Root Cause

- Frontend `backendWorkspaceMode(mode)` converted `goal` to `plan`, so the server treated goal pursuit like a one-shot planning request.
- Local-agent submit context had the same `goal -> plan` conversion.
- Backend schema did not accept `goal` for workspace chat stream requests.
- Normal workspace chat accumulated model stream chunks but suppressed deltas when grounding was enabled, making replies appear non-streaming.

## Changes

- `apps/agent-console/src/features/agents/hooks/useChatStream.ts` now sends `payload.mode === "goal"` unchanged.
- `apps/agent-console/src/features/agents/components/ChatSurface.tsx` now preserves local-agent `mode: workspaceMode` for goal mode.
- `apps/agent-console/src/features/tasks/api.ts` accepts `goal` in `AgentChatStreamPayload.mode`.
- `services/api-server/app/api/schemas.py` accepts `goal` in `AgentChatStreamRequest.mode` and local-agent workspace mode.
- `services/api-server/app/api/agents/_workspace_chat_helpers.py` allows workspace Runs with `mode="goal"`.
- `services/api-server/app/api/agents/agent_chat/streaming.py` adds goal pursuit events that create/continue a Run, enable sandbox execution, call `Executor(session).start_task(run)` or `execute_existing_plan(run)`, emit status deltas, usage, and done without creating `plan.json`.
- `workspace_text_events` now forwards safe model chunks as incremental `delta` events and only sends the unstreamed suffix or corrected answer at completion.

## Validation

```text
cd apps/agent-console && PATH="/Users/luohao/.nvm/versions/node/v20.9.0/bin:/usr/local/bin:$PATH" npm test -- src/features/agents/__tests__/useChatStream.test.tsx
12 passed

cd apps/agent-console && PATH="/Users/luohao/.nvm/versions/node/v20.9.0/bin:/usr/local/bin:$PATH" npm test -- src/features/agents/__tests__/ChatSurface.shell.test.tsx
19 passed

cd apps/agent-console && PATH="/Users/luohao/.nvm/versions/node/v20.9.0/bin:/usr/local/bin:$PATH" npm test -- src/features/agents/__tests__/useChatStream.test.tsx src/features/agents/__tests__/ChatSurface.shell.test.tsx
31 passed

cd apps/agent-console && PATH="/Users/luohao/.nvm/versions/node/v20.9.0/bin:/usr/local/bin:$PATH" npx tsc --noEmit --pretty false --types vite/client --skipLibCheck --jsx react-jsx --lib DOM,DOM.Iterable,ES2022 --module ESNext --moduleResolution Bundler --target ES2020 --esModuleInterop --allowSyntheticDefaultImports src/features/agents/hooks/useChatStream.ts src/features/agents/components/ChatSurface.tsx src/features/tasks/api.ts src/features/agents/__tests__/useChatStream.test.tsx
passed

cd services/api-server && .venv/bin/python -m pytest tests/test_agents.py::test_agent_workspace_pro_chat_stream_emits_incremental_deltas_with_grounding tests/test_agents.py::test_agent_workspace_goal_mode_executes_without_plan_artifact -q
2 passed

cd services/api-server && .venv/bin/python -m ruff check app/api/schemas.py app/api/agents/agent_chat/streaming.py app/api/agents/_workspace_chat_helpers.py tests/test_agents.py
passed

python3 -m py_compile services/api-server/app/api/schemas.py services/api-server/app/api/agents/agent_chat/streaming.py services/api-server/app/api/agents/_workspace_chat_helpers.py services/api-server/tests/test_agents.py
passed

python3 scripts/validate-docs.py
docs validation passed

git diff --check
passed
```

## Follow-Up

The broader old TestClient-backed backend grouping originally hit the SQLite in-memory table-scope issue (`no such table: agents`). That blocker is now closed in [[session-2026-06-16-local-dev-testclient-sqlite-staticpool]].
