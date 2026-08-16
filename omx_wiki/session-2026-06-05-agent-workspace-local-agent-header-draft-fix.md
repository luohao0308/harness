# Agent Workspace Local Agent Header Draft Fix - 2026-06-05

Category: session-log
Tags: `agent-console`, `agent-workspace`, `local-agent`, `composer`, `frontend-ui`, `responsive`, `review`

## Summary

Fixed the Agent Workspace issue where text typed into the composer disappeared after a few seconds when Local Agent mode was active.

The same pass moved Local Agent controls out of the old full-width row and into the top-left Workspace header, and made the top-left Agent name a switcher for moving between Agent workspaces.

Follow-up: local Agent connections are now also first-class options inside that same top-left switcher, so cloud Agents and local Agents share one selection surface.

## Delivered

- Local Agent polling hydrate now preserves the current workspace draft instead of replacing it with the empty `draft` from the Local Agent conversation summary.
- `ChatComposer` now waits for submit completion before clearing, and only clears if the textarea still contains the submitted draft.
- `ChatSurface` and `AgentWorkspacePage` now return `false` from not-sent Local Agent paths so failed, not-ready, cancelled, or superseded drafts are preserved.
- `WorkspaceShellBar` now renders the top-left Agent name as a `MenuSelect` backed by `/api/agents`.
- Agent selection in the header navigates to `/agents/{agentId}/workspace`.
- The top-left switcher now includes both `agent:{agentId}` cloud options and `local:{connectionId}` local Agent options, grouped as `智能体` and `本地 Agent`.
- Selecting a local Agent option enables that local connection and restores/creates its binding; selecting a cloud Agent disables local mode before navigating or returning to the cloud workspace.
- The old full-width Local Agent panel was removed from the chat surface.
- The separate local connection dropdown was removed; Local Agent enablement, selected connection, status, Session, queue, offline, and Claude V6 approval hints now render as compact header controls.
- Narrow-screen follow-up fixed reviewer-found clipping by allowing the header left group to shrink and by constraining Agent and Local Agent popover menus to the viewport.
- Stale local Agent pending state is gated behind local mode, so a pending local task cannot block cloud Agent submit after switching back.
- Late binding responses are ignored unless their `connection_id` still matches the currently selected local connection, preventing old connection A from overwriting current connection B.

## Files Changed

```text
apps/agent-console/src/features/agents/components/ChatComposer.tsx
apps/agent-console/src/features/agents/components/ChatSurface.tsx
apps/agent-console/src/features/agents/components/WorkspaceShellBar.tsx
apps/agent-console/src/features/agents/pages/AgentWorkspacePage.tsx
apps/agent-console/src/features/agents/__tests__/AgentWorkspacePage.team-launch.test.tsx
docs/development/ai/task-progress.yaml
omx_wiki/index.md
omx_wiki/log.md
omx_wiki/session-2026-06-05-agent-workspace-local-agent-header-draft-fix.md
```

## Review Notes

- UI reviewer Carver found a blocking narrow-screen issue: fixed left header width could crop the Agent/Local Agent controls.
  - Fix: header left group now uses `min-w-0 flex-[1_1_16rem] sm:min-w-[260px]`, and the Agent switcher uses `w-full max-w-[20rem] min-w-0`.
- UI reviewer Carver found a second blocking issue: narrow-screen popover menus could be clipped when opened.
  - Fix: both Agent and Local Agent `MenuSelect` menus are right-aligned and constrained with `w-[min(18rem,calc(100vw-3rem))]`.
- Final UI reviewer Aquinas returned `PASS`.
- Final code/state reviewer Fermat returned `PASS`.
- Follow-up UI/interaction reviewer Hubble returned `PASS` for the mixed cloud/local top-left selector, compact header state, old local dropdown removal, and responsive behavior.
- Follow-up code/state reviewer Poincare returned `PASS`, confirming the stale local pending blocker and stale binding response blocker are closed.

Consensus state: no remaining blocking UI/UX, responsive, accessibility, state, or test findings.

## Validation

```text
cd apps/agent-console && npm test -- AgentWorkspacePage.team-launch.test.tsx ChatSurface.shell.test.tsx
2 files / 26 tests passed

cd apps/agent-console && npm run lint -- --pretty false
passed

cd apps/agent-console && npm run build
passed

python3 scripts/validate-docs.py
passed

git diff --check
passed
```

Live smoke against `http://127.0.0.1:18082/agents/default/workspace` with API at `http://127.0.0.1:8000`:

```json
{"desktop":{"agentOptions":8,"oldLocalAgentRowCount":0,"horizontalOverflow":false}}
{"mobile390":{"scrollWidth":390,"clientWidth":390,"agentSwitcherVisible":true,"localAgentVisible":true,"composerVisible":true}}
{"draftPolling":{"session":"Session 078d5f7f","value":"等待几秒也不要消失","kept":true}}
{"mobileMenus":{"agentWithin":true,"localWithin":true,"agentWidth":288,"localWidth":288}}
```

Mocked Playwright smoke against `http://127.0.0.1:18082/agents/default/workspace`:

```json
{
  "desktopOptions": [
    "Default Agent",
    "Research Agent",
    "hao Local Agent",
    "Claude Code"
  ],
  "oldLocalSelectCount": 0,
  "localSessionVisible": true,
  "cloudSubmitAfterLocalPending": "POST /api/agents/default/runs/chat/stream",
  "mobile390Overflow": false,
  "mobileMenuInsideViewport": true
}
```

## Boundaries

- No backend API contract changed.
- No new frontend dependency was added.
- The Local Agent conversation summary still returns `draft: ""`; the page hydrate layer preserves the live store draft for this polling path.
- Current binding creation uses one mutation instance, so extremely fast local A -> B switches may wait for A's in-flight create to settle before B starts; reviewer Poincare classified this as a non-blocking latency watch item, not a correctness blocker.
