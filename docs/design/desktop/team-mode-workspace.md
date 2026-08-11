# Desktop Team Mode Workspace

## Status

- Status: Active implementation contract
- Last refreshed: 2026-07-31
- Route: `/teams/:teamId`
- Runtime: shared Agent Console renderer inside Electron
- Visual references:
  - `.omx/artifacts/visual-ralph/desktop-team-mode/reference-task-graph.png`
  - `.omx/artifacts/visual-ralph/desktop-team-mode/reference-team-inspector.png`

## Product Decision

Desktop Team Mode extends the existing web Team Mode; it does not replace or
fork its data model. The Team route has one shared Team session and three
presentation modes:

| Mode | Desktop behavior | Web behavior |
| --- | --- | --- |
| `协作` | Default. One active Agent conversation, an in-conversation member roster, and a resizable team inspector. | Not shown as the default web layout. |
| `任务图` | One active Agent conversation and a resizable dependency graph derived from Team tasks. | Not shown as the default web layout. |
| `多列` | Reuses the existing horizontal Agent columns without semantic changes. | Existing and unchanged default. |

The desktop mode switch is presentation-only. It must not change Team, Agent,
mailbox, wake, task, goal, SSE, or React Query contracts.

## User Outcome

The first desktop viewport must answer:

1. Which Agent conversation is active?
2. Which members are working, waiting, completed, or failed?
3. Which tasks are open, blocked, or completed, and how do they depend on each other?
4. Can the user continue messaging without leaving the current workspace?
5. Can the user return to the existing multi-column web workflow immediately?

## Information Architecture

### Shared Header

- Keep team identity, status, active-goal summary, Team tools, add-member, and
  task-board actions.
- Add a compact segmented view control: `协作 / 任务图 / 多列`.
- Show the segmented control only in Electron or an explicit desktop test
  harness. Browser Team Mode keeps its existing header and default layout.

### Collaboration View

- Main pane: the selected Agent conversation and its existing composer.
- Conversation supplement: a compact member roster that summarizes every slot,
  owner task, current status, and progress.
- Inspector pane: selected member identity, status, assigned tasks, recent
  mailbox activity, and task updates.
- Selecting a member in the roster or inspector changes the active conversation.
- The composer always targets the selected Agent slot; no generic dashboard
  target selector becomes the primary interaction.

### Task Graph View

- Main pane: the selected Agent conversation and existing composer.
- Graph pane: task dependency cards laid out from `blocked_by_json` and
  `blocks_json`, with explicit connectors and status color.
- Header: completed/total count plus a thin progress bar.
- Cards show task subject, owner, status, description, and dependency count.
- Selecting a card exposes its details without navigating away or mutating the task.
- Invalid or cyclic dependency data is condensed by strongly connected
  component, degrades to deterministic rows, and never blocks the conversation.

### Multi-Column View

- Reuse `TeamAgentTabs`, `TeamColumnList`, `AgentColumn`, and per-column composer.
- Preserve drag reorder, unread/task badges, full-screen Agent column, branch,
  pin, context compression, model selection, file attachment, stop, and wake behavior.

## Layout Contract

- Desktop minimum supported window remains `1024 x 768`.
- Collaboration default split: conversation `80%`, inspector `20%`.
- Task graph default split: conversation `56%`, graph `44%`.
- Pane separators are keyboard-focusable and visually quiet.
- The inspector can collapse to an icon control; reopening restores the prior split.
- The selected conversation's full-screen action controls the current desktop
  side pane instead of leaking hidden full-screen state into `多列`; the action
  is omitted when a narrow desktop layout has no side pane.
- No page-level horizontal overflow. The task graph may scroll inside its pane.
- Below desktop width, preserve the existing single-Agent responsive layout.
  Collaboration keeps its roster in the conversation, while Task graph becomes a
  full temporary surface instead of squeezing the composer.

## Visual Language

