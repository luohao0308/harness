# Agent Startup Context

This is the low-token entry point referenced by the repository root
`AGENTS.md`. Read this file before implementation work, then use
`scripts/agent-context-brief.py --task "<task>"` to choose the smallest deeper
context set.

## Project Target

AI Harness Platform is a production Agent infrastructure project:

```text
Model + Harness = Agent
```

The public website remains an information shell. The implementation center is
the Agent Console plus FastAPI backend. The product is not a generic chatbot:
the Harness owns model configuration, prompt control, tools, MCP, sandbox
policy, planning, execution, event sourcing, replay, Eval, Observability,
WarmPool, memory, knowledge grounding, context routing, and recovery.

## Current State

- Machine progress source: `docs/ai/task-progress.yaml`.
- Current stage: `07-private-deployable-harness-chain`.
- Current status: completed.
- Stage 01-07 are closed as the private deployable Harness proof.
- The active product direction after Stage 07 is Agent Knowledge Harness: a
  configurable, auditable, evaluable capability layer across memory, RAG,
  web research, MCP, skills, context/token routing, hallucination control,
  Eval, Observability, Policy/Sandbox, and Agent orchestration.
- P1-P7 Agent Knowledge Harness work is recorded in wiki and progress docs:
  local Knowledge/RAG grounding, local knowledge management, real policy-gated
  web research, backend context assembly, MCP/Skills productization,
  groundedness Eval/Observability, and release/demo hardening.
- Latest recorded handoff: P7 release/demo hardening plus Chinese-first
  selector and terminology UI follow-up on `origin/p7-release-demo-hardening`
  through `a5d046b`.

## Required Startup Flow

1. Read this file.
2. Read `docs/ai/task-progress.yaml` for machine progress truth.
3. Run a task-specific brief when a task is known:

   ```text
   python3 scripts/agent-context-brief.py --task "<user task>"
   ```

4. Read only the wiki pages and plan/context files named by the brief.
5. Do the requested work.
6. Before final handoff, update `docs/ai/task-progress.yaml` and one relevant
   `omx_wiki/` page with status, validation evidence, and blockers or next
   work.

## Canonical Reading Order

Use this order unless the task-specific brief narrows it:

1. `docs/ai/agent-startup-context.md`
2. `docs/ai/task-progress.yaml`
3. `omx_wiki/project-handoff-current-state.md`
4. `omx_wiki/agent-knowledge-harness-roadmap.md`
5. `omx_wiki/deep-interview-private-harness-chain.md`
6. Task-matched pages from `docs/ai/context-index.json`
7. Task-matched `.omx/plans/*.md` or `.omx/context/*.md`

## Task Routing Hints

- Knowledge/RAG, grounding, citations, prompt manifests, or selectors:
  read the P1/P2/P3 wiki pages first.
- Context routing, token budgets, pinned context, summaries, or memory:
  read the P4 wiki page and P4 ralplan first.
- MCP, tools, skills, capability registry, approvals, or ToolRunner:
  read the P5 wiki page first.
- Eval groundedness, forbidden leaks, regression deltas, or Observability
  grounding quality: read the P6 wiki page first.
- Release demo, seed data, migration/restore smoke, browser smoke, or runbooks:
  read the P7 wiki page first.
- Frontend selector, Chinese-first wording, Agent Console UI, or Run Detail UI:
  read the P7 wiki page and the relevant component paths after repository
  search.
- Local backend startup, ports, CORS, migrations, or Eval dataset problems:
  read the local-dev wiki pages before debugging.

## Completion Write-Back Contract

Every completed implementation task records:

- `docs/ai/task-progress.yaml`: task id, status, validation commands, result,
  concise acceptance notes.
- `omx_wiki/`: either a new `session-YYYY-MM-DD-*.md` page or an update to the
  relevant handoff/roadmap page.
- `omx_wiki/index.md`: add the page if a new wiki page is created.
- `omx_wiki/log.md`: add a one-line session-log entry.

If work is blocked, write the blocker, commands already run, unproven
acceptance criteria, and next recovery step instead of marking completion.
