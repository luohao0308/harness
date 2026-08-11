# Desktop Full Function Startup Smoke Rerun

Category: `session-log`

Tags: `desktop`, `electron`, `agent-console`, `terminal`, `packaging`, `smoke-test`, `verification`

## Summary

The desktop app was started and tested again end to end for the user request to
start and test all desktop functions. This rerun covered backend desktop APIs,
Agent Console desktop and terminal surfaces, Electron main/preload/native
integrations, local packaging, browser runtime, and real Electron runtime.

## Verification

- `services/api-server/.venv/bin/python -m pytest services/api-server/tests/test_desktop_sync.py services/api-server/tests/test_desktop_sync_integration.py services/api-server/tests/test_desktop_sync_operations.py services/api-server/tests/test_desktop_updates.py services/api-server/tests/test_plugins.py services/api-server/tests/test_terminal_websocket.py -q` -> 30 passed.
- `services/api-server/.venv/bin/python -m ruff check services/api-server/app/api/desktop_sync.py services/api-server/app/api/plugins.py services/api-server/app/api/terminal.py services/api-server/app/main.py services/api-server/tests/test_desktop_sync.py services/api-server/tests/test_desktop_sync_integration.py services/api-server/tests/test_desktop_sync_operations.py services/api-server/tests/test_desktop_updates.py services/api-server/tests/test_plugins.py services/api-server/tests/test_terminal_websocket.py` -> passed.
- `cd apps/agent-console && npx vitest run src/features/settings/pages/__tests__/AdvancedFeaturesPage.test.tsx src/lib/__tests__/desktop-bridge.test.ts src/features/agents/__tests__/WorkspaceShellBar.render.test.tsx src/features/agents/__tests__/ChatSurface.shell.test.tsx src/components/ui/__tests__/VirtualList.test.tsx src/features/terminal/components/__tests__/TerminalWorkspace.test.tsx src/features/terminal/components/__tests__/XtermTerminal.test.tsx src/stores/__tests__/terminalStore.test.ts` -> 8 files / 58 tests passed.
- `cd apps/agent-console && npm run build` -> passed with the existing large-chunk warning.
- `cd apps/desktop-app && npm test` -> 28 files / 259 tests passed before packaging.
- `cd apps/desktop-app && npm run build:main` -> passed.
- `cd apps/desktop-app && npm run build:renderer` -> copied Agent Console renderer into `apps/desktop-app/dist/renderer`.
- `cd apps/desktop-app && npx electron-builder --dir --publish never` -> passed with expected local unsigned/notarization warnings.
- Browser smoke on `http://127.0.0.1:5173/desktop` -> `桌面工作台`, `桌面状态摘要`, web fallback badge, `系统与发布`, horizontal overflow 0, console/page errors 0, screenshot `/tmp/harness-desktop-browser-1783100880239.png`.
- Browser smoke on `http://127.0.0.1:5173/terminal` -> 4 xterm containers, `echo browser-terminal-ok-1783100880239` output returned, Terminal 4 switching visible, horizontal overflow 0, console/page errors 0, screenshot `/tmp/harness-terminal-browser-1783100880239.png`.
- Real Electron smoke with isolated user data, `ELECTRON_RUN_AS_NODE=""`, `--no-proxy-server`, and temporary Vite `http://127.0.0.1:5174` -> bridge namespaces `agent`, `events`, `feedback`, `file`, `localModel`, `offline`, `profile`, `system`, `task`, `updates`, and `window` present; Profile save/switch restored to default; offline deterministic task completed; local-model settings round-tripped; file root set/list/read/write/watch/clear passed; startup state returned boolean; update check returned dev `not-available`; feedback metric/submission passed; Agent/task IPC reached the backend auth gate; independent Run window opened; terminal returned `echo electron-terminal-ok-1783101754057`; 2 Electron windows observed; screenshots `/tmp/harness-desktop-electron-1783101754057.png` and `/tmp/harness-terminal-electron-1783101754057.png`.
- `NO_PROXY=127.0.0.1,localhost curl --max-time 3 http://127.0.0.1:8000/health` -> 200.
- `NO_PROXY=127.0.0.1,localhost curl --max-time 3 -I http://127.0.0.1:5173/desktop` -> 200.
- `python3 scripts/validate-docs.py` -> passed.
- `ruby -e 'require "yaml"; YAML.load_file(".github/workflows/release.yml"); puts "release.yml YAML OK"'` -> passed.
- `bash -n scripts/release.sh` -> passed.
- `cd apps/desktop-app && npm rebuild better-sqlite3` -> rebuilt dependencies successfully after packaging changed the ABI.
- `cd apps/desktop-app && npm test -- src/stores/__tests__/task-store.test.ts src/stores/__tests__/offline-queue.test.ts src/services/__tests__/sync-metadata.test.ts` -> 65 passed.
- `cd apps/desktop-app && npm test` -> 28 files / 259 tests passed after Node ABI rebuild.
- `git diff --check` -> passed.

## Notes

- The shell still inherited `ELECTRON_RUN_AS_NODE=1`; real Electron startup was
  launched with that variable cleared.
- An interrupted Electron smoke left stale normal userData singleton state. The
  final real Electron proof used an isolated `/tmp/harness-electron-user-data-*`
  directory, then verified no temporary Electron/Vite processes remained.
- `agent` and `task` preload IPC calls reached the backend and returned the
  expected `401 Unauthorized` gate without a desktop auth token. Native desktop
  APIs were exercised directly.
- `electron-builder --dir` rebuilds `better-sqlite3` for Electron ABI. The
  checkout was rebuilt back to the current Node ABI and full desktop tests
  passed afterward.
- Local packaging does not prove Apple notarization or Windows Authenticode
  signing because those require external credentials.
