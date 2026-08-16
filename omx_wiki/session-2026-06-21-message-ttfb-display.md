# Message TTFB Display

Category: `session-log`

Tags: `frontend`, `agent-workspace`, `message-metadata`, `validation`

## Summary

Chat message bubbles now render `ttfb_ms` in the metadata row after `duration_ms` using `TTFB: <ms>ms`. Existing input token, output token, cost, and duration fields remain unchanged.

## Evidence

- `apps/agent-console/src/features/agents/components/ChatMessageBubble.tsx` includes numeric `ttfb_ms` in metadata visibility and renders it after duration.
- `apps/agent-console/src/features/agents/__tests__/ChatMessageList.render.test.tsx` now covers `TTFB: 123ms`.

## Validation

- `cd apps/agent-console && npx tsc --noEmit --pretty false --types vite/client --skipLibCheck --jsx react-jsx --lib DOM,DOM.Iterable,ES2022 --module ESNext --moduleResolution Bundler --target ES2020 --esModuleInterop --allowSyntheticDefaultImports src/features/agents/components/ChatMessageBubble.tsx src/features/agents/__tests__/ChatMessageList.render.test.tsx` passed.
- `cd apps/agent-console && npm test -- src/features/agents/__tests__/ChatMessageList.render.test.tsx --run` passed with `10 passed`.
- `cd apps/agent-console && npx vite build` passed.
- `python3 scripts/validate-docs.py` passed when the independent worktree used temporary links to the main workspace `AGENTS.md` and full `.omx` runtime context.

## Known Validation Blockers

- `cd apps/agent-console && npm run build` still fails in `tsc --noEmit` on existing stale test typing debt: missing `jest-axe` declarations, stale a11y imports, old `ChatMessageBubble` test props, and stale SAML fixture shapes.
- `cd services/api-server && uv run pytest tests/ -q` still fails during collection because `tests/integration/test_okta_logout.py` imports missing `Session` from `app.db.models`.
