# Desktop Startup Performance Budget

Category: `session-log`

Tags: `desktop`, `electron`, `startup`, `performance`, `release`, `ci`

## Outcome

Closed the documented repository gap for measured packaged Electron startup.
The main process now records monotonic app-ready, services-ready, and
renderer-loaded milestones, while the release workflow launches the packaged
host executable five times and blocks publication when any phase or total P95
exceeds its budget.

## Production Contract

- Default budgets are 2,000 ms to app ready, 1,500 ms from app ready to services
  ready, 3,500 ms from services ready to renderer loaded, and 6,000 ms total.
- The renderer milestone is recorded only after `BrowserWindow.loadURL(...)`
  resolves; smoke mode flushes its machine-readable report before exiting.
- Each sample uses a fresh `userData` directory and must be schema v1, packaged,
  internally consistent, and match the runner platform and architecture.
- Five samples are aggregated with nearest-rank P50/P95. Phase budgets must be
  identical across the sample set; any P95 violation fails the gate.
- Reports are written as
  `dist/startup-budget-report-<platform>-<arch>.json`, preventing cross-platform
  overwrite when GitHub Actions merges desktop artifacts.
- The compatible backend `startup_time_ms` metric is preserved and carries the
  structured phase report, budget result, and violation count. Delivery remains
  fail-soft when the API is offline.
- Release CI runs contract tests before packaging, uses Xvfb for Linux launch,
  uploads every platform report, and requires all Desktop matrix jobs before
  creating the GitHub Release.

## Key Files

- `apps/desktop-app/src/services/startup-performance.ts`
- `apps/desktop-app/src/main.ts`
- `apps/desktop-app/src/services/desktop-telemetry.ts`
- `apps/desktop-app/scripts/check-startup-budget.mjs`
- `apps/desktop-app/scripts/startup-budget-lib.mjs`
- `apps/desktop-app/scripts/startup-budget-lib.test.mjs`
- `.github/workflows/release.yml`

## Verification

- Startup aggregation contract: `5 passed`.
- Focused Desktop release/startup regression: `7 files / 40 tests passed`.
- Electron main-process TypeScript build: passed.
- Startup script syntax checks: passed.
- Release workflow YAML parse: passed.
- Git whitespace validation: passed.
- A pre-final-hardening full Desktop run passed `32 files / 286 tests`. The final
  full rerun reached `27 files / 201 tests passed`; the remaining five SQLite
  files could not load `better-sqlite3` because packaging had changed the native
  ABI and the required rebuild could not write user caches inside the sandbox.

## Verification Boundary

No local native P50/P95 result is claimed. The sandbox launch exited without a
report, and the approved GUI retry returned 503 from the external approval
service. Restoring the Node ABI for another full Vitest run hit the same approval
service after sandbox cache writes were denied. The implementation, contracts,
build, workflow, and documentation gates are verified. A directory package had
passed before the final report-validation/stdout-flush hardening; the latest
rebuild stopped only when `node-gyp` could not write `~/.electron-gyp`, and its
approved retry hit the same 503. The first authoritative native measurement will
be the macOS/Windows/Linux Release matrix.
