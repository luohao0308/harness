# Contributing

## Pull Requests

Before opening a PR, run the smallest relevant checks and include the exact commands in the PR body.

Required release-gate mirrors:

```bash
cd services/api-server && .venv/bin/ruff check app tests
cd services/api-server && .venv/bin/pytest
cd apps/agent-console && npm run lint -- --pretty false
cd apps/agent-console && npm run build
python3 scripts/validate-docs.py
git diff --check
```

## Commit Messages

This repository uses the Lore commit protocol. Commit messages should explain why the change exists and include useful trailers:

```text
Harden release automation so deployable artifacts are repeatable

Constraint: GitHub-hosted runners and GHCR are the v1 release path.
Confidence: high
Scope-risk: moderate
Tested: npm run build; pytest; validate-docs
Not-tested: live GHCR release push
```

## Dependency Updates

Dependabot opens weekly npm, pip, and GitHub Actions PRs. Security PRs should run the normal PR gate plus targeted smoke for the affected surface.

## Release Branches

Release tags must be reachable from `main`. Use `scripts/release.sh patch|minor|major` for version bumps and follow `docs/runbooks/release.md` for tag, release, and canary steps.
