# Tool Approval Modify UI

Category: `session-log`

Tags: `frontend`, `tool-approvals`, `run-detail`, `workspace-inspector`, `validation`

## Summary

Run Detail and Workspace Inspector pending tool approval cards now expose Modify beside Approve and Reject. Modify opens a `ConfigDialog` JSON editor, validates that the payload is an object, calls the existing `modifyToolApproval` API helper, and refreshes approval state after success.

## Evidence

- `apps/agent-console/src/features/runs/pages/RunDetailPage.tsx` now renders the third Modify action on pending approval cards and refreshes the Run workspace query after modification.
- `apps/agent-console/src/features/agents/components/InspectorDrawer.tsx` now renders compact pending approval controls in the runtime section and supports the same Modify JSON editor.
- `apps/agent-console/src/features/agents/pages/AgentWorkspacePage.tsx` passes active Run approvals and a refetch callback into the inspector.
- `docs/workspace-pro-gap-register.md` marks "Approve, Reject, Modify tool approvals" as implemented.

## Validation

- `cd apps/agent-console && npx tsc --noEmit --pretty false --types vite/client --skipLibCheck --jsx react-jsx --lib DOM,DOM.Iterable,ES2022 --module ESNext --moduleResolution Bundler --target ES2020 --esModuleInterop --allowSyntheticDefaultImports src/features/runs/pages/RunDetailPage.tsx src/features/agents/components/InspectorDrawer.tsx src/features/agents/pages/AgentWorkspacePage.tsx` passed.
- `cd apps/agent-console && npx vite build` passed.
- `cd services/api-server && uv run pytest tests/test_tool_approvals.py -q` passed with `3 passed`.
- `python3 scripts/validate-docs.py` passed when the independent worktree used temporary links to the main workspace `AGENTS.md` and full `.omx` runtime context.

## Known Validation Blockers

- `cd apps/agent-console && npm run build` still fails in `tsc --noEmit` on existing stale test typing debt: missing `jest-axe` declarations, stale a11y imports, old `ChatMessageBubble` test props, and stale SAML fixture shapes.
- `cd services/api-server && uv run pytest tests/ -q` still fails during collection because `tests/integration/test_okta_logout.py` imports missing `Session` from `app.db.models`.
