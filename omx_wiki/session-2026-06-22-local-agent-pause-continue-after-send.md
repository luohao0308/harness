# Local Agent Pause Continue After Send

Category: session-log
Tags: `agent-workspace`, `local-agent`, `pause`, `resume`, `browser-smoke`, `hao`

## Summary

Agent Workspace local Agent turns can now be paused after the message has been sent and continued later without duplicating the visible user bubble.

## Root Cause

Local Agent polling hydration dropped the optimistic pending assistant when a matching active bridge task existed but no server assistant message had been persisted yet. The task loop then skipped that same task, so the UI lost the control row and the user could not pause a sent message.

Live resume testing exposed a second frontend-only failure: resuming a hydrated paused turn could reuse a server user node whose id already existed in the rebuilt tree. The pending-user merge overwrote that node with `parent_id` equal to itself, and `buildActivePath(...)` entered a parent-cycle until the route crashed with `Invalid array length`.

## Changes

- Keep the pending assistant node while its matching local bridge task is active (`pending`, `leased`, or `running`), so the `暂停发送` control survives message/task polling hydration.
- Preserve an existing hydrated user node instead of reparenting it when resuming a paused turn, preventing self-parent cycles and duplicate user bubbles.
- Add cycle guards to Workspace active-path derivation in `AgentWorkspacePage`, `ChatSurface`, and the workspace store helpers.
- Keep the existing resume behavior that sends a fresh `client_message_id` while carrying `resume_of_client_message_id` / `resume_of_user_message_id`.

## Validation

```text
cd apps/agent-console && PATH="/Users/luohao/.nvm/versions/node/v20.9.0/bin:/usr/local/bin:$PATH" npx vitest run src/features/agents/__tests__/AgentWorkspacePage.team-launch.test.tsx
31 passed

cd apps/agent-console && PATH="/Users/luohao/.nvm/versions/node/v20.9.0/bin:/usr/local/bin:$PATH" npx vitest run src/features/agents/__tests__/ChatSurface.shell.test.tsx
26 passed

cd apps/agent-console && PATH="/Users/luohao/.nvm/versions/node/v20.9.0/bin:/usr/local/bin:$PATH" npx tsc --noEmit --pretty false --types vite/client,vitest/globals,@testing-library/jest-dom --skipLibCheck --jsx react-jsx --lib DOM,DOM.Iterable,ES2022 --module ESNext --moduleResolution Bundler --target ES2020 --esModuleInterop --allowSyntheticDefaultImports src/features/agents/pages/AgentWorkspacePage.tsx src/features/agents/components/ChatSurface.tsx src/features/agents/__tests__/AgentWorkspacePage.team-launch.test.tsx src/features/agents/__tests__/ChatSurface.shell.test.tsx src/features/tasks/api.ts src/features/agents/pages/agentWorkspaceDerive.ts src/stores/workspaceStore.ts
passed

services/api-server/.venv/bin/python -m py_compile services/api-server/app/api/agents/agent_local.py services/api-server/app/api/schemas.py
passed
```

Browser verification on `http://127.0.0.1:5173/agents/default/workspace?conversation_id=conv-chart-artifact-demo&run_id=demo-tool-approval-run` with `hao Local Agent` selected:

- Existing paused turn showed `继续发送`.
- Clicking `继续发送` sent `POST /api/agents/local-agent/bindings/7ea3bec8-aea2-4f3c-934c-bd21e46e5615/messages => 202` with new `client_message_id=local-1782063891122-f8a1b70c8eb2d8` and `resume_of_client_message_id=local-1782062842695-15e255cf140b2`, then the UI showed `暂停发送`.
- Unique sent message `暂停继续浏览器验证-1782063996356` returned local message `POST => 202`, showed `暂停发送`, had `userBubbleCount=1`, and left the composer empty.
- Clicking `暂停发送` sent `POST /api/tasks/9179794a-0832-4e61-ad76-aee5e29c1460/cancel => 202`; after pending cleared, `继续发送` was enabled.
- Current browser console errors/warnings: `0`.
- Screenshot: `local-agent-pause-continue-after-send.png`.

The browser proof uses real HAO local Agent binding/network state and does not rely on backend local mock assistant content.
