# Authenticated Terminal Sessions

Category: `session-log`

Tags: `terminal`, `auth`, `websocket`, `desktop`, `agent-console`

## Summary

Implemented authenticated terminal session capabilities end to end.

- Backend now exposes `POST /api/terminal/tokens` for the current authenticated
  principal.
- Tokens are short-lived, one-time, bound to terminal id plus user/org, and
  required before `/ws/terminal` accepts a shell session.
- WebSocket connections still keep the local-origin/client boundary, reject
  missing, expired, reused, or terminal-mismatched tokens, and enforce a per-user
  active-session cap.
- Terminal process launch now uses an explicit workspace/home cwd and a scrubbed
  environment instead of inheriting API server secrets.
- Agent Console obtains a fresh terminal token through the existing
  authenticated API helper before each connect and reconnect.

## Changed Files

- `services/api-server/app/api/terminal.py`
- `services/api-server/tests/test_terminal_websocket.py`
- `apps/agent-console/src/features/tasks/api.ts`
- `apps/agent-console/src/features/tasks/__tests__/api.test.ts`
- `apps/agent-console/src/features/terminal/services/terminalWebSocket.ts`
- `apps/agent-console/src/features/terminal/services/__tests__/terminalWebSocket.test.ts`
- `apps/agent-console/src/features/terminal/hooks/useTerminalWebSocket.ts`

## Verification

- `services/api-server/.venv/bin/python -m pytest services/api-server/tests/test_terminal_websocket.py -q` -> `9 passed`
- `services/api-server/.venv/bin/python -m ruff check services/api-server/app/api/terminal.py services/api-server/tests/test_terminal_websocket.py` -> passed
- `cd apps/agent-console && npx vitest run src/features/terminal/services/__tests__/terminalWebSocket.test.ts src/features/tasks/__tests__/api.test.ts --reporter=dot` -> `2 passed / 15 tests passed`
- `cd apps/agent-console && npx tsc --noEmit --pretty false --types vite/client,vitest/globals,@testing-library/jest-dom --skipLibCheck --jsx react-jsx --lib DOM,DOM.Iterable,ES2022 --module ESNext --moduleResolution Bundler --target ES2020 --esModuleInterop --allowSyntheticDefaultImports src/vite-env.d.ts src/features/tasks/api.ts src/features/tasks/__tests__/api.test.ts src/features/terminal/services/terminalWebSocket.ts src/features/terminal/services/__tests__/terminalWebSocket.test.ts src/features/terminal/hooks/useTerminalWebSocket.ts` -> passed
- `cd apps/agent-console && npx vitest run src/features/terminal/services/__tests__/terminalWebSocket.test.ts src/features/terminal/components/__tests__/TerminalWorkspace.test.tsx src/features/terminal/components/__tests__/XtermTerminal.test.tsx src/stores/__tests__/terminalStore.test.ts src/features/tasks/__tests__/api.test.ts --reporter=dot` -> `5 passed / 31 tests passed`
- `cd apps/agent-console && npx vite build` -> passed with existing chunk-size warning
- `cd apps/agent-console && npm run build` -> passed after restoring the missing enterprise coverage report module
- enterprise sidebar/chain/pricing Playwright suites -> `52 passed`

## Closeout

- The earlier unrelated Agent Console module-resolution blocker is resolved.
- The original process-local capability state was replaced by Redis atomic
  state with renewable session leases in
  [[session-2026-07-12-terminal-capability-shared-state]].
