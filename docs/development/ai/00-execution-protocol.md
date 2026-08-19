# AI Execution Protocol

## Role

The executing AI works as an implementation agent for the Forge Harness production AI control plane.

## Source Of Truth

For every new agent session, read the repository `AGENTS.md` first, then the
low-token startup context before any implementation work:

1. `AGENTS.md`
2. `docs/development/ai/agent-startup-context.md`
3. `docs/development/ai/task-progress.yaml`
4. Task-matched context from:

```text
python3 scripts/agent-context-brief.py --task "<user task>"
```

The brief chooses the smallest wiki, plan, and context set for the task. Use
filesystem reads as the reliable path for `omx_wiki/`; MCP wiki helpers are
secondary convenience tools.

Then read these product sources when the task changes contracts or crosses
module boundaries:

1. `docs/design/product-spec.md`
2. `docs/architecture/system-architecture-spec.md`
3. `docs/contracts/data-model-and-event-spec.md`
4. `docs/contracts/api/api-spec.md`
5. `docs/development/ai/task-progress.yaml`
6. The current file under `docs/development/ai/stages/`

## Execution Rules

- Implement the current stage as a runnable vertical slice.
- Do not build a normal chatbot as the product center.
- Do not add static console data.
- Do not add placeholder routes.
- Backend state must drive frontend state.
- Every state-changing Agent operation must write an event or audit record.
- Eval Harness remains a first-class module.
- PostgreSQL remains the production database path.

## Large Plan Decomposition Gate

Classify work as a large plan when the user explicitly asks for a large plan,
roadmap, or multi-stage delivery; when it changes a high-risk contract,
migration, security, release, or recovery boundary; or when at least two of
these signals apply:

- the work crosses two or more module or ownership boundaries;
- it has three or more ordered implementation phases;
- it produces multiple independently verifiable outcomes;
- it cannot reasonably fit in one focused implementation and verification session.

Before implementation, gather only the read-only evidence needed to split the
work into two to six ordered slices. Present the slices to the user with this
minimum contract:

| Slice | Outcome | Scope | Depends on | Acceptance | Rollback |
|---|---|---|---|---|---|
| S1 |  |  |  |  |  |

Set the plan state to `awaiting_user_confirmation`. The user may approve the
split or ask to merge, split further, reorder, add, or remove scope. Do not edit
product code, configuration, contracts, create a delivery PR, or mutate
external state until the user confirms the decomposition.

After confirmation, persist the plan under `docs/plans/`, mark it `approved`,
and execute with exactly one slice `in_progress`. Complete the slice acceptance
checks and record evidence before automatically advancing to the next approved
slice. Re-confirm only when new evidence materially changes the approved scope,
ordering, interface, migration, or risk; ordinary implementation detail changes
do not create another approval round.

## Stage Completion

Before advancing a stage:

```text
cd services/api-server && .venv/bin/python -m pytest
cd services/api-server && .venv/bin/python -m ruff check app tests
cd apps/agent-console && npm run build
python3 scripts/validate-docs.py
```

Then update:

- `docs/development/ai/task-progress.yaml`
- `omx_wiki/` with a session page or the relevant handoff page

Current work is summarized in `docs/TASKS.md`; machine history remains in the
progress YAML. Files under `docs/工作日志/archive/` are historical evidence and
are never progress write-back targets.

## Context And Progress Write-Back

- Start with `docs/development/ai/agent-startup-context.md`, not the whole wiki.
- Use `docs/development/ai/context-index.json` through `scripts/agent-context-brief.py` to
  select task-specific deep reads.
- Stop reading once the current state, matching handoff page, and write-back
  target are clear.
- Completed tasks update `docs/development/ai/task-progress.yaml` with status, validation
  commands, result, and acceptance notes.
- Completed tasks update `omx_wiki/` with status, validation evidence, and next
  work. Add new session pages to `omx_wiki/index.md` and `omx_wiki/log.md`.
- Blocked tasks record the blocker, evidence already collected, unproven
  acceptance criteria, and the next recovery step in the same two surfaces.

## Product Boundary

The console entry is Agent Workspace with a single Plan surface. The product is the Harness: Planner, Executor, Subagent Orchestrator, Event Sourcing, Tool Runtime, Guardrails, Eval Harness, Memory, Model Router, WarmPool, Trace, Replay, and Recovery.
