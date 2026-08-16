# Desktop Packaged Runtime And Bundle Closure

Category: `session-log`

Tags: `desktop`, `electron`, `packaging`, `performance`, `security`, `native-smoke`

## Outcome

The Agent Console performance goal and the real packaged Electron runtime are
closed for the repository-controlled surface.

- Modular ECharts registration and route-level chunking reduced the largest
  JavaScript asset to `504,967` bytes, below the `512,000` release gate.
- The desktop renderer build now rebuilds Agent Console with relative assets,
  a hash router, loopback HTTP/WS defaults, and a trusted internal
  `harness-app://renderer` origin.
- Packaged windows no longer load a blank `file://` page or rewrite loopback
  API URLs to the renderer hostname.
- API CORS and terminal WebSocket origin checks accept only the exact trusted
  desktop renderer origin in addition to existing loopback development origins.
- Auth bootstrap treats HTTP 401 as an anonymous login state while preserving
  network and server failures as actionable API errors.

## Native Evidence

The unsigned x64 unpacked app was built at:

```text
apps/desktop-app/release/mac/Harness Desktop.app
```

Playwright `_electron` launched that packaged executable against the real local
Harness API and verified:

- startup URL `harness-app://renderer/index.html#/`;
- a nonblank Dashboard with `desktopApi` available and no console, page, or
  request failures;
- native IPC route transition to `#/desktop` with the `桌面工作台` heading and
  offline-task controls;
- simulated HTTP 401 bootstrap transition to `#/login?next=%2F`, with the login
  heading visible and no false API-connection error.

## Verification

```text
cd apps/agent-console && npm run build && ../../scripts/check-bundle-size.sh dist && npm test -- --run --pool forks --poolOptions.forks.singleFork
passed: largest_js=504967; 95 files / 719 tests

cd apps/desktop-app && npm rebuild better-sqlite3 && npm test && npm run build:main
passed: 31 files / 278 tests; main build passed

cd services/api-server && .venv/bin/python -m pytest tests/test_cors.py tests/test_terminal_websocket.py -q
passed: 12 tests

cd services/api-server && .venv/bin/python -m ruff check app/main.py app/api/terminal.py tests/test_cors.py tests/test_terminal_websocket.py
passed

cd apps/desktop-app && npm run build:main && npm run build:renderer && ../../scripts/check-bundle-size.sh dist/renderer && npx electron-builder --dir --publish never
passed; signing and notarization skipped because credentials are not configured
```

## Remaining External Gates

- Apple Developer ID signing and notarization.
- Windows Authenticode signing.
- Production Sentry credentials and sourcemap upload.
- Shared terminal capability/session state for multi-replica API deployments.
