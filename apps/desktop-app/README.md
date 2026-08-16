# Harness Desktop App

Electron desktop shell for the AI Harness Platform. Product, design, release,
and support guidance lives in:

- `docs/development/desktop/README.md`
- `docs/design/desktop/apple-style-guidelines.md`
- `DESIGN.md`

## Scripts

| Command | Purpose |
| --- | --- |
| `npm start` | Launch Electron against the local renderer/dev setup with localhost proxy bypass and `ELECTRON_RUN_AS_NODE` cleared |
| `npm run dev` | Watch the Electron main process with `tsx` |
| `npm test` | Run desktop Vitest coverage |
| `npm run build:main` | Compile Electron main/preload/services through `tsconfig.build.json` |
| `npm run build:renderer` | Build Agent Console with desktop-relative assets and copy it into `dist/renderer` |
| `npm run package` | Build main/renderer and run `electron-builder --dir` |
| `npm run dist:mac` | Build macOS `dmg` and `zip` targets |
| `npm run dist:win` | Build Windows `nsis` targets |
| `npm run dist:linux` | Build Linux `AppImage`, `deb`, and `rpm` targets |
| `npm run test:startup-budget` | Test executable discovery, report validation, percentile aggregation, and budget failure contracts |
| `npm run check:startup-budget` | Launch the host-architecture packaged app five times and write its P50/P95 startup report |

## Local Launch

Start the API and Agent Console first:

```bash
cd services/api-server
source .venv/bin/activate
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

```bash
cd apps/agent-console
npm run dev
```

Then launch Electron:

```bash
cd apps/desktop-app
npm run build:main
NO_PROXY=localhost,127.0.0.1 ELECTRON_RUN_AS_NODE= VITE_DEV_SERVER_URL=http://127.0.0.1:5173 electron .
```

## Verification

Focused desktop verification:

```bash
cd apps/desktop-app
npm test
npm run build:main
npm run build:renderer
npx electron-builder --dir --publish never
npm run test:startup-budget
npm run check:startup-budget
```

The packaged startup gate writes
`dist/startup-budget-report-<platform>-<arch>.json`. It requires a desktop
session; Linux CI runs it through Xvfb. Release CI downloads the three platform
artifacts into separate directories, validates them again with
`scripts/validate-startup-budget-artifacts.mjs`, and publishes one
`desktop-startup-evidence.json` summary before GitHub Release creation.

The full production desktop matrix is documented in
`docs/development/desktop/README.md#verification-matrix`.

## Source Map

- `src/main.ts`: app startup, handler registration, packaged update check.
- `src/preload.ts` and `src/preload-api.ts`: renderer-safe desktop bridge.
- `src/services/window-manager.ts`: main and Run window creation/persistence.
- `src/services/system-integration.ts`: tray, native menu, login startup,
  shortcut, notifications, and `agentharness://` routing.
- `src/services/phase6-service.ts`: profiles, offline tasks, local model
  settings.
- `src/services/file-service.ts`: selected-root file bridge and watcher.
- `src/services/desktop-updates.ts`: backend-gated `electron-updater` workflow.
- `src/services/crash-reporting.ts`: Sentry and renderer crash capture.
- `src/services/startup-performance.ts`: monotonic startup milestones, phase
  budgets, report schema, and smoke-mode detection.
- `scripts/check-startup-budget.mjs`: isolated packaged startup samples and
  P50/P95 release gate.
- `scripts/validate-startup-budget-artifacts.mjs`: cross-platform artifact
  identity, sample-count, aggregate-integrity, and P95 release gate.

## Local Pitfalls

- `ELECTRON_RUN_AS_NODE=1` makes Electron run as Node. Clear it for real
  Electron smoke tests.
- `electron-builder --dir` rebuilds native modules for Electron ABI. Rebuild
  `better-sqlite3` for Node before running Node/Vitest tests again if ABI errors
  appear.
- Local unsigned macOS packages are not production notarization evidence. CI
  must provide Developer ID and notarization credentials for that claim.
