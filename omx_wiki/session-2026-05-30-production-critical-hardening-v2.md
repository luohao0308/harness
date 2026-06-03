# Production Critical Hardening v2

Category: `session-log`

Tags: `production`, `auth`, `jwt`, `first-run-admin`, `migration`, `deployment`, `code-review`

## Summary

Executed `.omx/plans/prd-production-critical-hardening-v2.md` and completed the required post-implementation code review. The slice closes the production blockers around always-on dev tokens, undocumented first admin login, missing JWT secret examples, and repeated Alembic seed id width regressions.

## Implemented

- Dev bearer tokens are enabled only for `APP_ENV=development` or `APP_ENV=test`; production and staging reject `dev-admin-token`.
- `AUTH_JWT_SECRET` no longer has a dev fallback and is validated at startup and JWT signing time for missing, placeholder, short, or production `dev-only-*` values.
- First-run admin bootstrap creates one owner user from `HARNESS_INITIAL_ADMIN_EMAIL` and `HARNESS_INITIAL_ADMIN_PASSWORD` only when the users table is empty.
- Added `scripts/create-admin.py` plus `python -m app.cli.create_admin` as a fallback owner creation path.
- Added patch migration `20260605_0032_remove_legacy_admin_seed.py` to remove original `dev-admin` and `dev-engineer` seed rows only when their original dev hash still matches.
- Added `scripts/check-migration-ids.py`, CI `migration-id-lint`, tests, and migration conventions docs.
- Updated production compose, private handoff compose, Helm secrets/deployments/job, env examples, smoke scripts, README, and deployment runbooks for real JWT login and first-run admin.
- Hardened production frontend auth so console builds no longer embed dev tokens, chat/SSE paths use stored JWTs, empty token args do not create empty Authorization headers, and org knowledge controls work for owner/admin JWT users.

## Code Review Fixes

- Fixed a TypeScript compile failure from a `headers` local variable collision in `useChatStream`.
- Preserved test-mode local console CORS behavior while keeping production/staging restricted.
- Added `AUTH_JWT_SECRET` to the Helm migration Job for deploy-surface consistency.
- Hardened migration downgrade so it restores missing legacy rows without clobbering or duplicating preserved legacy users whose password hash had changed.
- Added a bootstrap race regression test for concurrent first-admin creation.

## Validation

- `python3 scripts/check-migration-ids.py services/api-server/alembic/versions/` -> passed, 32 files.
- `cd services/api-server && .venv/bin/python -m pytest tests/test_cors.py tests/test_auth_env_gate.py tests/test_first_admin_bootstrap.py tests/test_migration_id_lint.py -q` -> `13 passed`.
- `cd services/api-server && .venv/bin/python -m pytest tests -q` -> `538 passed, 2 warnings`.
- `cd services/api-server && .venv/bin/python -m ruff check app tests ../../scripts/check-migration-ids.py ../../scripts/create-admin.py` -> passed.
- SQLite Alembic `upgrade head` reached `20260605_0032`.
- SQLite Alembic upgrade/downgrade path passed with an intermediate preserved custom `dev-admin` password hash.
- `cd apps/agent-console && npm run lint -- --pretty false` -> passed.
- `cd apps/agent-console && npm test -- --run --pool forks --poolOptions.forks.singleFork` -> `49 passed / 224 tests`.
- `cd apps/agent-console && npm run build && ../../scripts/check-bundle-size.sh dist` -> passed; largest JS chunk `479540` bytes under `512000`.
- Production compose config passed with required `AUTH_JWT_SECRET`.
- Private handoff compose config passed with required `AUTH_JWT_SECRET`.
- `helm version --short` -> `v4.2.0+g0646808`.
- `helm lint deploy/helm/harness` -> passed with `0 chart(s) failed`.
- `helm template harness deploy/helm/harness` -> passed; rendered Secret, ConfigMap, API/console Deployments, Services, Ingress, HPA, PDB, and migration Job.
- `python3 scripts/validate-docs.py` -> passed.
- `git diff --check` -> passed.

## Gaps

- Docker image build/push, live production smoke, and GitHub Actions execution were not run locally.

## Next Notes

- Keep production smoke tests on real JWTs via `HARNESS_AUTH_TOKEN`, `HARNESS_ADMIN_TOKEN`, and `HARNESS_OPERATOR_TOKEN`.
- Do not reintroduce build-time dev-token defaults in production console images.
- Keep corrective migration changes as patch migrations rather than rewriting already-landed history.
