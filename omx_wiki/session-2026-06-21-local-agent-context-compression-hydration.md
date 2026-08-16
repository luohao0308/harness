# Local Agent Context Compression Hydration

Category: session-log

Tags: `local-agent`, `agent-workspace`, `context-compression`, `frontend`, `browser-smoke`

## Summary

Agent Workspace local Agent conversations now preserve context compression
summaries across local message/task polling. A compressed HAO local Agent thread
stays reduced after hydration instead of returning to raw `100%` usage every
poll cycle.

## Root Cause

The previous context-compression fallback fix made generated summaries usable,
but local Agent polling had a separate overwrite path. Every session-message or
binding-task poll rebuilt the `local-agent:<bindingId>` conversation from
backend data and returned `contextCompressions: {}`.

That erased a ready summary from the active Workspace store. The right-bottom
context ring then recalculated from raw local Agent messages and jumped back to
100 even though compression had succeeded.

## Fix

- `localAgentConversationFromMessages(...)` accepts preserved
  `pinnedNodeIds`, `contextWindowTurns`, and `contextCompressions`.
- `localAgentHydrationStateForConversation(...)` reads those fields from the
  active store or existing local conversation before rebuilding from backend
  messages/tasks.
- `localAgentContextCompressionsForConversation(...)` filters summaries to the
  current `local-agent:<bindingId>:` branch prefix, so local Agent summaries do
  not leak across bindings.
- Local Agent polling and initial local conversation creation now pass the
  preserved hydration state into the rebuilt conversation summary.

## Validation

```text
cd apps/agent-console && PATH="/Users/luohao/.nvm/versions/node/v20.9.0/bin:/usr/local/bin:$PATH" npx vitest run src/features/agents/__tests__/AgentWorkspacePage.team-launch.test.tsx -t "preserves local Agent context compression summaries"
passed: 1 passed, 29 skipped

cd apps/agent-console && PATH="/Users/luohao/.nvm/versions/node/v20.9.0/bin:/usr/local/bin:$PATH" npx vitest run src/features/agents/__tests__/AgentWorkspacePage.team-launch.test.tsx
passed: 30 passed

cd apps/agent-console && PATH="/Users/luohao/.nvm/versions/node/v20.9.0/bin:/usr/local/bin:$PATH" npx tsc --noEmit --pretty false --types vite/client,vitest/globals,@testing-library/jest-dom --skipLibCheck --jsx react-jsx --lib DOM,DOM.Iterable,ES2022 --module ESNext --moduleResolution Bundler --target ES2020 --esModuleInterop --allowSyntheticDefaultImports src/features/agents/pages/AgentWorkspacePage.tsx src/features/agents/__tests__/AgentWorkspacePage.team-launch.test.tsx src/features/tasks/api.ts
passed

cd apps/agent-console && PATH="/Users/luohao/.nvm/versions/node/v20.9.0/bin:/usr/local/bin:$PATH" npx vitest run src/features/agents/__tests__/ChatSurface.shell.test.tsx
passed: 26 passed
```

Browser verification on the user URL selected `hao Local Agent`, waited through
several local polling cycles, and read the live DOM state:

```text
URL: http://127.0.0.1:5173/agents/default/workspace?conversation_id=conv-chart-artifact-demo&run_id=demo-tool-approval-run
connection_id: c465ba35-3782-44d9-a66c-0edfdf7933b2
binding_id: aee0f1fb-ce2d-4f8c-a987-41b36bbba47b
agent_session_id: 130bc185-25ab-437e-a9d4-62ad7a7aa8ab
summary badge: 36 条已摘要
context button: 背景信息窗口：2% 已用，预计发送 245 标记，共 16k。点击压缩上下文
100% present: false
local polling: session messages 200, binding tasks 200
console warnings/errors: 0
screenshot: local-agent-context-compression-fixed-verified.png
```

The regression test also verifies the behavioral contract that the next local
Agent send after hydration includes `compressed_context` with the preserved
summary.

## Boundaries

- This fix is frontend hydration preservation. It does not change compression
  backend semantics or compressor model selection.
- Local Agent summaries are intentionally scoped to the same binding prefix.
- The browser proof uses the real HAO local Agent connection and polling path,
  not a backend local mock model reply.
