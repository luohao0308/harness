# Contributing

This repository uses spec-first delivery. Read `AGENTS.md`, then use the
startup contract in `docs/development/ai/agent-startup-context.md` and
`scripts/agent-context-brief.py` before changing code.

## Local Checks

```bash
cd services/api-server && .venv/bin/python -m pytest
cd services/api-server && .venv/bin/python -m ruff check app tests
cd apps/agent-console && npm test -- --run --pool forks --poolOptions.forks.singleFork
cd apps/agent-console && npm run build
python3 scripts/validate-docs.py
```

## Change Rules

- Keep diffs scoped to the active PRD or stage.
- Preserve backend-driven Console state; avoid static placeholder data.
- Update `docs/development/ai/task-progress.yaml` and a relevant `omx_wiki/` session page
  when a delivery slice is complete or blocked.
- Use the Lore commit protocol from `AGENTS.md` for commits.
