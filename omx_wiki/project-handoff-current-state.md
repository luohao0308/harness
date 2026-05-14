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
10. [[agent-workspace-execution-evidence-architecture]] if the work touches Workspace context, Plan-Act, branching, Run Detail, or Eval Case capture
11. [[local-dev-eval-dataset-migration]] if Run Detail cannot list or save Eval Datasets
12. `.omx/plans/prd-private-deployment-experience.md` and `.omx/plans/test-spec-private-deployment-experience.md` if the next work touches private deployment handoff.

## Current State

Evidence from `docs/ai/task-progress.yaml`:

- `current_stage`: `07-private-deployable-harness-chain`
- `current_status`: `completed`
- `product`: `AI Harness Platform`
- `formula`: `Model + Harness = Agent`
- Stage 01-07 are recorded as completed.
- Post-stage hardening `workspace-browser-e2e-smoke` is recorded as completed.
- Private deployment experience is the latest completed post-stage lane: Docker Compose is the canonical private handoff path, host-port overrides are documented, Docker smoke and Agent Run smoke pass, and cleanup evidence is recorded.

Evidence from `docs/task-progress.md`:

- Stage 07 canonical Agent Run smoke is part of the regular release gate.
- Workspace browser smoke and compact chrome hardening were added after Stage 07.
- Broader browser smoke now has an explicit release-gate entrypoint through `cd apps/agent-console && npm run e2e:smoke:release`.
- Private deployment handoff now has a canonical Docker Compose path in `docs/runbooks/deployment.md`; static checks, compose config, compose startup, Docker smoke, Agent Run smoke, and compose cleanup have passed using intentional host-port overrides.

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
72591dc Document private deployment handoff
8a7abbb Catch private deployment wiring in smoke tests
d877233 Route console observability through configured API
11b1ddc Expose private deployment runtime URLs
0238b4a Keep local mock chat visible
0980192 Add release gate handoff visual report
```

Captured in wiki:

- [[project-handoff-current-state]]
- [[session-2026-05-14-workspace-execution-evidence]]
- [[agent-workspace-execution-evidence-architecture]]
- [[local-dev-eval-dataset-migration]]
- [[session-2026-05-13-workspace-browser-smoke]]

## Next Known Work

The latest completed lane is Private Deployment Experience. The next product lane should be chosen from fresh planning rather than by reopening Stage 07.

Useful follow-up slices:

- Keep using host-port overrides when default local development ports are occupied.
- Preserve the Private Deployment report at `.omx/reports/private-deployment-experience/report-20260514T074949Z.md` as the runtime evidence pointer.
- If deployment handoff expands later, keep it bounded to documented private handoff improvements unless a new plan explicitly authorizes installer, Kubernetes, cloud matrix, or full operations work.

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
- [[agent-workspace-execution-evidence-architecture]]
- [[local-dev-eval-dataset-migration]]
- [[session-2026-05-14-workspace-execution-evidence]]
