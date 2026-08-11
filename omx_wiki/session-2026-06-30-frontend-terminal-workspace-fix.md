# Frontend Terminal Workspace Fix

Category: session-log
Tags: `agent-console`, `terminal`, `electron-desktop`, `websocket`, `xterm`, `layout-persistence`, `browser-smoke`

## Summary

The Terminal workspace now passes the desktop verification path for four rendered terminal panes, live shell I/O, keyboard switching, panel resizing, and refresh-safe layout persistence.

## Delivered

- Added backend `/ws/terminal` WebSocket support in `services/api-server/app/api/terminal.py`.
- Mounted the terminal WebSocket router in `services/api-server/app/main.py` without an `/api` prefix to match the existing frontend `ws://localhost:8000/ws/terminal` contract.
- Created one local PTY shell per terminal WebSocket connection, with local-origin/client checks so the shell bridge is limited to local desktop/dev usage.
- Made terminal creation idempotent and changed titles to derive from `term-1` through `term-4`, preventing React dev Strict Mode/HMR duplicate creates from turning all panes into `Terminal 5`.
- Extended `terminal-layout` persistence with `verticalSizes` so the nested term-2/term-3 split survives refresh alongside the outer horizontal split.
- Delayed WebSocket connect by one tick to avoid Strict Mode cleanup producing browser `closed before connection established` console noise.
- Changed Electron development window startup so DevTools opens only when `HARNESS_DESKTOP_OPEN_DEVTOOLS=1` is set, keeping manual desktop verification focused on the app window by default.

## Validation

```text
services/api-server/.venv/bin/python -m pytest services/api-server/tests/test_terminal_websocket.py -q
2 passed

services/api-server/.venv/bin/python -m py_compile services/api-server/app/api/terminal.py services/api-server/app/main.py
passed

services/api-server/.venv/bin/python -m ruff check services/api-server/app/api/terminal.py services/api-server/app/main.py services/api-server/tests/test_terminal_websocket.py
All checks passed

cd apps/agent-console && npx vitest run src/features/terminal/components/__tests__/TerminalWorkspace.test.tsx src/features/terminal/components/__tests__/XtermTerminal.test.tsx src/stores/__tests__/terminalStore.test.ts
16 passed

cd apps/agent-console && npx tsc --noEmit --pretty false --types vite/client,vitest/globals,@testing-library/jest-dom --skipLibCheck --jsx react-jsx --lib DOM,DOM.Iterable,ES2022 --module ESNext --moduleResolution Bundler --target ES2020 --esModuleInterop --allowSyntheticDefaultImports <terminal-touched-files>
passed

cd apps/desktop-app && npm test -- src/config/__tests__/app.test.ts src/__tests__/main.test.ts src/__tests__/hot-reload.test.ts src/__tests__/window-manager.test.ts
16 passed

cd apps/desktop-app && npm run build:main
passed
```

Browser verification on `http://127.0.0.1:5173/terminal`:

```text
4 xterm containers rendered with titles Terminal 1, Terminal 2, Terminal 3, Terminal 4.
`echo terminal-clean-178277` returned shell output in the first terminal.
Cmd+1/2/3/4 switched active terminal, ending on Terminal 4.
Dragging the term-2/term-3 separator changed verticalSizes from [51.287, 48.713] to [52.647, 47.353].
After refresh, term-2 and term-3 kept the 360px / 324px split and localStorage kept verticalSizes [52.647, 47.353].
60-frame sample: avg 16.26ms, max 17.4ms, 0 frames over 50ms.
Console after the Strict Mode connection-delay fix contained only the React DevTools development info.
API health after terminal verification: 200 in 0.030s.
```

Electron desktop verification via Playwright `_electron` against the real desktop shell:

```text
Desktop window launched and visible.
DevTools did not open by default; the only app window URL was http://127.0.0.1:5173/.
Navigated to http://127.0.0.1:5173/terminal.
4 xterm containers rendered with titles Terminal 1, Terminal 2, Terminal 3, Terminal 4.
`echo electron-final-ok-178277` returned shell output in the first terminal.
Cmd+1/2/3/4 stayed on /terminal and switched active terminal 1 through 4.
Dragging the term-2/term-3 separator changed localStorage layout.
After refresh, the changed terminal layout persisted.
60-frame sample: avg 16.47ms, max 33.7ms, 0 frames over 50ms.
Page errors: 0.
```

## Notes

- The live shell prints a user-environment `Kiro CLI had an Error!: Operation not permitted` startup line from the local zsh profile. It does not block terminal I/O or layout behavior.
- The API was restarted in the existing `harness_api` tmux session so the desktop app could use the newly mounted WebSocket route.
