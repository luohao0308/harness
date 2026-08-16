# Agent Console UI UX Polish

Category: session-log
Tags: `agent-console`, `frontend`, `ui-ux`, `chinese-first`, `browser-smoke`

## Summary

Completed the ordered 18-task Agent Console UI/UX polish pass for `apps/agent-console/src`.

The work stayed inside existing React, TypeScript, TailwindCSS, React Router, TanStack Query, and Lucide React patterns. No `__tests__` files were edited and no dependencies were added.

## Delivered

- Walkthrough no longer blocks the full page; it renders as a bottom-right floating card with normal shadow.
- Onboarding now uses Chinese step labels and updates Step 2 endpoint defaults when the provider changes.
- Eval Harness uses a two-section layout without vertical/rotated text and has a guided dataset empty state.
- Dashboard terminology is Chinese-first, today runs are counted over the last 24 hours, the Demo banner is dismissible, and `Token 节省` naming is consistent.
- QuickActionFAB now chooses context-aware route actions.
- Workspace icon-only controls have accessible labels/tooltips, settings child navigation has a stronger active state, and all-zero metadata rows are hidden.
- Run History has status filtering plus keyword search.
- Model Settings uses neutral `未配置` badges and explanatory copy.
- Subagent Specialists table removes the Schema column, merges success/invocation stats, and caps tool whitelist badges with `+N`.
- Knowledge empty states guide upload/API setup; Help code blocks scroll horizontally; Token Savings no-evidence text is a passive status tag.

## Validation

```text
cd apps/agent-console && npx tsc --noEmit --pretty false --types vite/client --skipLibCheck --jsx react-jsx --lib DOM,DOM.Iterable,ES2022 --module ESNext --moduleResolution Bundler --target ES2020 --esModuleInterop --allowSyntheticDefaultImports <touched source files>
passed

cd apps/agent-console && npm test -- src/features/subagents/__tests__/SubagentSpecialistsPage.test.tsx src/features/knowledge/pages/__tests__/KnowledgePage.test.tsx src/features/agents/__tests__/KnowledgeManagementPanel.render.test.tsx src/features/runs/pages/__tests__/RunHistoryPage.test.tsx src/features/dashboard/pages/__tests__/DashboardPage.test.tsx src/features/onboarding/__tests__/OnboardingWizardPage.test.tsx src/features/settings/pages/__tests__/ModelSettingsPage.test.tsx --reporter=dot
7 files / 40 tests passed

cd apps/agent-console && npm test -- --reporter=json --outputFile=/tmp/agent-console-vitest-final.json
205/241 suites passed, 564/623 tests passed; remaining failures are existing stale test assumptions and a11y/test typing debt.

python3 scripts/validate-docs.py
passed

git diff --check
passed
```

Browser screenshots captured during the pass:

```text
verify-dashboard-final.png
verify-onboarding-step1-final.png
verify-onboarding-step2-final.png
verify-evals-final.png
verify-runs-final.png
verify-knowledge-final.png
verify-settings-models-final.png
verify-subagent-specialists-final.png
verify-token-savings-final.png
verify-workspace-final.png
verify-help-final.png
verify-walkthrough-final.png
```

## Boundaries

- No test files under `__tests__` were modified.
- No new dependencies were introduced.
- Repo-wide frontend tests remain red because of existing unrelated test debt; the relevant touched UI tests and source-limited TypeScript check passed.
