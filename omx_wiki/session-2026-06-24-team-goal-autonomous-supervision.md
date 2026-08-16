# Team Goal Autonomous Supervision

Category: session-log
Tags: `team-mode`, `team-goal`, `supervision`, `drift-correction`, `agent-console`, `api-server`

## Summary

Team Mode now supports a Team-owned active goal with Leader-side automatic supervision. A Team can keep working toward a durable goal while the Leader monitors drift, sends corrective messages, narrows tasks, reassigns work, or blocks the goal when the correction budget is exhausted.

The UI stays compact: the Team header shows the active goal, current status, task counts, drift/fix counters, and remaining budget, while the task board only adds a small `needs_correction` marker when the supervisor intervenes.

## Review Fixes

The follow-up code review findings are now closed for the Team Goal surface:

- Database invariant:
  `team_goals` now has a partial unique index that allows only one current `active` or `paused` goal per team. Service writes still return HTTP 409 on conflicts, and reads use deterministic latest-first `.limit(1)` so historical duplicate rows cannot crash Team projection.
- Pause semantics:
  current visible goals and auto-supervised goals are separate. A paused goal remains visible through `active_goal`, but automatic message/task supervision only runs when `status == "active"`.
- Terminal projection:
  terminal statuses now emit terminal `TEAM_GOAL_*` events, and the frontend clears `active_goal` for terminal goals even if an old or out-of-order terminal update arrives as `TEAM_GOAL_PROGRESS`.
- Input validation:
  create/update reject blank objectives and malformed or negative `max_interventions` with 422. The editor also disables saving an empty objective.

## Changes

- `services/api-server/app/db/models.py`
  - adds `TeamGoal`;
  - wires Team -> goals relationship;
  - restores `Session = UserSession` as a compatibility export for older backend imports.
- `services/api-server/alembic/versions/20260624_0046_create_team_goals.py`
  - creates `team_goals`.
- `services/api-server/app/api/teams.py`
  - adds Team Goal create/active/update/supervise routes;
  - includes `active_goal` in Team responses.
- `services/api-server/app/teams/goal_supervisor.py`
  - implements deterministic drift detection and bounded interventions.
- `services/api-server/app/teams/service.py`
  - adds Team Goal CRUD/projection helpers;
  - auto-runs supervision on Team message and task updates.
- `apps/agent-console/src/features/tasks/api.ts`
  - adds Team Goal types and request helpers.
- `apps/agent-console/src/features/teams/pages/TeamPage/*`
  - projects ordered `TEAM_GOAL_*` state;
  - adds the compact goal strip, pause/resume/edit controls, and correction badge.

## Supervision Rules

- Scope drift:
  teammate proposes dependency, destructive, deploy, or obvious scope-expansion work outside the goal boundary.
- Collaboration drift:
  teammate replies with standby/no-op while assigned work remains open.
- Task drift:
  teammate claims completion without a matching Team task completion update.
- Quality/evidence drift:
  teammate marks a task completed without the evidence/tests implied by the goal acceptance criteria.

Interventions are graded:

- Level 1:
  send a corrective Leader message.
- Level 2:
  mark the task `needs_correction` and narrow the task/evidence requirement.
- Level 3:
  reassign the task when possible; otherwise block the goal.

## Validation

```text
services/api-server/.venv/bin/python -m pytest services/api-server/tests/test_teams.py -q
42 passed

services/api-server/.venv/bin/python -m ruff check services/api-server/app/db/models.py services/api-server/app/api/teams.py services/api-server/app/teams services/api-server/tests/test_teams.py services/api-server/alembic/versions/20260624_0046_create_team_goals.py
passed

cd apps/agent-console && PATH="/Users/luohao/.nvm/versions/node/v20.9.0/bin:/usr/local/bin:$PATH" npx vitest run src/features/teams/__tests__/TeamPages.test.tsx
21 passed

cd apps/agent-console && PATH="/Users/luohao/.nvm/versions/node/v20.9.0/bin:/usr/local/bin:$PATH" npx tsc --noEmit --pretty false --types vite/client,vitest/globals,@testing-library/jest-dom --skipLibCheck --jsx react-jsx --lib DOM,DOM.Iterable,ES2022 --module ESNext --moduleResolution Bundler --target ES2020 --esModuleInterop --allowSyntheticDefaultImports src/features/teams/pages/TeamPage/index.tsx src/features/teams/pages/TeamPage/TeamHeader.tsx src/features/teams/pages/TeamPage/TeamGoalEditorDialog.tsx src/features/teams/pages/TeamPage/TeamTaskBoard.tsx src/features/teams/pages/TeamPage/teamState.ts src/features/teams/__tests__/TeamPages.test.tsx src/features/tasks/api.ts
passed

cd services/api-server && rm -f /tmp/harness-team-goals-review-fix.sqlite && DATABASE_URL=sqlite:////tmp/harness-team-goals-review-fix.sqlite .venv/bin/alembic upgrade heads
passed

python3 scripts/validate-docs.py
docs validation passed

git diff --check
passed
```

## Wider Validation Notes

- `cd apps/agent-console && npm run build` is still blocked by existing repo-wide TypeScript test debt outside the touched Team files:
  `jest-axe` typings, stale a11y imports/fixtures, and missing legacy `tasks/api` exports.
- `services/api-server/.venv/bin/python -m pytest services/api-server/tests` now gets past the old collection blocker because `app.db.models.Session` is available again, but the broader suite still fails in unrelated SAML and validation areas:
  - `app.services.saml_service` uses `OneLogin_Saml2_Settings.to_dict()` where the installed object does not provide it;
  - SAML metadata tests expect `generate_sp_metadata()` to return `str` while it currently returns `bytes`;
  - validation-service migration tests currently receive `Alembic configuration not found`.

Those blockers were already outside the Team Goal change surface; this session only made them visible sooner by removing the old collection-time import failure.
