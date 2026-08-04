# Desktop Team Mode Workspace

Category: `session-log`

Tags: `desktop`, `team-mode`, `agent-console`, `visual-ralph`, `accessibility`

## Summary

Electron Team Mode now adds two desktop-native presentation modes beside the unchanged web workflow. `协作` keeps one selected Agent conversation and composer at the center, with a compact member roster and narrow activity inspector. `任务图` keeps the same conversation state beside a resizable dependency graph. `多列` remains the existing Team implementation and is still the browser default.

## Product Boundary

- The implementation lives in the shared Agent Console Team route, not Electron main/preload code.
- Team HTTP, SSE, React Query, wake, mailbox, task, goal, branch, compression, model, attachment, and composer contracts remain shared.
- Desktop view selection is presentation-only and persists per Team as `harness-desktop-team-view-${teamId}`.
- Browser Team Mode does not render the desktop mode switch.

## Implementation

- Added a labeled `协作 / 任务图 / 多列` segmented button group to the desktop Team header.
- Added a chat-first Collaboration surface with compact member progress rows and an `80/20` resizable team activity inspector.
- Added a `56/44` Task graph surface with compact status cards, branch/merge connectors, selected-task dependency details, and owner navigation.
- Normalized graph edges from both `blocked_by_json` and `blocks_json`.
- Added deterministic strongly-connected-component handling: components are condensed before level calculation, internal cycle edges are removed, affected tasks stay in one stable row even with external prerequisites/downstream tasks, and the UI exposes a textual cycle fallback state.
- Bound persisted view state to its Team storage key so route changes cannot write the previous Team preference into the next Team.
- Wired the selected conversation's full-screen icon to collapse/restore the current inspector or graph pane; narrow desktop layouts omit the icon when no side pane is present.
- Aligned Electron responsive behavior to the documented 1024px desktop boundary. At narrower widths Collaboration keeps the single-Agent composer; Task graph becomes a full temporary surface.
- Retained the existing web multi-column and 390px single-column behavior.

## Visual Evidence

- References: `.omx/artifacts/visual-ralph/desktop-team-mode/reference-team-inspector.png` and `reference-task-graph.png`.
- Final screenshots: `desktop-collaboration.png`, `desktop-task-graph.png`, `desktop-columns.png`, `web-columns.png`, and `web-mobile.png` in the same artifact directory.
- Final Visual Ralph verdict: Collaboration `92`, Task graph `91`, recorded in `visual-verdict-final.json`.
- Secondary pixel evidence: `collaboration-pixel-diff.png`, `task-graph-pixel-diff.png`, and `pixel-diff-metrics.json`.

## Verification

- `cd apps/agent-console && npm run lint -- --pretty false` -> passed.
- `cd apps/agent-console && npm test -- --run src/features/teams/__tests__/TeamPages.test.tsx` -> 25 passed.
- `cd apps/agent-console && npm run build` -> passed; 2408 modules transformed.
- Full Chromium Team desktop/create-send/mobile regression -> 3 passed.
- `python3 scripts/validate-docs.py` -> passed.
- `git diff --check` -> passed.

The final full three-case Playwright rerun passed on 2026-08-04. It covers desktop Collaboration/Task graph/columns without replacing the existing column mode, Team creation plus Leader send and extra-column opening, and the 390px mobile single-column send/overflow path. This closes the previous approval-service browser evidence gap.

## Review Closure

- Per-Team persistence is restored safely and invalid values return to Collaboration.
- Team-to-Team route changes do not cross-write local view preferences.
- The view control uses segmented buttons with `aria-pressed`, avoiding an incomplete tab contract.
- Task cards expose named dependencies and downstream tasks to screen readers.
- Collapse controls are localized.
- The conversation full-screen control operates on the visible desktop side pane instead of mutating hidden multi-column state.
- Narrow Electron windows no longer expose a Task graph mode that renders no graph.
- The cleanup pass preserved the tested storage and cycle fail-safe boundaries while removing duplicate filtering, conflicting utility classes, and silent Tarjan invariant defaults; the closeout follow-up strengthened both boundaries with route-transition and condensed-component regressions.
