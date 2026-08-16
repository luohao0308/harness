# Frontend Terminal UI Soft Boundaries

## Outcome

The terminal workspace now uses a quieter visual hierarchy. Desktop renders its single terminal as an integrated tool surface with a low-contrast outline and restrained active focus ring. Terminal headers, surface background, and surrounding page background are adjacent neutral tones, and xterm content has consistent inner breathing room. Web four-panel resizing and panel behavior remain unchanged.

## Evidence

- `apps/agent-console/src/features/terminal/components/TerminalWorkspace.tsx` selects the integrated desktop appearance and keeps the multi-panel web layout.
- `apps/agent-console/src/features/terminal/components/TerminalPane.tsx` owns the shared panel/header treatment and 12px xterm content padding.
- `apps/agent-console/src/features/terminal/lib/terminalTheme.ts` uses `#FBFBFC` to align terminal output with the softened surface.
- `DESIGN.md` records the terminal boundary rule under visual shape and elevation.

## Validation

- `cd apps/agent-console && npm test -- --run src/features/terminal/components/__tests__/TerminalWorkspace.test.tsx src/features/terminal/components/__tests__/XtermTerminal.test.tsx` -> 2 files / 14 tests passed.
- `cd apps/agent-console && npm run build` -> passed; 2414 modules transformed.
- `python3 scripts/validate-docs.py` -> passed.
- `git diff --check` -> passed.
- Browser smoke rendered the API-backed Web terminal at `http://127.0.0.1:4178/terminal`; the Electron preload object is not injectable in the browser page, so desktop geometry is covered by the desktop branch contract test rather than claimed as a browser screenshot.

## Follow-up

No behavior or terminal transport changes are pending. Future desktop visual checks should use the packaged Electron smoke profile when a fresh renderer screenshot is required.
