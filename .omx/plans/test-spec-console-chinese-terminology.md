# Test Spec: Console Chinese Terminology

## Scope

Validate the PRD in `.omx/plans/prd-console-chinese-terminology.md`.

## Required Commands

Run from repo root:

```sh
cd apps/agent-console && npm run lint
cd apps/agent-console && npm run test
cd apps/agent-console && npm run e2e:smoke:release
```

If `e2e:smoke:release` is infeasible, run targeted existing smoke specs covering the console main route and at least one secondary route, and document the blocker plus exact replacement command.

## Unit / Render Coverage

Required updates or additions:

- `ConsoleShell` render coverage:
  - Chinese shell/chrome appears by default.
  - Language toggle is absent.
  - Old persisted `en-US` or explicit old locale setup still renders Chinese UI.
- Agent workspace related render tests:
  - Replace English role/name assertions with Chinese UI assertions unless the string is raw/canonical.
  - Check retained `Agent` use is intentional/canonical or explanatory copy uses `智能体`.
- Route/component tests touched by copy updates:
  - Replace English-mode assertions.
  - Assert `沙箱` and `子代理` where those labels appear.
  - Preserve raw ids, API paths, provider/model ids, and backend/user-generated content.

## Browser Smoke Coverage

Release smoke target:

- Prefer `cd apps/agent-console && npm run e2e:smoke:release`.

Minimum targeted substitute if release smoke cannot run:

- Main route: `/agents` or `/agents/default/workspace`
  - Chinese shell/nav/search/title visible.
  - No language toggle.
- Secondary route: `/sandboxes` or `/runs/:runId/subagents`
  - `沙箱` or `子代理` visible as user-facing label.
  - Raw ids/backend evidence remain unchanged.

## Static Search Classification

Run searches for:

- `English`
- `Language`
- `中文`
- `en-US`
- `Sandbox`
- `Subagent`
- `Agent`
- visible locale/language branching

Classify each remaining user-visible English hit as:

- `raw/canonical`
- `user/backend supplied`
- `explained visible term`
- `bug to translate`

The implementation is not complete while any `bug to translate` remains.

## Route Checklist Evidence

For every route/surface in the PRD route matrix, record one of:

- Render/unit test evidence.
- Browser smoke evidence.
- Static/manual verification note.

Each route note must confirm:

- Chinese UI reviewed.
- No visible language toggle.
- `Sandbox` / `Subagent` / `Agent` glossary rules followed where applicable.
- Required retained technical English terms are explained or marked not visible/raw-only.
- Raw/canonical values are preserved.

## Acceptance Gates

Pass criteria:

- `npm run lint` passes.
- `npm run test` passes.
- Release e2e smoke passes, or targeted smoke replacement is run with a documented release-smoke blocker.
- Static search classification has no unresolved `bug to translate`.
- Route checklist is complete.

Residual risk to report if present:

- Any skipped e2e coverage.
- Any retained English term that is visible but not yet explained due to UI constraints.
- Any route verified only by static/manual inspection rather than render/browser test.
