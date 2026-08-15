# Deep Interview Spec: Console Chinese Terminology

## Metadata

- Profile: standard
- Rounds: 5
- Final ambiguity: 8.7%
- Threshold: 20%
- Context type: brownfield
- Context snapshot: `.omx/context/website-chinese-i18n-20260515T040524Z.md`
- Transcript: `.omx/interviews/console-chinese-terminology-20260515T042314Z.md`

## Intent

Make the agent console usable as a Chinese-first product surface, while preserving technical precision for identifiers, API/protocol names, brands, and backend-provided values.

## Desired Outcome

All console pages render as fixed Chinese UI. The existing English language switching behavior should be removed. English should remain only where it is a canonical identifier, code/API/protocol/brand name, model/provider value, or raw backend/user-generated value that should not be translated.

For hard technical terms that remain in English, add concise Chinese explanation through adjacent small text or a small question-mark tooltip where it improves comprehension without clutter.

## In Scope

- `apps/agent-console` only.
- All console routes:
  - `/agents`
  - `/agents/:agentId/workspace`
  - `/runs`
  - `/runs/:runId`
  - `/runs/:runId/events`
  - `/runs/:runId/subagents`
  - `/subagents`
  - `/subagents/:subagentId`
  - `/sandboxes`
  - `/observability`
  - `/tools`
  - `/evals`
  - `/settings/models`
  - `/settings/policies`
- Shared console shell, navigation, search, empty states, dialogs, popovers, menus, labels, placeholders, aria labels, button text, table headers, chart labels, panel titles, and test-visible UI copy.
- Update tests that currently assert English-mode UI.

## Out of Scope / Non-goals

- `apps/web-site` marketing website.
- GitHub docs, OpenAPI documents, backend API schemas, and external linked pages.
- Translating API paths, HTTP methods, code blocks, environment variable names, provider/model ids, status enum raw values where the raw value itself is important evidence, or user/backend-generated content.
- Adding a full bilingual mode or locale routes.

## Decision Boundaries

OMX may decide without further confirmation:
- Remove the existing language toggle from the console UI.
- Remove or simplify `en-US` branches where they only support the old English UI.
- Refactor local UI strings toward fixed Chinese when it keeps diffs focused.
- Add a small reusable tooltip/glossary component using existing dependencies and lucide icons.
- Update tests and snapshots to assert the Chinese UI.
- Keep raw backend values visible while adding Chinese labels or explanations around them.

OMX should not decide without confirmation:
- Add new runtime dependencies.
- Change backend API contracts.
- Change persisted data formats.
- Translate or mutate user-generated/backend-generated raw content.
- Redesign the console layout beyond what is needed for Chinese text fit and tooltip affordances.

## Terminology Rules

Translate as Chinese:
- `Sandbox` -> `沙箱`
- `Docker Sandbox` -> `Docker 沙箱`
- `Subagent` -> `子代理`
- `Agent` may remain `Agent` only when used as a canonical product/entity name; otherwise prefer `智能体` if the surrounding copy is explanatory.
- `Run` -> `运行` or `运行记录`, depending on UI context.
- `Tool` -> `工具`
- `Observability` -> `观测`
- `Eval` -> `评测`
- `Policy` -> `策略`
- `Model` -> `模型`

Keep as canonical English:
- API paths and methods, such as `GET /api/tasks`.
- Protocol/spec names, such as `OpenAPI`, `SSE`.
- Brand/tool names, such as `Harness`, `Docker`, `Prometheus`, `Grafana`, provider/model ids.
- Code identifiers, environment variables, enum/raw backend values, trace ids, run ids, agent ids, and file names.

Explain when helpful:
- `OpenAPI`: API 规范文档，可导入调试工具。
- `SSE`: 服务端事件流，用于实时推送。
- `Prometheus`: 指标采集与告警系统。
- `Grafana`: 可视化监控面板。
- `Planner`: 规划器，将目标拆成步骤。
- `Executor`: 执行器，按步骤调用工具。
- `Replay`: 重放，用历史事件重建运行状态。
- `WarmPool`: 预热池，减少沙箱冷启动等待。

## Constraints

- No new dependencies unless explicitly requested.
- Prefer existing `useI18n` / local helper patterns where they reduce churn, but the final visible console UI should be fixed Chinese.
- Keep UI density and layout stable; Chinese text must not overflow compact controls.
- Tooltips must be keyboard/mouse accessible enough for normal usage, with `title` acceptable for simple cases if consistent with existing UI.

## Testable Acceptance Criteria

- Console has no user-facing English language toggle.
- Console shell and every route listed in scope displays Chinese UI copy by default.
- Old English-only assertions in console tests are updated or removed.
- `Sandbox` user-facing labels are translated to `沙箱`; `Subagent` user-facing labels are translated to `子代理`.
- Code/API/protocol/brand/raw backend values remain unchanged.
- Hard-to-translate retained English terms have concise Chinese explanation via adjacent small text or tooltip where they appear as user-facing concepts.
- Typecheck passes for `apps/agent-console`.
- Relevant unit/render tests pass after copy updates.
- At least one browser smoke or targeted render check validates the main console route and one secondary route.

## Assumptions Exposed + Resolutions

- Assumption: the marketing website was part of "网站所有页面".
  Resolution: user clarified only the console is in scope.
- Assumption: existing Chinese/English toggle should remain.
  Resolution: user selected fixed Chinese UI and removal of English switching.
- Assumption: all English technical terms need preservation.
  Resolution: user selected preservation only for code/API/protocol/brand/raw values, with most UI terms translated.
- Assumption: `Sandbox` and `Subagent` should remain English.
  Resolution: translate them as `沙箱` and `子代理`.

## Brownfield Evidence Notes

- Existing console i18n surface: `apps/agent-console/src/lib/i18n.ts`
- Existing locale store: `apps/agent-console/src/stores/consoleStore.ts`
- Existing language toggle: `apps/agent-console/src/app/ConsoleShell.tsx`
- Route inventory: `apps/agent-console/src/app/routes.tsx`
- Likely major text surfaces: `apps/agent-console/src/features/**`

## Recommended Handoff

Use `$ralplan` or direct execution from this spec. Planning is useful because the change touches many UI surfaces and tests, but implementation can remain local to `apps/agent-console`.
