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

## Release Build

`release.yml` runs on `v*.*.*` tags after verifying the tag is reachable from
`origin/main`. It builds tagged API and Console images, packages the Helm chart,
and builds Harness Desktop installers on macOS, Windows, and Linux.

Desktop release jobs build the Agent Console renderer first, run focused desktop
tests for `electron-updater`, Sentry crash reporting, main-process startup
ordering, telemetry, and startup-budget aggregation, then package:

- macOS `dmg` and `zip`
- Windows `nsis` installer
- Linux `AppImage`, `deb`, and `rpm`
- updater metadata and blockmap files for incremental downloads
- `startup-budget-report-<platform>-<arch>.json` with five packaged samples plus
  phase/total P50 and P95 timings

After packaging, every platform launches its host-architecture executable with
a fresh profile five times. Linux uses Xvfb. A malformed/unpackaged/wrong-arch
report or any P95 budget violation fails `desktop-build`. A separate
`desktop-startup-evidence` job then downloads the three artifacts without
merging them, requires one five-sample report for each expected platform and
architecture, recomputes aggregate fields, and emits
`desktop-startup-evidence.json`. GitHub Release depends on both gates.

Tags containing `-beta.` are published as GitHub prereleases and use the desktop
beta update channel. Other tags use the stable channel. The GitHub Release
contains Helm artifacts, all desktop installers and updater metadata, the three
raw startup reports, and the independent startup evidence summary.

Required desktop release secrets:

- `MACOS_CSC_LINK`, `MACOS_CSC_KEY_PASSWORD`
- `APPLE_API_KEY`, `APPLE_API_KEY_ID`, `APPLE_API_ISSUER`
- `APPLE_ID`, `APPLE_APP_SPECIFIC_PASSWORD`, `APPLE_TEAM_ID`
- `WINDOWS_CSC_LINK`, `WINDOWS_CSC_KEY_PASSWORD`
- `HARNESS_DESKTOP_SENTRY_DSN`
- `SENTRY_AUTH_TOKEN`, `SENTRY_ORG`, `SENTRY_PROJECT` for sourcemap upload

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
cd apps/desktop-app && npm run test -- src/__tests__/desktop-updates.test.ts src/__tests__/crash-reporting.test.ts
cd apps/desktop-app && npm run test:startup-budget
cd apps/desktop-app && npm run build:main
cd apps/desktop-app && npm run build:renderer
cd apps/desktop-app && npx electron-builder --dir --publish never
cd apps/desktop-app && npm run check:startup-budget
scripts/check-bundle-size.sh apps/agent-console/dist
python3 scripts/validate-docs.py
git diff --check
```

For desktop-specific release candidate coverage, use the verification matrix in
`docs/development/desktop/README.md#verification-matrix`. It extends the local mirrors with
`electron-builder --dir --publish never`, browser `/desktop` and `/terminal`
smoke checks, real Electron preload bridge smoke, and release YAML/script
validation.
