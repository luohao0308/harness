# Agent Startup Context

Low-token entry point. Read this, then run the brief for your task.

## Project Identity

```text
Forge Harness

Model + Harness = Agent
```

Forge Harness — private enterprise AI infrastructure: model config, tools, MCP,
sandbox policy, planning, execution, event sourcing, eval, observability, warmpool,
knowledge grounding, context routing. Not a generic chatbot.

## Current State

Machine progress source: `docs/development/ai/task-progress.yaml`
- Stage 07 (private deployable Harness chain): **completed**
- Active direction: Agent Knowledge Harness — memory, RAG, web research, MCP/skills,
  context/token routing, eval, observability, policy/sandbox, agent orchestration.
- Latest handoff: P7 release/demo hardening on `origin/p7-release-demo-hardening`.

## Startup Flow

1. Read this file.
2. Read `docs/development/ai/task-progress.yaml` for machine progress.
3. Run task brief: `python3 scripts/agent-context-brief.py --task "<task>"`
4. Read only the pages the brief names.
5. Do the work.
6. Write back (see below).

## Key References

| Purpose | Path |
| --- | --- |
| Module → docs map | `docs/architecture/MODULE-INDEX.md` |
| Feature → spec map | `docs/contracts/SPEC-INDEX.md` |
| Feature → implementation/maturity/evidence map | `docs/development/ai/feature-catalog.json` and generated `docs/FEATURE-MATRIX.md` |
| Known errors & fixes | `docs/development/ai/error-registry.md` |
| Design anti-patterns | `docs/development/ai/anti-patterns.md` |
| Current handoff state | `omx_wiki/project-handoff-current-state.md` |

## Completion Write-Back Contract

Every completed task records:
- `docs/development/ai/task-progress.yaml`: task id, status, validation commands, result.
- `omx_wiki/`: new `session-YYYY-MM-DD-*.md` or update to the handoff page.
- `omx_wiki/log.md`: one-line session-log entry.

If blocked, record the blocker, commands run, unmet criteria, and next step.
