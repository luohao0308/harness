# Desktop Production Hardening Closeout

Category: `session-log`

Tags: `desktop`, `electron`, `security`, `offline-sync`, `updates`, `privacy`, `e2e`

## Outcome

The desktop production-hardening pass is complete for the repository-controlled
surface. The implementation now covers authenticated terminal capabilities,
encrypted profile credentials, a symlink-safe atomic file bridge, gated update
state transitions, profile-scoped offline sync, privacy redaction, local-model
trust boundaries, secure Electron navigation, and renderer status/control
surfaces.

The closeout also restored the Agent Console production build by adding the
missing deterministic enterprise coverage report. The report is generated from
the current navigation, route, cross-feature Playwright, and official pricing
source evidence instead of hard-coded pass flags.

## Production Gates

- Terminal access uses authenticated 30-second one-time capability tokens,
  principal and terminal binding, reuse/expiry rejection, active-session caps,
  a scrubbed environment, and an explicit cwd.
- Profile credentials migrate from plaintext state to Electron `safeStorage` or
  session-only storage; renderer IPC receives metadata only.
- File operations reject symlink traversal, enforce root containment and a 1 MiB
  write cap, and use same-directory atomic rename writes.
- Updates require trusted HTTPS feeds and explicit available/downloaded state
  transitions; renderer-created windows and cross-origin navigation are denied.
- Offline sync owns profile-scoped SQLite resources, authenticated operation
  push, reconnect backoff, conflicts, manual sync, promotion from offline result,
  and quit cleanup.
- Crash/feedback payloads redact credentials and user-home paths recursively.
- Local-model calls default to loopback, require an explicit environment opt-in
  for remote endpoints, time out after 10 seconds, and expose health/fallback
  evidence.

## Verification

- `cd apps/desktop-app && npm test` -> `30 files / 276 tests passed`
- `cd apps/desktop-app && npm run build:main` -> passed
- Desktop backend matrix -> `37 passed`
- Desktop backend Ruff scope -> passed
- Agent Console desktop/terminal/API Vitest -> `6 files / 34 tests passed`
- Agent Console desktop workbench Vitest -> `4 passed`
- Enterprise coverage report Vitest -> passed
- `cd apps/agent-console && npm run build` -> passed
- Enterprise Playwright sidebar, chain, and pricing suites -> `52 passed`
- `cd apps/agent-console && npx playwright test --list` -> `332 tests in 31 files`
- `python3 scripts/validate-docs.py` -> passed
- `git diff --check` -> passed

## Remaining External Gates

- Real Apple Developer ID signing and notarization still require release
  credentials and an external notarization round trip.
- Windows Authenticode and production Sentry sourcemap upload remain
  credential-gated release operations.
- Terminal capability/session state was subsequently moved to Redis atomic
  shared state with renewable leases in
  [[session-2026-07-12-terminal-capability-shared-state]].
- Packaged Electron native smoke was repeated in the follow-up
  [[session-2026-07-12-desktop-packaged-runtime-and-bundle-closure]], including
  trusted renderer origin, API CORS, Dashboard, `/desktop` IPC routing, and 401
  login bootstrap evidence.
