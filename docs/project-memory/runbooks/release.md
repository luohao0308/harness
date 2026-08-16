# Release Runbook

## Version Bump

Prepare a version bump locally:

```bash
scripts/release.sh patch
```

The script updates:

- `apps/agent-console/package.json`
- `apps/agent-console/package-lock.json`
- `apps/desktop-app/package.json`
- `apps/desktop-app/package-lock.json`
- `services/api-server/pyproject.toml`

Run validation before committing the bump.

## Tag Release

```bash
git tag -a v0.1.1 -m "Release v0.1.1"
git push origin HEAD --tags
```

`release.yml` requires the tag commit to be reachable from `origin/main`, generates release notes from tags, builds tagged GHCR images, packages the Helm chart, creates a GitHub Release, and opens an ops PR that updates default Helm image tags.

Stable desktop releases use normal semver tags, for example `v0.2.0`. Beta
desktop releases use prerelease semver tags containing `-beta.`, for example
`v0.3.0-beta.1`. The release workflow marks beta tags as GitHub prereleases and
sets `HARNESS_DESKTOP_UPDATE_CHANNEL=beta` for the desktop build matrix.

## Desktop Packaging

`release.yml` builds Harness Desktop on macOS, Windows, and Linux. The desktop
matrix builds the Agent Console renderer, installs `apps/desktop-app`
dependencies, runs updater/crash/startup contract tests, packages the app, and
then runs five isolated host-architecture startup samples:

```bash
cd apps/desktop-app
npm run dist:mac
npm run dist:win
npm run dist:linux
npm run check:startup-budget
```

The generated GitHub Release assets include:

- macOS: signed and notarized `dmg` plus `zip` for `x64` and `arm64`
- Windows: Authenticode signed `nsis` installers for `x64` and `arm64`
- Linux: `AppImage`, `deb`, and `rpm` for `x64` and `arm64`
- electron-updater metadata: `latest.yml`, `latest-mac.yml`,
  `latest-linux.yml`, and matching blockmaps
- measured startup evidence:
  `startup-budget-report-<platform>-<arch>.json` with raw samples and P50/P95
- independently validated cross-platform summary:
  `desktop-startup-evidence.json`

The GitHub Release is blocked when a packaged report is malformed, comes from a
different platform/architecture, does not contain exactly five samples, is
missing or duplicated across artifacts, disagrees with its aggregate fields,
uses a different app version, or exceeds any phase or total P95 budget.

Use `docs/development/desktop/README.md` as the desktop production release checklist. It
defines the local release-candidate gate, external signing/notarization gate,
update-channel expectations, privacy/security checks, and support playbook.

## Desktop Signing Secrets

Configure these GitHub Actions secrets before promoting desktop releases:

- `MACOS_CSC_LINK`: base64 certificate or secure URL for the Apple Developer ID
  Application certificate.
- `MACOS_CSC_KEY_PASSWORD`: password for the macOS signing identity.
- `APPLE_API_KEY`, `APPLE_API_KEY_ID`, `APPLE_API_ISSUER`: preferred App Store
  Connect API credentials for notarization.
- `APPLE_ID`, `APPLE_APP_SPECIFIC_PASSWORD`, `APPLE_TEAM_ID`: fallback Apple ID
  notarization credentials.
- `WINDOWS_CSC_LINK`: base64 certificate or secure URL for the Authenticode
  code-signing certificate.
- `WINDOWS_CSC_KEY_PASSWORD`: password for the Windows signing certificate.

Local unsigned packaging is allowed for verification. CI should have signing
secrets for release tags; otherwise macOS notarization and Windows Authenticode
signing will be skipped or fail depending on the runner certificate state.

## Desktop Updates

The desktop app checks `/api/desktop/updates/check` before invoking
`electron-updater`. The backend owns channel policy and returns the GitHub
Release metadata feed URL. Configure these deployment variables:

- `DESKTOP_UPDATE_STABLE_VERSION`: latest stable desktop version.
- `DESKTOP_UPDATE_BETA_VERSION`: latest beta desktop version.
- `DESKTOP_UPDATE_LATEST_VERSION`: optional fallback used by both channels.
- `DESKTOP_UPDATE_GITHUB_REPO`: owner/repo for GitHub Releases, default
  `luohao0308/harness`.
- `DESKTOP_UPDATE_FEED_BASE_URL`: optional override for update metadata hosting.
- `DESKTOP_UPDATE_RELEASE_BASE_URL`: optional override for human release links.
- `DESKTOP_UPDATE_NOTES`: optional short note returned by the update endpoint.

Keep backend versions aligned with the published GitHub Release assets. Stable
clients ignore beta metadata; beta clients opt into prerelease updates.

## Desktop Crash Reporting

Set `HARNESS_DESKTOP_SENTRY_DSN` in the release workflow or runtime environment.
The desktop build sets `SENTRY_RELEASE=harness-desktop@<tag>`, initializes
Sentry in the Electron main process, captures uncaught main-process failures,
records renderer crashes/unresponsive windows, and uploads desktop sourcemaps
when `SENTRY_AUTH_TOKEN`, `SENTRY_ORG`, and `SENTRY_PROJECT` are configured.

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
