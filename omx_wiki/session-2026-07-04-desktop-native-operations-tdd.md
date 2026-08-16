# Desktop Native Operations TDD

Category: `session`

Tags: `desktop`, `electron`, `agent-console`, `tdd`, `apple-style`, `native-operations`

## Summary

Implemented the first code slice from the desktop production documentation using
TDD. The desktop docs promised that `/desktop` would surface native operations
for settings, updates, feedback, file roots, and system startup. The previous
workbench covered Profile, Run windows, offline tasks, local model settings,
plugins, templates, and high contrast, but did not expose a native
`系统与发布` surface.

## TDD Flow

Red phase:

```text
cd apps/agent-console && npx vitest run src/features/settings/pages/__tests__/AdvancedFeaturesPage.test.tsx --reporter=dot
-> failed because the test could not find `系统与发布`
```

Green phase:

- Added a regression that requires `/desktop` to expose:
  - system login-item startup state and toggle;
  - explicit file-root display, root selection, and file-watch start/stop;
  - update channel/status/current/latest version and check/download/install
    controls;
  - feedback submission;
  - startup/crash/sync desktop metric summaries.
- Implemented the `系统与发布` chapter in
  `apps/agent-console/src/features/settings/pages/AdvancedFeaturesPage.tsx`.
- Extended `apps/agent-console/src/vite-env.d.ts` with typed
  `desktopApi.updates` and `desktopApi.feedback` contracts.

## Verification

```text
cd apps/agent-console && npx vitest run src/features/settings/pages/__tests__/AdvancedFeaturesPage.test.tsx --reporter=dot
-> 1 file / 3 tests passed

cd apps/agent-console && npx tsc --noEmit --pretty false --types vite/client,vitest/globals,@testing-library/jest-dom --skipLibCheck --jsx react-jsx --lib DOM,DOM.Iterable,ES2022 --module ESNext --moduleResolution Bundler --target ES2020 --esModuleInterop --allowSyntheticDefaultImports src/vite-env.d.ts src/features/settings/pages/AdvancedFeaturesPage.tsx src/features/settings/pages/__tests__/AdvancedFeaturesPage.test.tsx
-> passed

cd apps/agent-console && npx vitest run src/features/settings/pages/__tests__/AdvancedFeaturesPage.test.tsx src/lib/__tests__/desktop-bridge.test.ts src/features/agents/__tests__/WorkspaceShellBar.render.test.tsx src/features/agents/__tests__/ChatSurface.shell.test.tsx src/components/ui/__tests__/VirtualList.test.tsx src/features/terminal/components/__tests__/TerminalWorkspace.test.tsx src/features/terminal/components/__tests__/XtermTerminal.test.tsx src/stores/__tests__/terminalStore.test.ts --reporter=dot
-> 8 files / 58 tests passed

cd apps/agent-console && npm run build
-> passed with existing chunk-size warning

python3 scripts/validate-docs.py
-> docs validation passed

git diff --check
-> passed
```

## Design Alignment

The implementation follows `DESIGN.md` and
`docs/design/desktop/apple-style-guidelines.md`:

- native settings are grouped by intent instead of being scattered;
- file-root and update-channel trust boundaries are visible;
- update downloads still go through the backend-gated Electron update API;
- feedback payloads are user-triggered;
- icon+text buttons are used for native commands;
- the workbench remains a short operating document, not a dashboard pile.

## Notes

- `AdvancedFeaturesPage.tsx` and its test were already untracked desktop
  workbench files in this local worktree. This slice continued in those files
  without reverting unrelated changes.
- This slice did not change Electron main/preload runtime code; it exposes
  existing preload namespaces through the Agent Console desktop workbench.
