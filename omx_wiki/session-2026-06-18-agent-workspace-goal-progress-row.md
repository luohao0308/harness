# Session 2026-06-18 Agent Workspace Goal Progress Row

Category: session-log

Tags: `workspace`, `goal-mode`, `goal-progress`, `streaming`, `ui`, `agent-console`, `sse`

## Summary

Agent Workspace `追踪目标模式` now behaves like a Codex-style persistent goal loop with a compact active progress row above the composer, a dedicated dark edit modal, pause/resume controls, and completion that keeps the goal row visible instead of falling back to the old run-summary card.

## Outcome

- Backend SSE now emits `goal_progress` events with goal text, phase, turn, step count, elapsed time, and status.
- Goal mode continues through existing runs, surfaces planning/execution/paused/completed states, and keeps `WAITING_SUBAGENTS` in the live pursuit loop instead of treating it like a stop state.
- Frontend stores goal metadata on the assistant node and renders an active goal row above the composer.
- The goal row exposes edit, pause/resume, and clear actions; editing opens a dedicated dark modal instead of using the composer or expanding inline inside the row.
- Server-paused goal runs stay resumable on the frontend, and the resume path only auto-fires for the per-stream guard pause.
- `PAUSED` goal streams now report that the goal is paused and resumable instead of describing the run as terminal.
- Completed goal runs remain represented by the goal row, so the UI does not jump back to the legacy `运行 ... 查看运行详情` summary treatment.

## Validation

```text
cd services/api-server && .venv/bin/python -m pytest tests/test_agents.py::test_agent_workspace_goal_mode_executes_without_plan_artifact tests/test_agents.py::test_agent_workspace_goal_mode_continues_paused_existing_plan -q
2 passed

cd services/api-server && .venv/bin/python -m ruff check app/api/agents/agent_chat/streaming.py tests/test_agents.py
All checks passed!

python3 -m py_compile services/api-server/app/api/agents/agent_chat/streaming.py services/api-server/tests/test_agents.py
passed

cd apps/agent-console && PATH="/Users/luohao/.nvm/versions/node/v20.9.0/bin:/usr/local/bin:$PATH" npx vitest run src/features/agents/__tests__/useChatStream.test.tsx src/features/agents/__tests__/ChatSurface.shell.test.tsx src/features/agents/__tests__/ChatMessageList.render.test.tsx
46 passed

cd apps/agent-console && PATH="/Users/luohao/.nvm/versions/node/v20.9.0/bin:/usr/local/bin:$PATH" npx tsc --noEmit --pretty false --types vite/client --skipLibCheck --jsx react-jsx --lib DOM,DOM.Iterable,ES2022 --module ESNext --moduleResolution Bundler --target ES2020 --esModuleInterop --allowSyntheticDefaultImports src/features/agents/components/ChatSurface.tsx src/features/agents/components/ChatMessageList.tsx src/features/agents/hooks/useChatStream.ts
passed

python3 scripts/validate-docs.py
passed

git diff --check
passed

curl --noproxy '*' -s http://127.0.0.1:8000/health
{"status":"ok","service":"api-server"}

OpenAPI check for AgentChatStreamRequest
goal True
enable_sandbox_default False
enable_network_default False

Playwright / Chrome DevTools browser smoke on http://127.0.0.1:5173/agents/default/workspace
confirmed the compact goal bar, dark edit modal, save -> paused/resumable goal row, pause -> `目标已暂停`, resume -> `进行中的目标`, completion -> `目标已完成`, and no legacy run-summary card for goal-mode completion
```

## Notes

- Existing dirty worktree changes unrelated to goal mode were left untouched.
- The current loop guard pauses the stream when the run cannot be advanced to a terminal state inside one SSE request, so the UI can resume it cleanly.
- The live browser smoke used a controlled SSE stream for the goal lifecycle so the UI behavior could be verified independently of the currently configured model/provider key.
