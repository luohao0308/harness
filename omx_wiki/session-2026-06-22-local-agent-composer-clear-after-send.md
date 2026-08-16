# Local Agent Composer Clear After Send

Category: `session-log`

Tags: `agent-workspace`, `local-agent`, `composer`, `frontend`, `browser-verification`

## Summary

Agent Workspace local Agent sends now clear the composer as soon as the backend accepts the message. Later local Agent session-message and binding-task polling hydration does not restore the sent draft.

## Root Cause

`ChatComposer.submitAndMaybeClear()` already clears the draft unless `onSubmit()` returns `false`.

The live local Agent path could still return `false` after `localSendMutation.mutateAsync(...)` had already succeeded with HTTP 202. When the response-state guard `responseStillTargetsCurrentLocalConversation` failed during local hydration, `ChatComposer` interpreted the result as a failed send and preserved the sent text in the textarea.

## Fix

`apps/agent-console/src/features/agents/pages/AgentWorkspacePage.tsx` now clears the submitted draft immediately after the local Agent message POST returns successfully, while the selected local connection still matches the binding.

The clear is guarded by `useWorkspaceStore.getState().draft.trim() === goal`, so a user typing a newer draft while the send is in flight is not wiped. The later post-invalidation clear remains as a second safeguard.

`apps/agent-console/src/features/agents/__tests__/AgentWorkspacePage.team-launch.test.tsx` now asserts the local Agent composer is empty after the POST and remains empty after final hydration.

## Validation

- `cd apps/agent-console && PATH="/Users/luohao/.nvm/versions/node/v20.9.0/bin:/usr/local/bin:$PATH" npx vitest run src/features/agents/__tests__/AgentWorkspacePage.team-launch.test.tsx -t "sends through a local Agent binding|stale local Agent send responses"` -> 2 passed.
- `cd apps/agent-console && PATH="/Users/luohao/.nvm/versions/node/v20.9.0/bin:/usr/local/bin:$PATH" npx vitest run src/features/agents/__tests__/AgentWorkspacePage.team-launch.test.tsx` -> 30 passed.
- `cd apps/agent-console && PATH="/Users/luohao/.nvm/versions/node/v20.9.0/bin:/usr/local/bin:$PATH" npx tsc --noEmit --pretty false --types vite/client,vitest/globals,@testing-library/jest-dom --skipLibCheck --jsx react-jsx --lib DOM,DOM.Iterable,ES2022 --module ESNext --moduleResolution Bundler --target ES2020 --esModuleInterop --allowSyntheticDefaultImports src/features/agents/pages/AgentWorkspacePage.tsx src/features/agents/__tests__/AgentWorkspacePage.team-launch.test.tsx src/features/tasks/api.ts` -> passed.
- Browser verification on `http://127.0.0.1:5173/agents/default/workspace?conversation_id=conv-chart-artifact-demo&run_id=demo-tool-approval-run` with `hao Local Agent` selected sent `清空输入框验证 003`.
- Network showed `POST /api/agents/local-agent/bindings/7ea3bec8-aea2-4f3c-934c-bd21e46e5615/messages => 202 Accepted`.
- Immediate DOM check showed `composerValue=""`, `hasSentTextInComposer=false`, `sentTextVisibleInThread=true`, `pendingApproval=true`, and `processing=false`.
- After several local message/task polling cycles returned 200, DOM still showed `composerValue=""` and `hasSentTextInComposer=false`.
- Screenshot: `local-agent-composer-cleared-after-send.png`.

## Evidence Boundary

This proof validates the composer state after a real local Agent POST and subsequent polling hydration. It does not rely on backend local mock model assistant replies.
