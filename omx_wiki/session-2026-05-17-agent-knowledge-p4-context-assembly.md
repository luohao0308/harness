# Session 2026-05-17 Agent Knowledge P4 Context Assembly

Category: `session-log`

Tags: `agent-knowledge-harness`, `p4`, `context-assembly`, `memory`, `token-budget`, `manifest`, `workspace`, `run-detail`

## Summary

Agent Knowledge Harness P4 memory and context router V2 is implemented, reviewed, split into atomic commits, and pushed to `origin/main` through `6c4a95d`.

The delivered slice moves Workspace chat context assembly from frontend-authoritative truncation to backend-authoritative assembly with deterministic token-budget pruning, scoped memory eligibility, pinned-message tagging, compressed-summary eligibility checks, persisted context manifests, and model-call context manifest binding.

## Pushed Commits

```text
45da62f Add context assembly storage contract
d2b6e50 Assemble authoritative workspace context
dc0f916 Expose backend context assembly in Workspace
c97a333 Cover context assembly regressions
6c4a95d Record P4 context assembly handoff
```

Push evidence:

```text
git push origin main
76f11d5..6c4a95d  main -> main
git rev-list --left-right --count origin/main...HEAD
0 0
```

## Key Implementation Points

- `ContextAssemblyManifest` is the parent model-input assembly record; `PromptAssemblyManifest` remains retrieval-evidence focused.
- `ModelCall.context_manifest_id` points to context manifests, allowing N model calls per manifest.
- `AgentMemoryRecord` supports `org`, `agent`, `user`, and `run` scopes with SQL-level eligibility filtering.
- Backend token estimation owns the final budget decision and records included/omitted refs.
- Pinned Workspace messages are wrapped in `<pinned_message>` blocks so the model can distinguish explicit pinned context from ordinary history.
- Memory text is wrapped as evidence, scanned for prompt-injection-like strings, and downgraded to low trust when needed.
- Context assembly can run in shadow or authoritative mode through `settings.context_assembly_v2_enabled`.
- Run Detail exposes context assembly manifest evidence without raw prompt previews.

## Verification

Latest commit/push verification:

```text
git diff --check -> passed
cd services/api-server && uv run ruff check app tests -> passed
cd services/api-server && uv run pytest tests/test_context_router.py tests/test_agents.py tests/test_model_gateway.py -q -> 69 passed
```

Broader P4 verification recorded before commit splitting:

```text
cd services/api-server && uv run pytest tests/test_context_router.py tests/test_agents.py tests/test_knowledge_rag.py tests/test_evals.py -q -> 91 passed
cd services/api-server && uv run pytest tests -q -> 260 passed
DATABASE_URL=sqlite:////tmp/harness-p4-alembic.sqlite uv run alembic upgrade head -> reached 20260517_0017
cd apps/agent-console && npm test -> 139 passed
cd apps/agent-console && npm run lint -> passed
cd apps/agent-console && npm run build -> passed
python3 scripts/validate-docs.py -> passed
```

Manual pin smoke after the final fix:

```text
Pinned input: 请记住：PinnedSecret=BLUE-17
Follow-up: 我 pin 的那条消息是什么？
Observed response included: PinnedSecret=BLUE-17
```

## Local Runtime

Non-default ports were used because default ports were not requested:

```text
Frontend: http://127.0.0.1:5179/
Backend:  http://127.0.0.1:8017/
```

Health checks returned `200` for both frontend and backend docs/health endpoints.

## Remaining Local Untracked Files

These were intentionally not committed or pushed during the Git Master pass:

```text
.omc/
.vscode/
apps/agent-console/src/features/agents/lib/_probe.ts
services/api-server/uv.lock
```

They appear to be local runtime/IDE/probe state or an untracked lockfile outside existing repository history.

## Next Work

The next planned Agent Knowledge Harness lane is P5 MCP and Skills productization.

Start from [[agent-knowledge-harness-roadmap]] and [[project-handoff-current-state]] before beginning P5.
