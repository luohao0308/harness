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

## Delivery Flow

Harness uses a single stable trunk with short-lived branches:

```text
main
feat/<scope>-<short-name>
fix/<scope>-<short-name>
docs/<short-name>
chore/<short-name>
```

Create branches from the current `origin/main`, open a PR back to `main`, wait for required CI, then squash merge and delete the short-lived branch. Release branches are reserved for multi-platform release candidates; `develop` is not a required daily integration layer.

Install the lightweight repository hooks once per clone:

```bash
scripts/install-git-hooks.sh
```

## Commit Messages

Commit and PR titles use Conventional Commits:

```text
<type>(<scope>): <imperative summary>

feat(team): add overview and focused conversation
fix(local-agent): isolate binding state
docs(workflow): explain release rollback
```

Allowed types are `feat`, `fix`, `refactor`, `docs`, `test`, `chore`, `ci`, `build`, `perf`, and `revert`. Scope is lowercase kebab-case, and the complete title is at most 88 characters. Non-trivial bodies should state Why, Impact, and Validation without claiming tests that were not run.

Local `fixup!` and `squash!` commits are allowed while developing, but the PR gate requires them to be folded before review.

## Dependency Updates

Dependabot opens weekly npm, pip, and GitHub Actions PRs. Security PRs should run the normal PR gate plus targeted smoke for the affected surface.

## Releases

Release tags must be reachable from `main`. Use `scripts/release.sh patch|minor|major` for version bumps and follow `docs/project-memory/runbooks/release.md` for tag, release, and canary steps.
