# Desktop Phase 4 Packaging Distribution

Category: `session-log`

Tags: `desktop`, `electron`, `release`, `auto-update`, `code-signing`, `sentry`

## Summary

Electron Desktop Phase 4 is implemented for packaging and distribution. The
desktop app now has electron-builder multi-platform targets, CI release matrix
builds, backend-gated stable/beta update checks, electron-updater metadata,
Sentry crash reporting, and release documentation for signing and channel
operations.

## Changes

- Added `apps/desktop-app/electron-builder.yml` for GitHub Releases publishing,
  stable/beta update metadata, macOS dmg/zip, Windows NSIS, Linux AppImage/deb/rpm,
  hardened runtime entitlements, protocol registration, and blockmap generation.
- Added macOS signing resources under `apps/desktop-app/build/` and the
  `scripts/notarize.mjs` after-sign hook. Local unsigned builds skip
  notarization; CI uses Apple API key or Apple ID credentials when configured.
- Added `apps/desktop-app/src/services/desktop-updates.ts` with
  `electron-updater`, channel resolution, backend update policy checks, update
  IPC handlers, renderer status events, and packaged-app startup checks.
- Added `/api/desktop/updates/check` in `services/api-server/app/api/desktop_sync.py`
  with stable/beta semver comparison, platform-specific metadata file selection,
  GitHub Release/feed URL generation, and regression tests.
- Added Sentry crash reporting in `apps/desktop-app/src/services/crash-reporting.ts`
  with release/channel metadata, main-process exception capture, and renderer
  crash/unresponsive capture.
- Extended `.github/workflows/release.yml` with a macOS/Windows/Linux desktop
  build matrix, signing/notarization/AuthentiCode/Sentry secrets, Linux packaging
  dependencies, desktop artifact upload, and GitHub Release attachment.
- Extended `scripts/release.sh`, `docs/project-memory/runbooks/release.md`, and
  `docs/project-memory/runbooks/cicd.md` for desktop version bumping, signing secrets, update
  endpoint env vars, Sentry, beta/stable tags, and local validation commands.

## Verification

- `cd apps/desktop-app && npm run test -- src/__tests__/desktop-updates.test.ts src/__tests__/crash-reporting.test.ts` -> 2 files / 7 tests passed.
- `services/api-server/.venv/bin/python -m pytest services/api-server/tests/test_desktop_updates.py -q` -> 4 passed.
- `services/api-server/.venv/bin/python -m ruff check services/api-server/app/api/desktop_sync.py services/api-server/tests/test_desktop_updates.py` -> passed.
- `cd apps/desktop-app && npm run build:main` -> passed.
- `cd apps/desktop-app && npm run build:renderer` -> passed.
- `cd apps/desktop-app && npx electron-builder --dir --publish never` -> passed with expected local warnings for missing Developer ID signing identity and Apple notarization credentials.
- `ruby -e 'require "yaml"; YAML.load_file(".github/workflows/release.yml"); puts "release.yml YAML OK"'` -> `release.yml YAML OK`.
- `bash -n scripts/release.sh` -> passed.
- `python3 scripts/validate-docs.py` -> passed.
- `git diff --check` -> passed.

## Boundaries

- Local validation cannot prove real Apple notarization or Authenticode signing
  without private certificates. Release signing is wired through CI secrets.
- The desktop production build intentionally uses `tsconfig.build.json` to compile
  only the packaged Electron entrypoints and services; older offline-sync desktop
  test/type debt remains outside the packaging boundary.
- electron-builder reports unresolved dependency warnings from dependency
  traversal during local packaging, but the directory build completes and writes
  a packaged macOS app.
