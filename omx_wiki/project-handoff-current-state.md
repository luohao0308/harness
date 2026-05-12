# Project Handoff Current State

Category: `reference`

Tags: `handoff`, `current-state`, `deep-interview`, `task-progress`, `workspace`, `stage-07`

## Purpose

This is the first page a new session or incoming agent should read. It connects the accepted `$deep-interview` goal, current stage evidence, and the next known work without requiring chat history.

## Product Target

The project is the AI Harness Platform:

```text
Model + Harness = Agent
```

The public website remains a public information shell. The implementation center is the Agent Console plus FastAPI backend.

## Authoritative Reading Order

Read these first:

1. [[deep-interview-private-harness-chain]]
2. `.omx/specs/deep-interview-project-positioning-orchestration.md`
3. `.omx/plans/prd-private-deployable-harness-chain.md`
4. `.omx/plans/test-spec-private-deployable-harness-chain.md`
5. `docs/ai/task-progress.yaml`
6. `docs/task-progress.md`
7. Latest relevant `.omx/context/*.md`
8. [[workspace-demo-ready-constraints]] if the next work touches Agent Workspace
9. [[local-dev-backend-port-cors]] if the frontend cannot reach the backend

## Current State

Evidence from `docs/ai/task-progress.yaml`:

- `current_stage`: `07-private-deployable-harness-chain`
- `current_status`: `completed`
- `product`: `AI Harness Platform`
- `formula`: `Model + Harness = Agent`
- Stage 01-07 are recorded as completed.
- Post-stage hardening `workspace-browser-e2e-smoke` is recorded as completed.
- Non-Workspace browser e2e coverage remains deferred.

Evidence from `docs/task-progress.md`:

- Stage 07 canonical Agent Run smoke is part of the regular release gate.
- Workspace browser smoke and compact chrome hardening were added after Stage 07.
- Broader browser e2e coverage for non-Workspace routes remains the explicit not-completed item.

## Existing Handoff Solution

The project already has a partial handoff solution:

- `.omx/specs/` preserves deep-interview outcomes.
- `.omx/plans/` preserves PRD and test-spec artifacts.
- `.omx/context/` preserves task-level context snapshots.
- `docs/ai/task-progress.yaml` is the machine-readable progress source.
- `docs/task-progress.md` is the human-readable progress source.

The gap this wiki closes is discoverability. A new session can now start from this page and follow the links instead of guessing which `.omx` artifact is authoritative.

## Deep Interview Target In One Paragraph

The accepted next-phase goal was a privately deployable enterprise internal-test platform that proves a complete Harness chain end to end. The target is not Kubernetes, full multi-tenant RBAC, polished marketing, or SaaS commercialization. See [[deep-interview-private-harness-chain]] for the binding chain.

## Most Recent Completed Work

Recent pushed commits on `main`:

```text
3fff603 Record Workspace browser hardening progress
ced5be0 Document Workspace browser smoke flow
a3903d2 Cover Workspace demo controls in browser smoke
7eaeab3 Add Workspace browser smoke tooling
9e8172f Keep Workspace chrome compact
```

Captured in wiki:

- [[session-2026-05-13-workspace-browser-smoke]]

## Next Known Work

The clearest remaining work is broader browser e2e coverage outside the Workspace route. Current Playwright smoke intentionally focuses on `/agents/default/workspace`.

Potential next slices:

- Non-Workspace browser e2e for Run Detail, Eval, Observability, Tools, Sandboxes, or Agent Studio.
- Handoff hygiene: align top-level `README.md` and `docs/human/10-task-progress.md` if they lag behind `docs/ai/task-progress.yaml`.
- Keep `omx_wiki/` aligned with accepted deep-interview decisions, progress docs, and repeated local-development lessons.

## Stop Rules For Future Agents

Do not claim product completion from UI polish alone. Stage claims must map to evidence in `docs/ai/task-progress.yaml`, `docs/task-progress.md`, test output, and the relevant `.omx/plans/test-spec-*.md`.

Do not change the product target away from `Model + Harness = Agent` without a new explicit user decision.

Do not treat legacy `/api/tasks/*` as the primary product proof. Agent Run is the product execution object; task APIs are compatibility plumbing.

## Related Pages

- [[deep-interview-private-harness-chain]]
- [[workspace-demo-ready-constraints]]
- [[wiki-capture-candidates]]
- [[local-dev-backend-port-cors]]
- [[session-2026-05-13-workspace-browser-smoke]]
