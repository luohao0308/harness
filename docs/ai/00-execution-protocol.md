# AI Execution Protocol

## Role

The executing AI works as an implementation agent for a Production Agent Harness Platform.

## Source Of Truth

For every new agent session, read the repository `AGENTS.md` first, then the
low-token startup context before any implementation work:

1. `AGENTS.md`
2. `docs/ai/agent-startup-context.md`
3. `docs/ai/task-progress.yaml`
4. Task-matched context from:

```text
python3 scripts/agent-context-brief.py --task "<user task>"
```

The brief chooses the smallest wiki, plan, and context set for the task. Use
filesystem reads as the reliable path for `omx_wiki/`; MCP wiki helpers are
secondary convenience tools.

Then read these product sources when the task changes contracts or crosses
module boundaries:

1. `docs/00-product-spec.md`
2. `docs/01-system-architecture.md`
3. `docs/02-data-model-and-event-spec.md`
4. `docs/03-api-spec.md`
5. `docs/ai/task-progress.yaml`
6. The current file under `docs/ai/stages/`

## Execution Rules

- Implement the current stage as a runnable vertical slice.
- Do not build a normal chatbot as the product center.
- Do not add static console data.
- Do not add placeholder routes.
- Backend state must drive frontend state.
- Every state-changing Agent operation must write an event or audit record.
- Eval Harness remains a first-class module.
- PostgreSQL remains the production database path.

## Stage Completion

Before advancing a stage:

```text
cd services/api-server && .venv/bin/python -m pytest
cd services/api-server && .venv/bin/python -m ruff check app tests
cd apps/agent-console && npm run build
python3 scripts/validate-docs.py
```

Then update:

- `docs/ai/task-progress.yaml`
- `omx_wiki/` with a session page or the relevant handoff page

`docs/task-progress.md` and `docs/human/10-task-progress.md` remain useful
human-facing summaries, but the required write-back path for agent work is the
machine progress YAML plus wiki handoff.

## Context And Progress Write-Back

- Start with `docs/ai/agent-startup-context.md`, not the whole wiki.
- Use `docs/ai/context-index.json` through `scripts/agent-context-brief.py` to
  select task-specific deep reads.
- Stop reading once the current state, matching handoff page, and write-back
  target are clear.
- Completed tasks update `docs/ai/task-progress.yaml` with status, validation
  commands, result, and acceptance notes.
- Completed tasks update `omx_wiki/` with status, validation evidence, and next
  work. Add new session pages to `omx_wiki/index.md` and `omx_wiki/log.md`.
- Blocked tasks record the blocker, evidence already collected, unproven
  acceptance criteria, and the next recovery step in the same two surfaces.

## Product Boundary

The console entry is Agent Workspace with a single Plan surface. The product is the Harness: Planner, Executor, Subagent Orchestrator, Event Sourcing, Tool Runtime, Guardrails, Eval Harness, Memory, Model Router, WarmPool, Trace, Replay, and Recovery.
