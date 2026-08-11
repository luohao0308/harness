# Desktop Phase 6 Advanced Features

Category: `session-log`

Tags: `desktop`, `electron`, `plugins`, `workspace-isolation`, `accessibility`, `offline`, `performance`

## Summary

Desktop Phase 6 is implemented as a targeted advanced-features slice across the
Electron main process, Agent Console, and FastAPI backend. It adds independent
Agent Run windows with persisted window state, workspace/account profile
isolation, plugin marketplace and Prompt template APIs, offline simple-task
execution with optional local-model inference, virtualized long-chat rendering,
and high-contrast accessibility controls.

## Changes

- Added `services/api-server/app/api/plugins.py` and registered it from
  `services/api-server/app/main.py`, exposing org-scoped marketplace
  install/uninstall plus Prompt template list/create/update/delete APIs.
- Stored plugin installations and Prompt templates in existing `SystemSetting`
  rows keyed by organization, so the slice avoids a migration while preserving
  workspace isolation.
- Added Electron Phase 6 services for persisted profiles, active profile,
  Run-window bounds, local-model settings, offline task history, and
  deterministic local fallback results under `app.getPath("userData")`.
- Added independent Run windows keyed by active profile and Run id. Reopening a
  Run focuses the existing window, restores persisted bounds/maximized state,
  and routes to `/runs/{run_id}` through the desktop route bridge.
- Extended the preload API with profile, window, offline-task, and local-model
  IPC surfaces.
- Added Agent Console `/settings/advanced` for workspace profiles, Run windows,
  offline tasks, local-model configuration, plugin marketplace controls, Prompt
  templates, and high-contrast mode.
- Added a WorkspaceShellBar action to open the current Run in a separate desktop
  window when the Electron bridge is available.
- Extended `VirtualList` with stable item keys and ARIA list/listitem semantics,
  and virtualized `ChatMessageList` for conversations over 120 nodes.
- Added high-contrast CSS and startup restoration from `localStorage`.

## Verification

- `services/api-server/.venv/bin/python -m pytest services/api-server/tests/test_plugins.py -q` -> 2 passed.
- `services/api-server/.venv/bin/python -m ruff check services/api-server/app/api/plugins.py services/api-server/app/main.py services/api-server/tests/test_plugins.py` -> passed.
- `cd apps/desktop-app && npm test -- src/__tests__/phase6-service.test.ts src/__tests__/window-manager.test.ts src/__tests__/preload.test.ts src/__tests__/main.test.ts src/__tests__/lifecycle.test.ts` -> 28 passed.
- `cd apps/desktop-app && npm run build:main` -> passed.
- `cd apps/agent-console && npx vitest run src/components/ui/__tests__/VirtualList.test.tsx src/features/settings/pages/__tests__/AdvancedFeaturesPage.test.tsx` -> 3 passed.
- `cd apps/agent-console && npx tsc --noEmit ... <phase-6-touched-files>` -> passed.
- `python3 scripts/validate-docs.py` -> passed.
- `git diff --check` -> passed.

## Boundaries

- Plugin marketplace entries are curated in the backend for this slice; external
  package upload, remote plugin signing, and executable third-party plugin code
  remain future hardening.
- Offline execution supports deterministic local results and optional local
  model calls. It does not replace the audited online Agent Run path; results can
  be carried forward when connectivity returns.
- The startup/performance work is focused on the Phase 6 surface: virtualized
  long conversations, compact advanced settings, and desktop main-process build
  validation. A full measured startup budget harness remains future work.
- Full repo-wide Agent Console build still has unrelated stale TypeScript/a11y
  debt outside the touched Phase 6 files, so completion evidence is targeted
  frontend tests plus touched-file TypeScript.
