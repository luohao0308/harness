# Local Agent Bridge Timeout Fallback

Category: `session-log`

Tags: `local-agent`, `agent-workspace`, `timeout`, `fallback`, `validation`

## Summary

Agent Workspace local Agent turns no longer remain indefinitely on `本地 Agent 正在处理` when the bridge task stops returning. Active local bridge tasks now fail closed after a 180-second idle timeout unless they are waiting on explicit local tool/approval state. Offline local Agents also expose an inline `恢复` action in the Workspace header so users can refresh the connection and resume an existing binding in place.

## Evidence

- `services/api-server/app/api/agents/agent_local.py` now expires stale `pending` / `leased` / `running` bridge tasks during binding-task polling and bridge pulls.
- Timeout finalization marks the bridge task `failed`, closes the associated Run as `FAILED`, stores `terminal_error_message` plus timeout metadata, and emits `LOCAL_AGENT_MESSAGE_FAILED`.
- Bridge event receipt now refreshes bridge-task activity, so long-running local tasks that keep sending deltas/events are not timed out while making progress.
- Tasks with unresolved local tool state are skipped by the bridge-task timeout and keep the existing tool-decision TTL path.
- `apps/agent-console/src/features/agents/pages/AgentWorkspacePage.tsx` now keeps terminal failed local-agent tasks anchored to the optimistic user/assistant pair when polling discovers the failure, so the error bubble remains visible and the composer unlocks without waiting for SSE.
- The offline local Agent control renders `恢复`, invalidates/refetches local connections, local bindings, session messages, binding tasks, and the active Run workspace, then reuses the existing local-Agent enable/binding restore path.
- Offline pending assistant copy now says users can click `恢复` to synchronize the connection. A follow-up recovery-command pass replaced the still-offline Agent Studio-only guidance with an inline generated `bridge run` command for the existing connection.

## Validation

- `services/api-server/.venv/bin/python -m pytest services/api-server/tests/test_local_agents.py::test_local_agent_stale_active_task_auto_fails_on_binding_poll services/api-server/tests/test_local_agents.py::test_local_agent_stale_task_waiting_on_local_tool_does_not_timeout -q` passed with `2 passed`.
- `services/api-server/.venv/bin/python -m pytest services/api-server/tests/test_local_agents.py::test_local_agent_pending_task_is_api_projected_and_not_released_twice services/api-server/tests/test_local_agents.py::test_local_agent_stale_active_task_auto_fails_on_binding_poll services/api-server/tests/test_local_agents.py::test_local_agent_stale_task_waiting_on_local_tool_does_not_timeout services/api-server/tests/test_local_agents.py::test_local_agent_failed_task_is_projected_with_error_message services/api-server/tests/test_local_agents.py::test_local_agent_failed_ack_closes_run_and_projects_error_message -q` passed with `5 passed`.
- `services/api-server/.venv/bin/python -m ruff check services/api-server/app/api/agents/agent_local.py services/api-server/tests/test_local_agents.py && services/api-server/.venv/bin/python -m py_compile services/api-server/app/api/agents/agent_local.py services/api-server/tests/test_local_agents.py` passed.
- `cd apps/agent-console && PATH="/Users/luohao/.nvm/versions/node/v20.9.0/bin:/usr/local/bin:$PATH" npx vitest run src/features/agents/__tests__/ChatSurface.shell.test.tsx src/features/agents/__tests__/useChatStream.test.tsx` passed with `40 passed`.
- `cd apps/agent-console && PATH="/Users/luohao/.nvm/versions/node/v20.9.0/bin:/usr/local/bin:$PATH" npx vitest run src/features/agents/__tests__/AgentWorkspacePage.team-launch.test.tsx -t "optimistic local Agent bubble"` passed with `1 passed, 25 skipped`.
- `cd apps/agent-console && PATH="/Users/luohao/.nvm/versions/node/v20.9.0/bin:/usr/local/bin:$PATH" npx vitest run src/features/agents/__tests__/AgentWorkspacePage.team-launch.test.tsx` passed with `26 passed`.
- `cd apps/agent-console && PATH="/Users/luohao/.nvm/versions/node/v20.9.0/bin:/usr/local/bin:$PATH" npx tsc --noEmit --pretty false --types vite/client --skipLibCheck --jsx react-jsx --lib DOM,DOM.Iterable,ES2022 --module ESNext --moduleResolution Bundler --target ES2020 --esModuleInterop --allowSyntheticDefaultImports src/features/agents/pages/AgentWorkspacePage.tsx src/features/tasks/api.ts` passed.

## Known Validation Notes

- `git diff --check` initially reported a pre-existing trailing blank line in `omx_wiki/log.md` after the wiki query entry. The closeout log update removed the EOF whitespace while preserving the query record.
