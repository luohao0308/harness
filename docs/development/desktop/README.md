# Harness Desktop Production Guide

## Status

Harness Desktop is the Electron shell for the AI Harness Platform:

```text
Model + Harness = Agent
```

The latest startup performance gate is recorded in
`omx_wiki/session-2026-07-31-desktop-startup-performance-budget.md`. The broader
runtime smoke remains documented in
`omx_wiki/session-2026-07-04-desktop-full-function-startup-smoke.md`. Together
they cover packaged launch budgets, browser fallback, real Electron preload
bridge, `/desktop`, `/terminal`, packaging, and focused backend/frontend/desktop
test surfaces. This guide is the production operating entry point for desktop
development, release, and support.

Credential-gated boundaries remain explicit:

- Apple Developer ID signing and notarization require private Apple credentials.
- Windows Authenticode signing requires a private Windows certificate.
- Sentry sourcemap upload requires private Sentry credentials.
- Local packaging can prove builder shape, metadata, native module rebuilds, and
  updater metadata, but not external trust services.

## Product Contract

Desktop is not a marketing wrapper and not a second web console. It is the native
operating surface for internal testers who need local Agent execution, workspace
profile isolation, independent Run windows, offline work, local model fallback,
file access, native notifications, deep links, updates, and crash evidence.

The desktop first screen must answer:

1. Is the Electron bridge connected?
2. Which workspace profile is active?
3. What can I do now?
4. Where are the latest windows, offline tasks, and results?
5. What is local-only, backend-backed, or credential-gated?

## Capability Map

| Surface | User value | Runtime owner | Minimum acceptance |
| --- | --- | --- | --- |
| `/desktop` workbench | Desktop state, next actions, profiles, windows, offline tasks, local model, plugins, templates | Agent Console `AdvancedFeaturesPage` plus Electron preload bridge | Browser fallback renders; Electron bridge connected mode renders; no horizontal overflow |
| `/terminal` workspace | Four local shell panes for operator workflows | Agent Console terminal UI, `/ws/terminal` backend PTY, and Redis capability state | Four terminals render; authenticated one-time tokens work across API replicas; command output returns; terminal switching works |
| `/teams/:teamId` desktop Team workspace | Conversation-first collaboration, task dependency graph, and the existing web multi-column mode | Shared Agent Console Team renderer and existing Team HTTP/SSE APIs | Desktop defaults to collaboration; all three views preserve the same Team state; web remains multi-column by default |
| Profile isolation | Separate API base URL, auth token, and data path per workspace/account | `desktopApi.profile`, `phase6-store`, shared API resolver | Save, switch, and broadcast `profile:changed` |
| Independent Run windows | Review Runs without losing the main workbench | `desktopApi.window`, `window-manager` | `openRun(runId)` opens/focuses persisted Run window |
| Offline simple tasks | Keep useful local work available without network access | `desktopApi.offline`, `phase6-service` | Deterministic task completes; optional local model fails soft |
| Local model settings | Use Ollama or OpenAI-compatible local endpoints | `desktopApi.localModel` | Settings round-trip; fallback output remains deterministic when unavailable |
| File bridge | Root-scoped local file list/read/write/watch | `desktopApi.file`, `file-service` | Root selection is explicit; file operations stay under selected root |
| System integration | Tray, close-to-tray, login startup, shortcut, native menu, notifications, deep links | `desktopApi.system`, `system-integration` | Route events normalize to console routes; notifications click through |
| Updates | Stable/beta policy-gated desktop updates | `desktopApi.updates`, `/api/desktop/updates/check`, `electron-updater` | Backend policy is checked before updater download |
| Feedback and metrics | Beta feedback, startup timing, crash and sync health | `desktopApi.feedback`, desktop telemetry endpoints, Sentry | Feedback submits; metric summary reports startup/crash/sync evidence |
| Startup performance | Keep packaged launch latency within explicit phase and total budgets | `startup-performance`, `check-startup-budget.mjs`, Release matrix | Five isolated packaged samples produce P50/P95 evidence; every P95 stays within budget |
| Packaging | macOS, Windows, Linux release artifacts | `electron-builder.yml`, `.github/workflows/release.yml` | Local `--dir` package passes; CI signs/notarizes when secrets exist |

## Local Startup

The desktop Team presentation and screenshot contract is documented in
`docs/design/desktop/team-mode-workspace.md`.

Start the backend and Console through
`docs/project-memory/runbooks/local-development.md`, then launch Electron:

```bash
cd apps/agent-console
npm ci
npm run dev
```

```bash
cd apps/desktop-app
npm ci
npm run build:main
NO_PROXY=localhost,127.0.0.1 ELECTRON_RUN_AS_NODE= VITE_DEV_SERVER_URL=http://127.0.0.1:5173 electron .
```

