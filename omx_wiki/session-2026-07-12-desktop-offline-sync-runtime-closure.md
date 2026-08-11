# Desktop Offline Sync Runtime Closure

Category: `session`

Tags: `desktop`, `offline-sync`, `sqlite`, `ipc`, `startup`, `backoff`, `auth`

## Outcome

Desktop app startup now wires a profile-scoped SQLite offline sync runtime that owns task, queue, and sync-metadata stores, uses the existing main-process API client for authenticated sync requests, auto-syncs on reconnect with bounded exponential backoff, exposes status/conflicts via IPC, and closes DB/network resources on quit.

## Changed Surface

- `apps/desktop-app/src/main.ts`
- `apps/desktop-app/src/services/offline-sync-runtime.ts`
- `apps/desktop-app/src/services/sqlite-sync-service.ts`
- `apps/desktop-app/src/services/sync-service.ts`
- `apps/desktop-app/src/services/window-manager.ts`
- focused desktop tests for sync, runtime, lifecycle, and Phase 6 integration

## Verification

- `cd apps/desktop-app && npm test -- src/services/__tests__/sync-service.test.ts src/services/__tests__/offline-sync-runtime.test.ts src/stores/__tests__/offline-queue.test.ts src/stores/__tests__/task-store.test.ts src/services/__tests__/sync-metadata.test.ts src/__tests__/lifecycle.test.ts src/__tests__/phase6-service.test.ts` -> `7 files / 93 tests passed`
- `cd apps/desktop-app && npm run build:main` -> passed
- `cd apps/desktop-app && npm test` -> `30 files / 276 tests passed`

## Notes

- Phase 6 offline simple tasks are still separate from sync by default.
- A dedicated `offline:promote-result-to-pending-agent-task` IPC now turns a completed offline result into a pending Agent task queue entry.
- Sync telemetry is best effort and does not block the runtime.
