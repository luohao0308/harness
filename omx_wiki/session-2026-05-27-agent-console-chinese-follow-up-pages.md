# Agent Console Chinese Follow-up Pages

Category: `session-log`

Tags: `agent-console`, `chinese-first`, `agent-studio`, `knowledge`, `team`, `playwright`

## Summary

This follow-up closed the remaining high-visibility mixed English wording on
Agent Studio, Knowledge, and Team pages after the MCP / Skill store polish was
already stable.

The goal was to stay aligned with the user's fixed 10-point target while
continuing autonomous browser-verified cleanup.

## Delivered

- Agent Studio now uses Chinese-first wording for the last visible `Agent`
  action labels in this slice:
  - `智能体创建成功 / 失败`
  - `智能体克隆成功 / 失败`
  - `附加到当前智能体`
  - `MCP / 技能 / 工具`
  - `当前智能体已切换到 ...`
- Knowledge workbench now shows `智能体作用域` and `知识库智能体`.
- Team create/member flows now use `队长智能体`, `队长智能体定义`,
  `智能体定义`, `选择智能体`, and `没有可用的智能体`.
- Team list, Team header, Agent cards, and Team member previews no longer show
  raw `ACTIVE`; they now render the Chinese-first label `活跃中`.
- Mocked browser cases were refreshed to use Chinese fixture names such as
  `默认智能体`, `研究智能体`, and `队长`, so smoke pages do not reintroduce
  avoidable English from test data.

## Additional Follow-up

- `/subagents` and `/subagents/:subagentId` no longer generate broken task
  links. Task navigation now points to concrete `/runs/:runId` and
  `/runs/:runId/subagents` routes.
- Run History, Eval run history, Eval latest-run summary, Eval per-case
  results, and Eval case expectations no longer expose raw
  `COMPLETED / PASSED / FAILED` values to users. They now render the
  Chinese-first labels `已完成 / 通过 / 失败`.
- The Eval "save case from run" flow now uses a novice-friendly expected-status
  picker with visible Chinese guidance instead of a bare `COMPLETED` input.
- Browser smoke added a concrete Subagents link-verification case so the fixed
  route wiring is covered by regression tests.

## Validation

```text
cd apps/agent-console && npm test -- src/features/agents/__tests__/AgentListPage.studio.test.tsx src/features/knowledge/pages/__tests__/KnowledgePage.test.tsx src/features/teams/__tests__/TeamPages.test.tsx
3 files / 23 tests passed

cd apps/agent-console && npm run lint -- --pretty false
passed

cd apps/agent-console && HARNESS_PLAYWRIGHT_EXTERNAL_SERVER=1 npx playwright test --project=chromium --headed e2e/agent-studio-feedback.smoke.spec.ts e2e/team-mode.smoke.spec.ts e2e/knowledge-demo.smoke.spec.ts
10 passed

cd apps/agent-console && HARNESS_PLAYWRIGHT_EXTERNAL_SERVER=1 npx playwright test --project=chromium e2e/agent-workspace.smoke.spec.ts e2e/agent-workspace-success.smoke.spec.ts e2e/agent-studio.smoke.spec.ts e2e/agent-studio-feedback.smoke.spec.ts e2e/team-mode.smoke.spec.ts e2e/tools-page.smoke.spec.ts e2e/run-detail.smoke.spec.ts e2e/sandboxes-page.smoke.spec.ts e2e/eval-page.smoke.spec.ts e2e/subagents-feedback.smoke.spec.ts e2e/observability.smoke.spec.ts e2e/knowledge-demo.smoke.spec.ts e2e/nav-resilience.spec.ts
53 passed

python3 scripts/validate-docs.py
passed

git diff --check
passed
```

Additional follow-up validation:

```text
cd apps/agent-console && npm test -- src/features/runs/pages/__tests__/RunHistoryPage.test.tsx
1 test passed

cd apps/agent-console && npm run lint -- --pretty false
passed

cd apps/agent-console && npm run build
passed

cd apps/agent-console && HARNESS_PLAYWRIGHT_EXTERNAL_SERVER=1 npx playwright test --project=chromium --headed e2e/subagents-feedback.smoke.spec.ts e2e/eval-page.smoke.spec.ts
7 passed

cd apps/agent-console && HARNESS_PLAYWRIGHT_EXTERNAL_SERVER=1 npx playwright test --project=chromium e2e/agent-workspace.smoke.spec.ts e2e/agent-workspace-success.smoke.spec.ts e2e/agent-studio.smoke.spec.ts e2e/agent-studio-feedback.smoke.spec.ts e2e/team-mode.smoke.spec.ts e2e/tools-page.smoke.spec.ts e2e/run-detail.smoke.spec.ts e2e/sandboxes-page.smoke.spec.ts e2e/eval-page.smoke.spec.ts e2e/subagents-feedback.smoke.spec.ts e2e/observability.smoke.spec.ts e2e/knowledge-demo.smoke.spec.ts e2e/nav-resilience.spec.ts
54 passed
```

## Notes

- This pass stayed deliberately narrow: it only touched the user-visible Chinese
  wording and status presentation on the remaining high-value pages plus the
  related browser/manual cases.
- The existing React `act(...)` warnings in some Knowledge/Team tests still
  appear, but the tests pass and they are not new regressions from this slice.
- Searching `apps/agent-console/src` for `alert|confirm|prompt` now shows only
  the shared custom confirm helper callsites, not browser-native modal usage.