- Reuse the web Console palette, typography, borders, badges, buttons, and Lucide icons.
- Page and panels: white and slate surfaces with `1px` borders.
- Selected state: pale blue surface and blue border.
- Completed: emerald; active/running: cyan/blue; blocked/waiting: amber;
  failed: red; idle/default: slate.
- Cards use at most `8px` radius. Major panes are unframed and separated by
  borders, not nested cards.
- Motion is limited to status/progress transitions and pane resizing; honor
  reduced motion.

## State And Persistence

- Desktop detection uses the existing preload boundary (`window.desktopApi`).
- Persist the selected desktop view per Team in local storage under
  `harness-desktop-team-view-${teamId}`.
- Route changes bind the view value to its Team storage key before persistence,
  so a previous Team preference is never written into the next Team key.
- Default desktop view is `协作`; invalid stored values fall back to `协作`.
- Web never reads or writes the desktop view preference.
- Active Agent selection, Agent order, drafts, streaming wakes, and cache keys
  remain owned by the existing Team page state.

## Component Ownership

- `TeamPage/index.tsx`: shared query, mutation, realtime, and modal owner.
- `TeamWorkspaceSurface.tsx`: selects web columns or a desktop workspace mode.
- `DesktopTeamViewSwitch.tsx`: segmented mode control.
- `DesktopTeamMemberRoster.tsx`: compact in-conversation Agent cards.
- `DesktopTeamInspector.tsx`: selected-member activity and task rail.
- `DesktopTeamTaskGraph.tsx`: deterministic dependency visualization.
- `TeamColumnList.tsx` / `AgentColumn.tsx`: existing conversation/composer,
  extended only with an optional presentation supplement.

Electron main/preload code does not gain Team-specific APIs for this change.
The shared renderer continues to use the existing authenticated Team HTTP/SSE path.

## Accessibility

- The view switch uses a labeled segmented-button group with `aria-pressed` selected state.
- Member and task cards are buttons when selectable and expose status in text.
- Graph connectors are decorative; the same dependency relation is present in
  card text for screen readers.
- Pane separators are keyboard operable through `react-resizable-panels`.
- Focus remains in the selected conversation when switching members unless the
  user explicitly opens a secondary control.
- Color is never the only status signal.

## Verification Contract

Required automated checks:

```bash
cd apps/agent-console
npx vitest run src/features/teams/__tests__/TeamPages.test.tsx
npm run build
```

Required visual states:

| Artifact | Viewport | Route/state |
| --- | --- | --- |
| `desktop-collaboration.png` | `1440 x 900` | Electron bridge present; Team has at least four Agents and four tasks |
| `desktop-task-graph.png` | `1440 x 900` | Same Team; `任务图` selected; includes branch, completed, active, and failed states |
| `desktop-columns.png` | `1440 x 900` | Same Team; `多列` selected |
| `web-columns.png` | `1440 x 900` | No Electron bridge; existing multi-column default |
| `web-mobile.png` | `390 x 844` | No Electron bridge; one active Agent and no document overflow |

Final visual comparison uses the two archived references as directional targets,
with a Visual Ralph score of at least `90`. Exact copied branding, avatars, and
reference application chrome are excluded; layout hierarchy, density, split
proportions, task/member states, and composer continuity are in scope.

Final evidence is archived beside the screenshots:

- `visual-verdict-final.json`: Collaboration `92`, Task graph `91`.
- `collaboration-pixel-diff.png` and `task-graph-pixel-diff.png`: secondary
  normalized pixel-difference overlays.
- `pixel-diff-metrics.json`: reproduction method and normalized mean absolute error.

## Non-Goals

- No new Team backend entities or endpoints.
- No new desktop IPC surface.
- No replacement of the existing web multi-column Team Mode.
- No Run Detail, Trace, or Observability dashboard as the Team first screen.
- No direct task mutation from graph cards in this slice.
- No copied third-party branding or reference avatars.
