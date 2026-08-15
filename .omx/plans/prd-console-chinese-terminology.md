# PRD: Console Chinese Terminology

## Source Of Truth

- Deep-interview spec: `.omx/specs/deep-interview-console-chinese-terminology.md`
- Transcript: `.omx/interviews/console-chinese-terminology-20260515T042314Z.md`
- Ralplan consensus: Planner revised after Architect/Critic review; final Architect and Critic verdicts: `APPROVE`.

## Goal

Convert `apps/agent-console` into a fixed Chinese console experience across all routes, while preserving canonical technical values and raw backend/user-generated evidence.

## Scope

Only `apps/agent-console` is in scope.

Routes requiring coverage:

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

Shared surfaces requiring coverage:

- Console shell, navigation, breadcrumbs, search, filters, tabs, dialogs, popovers, menus, empty/loading/error states, aria labels, table/chart labels, forms, buttons, and test-visible copy.

## Non-Goals

- Do not change `apps/web-site`.
- Do not add dependencies.
- Do not change backend API contracts, schemas, persisted data formats, or generated/user/backend content.
- Do not implement or preserve a user-facing bilingual mode.
- Do not translate API paths, HTTP methods, code identifiers, env vars, filenames, provider/model ids, trace/run/agent/subagent ids, enum/raw backend values, or user-generated text.

## Decision

Use a Chinese-only compatibility strategy:

- Remove visible language-toggle affordances.
- Ensure persisted `en-US` or unsupported locale state cannot render English UI.
- `useI18n` may remain only as a Chinese-only compatibility wrapper while call sites are migrated safely.
- Static search findings for English must be classified as one of:
  - `raw/canonical`
  - `user/backend supplied`
  - `explained visible term`
  - `bug to translate`

## RALPLAN-DR

Principles:

- Every user-facing console surface renders fixed Chinese UI.
- Preserve canonical precision for code, API/protocol names, brands, ids, enum/raw/backend/user values.
- Keep churn bounded to `apps/agent-console`.
- Use existing helper patterns only where they reduce risk without keeping hidden English mode alive.
- Verification must prove both removal of English mode and route-wide Chinese coverage.

Decision drivers:

- User selected fixed Chinese UI, not bilingual mode.
- Existing persisted `en-US` must not cause English UI.
- Route and test surface is broad, so implementation needs checklist-driven coverage.

Alternatives:

- Chosen: keep a Chinese-only compatibility wrapper around `useI18n`, remove visible language switching, convert console UI copy to Chinese.
- Rejected: keep bilingual toggle. It conflicts with fixed Chinese product direction.
- Rejected: translate every English token. It would corrupt canonical identifiers such as `OpenAPI`, `SSE`, provider/model ids, API paths, ids, and raw evidence values.
- Rejected: remove `useI18n` entirely in one pass. Too much churn across routes and tests; compatibility wrapper gives safer migration while blocking English rendering.

## Glossary

Translate user-facing explanatory terms:

- `Sandbox` -> `沙箱`
- `Docker Sandbox` -> `Docker 沙箱`
- `Subagent` -> `子代理`
- `Agent` -> use `智能体` in explanatory UI copy; retain `Agent` only for canonical product/entity naming.
- `Run` -> `运行` or `运行记录`, depending on context.
- `Tool` -> `工具`
- `Observability` -> `观测`
- `Eval` -> `评测`
- `Policy` -> `策略`
- `Model` -> `模型`

Retain canonical English:

- API paths/methods, code identifiers, env vars, file names.
- Protocol/spec names: `OpenAPI`, `SSE`.
- Brands/tools: `Harness`, `Docker`, `Prometheus`, `Grafana`.
- Provider/model ids, trace/run/agent/subagent ids, enum/raw backend values, user-generated values.

Required explanation rule:

For retained user-facing `OpenAPI`, `SSE`, `Prometheus`, `Grafana`, `Planner`, `Executor`, `Replay`, and `WarmPool`, add concise Chinese explanation via small text or tooltip. If a term is not visible to users, or appears only as raw backend/data evidence, record that in the route checklist.

Suggested explanations:

- `OpenAPI`: API 规范文档，可导入调试工具。
- `SSE`: 服务端事件流，用于实时推送。
- `Prometheus`: 指标采集与告警系统。
- `Grafana`: 可视化监控面板。
- `Planner`: 规划器，将目标拆成步骤。
- `Executor`: 执行器，按步骤调用工具。
- `Replay`: 重放，用历史事件重建运行状态。
- `WarmPool`: 预热池，减少沙箱冷启动等待。

## Implementation Plan

1. Inventory current text surfaces from `routes.tsx`, `ConsoleShell.tsx`, `src/features/**`, shared components, stores, test fixtures, and render/e2e specs.
2. Convert `useI18n`/locale rendering to Chinese-only behavior; remove visible language toggle and any visible `English` / `Language` / locale-switching affordance.
3. Convert shell/shared UI copy to Chinese, including nav, search, breadcrumbs, buttons, placeholders, aria labels, menus, popovers, dialogs, tables, charts, and empty/error states.
4. Convert each route in the route matrix to Chinese UI copy using the glossary. Preserve raw/canonical values.
5. Add concise explanations for retained user-facing technical English terms, or document why the term is raw-only/not visible.
6. Update render/unit/e2e tests away from English-mode assumptions.
7. Run static searches, complete the route checklist, then run verification commands.

## Route Checklist

For every route/surface listed in scope, record during execution:

- Chinese UI reviewed.
- No visible language toggle.
- `Sandbox` translated to `沙箱` when user-facing.
- `Subagent` translated to `子代理` when user-facing.
- `Agent` retained only as canonical product/entity term; explanatory copy uses `智能体`.
- Retained English terms are explained or documented as not visible/raw-only.
- Raw/canonical/user/backend values are preserved unchanged.

## Acceptance Criteria

- No user-facing English language toggle remains.
- Persisted `en-US` cannot render English UI.
- Every in-scope route renders Chinese UI by default.
- User-facing `Sandbox`, `Subagent`, and explanatory `Agent` copy follow glossary rules.
- Canonical/raw/code/API/protocol/brand/id/backend/user-generated values remain unchanged.
- Required retained English user-facing concepts have Chinese explanation or checklist justification.
- Tests no longer depend on English-mode UI.
- Chinese text fits existing compact controls without obvious layout breakage.

## Execution Handoff

Recommended lane: `$ralph` single-owner execution, because the work is broad but localized to `apps/agent-console` and needs consistent terminology plus route-by-route verification.

Team lane if speed matters:

- Executor A: i18n/store/shell/shared labels.
- Executor B: agents/runs/subagents surfaces.
- Executor C: sandboxes/observability/tools/evals/settings surfaces.
- Test engineer: render/e2e assertion updates and smoke coverage.
- Verifier: route checklist, static searches, final commands.

## Agent Roster Guidance

- `executor`: code changes in `apps/agent-console`.
- `test-engineer`: test migration and smoke coverage.
- `verifier`: static search classification, route checklist, final validation.
- `code-reviewer`: final risk review if the diff is large.

Suggested reasoning:

- Executor: medium.
- Test engineer: medium.
- Verifier/code reviewer: high.