Use the package script when the renderer has already been built or copied:

```bash
cd apps/desktop-app
npm start
```

Important local notes:

- Clear `ELECTRON_RUN_AS_NODE`; when it is inherited as `1`, Electron behaves as
  Node and `require("electron")` does not expose the real runtime API.
- Keep `NO_PROXY=localhost,127.0.0.1` so local API and Vite calls bypass global
  proxy settings.
- `electron-builder --dir` rebuilds native modules for Electron ABI. If Node
  tests fail afterward in the same checkout, rebuild `better-sqlite3` for Node
  before rerunning Vitest.

## Verification Matrix

Run the smallest matrix that proves the changed surface.

### Pull Request Desktop Gate

```bash
services/api-server/.venv/bin/python -m pytest \
  services/api-server/tests/test_desktop_sync.py \
  services/api-server/tests/test_desktop_sync_integration.py \
  services/api-server/tests/test_desktop_sync_operations.py \
  services/api-server/tests/test_desktop_updates.py \
  services/api-server/tests/test_plugins.py \
  services/api-server/tests/test_terminal_websocket.py \
  services/api-server/tests/test_terminal_capability_store.py -q

services/api-server/.venv/bin/python -m ruff check \
  services/api-server/app/api/desktop_sync.py \
  services/api-server/app/api/plugins.py \
  services/api-server/app/api/terminal.py \
  services/api-server/app/services/terminal_capability_store.py \
  services/api-server/app/main.py \
  services/api-server/tests/test_desktop_sync.py \
  services/api-server/tests/test_desktop_sync_integration.py \
  services/api-server/tests/test_desktop_sync_operations.py \
  services/api-server/tests/test_desktop_updates.py \
  services/api-server/tests/test_plugins.py \
  services/api-server/tests/test_terminal_websocket.py \
  services/api-server/tests/test_terminal_capability_store.py

cd apps/agent-console
npx vitest run \
  src/features/settings/pages/__tests__/AdvancedFeaturesPage.test.tsx \
  src/lib/__tests__/desktop-bridge.test.ts \
  src/features/agents/__tests__/WorkspaceShellBar.render.test.tsx \
  src/features/agents/__tests__/ChatSurface.shell.test.tsx \
  src/components/ui/__tests__/VirtualList.test.tsx \
  src/features/terminal/components/__tests__/TerminalWorkspace.test.tsx \
  src/features/terminal/components/__tests__/XtermTerminal.test.tsx \
  src/stores/__tests__/terminalStore.test.ts
npm run build

cd ../desktop-app
npm test
npm run build:main
```

### Release Candidate Gate

```bash
cd apps/desktop-app
npm run build:main
npm run build:renderer
npx electron-builder --dir --publish never
npm run test:startup-budget
npm run check:startup-budget
```

`check:startup-budget` launches the packaged executable and therefore requires a
desktop session. Release CI uses `xvfb-run` on Linux and native sessions on
macOS/Windows.

### Startup Performance Gate

The packaged smoke records monotonic milestones only after Electron app ready,
main-process services ready, and the main renderer load promise resolves. The
default budgets are:

| Phase | Budget |
| --- | ---: |
| Process start to Electron app ready | 2,000 ms |
| App ready to main-process services ready | 1,500 ms |
| Services ready to main renderer loaded | 3,500 ms |
| Process start to main renderer loaded | 6,000 ms |

The runner uses five fresh `userData` directories by default, verifies that each
report came from a packaged executable matching the host platform and
architecture, and fails when any phase P95 exceeds its budget. It writes
`dist/startup-budget-report-<platform>-<arch>.json` with raw samples, P50/P95,
budgets, and violations. Release CI uploads all three host reports alongside the
installers and does not create the GitHub Release when a gate fails.

Controlled overrides are available for performance-lab or slower dedicated
runners:

```text
HARNESS_DESKTOP_STARTUP_APP_READY_BUDGET_MS
HARNESS_DESKTOP_STARTUP_SERVICES_BUDGET_MS
HARNESS_DESKTOP_STARTUP_RENDERER_BUDGET_MS
HARNESS_DESKTOP_STARTUP_TOTAL_BUDGET_MS
HARNESS_DESKTOP_STARTUP_SAMPLES            # 1-10, default 5
HARNESS_DESKTOP_STARTUP_TIMEOUT_MS         # max 120000, default 30000
HARNESS_DESKTOP_STARTUP_REPORT_PATH
HARNESS_DESKTOP_EXECUTABLE
```

Budget overrides must be explicit CI configuration and reviewed like any other
release threshold change. Do not increase them to hide a regression.

Then prove runtime behavior:

- Browser smoke `http://127.0.0.1:5173/desktop`.
- Browser smoke `http://127.0.0.1:5173/terminal`.
- Real Electron smoke with `ELECTRON_RUN_AS_NODE=""` and
  `VITE_DEV_SERVER_URL=http://127.0.0.1:5173`.
