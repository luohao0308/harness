# Product Screenshot Catalog

This directory is the durable evidence set for desktop and web-console product
reviews. Source screenshots are preserved; historical files are copied into the
archive rather than moved or renamed at their original locations.

## Current audit batch

`2026-08-05/web-current/` contains 25 current web-console views captured from
`http://127.0.0.1:5173`. The set covers:

| File | Feature |
| --- | --- |
| `01-dashboard.png` | Dashboard |
| `02-agents.png` | Agent list |
| `03-agent-workspace.png` | Agent workspace |
| `04-teams.png` | Teams |
| `05-runs.png` | Run history |
| `06-run-detail.png` | Run detail |
| `07-knowledge.png` | Knowledge base |
| `08-tools.png` | Tool registry |
| `09-sandboxes.png` | Sandboxes |
| `10-terminal.png` | Terminal |
| `11-observability.png` | Observability |
| `12-token-savings.png` | Token savings |
| `13-evals.png` | Evaluations |
| `14-subagents.png` | Subagents |
| `15-specialists.png` | Specialist route terminal ID/permission load failure |
| `16-model-settings.png` | Model settings |
| `17-advanced-settings.png` | Advanced settings |
| `18-help.png` | Help center |
| `19-desktop-browser-fallback.png` | Desktop browser fallback |
| `20-onboarding.png` | Onboarding |
| `21-cost-dashboard.png` | Cost dashboard |
| `22-trace-explorer.png` | Trace explorer (`/observability/trace`) |
| `23-data-management.png` | Data management |
| `24-subagent-marketplace.png` | Subagent marketplace |
| `25-tools-config.png` | Tool configuration |

All current web views were checked for horizontal overflow during capture.
`20-onboarding.png` records the intentional redirect to Dashboard after setup is
complete. `23-data-management.png` deliberately records the expanded console
error boundary because `/settings/data` currently returns `404 Not Found`; it
is defect evidence, not an accepted functional state. `15-specialists.png`
records the stable terminal state where `/subagents/specialists` reports that
the subagent could not be loaded and asks the operator to check the ID or
permission; it is also defect evidence rather than a loading-state capture.

`2026-08-05/desktop-current/` contains native Electron evidence. The strongest
current verification images are:

| File | Evidence status |
| --- | --- |
| `02-desktop-workbench-native.png` | Native bridge connected |
| `04-desktop-offline-sync-error.png` | Pre-fix `better-sqlite3` binding failure retained as defect evidence |
| `05-desktop-workbench-after-rebuild.png` | Native bridge and desktop status restored after rebuild |
| `07-desktop-live-relaunch.png` | Fresh Electron relaunch on 2026-08-07 |
| `08-desktop-offline-execution-success.png` | Offline execution UI; also exposes the authenticated sync `401` state |
| `09-desktop-offline-result-success.png` | Completed deterministic local result visible in the native app |

`06-desktop-offline-after-rebuild.png` is retained for traceability but is not
accepted as desktop evidence because it captured the wrong foreground window.

## Historical web archive

`archive/web-legacy/2026-06-21/` contains representative high-resolution final
screens, unique interaction states, and the first-Agent-run demo pair. Sources
were copied from the repository root and `docs/design/media/gifs/`. The root screenshot set
was introduced in Git commit `e397e1e`; the demo pair in `722802f`.

`archive/web-legacy/2026-08-04-team-mode/` contains the five accepted Team Mode
visual outputs copied from `.omx/artifacts/visual-ralph/desktop-team-mode/`:

- `desktop-collaboration.png`
- `desktop-task-graph.png`
- `desktop-columns.png`
- `web-columns.png`
- `web-mobile.png`

Pixel-diff files, reference images, duplicate dashboard/workspace variants, and
intermediate non-final verification captures are intentionally excluded.

## Evidence boundaries

- A screenshot proves only the visible state at capture time.
- The `first-agent-run` demo used local mocked SSE/API flows and is not evidence
  of an external model provider or Docker execution.
- The native offline result proves local deterministic execution. Synchronizing
  that result still requires an authenticated API session.
- Electron may log `eglQueryDeviceAttribEXT: Bad attribute` on this macOS host;
  the warning did not prevent window creation or offline task execution.
