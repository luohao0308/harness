# Desktop Workbench Document Polish

Category: `session-log`

Tags: `desktop`, `agent-console`, `electron`, `ui-polish`, `design`

## Summary

Desktop now has a first-class `/desktop` Agent Console workbench instead of being discoverable only through `/settings/advanced`. The page keeps the existing Electron Desktop capabilities but presents them as a concise operating document: current state, immediate actions, metrics, chapters, folded configuration, and recent results.

## Changed

- `DESIGN.md` now lists `/desktop` / `/settings/advanced` as a primary desktop product surface and records the desktop workbench rule: explicit title, short chapters, scannable state, actions near evidence, folded configuration.
- `apps/agent-console/src/app/consoleNav.ts` adds the top-level `桌面` nav item.
- `apps/agent-console/src/app/routes.tsx` adds `/desktop` and keeps `/settings/advanced` routed to the same page.
- `apps/agent-console/src/app/ConsoleShell.tsx` maps the desktop nav icon.
- `apps/agent-console/src/features/settings/pages/AdvancedFeaturesPage.tsx` is reworked into a document-style workbench with:
  - bridge/offline mode badges;
  - `现在可做` action steps;
  - desktop state metrics;
  - sticky chapter navigation;
  - workspace/window, offline execution, plugin/template, and recent-result sections;
  - folded Profile, local-model, and prompt-template configuration;
  - explicit `ollama` / `openai-compatible` local-model provider choice.
- `apps/desktop-app/src/__tests__/lifecycle.test.ts` now matches the asynchronous main-process startup path by waiting for the activate handler and mocking real Electron `app.isReady()`.

## Verification

- `cd apps/agent-console && npx vitest run src/features/settings/pages/__tests__/AdvancedFeaturesPage.test.tsx` -> 2 passed.
- `cd apps/agent-console && npx tsc --noEmit --pretty false --types vite/client,vitest/globals,@testing-library/jest-dom --skipLibCheck --jsx react-jsx --lib DOM,DOM.Iterable,ES2022 --module ESNext --moduleResolution Bundler --target ES2020 --esModuleInterop --allowSyntheticDefaultImports src/app/consoleNav.ts src/app/ConsoleShell.tsx src/app/routes.tsx src/features/settings/pages/AdvancedFeaturesPage.tsx src/features/settings/pages/__tests__/AdvancedFeaturesPage.test.tsx src/vite-env.d.ts` -> passed.
- `cd apps/agent-console && npm run build` -> passed with existing chunk-size warning.
- `cd apps/desktop-app && npm test -- src/__tests__/phase6-service.test.ts src/__tests__/window-manager.test.ts src/__tests__/preload.test.ts src/__tests__/main.test.ts src/__tests__/lifecycle.test.ts` -> 28 passed.
- `cd apps/desktop-app && npm run build:main` -> passed.
- Browser verification on `http://127.0.0.1:5173/desktop` at 1440x980 -> `桌面工作台`, `现在可做`, `章节`, and `桌面状态摘要` rendered; horizontal overflow 0; console errors/warnings 0; screenshot `/tmp/harness-desktop-page.png`.
- Browser verification on `http://127.0.0.1:5173/desktop` at 390x844 -> `桌面工作台` rendered; horizontal overflow 0; console errors/warnings 0; screenshot `/tmp/harness-desktop-page-mobile.png`.
- Electron desktop verification via Playwright `_electron` on `http://localhost:5173/desktop` -> desktop window launched after clearing a stale local Electron single-instance process, route `/desktop`, title `桌面工作台`, desktop bridge connected, `现在可做` and `桌面状态摘要` rendered; horizontal overflow 0; screenshot `/tmp/harness-electron-desktop-page.png`; only the expected Electron development CSP warning was logged.
- `NO_PROXY=127.0.0.1,localhost curl --max-time 3 http://127.0.0.1:8000/health` -> 200.
- `git diff --check` -> passed.

## Notes

- `/settings/advanced` remains valid for old links.
- The first two browser checks intentionally cover web fallback mode. The final Electron smoke covers the same page with the real preload bridge connected.
- Electron development mode logs the standard insecure-CSP warning for Vite; the warning states it does not show once packaged.
