# Desktop Functional Screenshot Audit

Category: `session-log`

Tags: `desktop`, `electron`, `agent-console`, `screenshots`, `browser-smoke`, `docx`, `verification`

## Summary

The native Electron desktop was relaunched with isolated user data, repaired
after a `better-sqlite3` ABI mismatch, and verified through a deterministic
offline task. The current web console was captured across 25 primary routes,
historical web screenshots were curated into a non-destructive archive, and a
32-page functional screenshot catalog was produced with 38 inline images.

## Runtime Results

- Electron started with the native desktop bridge connected and zero sync
  errors after rebuilding `better-sqlite3`.
- A desktop offline task reached `status=completed` with
  `modelSource=deterministic-local`; the result and queue action are visible in
  the accepted desktop screenshots.
- Unauthenticated desktop sync returned `401 Unauthorized` and entered the
  scheduled retry path. This is recorded as an authentication gate, not an
  offline-execution failure.
- The API, Agent Console Vite server, and Electron process remained running at
  the end of the audit.
- The host continued to emit non-blocking Electron EGL warnings while window
  creation and offline execution succeeded.

## Screenshot Inventory

- `docs/design/media/screenshots/2026-08-05/web-current/` contains 25 current web feature
  captures. Twenty-three show a functional or intentional redirect state.
- `15-specialists.png` records the stable terminal error
  `子代理加载失败，请检查 ID 或权限。` instead of the earlier loading skeleton.
- `23-data-management.png` records the expanded `/settings/data` error boundary
  with `404 Not Found`.
- `07-knowledge.png`, `09-sandboxes.png`, and `25-tools-config.png` were
  recaptured after their data requests reached stable rendered states.
- `docs/design/media/screenshots/2026-08-05/desktop-current/` contains nine native desktop
  captures. `07`, `08`, and `09` are the strongest current relaunch, execution,
  and completed-result evidence.
- `docs/design/media/screenshots/archive/web-legacy/2026-06-21/` contains 20 accepted legacy
  files, and `2026-08-04-team-mode/` contains five Team Mode visual outputs.
  Originals were copied, not moved or deleted.

## Verification

- Desktop-related backend pytest -> `43 passed`.
- Desktop Vitest -> `32 files / 287 tests passed`.
- Desktop startup contracts -> `5 passed`.
- Desktop `build:main` -> passed.
- Agent Console production build -> passed, `2408 modules`.
- Release browser smoke -> `12 passed / 38 failed`; failures predominantly
  cluster around stale auth and new-request fixtures and are kept separate from
  the two visible product defects.
- DOCX image audit -> 38 inline images.
- DOCX accessibility audit -> high 0, medium 0, low 0.
- DOCX style lint -> expected direct-formatting and figure-title notices only.
- Canonical DOCX render -> 32 pages; every page inspected with no clipping,
  overlap, missing glyphs, broken tables, or misplaced page furniture.
- `python3 scripts/validate-docs.py` -> passed.
- `git diff --check` -> passed.

## Deliverables

- `docs/工作日志/reports/harness-desktop-web-functional-screenshot-catalog-2026-08-07.docx`
- `docs/design/media/screenshots/README.md`
- Current desktop/web screenshot directories and the historical web archive
  listed above.

## Follow-up

- Restore `/settings/data` and its loader/API contract.
- Repair `/subagents/specialists` route resolution or its ID/permission
  contract.
- Refresh shared Playwright fixtures for `/api/auth/me`, Agent list parameters,
  and local-Agent connection requests.
- Retest desktop sync with an authenticated Electron session.