- Release workflow parse and script syntax:

```bash
ruby -e 'require "yaml"; YAML.load_file(".github/workflows/release.yml"); puts "release.yml YAML OK"'
bash -n scripts/release.sh
python3 scripts/validate-docs.py
git diff --check
```

### External Promotion Gate

Before publishing a stable desktop release, CI must prove:

- macOS `dmg` and `zip` are signed with Developer ID and notarized.
- Windows `nsis` installers are Authenticode signed.
- Linux `AppImage`, `deb`, and `rpm` launch on supported architectures.
- macOS, Windows, and Linux startup reports are present and each packaged P95
  gate passed on the release runner.
- `latest*.yml` metadata and blockmaps match the GitHub Release assets.
- Stable clients ignore beta metadata; beta clients can opt into prerelease
  updates.
- Sentry release, sourcemaps, and crash events are visible in the target project.

## Release Operations

Stable releases use normal semver tags, for example:

```bash
git tag -a v0.2.0 -m "Release v0.2.0"
git push origin HEAD --tags
```

Beta releases use prerelease tags containing `-beta.`, for example:

```bash
git tag -a v0.3.0-beta.1 -m "Release v0.3.0-beta.1"
git push origin HEAD --tags
```

The release workflow builds desktop artifacts on macOS, Windows, and Linux and
attaches installers plus updater metadata to GitHub Releases. The backend update
policy is configured with:

```text
DESKTOP_UPDATE_STABLE_VERSION
DESKTOP_UPDATE_BETA_VERSION
DESKTOP_UPDATE_LATEST_VERSION
DESKTOP_UPDATE_GITHUB_REPO
DESKTOP_UPDATE_FEED_BASE_URL
DESKTOP_UPDATE_RELEASE_BASE_URL
DESKTOP_UPDATE_NOTES
```

See `docs/project-memory/runbooks/release.md` for the release script and signing secret names.

## Privacy And Security

Desktop must keep native trust boundaries visible:

- Renderer code talks to native APIs only through `contextBridge`.
- `nodeIntegration` stays disabled, `contextIsolation` stays enabled, and the
  Electron window sandbox stays enabled.
- File access is root-scoped; users choose or set the workspace root before
  list/read/write/watch operations.
- Workspace profiles contain API base URL, auth token, and local data path; do
  not expose tokens in screenshots, logs, crash reports, or feedback payloads.
- Feedback logs and screenshot data are user-initiated support payloads, not
  automatic telemetry.
- Crash reporting must redact credentials and bind events to release/channel
  metadata.
- Production Terminal capability state requires Redis. Token consumption,
  per-principal session caps, and renewable leases must remain shared across API
  replicas; production must fail closed when Redis is unavailable.
- Local model endpoints are optional. Failure to reach them must fall back to
  deterministic offline output without blocking the workbench.

## Support Playbook

| Symptom | Check | Recovery |
| --- | --- | --- |
| Electron opens as Node or exits before window creation | `env | grep ELECTRON_RUN_AS_NODE` | Relaunch with `ELECTRON_RUN_AS_NODE=` |
| `/desktop` says web fallback in Electron | DevTools console and `window.desktopApi` | Rebuild `build:main`, confirm preload path, relaunch Electron |
| Terminal panes render but commands do not return | API `/health`, `/ws/terminal`, browser console | Restart API server and verify backend terminal tests |
| Node/Vitest fails after packaging | Native module ABI for `better-sqlite3` | Rebuild `better-sqlite3` for Node, then rerun `npm test` |
| Updates never become available | `/api/desktop/updates/check` payload | Align backend version env with published GitHub Release metadata |
| macOS users see Gatekeeper warnings | Signing/notarization logs and CI secrets | Verify Developer ID certificate, hardened runtime, notarization, and staple |
| Feedback metrics missing | `/api/desktop` metric endpoints and Sentry DSN | Confirm backend endpoint auth, `HARNESS_DESKTOP_SENTRY_DSN`, and release env |

## Apple Platform References

Production macOS releases must follow Apple platform trust and design guidance:

- Apple Human Interface Guidelines: https://developer.apple.com/design/human-interface-guidelines
- HIG Accessibility: https://developer.apple.com/design/human-interface-guidelines/accessibility
- HIG Settings: https://developer.apple.com/design/human-interface-guidelines/settings
- HIG Notifications: https://developer.apple.com/design/human-interface-guidelines/notifications
- HIG Menu Bar: https://developer.apple.com/design/human-interface-guidelines/the-menu-bar
- Notarizing macOS software before distribution: https://developer.apple.com/documentation/security/notarizing_macos_software_before_distribution
- Hardened Runtime: https://developer.apple.com/documentation/security/hardened_runtime
