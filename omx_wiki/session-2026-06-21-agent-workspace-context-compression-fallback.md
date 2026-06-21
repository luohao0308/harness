# Agent Workspace Context Compression Fallback

Category: session-log

Tags: `agent-workspace`, `context-compression`, `frontend`, `browser-smoke`, `local-agent`

## Summary

Agent Workspace context compression now remains usable when the backend reports
the effective compressor model after fallback. The UI stores compression
summaries against the provider/model selected when compression was requested,
so the right-bottom context ring no longer rejects a freshly generated summary
and jumps back to 100.

## Root Cause

The context ring uses the effective prompt size: compression summary plus
uncovered raw messages. A summary is usable only when its compressor provider
and model match the current Workspace model selection.

The backend compression response reports the actual model that generated the
summary. When a request selected an unconfigured provider such as
`openai-compatible` / `gpt-5.5` but the backend executed with a configured
fallback such as `deepseek-flash` / `deepseek-v4-flash`, `ChatSurface` stored
the fallback model ids. The current UI selection still stayed on the requested
model, so `isCompressionSummaryUsable(...)` rejected the summary immediately.
That made manual compression appear successful, then the ring returned to raw
usage. Background compression had the same issue.

## Fix

- `ChatSurface` now commits compression responses with the provider/model used
  for the request, normalized through the existing model-id helper.
- The backend response still carries the actual compressor provider/model for
  audit and cache behavior; the frontend usability key is the request context.
- Regression coverage now includes both manual ring compression and automatic
  over-threshold compression when the response reports a fallback compressor.

## Validation

```text
cd apps/agent-console && PATH="/Users/luohao/.nvm/versions/node/v20.9.0/bin:/usr/local/bin:$PATH" npx vitest run src/features/agents/__tests__/ChatSurface.shell.test.tsx -t "compression|fallback compressor|auto-compresses|usage ring|slash command menu|original branch"
passed: 5 tests

cd apps/agent-console && PATH="/Users/luohao/.nvm/versions/node/v20.9.0/bin:/usr/local/bin:$PATH" npx vitest run src/features/agents/__tests__/ChatSurface.shell.test.tsx
passed: 26 tests

cd apps/agent-console && PATH="/Users/luohao/.nvm/versions/node/v20.9.0/bin:/usr/local/bin:$PATH" npx tsc --noEmit --pretty false --types vite/client,vitest/globals,@testing-library/jest-dom --skipLibCheck --jsx react-jsx --lib DOM,DOM.Iterable,ES2022 --module ESNext --moduleResolution Bundler --target ES2020 --esModuleInterop --allowSyntheticDefaultImports src/features/agents/components/ChatSurface.tsx src/features/agents/__tests__/ChatSurface.shell.test.tsx
passed

curl --noproxy '*' http://127.0.0.1:5173/agents/default/workspace?conversation_id=conv-chart-artifact-demo&run_id=demo-tool-approval-run
HTTP 200

curl --noproxy '*' http://127.0.0.1:8000/health
HTTP 200

git diff --check
passed
```

Browser verification on the target Workspace URL injected a completed two-node
conversation into the same Vite store module, set the context limit to `16k`,
and let the real UI auto-compress through the live API:

```text
POST /api/agents/default/context/compress -> 200
response.status: ok
response.cache_status: recomputed
response.compressor_provider: deepseek-flash
response.compressor_model: deepseek-v4-flash
response.estimated_original_tokens: 9950
response.estimated_summary_tokens: 16
stored summary status: ready
stored coverage: 2 nodes
right-bottom ring: 背景信息窗口：1% 已用，预计发送 61 标记，共 16k
```

Repo-wide `cd apps/agent-console && npm run lint` remains blocked by existing
unrelated TypeScript debt in stale a11y tests, `jest-axe` matcher declarations,
old `ChatMessageBubble` props, and missing API exports in Eval/Tools surfaces.
No lint error pointed at the files changed in this fix.
