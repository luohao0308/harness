# P3 P6 P7 Auth Retention CI/CD

Category: session-log
Tags: `auth`, `rbac`, `retention`, `data-lifecycle`, `cicd`, `release`, `security`, `task-progress`

## Summary

P3 AuthN/AuthZ/RBAC, P6 data lifecycle retention, and P7 CI/CD release engineering are implemented and verified on `p7-release-demo-hardening`.

The delivery adds real JWT/API-key auth, organization-scoped RBAC, user/API-key/audit settings, retention/export/delete management, GitHub Actions release gates, Dependabot, production Dockerfiles, CI compose smoke, bundle/release scripts, Helm canary defaults, and deployment runbooks.

## Review Fixes

Code review found and fixed blocking issues before completion:

- JWT principals now require a current active user and accepted organization membership; removed users or removed memberships cannot keep using old access tokens.
- API-key principals now require a current active user and accepted organization membership.
- Organization export ZIP payloads redact credential verifier fields: `users.password_hash` and `api_keys.key_hash`.
- PR whitespace checks now fetch full history before diffing against the pull request base branch.
- API production Dockerfile healthcheck now uses a single `python -c` command instead of Dockerfile here-doc parsing.

## Validation

```text
cd services/api-server && .venv/bin/pytest tests/test_auth.py tests/test_auth_rbac_api_keys.py tests/test_retention_data_management.py -q
11 passed

cd services/api-server && .venv/bin/ruff check app tests
All checks passed

cd services/api-server && .venv/bin/pytest tests -q
518 passed, 2 warnings

cd services/api-server && DATABASE_URL=sqlite:////tmp/harness-p3-p6-p7-review.sqlite .venv/bin/alembic upgrade head
reached 20260604_0031

cd apps/agent-console && npm run lint -- --pretty false
passed

cd apps/agent-console && npm test -- --run --pool forks --poolOptions.forks.singleFork
48 files / 223 tests passed

cd apps/agent-console && npm run build && ../../scripts/check-bundle-size.sh dist
passed; largest_js=476410 max=512000

docker compose -f compose.ci.yml config
passed

bash -n scripts/check-bundle-size.sh scripts/changelog-from-tags.sh scripts/release.sh
passed

python3 scripts/validate-docs.py
passed

git diff --check
passed
```

## Boundaries

- Helm template/lint was not run because Helm is not installed in this environment.
- Docker image build/push and GitHub Actions execution were not run locally.
- OAuth provider callbacks remain local stub surfaces for this slice; real external OAuth provider integration is a future credentialed task.
