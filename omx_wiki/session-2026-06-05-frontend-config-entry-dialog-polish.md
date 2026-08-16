# Frontend Config Entry Dialog Polish - 2026-06-05

Category: session-log
Tags: `agent-console`, `agent-studio`, `eval-harness`, `frontend-ui`, `config-dialog`, `review-consensus`

## Summary

The Console configuration-heavy areas now use compact entry cards and `ConfigDialog` flows instead of keeping long forms visible on the main page.

This pass focused on the user-requested surfaces in Agent Studio and Eval Harness: Agent template creation/clone, local Agent pairing, capability attachment, Token saving plan, dataset creation, saved-run Eval case creation, and LangGraph vs Native experiment setup.

## Delivered

- Agent Studio now exposes four configuration entry cards for role templates, local Agent connection, capability/readiness, and Token saving plan.
- Agent template create/clone and Token saving plan controls moved into `ConfigDialog` while preserving existing API mutations and success-close behavior.
- Agent Studio tests now open the relevant dialogs before asserting create, clone, capability attachment, and Token optimizer behavior.
- Eval Harness now shows a compact configuration entry section plus dataset list instead of two always-visible setup forms.
- Dataset creation and saved-run case creation moved into `ConfigDialog`.
- LangGraph vs Native keeps the experiment meaning and selected-run summary visible, but moves run selection and experiment creation into a dialog.
- Eval layout now stacks before the `xl` breakpoint instead of forcing the fixed three-column grid on narrow widths.
- Fixed a reviewer-found stale selection bug: switching active datasets now clears Native/LangGraph run selections, and experiment creation requires both selected runs to belong to the current dataset.

## Files Changed

```text
apps/agent-console/src/features/agents/pages/AgentListPage.tsx
apps/agent-console/src/features/agents/__tests__/AgentListPage.studio.test.tsx
apps/agent-console/src/features/evals/pages/EvalHarnessPage.tsx
apps/agent-console/src/features/evals/pages/__tests__/EvalHarnessPage.langgraph.test.tsx
docs/development/ai/task-progress.yaml
omx_wiki/index.md
omx_wiki/log.md
omx_wiki/session-2026-06-05-frontend-config-entry-dialog-polish.md
```

## Review Consensus

Two related reviewer agents were run after implementation:

- Hypatia, UX/UI reviewer: `PASS`
  - Confirmed `/agents` and `/evals` now follow the compact entry-card plus dialog pattern, preserve Chinese-first status-first hierarchy, and keep responsive stacking.
  - Non-blocking observation: the shared `ConfigDialog` still has the existing baseline limitation of no explicit focus trap; this was not introduced or worsened by this task.
- Lagrange, code/test reviewer: initial `BLOCKING`, then `PASS`
  - Initial blocker: Eval contrast experiment selections could become stale after switching datasets.
  - Fix: dataset selection now clears Native/LangGraph run IDs, `canCreateExperiment` requires both IDs to exist in the active dataset's run options, and a regression test covers the reset/disabled-submit path.
  - Final复审: blocker resolved, no new blocking findings.

Consensus state: no remaining blocking UX/UI, responsive, accessibility, React state, or test findings.

## Validation

```text
cd apps/agent-console && npm test -- AgentListPage.studio.test.tsx
1 file / 5 tests passed

cd apps/agent-console && npm test -- EvalHarnessPage.langgraph.test.tsx
1 file / 2 tests passed

cd apps/agent-console && npm run lint -- --pretty false
passed

cd apps/agent-console && npm run build
passed

python3 scripts/validate-docs.py
passed

git diff --check
passed
```

Browser smoke against the running Vite dev server at `http://127.0.0.1:18082`:

```json
{"agentsDialogs":true,"evalsDialogs":true,"agentsOverflow":false,"evalsOverflow":false}
```

## Boundaries

- No backend API contract changed.
- No new frontend dependency was added.
- Existing `ConfigDialog` behavior was reused.
- The page still uses the current shared dialog accessibility baseline; focus trapping can be handled as a separate hardening task if desired.
