# Desktop Full Function Startup Smoke

Category: `session-log`

Tags: `desktop`, `electron`, `agent-console`, `terminal`, `packaging`, `smoke-test`

## Summary

The full desktop surface was started and tested end to end. The verification covered backend desktop APIs, Agent Console desktop and terminal surfaces, Electron main/preload/native integrations, packaging, browser runtime, and real Electron runtime.

## Scope Covered

- Desktop workbench `/desktop` in browser fallback mode and real Electron bridge mode.
- Terminal workspace `/terminal` with four xterm panes and live shell WebSocket I/O.
- Electron preload bridge APIs for profiles, independent Run windows, local-model settings, offline tasks, file bridge, system startup state, updates/feedback namespaces, and event subscriptions.
- Electron native integrations through unit coverage: tray/menu/shortcut/deep-link/notification routing, crash reporting, update checks, preload exposure, window persistence, lifecycle, file bridge, task/agent IPC, SSE bridge, offline queue/task store/sync service, and production/dev startup.
- Desktop backend APIs for sync, sync operations, update checks, plugin marketplace, Prompt templates, and terminal WebSocket.
- Packaging/distribution path through `electron-builder --dir --publish never`.

## Fixes During Verification

- Added missing `app.isReady()` to older Electron test mocks so system/production/e2e tests match the current startup path.
- Added `setCrashReportingSentryForTests(...)` as a test-only injection seam for the delayed CommonJS Sentry loader used by `crash-reporting.ts`; production still lazy-loads `@sentry/electron/main`.
- Ran Ruff import fixes for desktop sync tests.
- Rebuilt `better-sqlite3` for the current Node x64 ABI after discovering the installed native module was arm64.
- Confirmed `electron-builder` recompiles `better-sqlite3` to Electron ABI for packaged output, then rebuilt it back to Node ABI before final Vitest verification.
- Confirmed real Electron startup must clear inherited `ELECTRON_RUN_AS_NODE=1`; with `ELECTRON_RUN_AS_NODE=""`, Electron exposes the real `require("electron")` API and the desktop app launches.

## Verification

- `services/api-server/.venv/bin/python -m pytest services/api-server/tests/test_desktop_sync.py services/api-server/tests/test_desktop_sync_integration.py services/api-server/tests/test_desktop_sync_operations.py services/api-server/tests/test_desktop_updates.py services/api-server/tests/test_plugins.py services/api-server/tests/test_terminal_websocket.py -q` -> 30 passed.
- `services/api-server/.venv/bin/python -m ruff check services/api-server/app/api/desktop_sync.py services/api-server/app/api/plugins.py services/api-server/app/api/terminal.py services/api-server/app/main.py services/api-server/tests/test_desktop_sync.py services/api-server/tests/test_desktop_sync_integration.py services/api-server/tests/test_desktop_sync_operations.py services/api-server/tests/test_desktop_updates.py services/api-server/tests/test_plugins.py services/api-server/tests/test_terminal_websocket.py` -> passed.
- `cd apps/agent-console && npx vitest run src/features/settings/pages/__tests__/AdvancedFeaturesPage.test.tsx src/lib/__tests__/desktop-bridge.test.ts src/features/agents/__tests__/WorkspaceShellBar.render.test.tsx src/features/agents/__tests__/ChatSurface.shell.test.tsx src/components/ui/__tests__/VirtualList.test.tsx src/features/terminal/components/__tests__/TerminalWorkspace.test.tsx src/features/terminal/components/__tests__/XtermTerminal.test.tsx src/stores/__tests__/terminalStore.test.ts` -> 57 passed.
- `cd apps/agent-console && npm run build` -> passed with existing chunk-size warning.
- `cd apps/desktop-app && npm test` -> 28 files / 259 tests passed.
- `cd apps/desktop-app && npm run build:main` -> passed.
- `cd apps/desktop-app && npm run build:renderer` -> copied Agent Console renderer to `apps/desktop-app/dist/renderer`.
- `cd apps/desktop-app && npx electron-builder --dir --publish never` -> passed; local macOS signing/notarization skipped because no Developer ID / Apple credentials are configured, as expected.
- Browser smoke on `http://127.0.0.1:5173/desktop` -> heading `桌面工作台`, `aria-label="桌面状态摘要"`, web fallback badge, horizontal overflow 0, console/page errors 0; screenshot `/tmp/harness-desktop-browser-1783096287671.png`.
- Browser smoke on `http://127.0.0.1:5173/terminal` -> 4 xterm containers, `echo browser-terminal-ok-1783096287671` output returned, terminal 4 switching visible, console/page errors 0; screenshot `/tmp/harness-terminal-browser-1783096287671.png`.
- Electron smoke via Playwright `_electron` with `ELECTRON_RUN_AS_NODE=""` and `VITE_DEV_SERVER_URL=http://127.0.0.1:5173` -> desktop bridge connected, `/desktop` rendered with overflow 0, preload API namespaces present (`agent`, `events`, `feedback`, `file`, `localModel`, `offline`, `profile`, `system`, `task`, `updates`, `window`), profile save/switch succeeded, offline deterministic task completed and listed, local-model settings round-tripped, independent Run window opened `/runs/demo-tool-approval-run`, file root `/tmp` listed, startup state returned boolean, 2 Electron windows observed; screenshot `/tmp/harness-desktop-electron-1783096287671.png`.
- Electron terminal smoke -> 4 xterm containers, `echo electron-terminal-ok-1783096287671` output returned, terminal 4 switching visible, page errors 0; screenshot `/tmp/harness-terminal-electron-1783096287671.png`. Only expected Electron development CSP warnings were logged.
- `NO_PROXY=127.0.0.1,localhost curl --max-time 3 http://127.0.0.1:8000/health` -> 200.
- `NO_PROXY=127.0.0.1,localhost curl --max-time 3 -I http://127.0.0.1:5173/desktop` -> 200.
- `python3 scripts/validate-docs.py` -> passed.
- `ruby -e 'require "yaml"; YAML.load_file(".github/workflows/release.yml"); puts "release.yml YAML OK"'` -> passed.
- `bash -n scripts/release.sh` -> passed.
- `git diff --check` -> passed.

## Notes

- The active shell had `ELECTRON_RUN_AS_NODE=1`; this is useful for some automation but makes Electron execute as Node. Desktop startup commands and Playwright Electron smoke must clear it.
- `electron-builder --dir` mutates the workspace native module ABI while rebuilding for packaged Electron. Rebuild `better-sqlite3` for Node before running Node/Vitest tests again in the same checkout.
- The packaging smoke does not prove real Apple notarization or Authenticode signing because those require external credentials.
