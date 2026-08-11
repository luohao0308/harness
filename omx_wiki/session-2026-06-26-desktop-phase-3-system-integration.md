# Desktop Phase 3 System Integration

Category: `session-log`

Tags: `desktop`, `electron`, `system-integration`, `tray`, `notifications`, `deep-link`

## Summary

Electron Desktop Phase 3 is implemented as a native integration layer around the existing Agent Console. The app now supports tray/background operation, native notifications with click-through routing, login-startup toggles, global wake shortcut, `agentharness://` deep links, and platform-style native menus.

## Implementation

- Added `apps/desktop-app/src/services/system-integration.ts` for tray setup, close-to-tray behavior, menu templates, login item IPC, global `CommandOrControl+Shift+A` wake shortcut, notification routing, single-instance handling, and `agentharness://` route parsing.
- Updated `apps/desktop-app/src/main.ts` to register early protocol handlers, keep the app alive after all windows close, hide instead of closing when tray is available, and restore the hidden window on macOS activate.
- Exposed `desktopApi.system` and `events.onOpenRoute` through preload so renderer code can show/hide the window, query/set startup, show native notifications, consume pending deep-link routes, and receive route-open events.
- Wired Agent SSE terminal/conflict/error events to native notifications, with notification clicks navigating to Run detail routes.
- Added `apps/agent-console/src/lib/desktop-bridge.ts` and installed it in `apps/agent-console/src/main.tsx` so pending and live desktop routes navigate through the console router.
- Registered the `agentharness` protocol in Electron builder metadata.

## Verification

- `cd apps/desktop-app && CI=1 npm test` -> 21 files / 223 tests passed.
- `cd apps/agent-console && npx vitest run src/lib/__tests__/desktop-bridge.test.ts` -> 1 file / 3 tests passed.
- `cd apps/desktop-app && npm run type-check` remains blocked by existing desktop TypeScript debt in old tests, DOM `window` / `navigator` lib usage, sqlite/json `unknown` typing, and shared api-client generic typing; no Phase 3 file appears in the error list.
- `cd apps/agent-console && npm run lint` remains blocked by existing repo-wide TypeScript/a11y debt around `jest-axe` declarations, stale a11y imports, old `ChatMessageBubble` props, missing Eval/Tools `tasks/api` exports, and SAML fixture shape changes; no desktop bridge file appears in the error list.

## Notes

Deep-link coverage includes explicit route links, Run/Team/Agent query links, host-path links, and triple-slash route links. Native menus use cross-platform Electron roles where possible and Chinese-first labels for Harness-specific actions.
