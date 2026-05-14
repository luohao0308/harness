# Session 2026-05-14 Workspace Execution Evidence

Category: `session-log`

Tags: `workspace`, `context-compression`, `plan-act`, `branching`, `run-detail`, `eval-case`, `playwright`, `git`

## Summary

Commit `e78f52a` was pushed to `origin/main` with a broad Workspace execution evidence update.

The work connects the Agent Workspace chat surface to durable execution proof:

- context compression with effective prompt usage,
- Plan-Act approval and execution,
- branch creation/switching,
- search reveal without history hiding,
- Run Detail evidence views,
- Replay,
- Eval Case capture from completed/failed Runs.

## Git Record

Pushed commit:

```text
e78f52a Preserve agent workspace execution evidence
```

Push result:

```text
2d6ed7e..e78f52a main -> main
```

Unrelated local files were intentionally not included in the commit:

- `.omc/`
- `.vscode/`
- `demo-guide.html`
- `omx_wiki/log.md`
- `apps/agent-console/src/features/agents/lib/_probe.ts`
- empty `.gitkeep` files

## Product Changes

### Context Compression

- Added branch/path-scoped summary state.
- Added backend compression endpoint.
- Added prompt assembly with compressed summary plus pinned/uncovered raw messages.
- Added context ring click-to-compress behavior.
- Added automatic compression threshold support.
- Changed ring usage to effective prompt estimate after compression.

### Plan-Act

- Approval runs from the original user goal.
- Plan-Act result nodes use mode `plan`.
- Approval panel only appears for `codex_plan`, preventing approval loops.

### Conversation Branching

- Assistant messages expose Branch.
- Branching creates sibling assistant nodes from the prior user goal.
- Branch switcher shows `1/2`, arrows, and switches sibling branches.

### Search

- Search hit inside the current active path scrolls/highlights only.
- Search no longer hides later messages by changing the active leaf unnecessarily.

### Slash Commands

- Slash command menu supports mouse/touch selection through pointer-down plus click fallback.

### Run Detail

- Plan DAG displays `depends_on`.
- Step labels include execution mode, Sandbox, Subagent, and tool hints.
- Tool Calls, Guardrails, Event Stream, Model Calls, Replay, and Eval Case saving are covered by smoke tests.

### Eval Case Capture

- COMPLETED/FAILED Runs show `Save as Eval Case`.
- Existing Dataset can be selected.
- If no Dataset exists, the UI can create a default `Saved Runs` dataset and then save.

## Verification

Frontend:

```text
cd apps/agent-console
npm test -> 26 files / 129 tests passed
npm run lint -> passed
npm run build -> passed
npx playwright test --project=chromium e2e/run-detail.smoke.spec.ts -> 9 passed
npm run e2e:smoke -> 13 passed
```

Backend:

```text
cd services/api-server
./.venv/bin/python -m pytest tests/test_agents.py -q -> 34 passed
./.venv/bin/python -m ruff check app/api/agents.py app/api/tasks.py app/api/schemas.py -> passed
```

Runtime:

```text
GET http://127.0.0.1:8000/health -> {"status":"ok","service":"api-server"}
GET http://127.0.0.1:5173/agents/default/workspace -> 200
GET http://127.0.0.1:5173/runs -> 200
```

Eval Dataset migration:

```text
cd services/api-server
./.venv/bin/python -m alembic upgrade head
```

This fixed the local `eval_datasets.baseline_run_id` missing-column error.

## Files Of Interest

Frontend:

- `apps/agent-console/src/features/agents/components/ChatSurface.tsx`
- `apps/agent-console/src/features/agents/components/ContextRing.tsx`
- `apps/agent-console/src/features/agents/lib/contextCompression.ts`
- `apps/agent-console/src/features/agents/hooks/useChatStream.ts`
- `apps/agent-console/src/features/runs/pages/RunDetailPage.tsx`

Backend:

- `services/api-server/app/api/agents.py`
- `services/api-server/app/api/schemas.py`
- `services/api-server/app/api/tasks.py`
- `services/api-server/tests/test_agents.py`

Tests:

- `apps/agent-console/src/features/agents/__tests__/ChatSurface.shell.test.tsx`
- `apps/agent-console/src/features/agents/__tests__/planApprovalGate.test.ts`
- `apps/agent-console/src/features/agents/__tests__/agentWorkspaceDerive.test.ts`
- `apps/agent-console/e2e/run-detail.smoke.spec.ts`

## Related Pages

- [[agent-workspace-execution-evidence-architecture]]
- [[local-dev-eval-dataset-migration]]
- [[project-handoff-current-state]]
- [[session-2026-05-13-workspace-browser-smoke]]
