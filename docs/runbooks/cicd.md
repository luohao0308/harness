# CI/CD Runbook

## Pull Request Gate

Required GitHub Actions workflow:

```bash
.github/workflows/pr-check.yml
```

Required jobs:

- `lint-backend`: `ruff check app tests`
- `lint-frontend`: `npm run lint -- --pretty false`
- `test-backend`: PostgreSQL and Redis service containers plus `pytest`
- `test-frontend`: single-fork Vitest
- `build-frontend`: Vite build plus `scripts/check-bundle-size.sh`
- `migration-preflight`: PostgreSQL Alembic `upgrade head`
- `docs-validation`: `python3 scripts/validate-docs.py`
- `whitespace`: `git diff --check`

Configure branch protection on `main` to require the `PR Check` workflow before merge.

## Main Build

`main-build.yml` builds and publishes:

```text
ghcr.io/<owner>/harness-api:sha-<sha>
ghcr.io/<owner>/harness-api:latest
ghcr.io/<owner>/harness-console:sha-<sha>
ghcr.io/<owner>/harness-console:latest
```

It also packages `deploy/helm/harness` and boots `compose.ci.yml` for a health smoke.

## Scheduled Security

`scheduled-security.yml` runs weekly:

```bash
pip-audit -r /tmp/harness-requirements.txt
npm audit --audit-level=high
```

Dependabot opens weekly PRs for npm, pip, and GitHub Actions updates.

## Local Mirrors

```bash
cd services/api-server && .venv/bin/ruff check app tests
cd services/api-server && .venv/bin/pytest
cd apps/agent-console && npm run lint -- --pretty false
cd apps/agent-console && npm run build
scripts/check-bundle-size.sh apps/agent-console/dist
python3 scripts/validate-docs.py
git diff --check
```
