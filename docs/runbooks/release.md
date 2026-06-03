# Release Runbook

## Version Bump

Prepare a version bump locally:

```bash
scripts/release.sh patch
```

The script updates:

- `apps/agent-console/package.json`
- `apps/agent-console/package-lock.json`
- `services/api-server/pyproject.toml`

Run validation before committing the bump.

## Tag Release

```bash
git tag -a v0.1.1 -m "Release v0.1.1"
git push origin HEAD --tags
```

`release.yml` requires the tag commit to be reachable from `origin/main`, generates release notes from tags, builds tagged GHCR images, packages the Helm chart, creates a GitHub Release, and opens an ops PR that updates default Helm image tags.

## Changelog

Preview release notes:

```bash
scripts/changelog-from-tags.sh v0.1.1
```

Update `CHANGELOG.md` only for curated human-facing release notes. Generated notes remain attached to the GitHub Release.

## Canary

Render canary YAML:

```bash
helm template harness deploy/helm/harness \
  --set canary.enabled=true \
  --set canary.weight=5 \
  --set canary.image.api=agent-harness-api-server:v0.1.1
```

Deploy 5 percent API traffic:

```bash
helm upgrade --install harness deploy/helm/harness \
  --set canary.enabled=true \
  --set canary.weight=5 \
  --set canary.image.api=agent-harness-api-server:v0.1.1
```

Observe readiness, API error rate, SSE stability, and smoke checks for five minutes. Promote by setting the main image tag to the canary tag and disabling canary.

## Smoke

For a deployed stack:

```bash
cd apps/agent-console
HARNESS_PLAYWRIGHT_EXTERNAL_SERVER=1 \
HARNESS_PLAYWRIGHT_BASE_URL=https://harness.example.com \
npx playwright test --project=chromium e2e/smoke-deploy.spec.ts
```
