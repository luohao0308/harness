# Desktop Codex Task Workspace

Category: `session-log`

Tags: `desktop`, `electron`, `agent-console`, `workspace`, `codex-style`, `verification`

## Summary

Electron now opens directly into a compact, Codex-style task workspace while
the browser keeps the existing full Harness console. The desktop home is the
Agent Workspace, not the `/desktop` capability page; desktop settings and
native operations remain available as secondary tools. The final desktop
operation shell now separates use from observation: Electron exposes direct
actions, while the browser remains the full metrics and audit console.

## Interaction Contract

- The Electron main window opens `/agents/default/workspace`.
- The desktop Agent Workspace bypasses the browser `ConsoleShell`; browser
  visits to the same route still render the complete console navigation.
- The `280px` desktop sidebar contains Harness identity, `新建任务`, task
  history, and a narrow operation rail links tasks, teams, runs, terminal,
  files, approvals, and settings.
- The workspace header is a stable single row with icon-focused actions. It
  omits the browser back link, duplicate workspace selector, local-Agent
  status line, and idle Run badge.
- Active Runs keep direct detail navigation and expose the native independent
  Run-window action only in Electron.
- `/teams` opens the current team or a create-team empty state; the local
  database is migrated through `20260628_0049`, so Team list, detail, and
  event-stream requests complete successfully.
- `/terminal` starts one desktop shell session to avoid consuming the server's
  four-session limit; the browser keeps the existing four-pane terminal.
  Embedded zsh/bash sessions skip user startup scripts, so host integrations
  cannot inject startup failures into the Harness terminal.
- Files and approvals deep-link into the Agent Workspace without overlapping
  panels. `/desktop` is a scrollable operational settings page for workspace,
  window, offline/local-model, file, update, plugin, template, and feedback
  actions rather than a desktop metrics dashboard.

## Verification

- Agent Console focused shell regression -> `3 files / 21 tests passed`.
- Agent Console TypeScript lint -> passed.
- Agent Console production build -> passed.
- Desktop operation regression -> `6 files / 82 tests passed` with one worker.
- Desktop startup/lifecycle/window regression -> `14 passed`.
- Full Desktop Vitest after restoring the Node ABI -> `32 files / 287 tests passed`.
- Desktop `build:main` -> passed.
- Real Electron visual smoke -> `/agents/default/workspace`, desktop shell and
  header present, browser console navigation absent, task sidebar width `280`,
  workspace selector absent, document horizontal overflow `0`.
- Local PostgreSQL migration -> `20260628_0049 (head)`.
- Backend Terminal regression -> `12 passed`; Ruff and Python compilation pass.
- Live Electron Team requests -> list, detail, and event stream returned `200`.
- Live Electron Terminal -> one token issued, one WebSocket accepted, and a
  clean shell prompt rendered without the prior Kiro startup error.
- `python3 scripts/validate-docs.py` -> passed.
- `git diff --check` -> passed.

## Evidence

- Screenshot: `.omx/artifacts/desktop-codex-shell/desktop-workspace.png`.
- Electron visual inspection confirms the intended quiet task-first hierarchy
  at desktop width with no overlapping controls.
- Final visual testing used the live backend, Vite renderer, and real Electron
  process. Team, Terminal, Files, Approvals, and Desktop Settings were opened
  through native deep links before returning the window to the task workspace.

## Follow-up Rules

- Keep desktop detection at the existing `window.desktopApi` boundary.
- Preserve the browser console shell when refining desktop presentation.
- Keep operational capabilities in the desktop rail and management-heavy
  metrics, audit, and observability surfaces in the browser console.
