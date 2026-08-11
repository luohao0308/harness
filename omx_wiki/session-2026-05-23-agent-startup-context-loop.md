# Agent Startup Context Loop

Category: session-log
Tags: `handoff`, `startup-context`, `context-index`, `task-progress`, `wiki`, `agent-knowledge-harness`

## Summary

This session adds a low-token context loop for new agents. The goal is to keep
new sessions aligned with the project target and current progress without
forcing them to read the full wiki.

The actual new-session entrypoint is now the repository root `AGENTS.md`, which
points at the startup context and task brief.

The default entry is now:

```text
docs/development/ai/agent-startup-context.md
python3 scripts/agent-context-brief.py --task "<user task>"
```

The required write-back path is `docs/development/ai/task-progress.yaml` plus a relevant
`omx_wiki/` session or handoff page.

## Delivered

- Added `docs/development/ai/agent-startup-context.md` as the first low-token read for new
  sessions.
- Added repository root `AGENTS.md` as the actual automatic new-session entry
  point before the startup context.
- Added `docs/development/ai/context-index.json` as the machine-readable route index for
  wiki, plan, and context files.
- Added `scripts/agent-context-brief.py` using only the Python standard
  library.
- Updated `docs/development/ai/00-execution-protocol.md` and `README.md` with the startup
  and write-back contract.
- Extended `scripts/validate-docs.py` to check the startup context, context
  index, wiki index, and brief script.

## Validation

Completed validation for this session:

```text
python3 -m py_compile scripts/agent-context-brief.py scripts/validate-docs.py
passed

python3 scripts/agent-context-brief.py
passed and returned the canonical project-handoff route

python3 scripts/agent-context-brief.py --task "RAG retrieval and Run Detail grounding"
passed and returned Knowledge/RAG plus Eval/Observability grounding routes

python3 scripts/agent-context-brief.py --task "frontend UI selector"
passed and returned the frontend UI console route

python3 scripts/validate-docs.py
docs validation passed

git diff --check
passed
```

Independent subagent acceptance:

- `verifier` result: PASS. The fresh-session simulation for RAG, context router,
  and frontend UI selector tasks identified project target, current progress,
  relevant deep reads, and write-back targets without reading the whole wiki.
- `architect` result: WATCH. The design is proportionate, but route matching and
  evidence drift needed tighter guardrails. This page and the brief script were
  updated to address those concerns.

## Boundaries

- No external dependencies are added.
- No hook-based injection is added in this pass.
- Filesystem wiki reads remain the reliable path because MCP wiki page reads can
  fail in this environment.
- This session does not alter product runtime behavior.
