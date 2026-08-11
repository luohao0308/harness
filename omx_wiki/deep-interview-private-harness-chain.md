# Deep Interview Private Harness Chain

Category: `decision`

Tags: `deep-interview`, `harness-chain`, `product-target`, `stage-07`, `private-deployment`

## Decision

The accepted project-wide target is a production enterprise AI Harness Platform:

```text
Model + Harness = Agent
```

The next-phase outcome selected in `$deep-interview` was a real privately deployable enterprise internal-test platform with a complete first-phase Harness chain.

## Source Artifacts

- `.omx/interviews/project-positioning-orchestration-20260510T201421Z.md`
- `.omx/specs/deep-interview-project-positioning-orchestration.md`
- `.omx/plans/prd-private-deployable-harness-chain.md`
- `.omx/plans/test-spec-private-deployable-harness-chain.md`
- `docs/development/ai/stages/07-private-deployable-harness-chain.md`
- `docs/development/ai/task-progress.yaml`

## User Decisions Captured In Deep Interview

- Main goal: private enterprise internal-test platform.
- Reason: prove a complete Harness chain.
- Explicit non-goals:
  - Kubernetes.
  - Full multi-tenant RBAC.
  - Polished marketing website.
  - Full SaaS commercialization.
- Harness agents/OMX may autonomously decide routine docs structure, stage splitting, tests, local refactors, bug fixes, API/frontend alignment, deployment script fixes, and progress updates.
- Harness agents/OMX must pause before significant new dependencies, destructive database migrations, auth/RBAC expansion, Kubernetes topology, product repositioning, or deleting large functional areas.

## Binding Harness Chain

The first-phase internal-test platform succeeds when this chain is demonstrably true:

```text
Private deployment
-> Agent configuration
-> User goal in Agent Workspace
-> Agent Run
-> Planner
-> Executor
-> Tool/MCP call
-> Sandbox/WarmPool isolation
-> Subagent asynchronous work
-> Event Store audit trail
-> Workspace live visibility
-> Run Detail replay/diagnosis
-> Eval Case/regression
-> Observability evidence
```

## Completion Evidence

Stage 07 is recorded complete in `docs/development/ai/task-progress.yaml` and `docs/development/ai/stages/07-private-deployable-harness-chain.md`.

Recorded Stage 07 evidence includes:

- Canonical smoke script: `scripts/smoke-test-agent-run.py`.
- Smoke starts from primary `POST /api/agents/default/runs`.
- Evidence run id: `3a310efa-dcbd-4216-b78c-c49241e97245`.
- Evidence categories: run/task/replay/tool/sandbox/subagent/eval/observability.
- Full backend regression, Ruff, frontend build, docs validation, Docker compose config, Docker smoke, Agent Run smoke, and diff check were recorded as passed.

## Current Interpretation

Stage 07 closed the core private-deployable Harness-chain proof. Later work should not reopen the product-wide target unless new evidence shows a gap in the recorded chain. Current post-stage work is hardening and productization, especially browser smoke and Workspace clarity.

## Related Pages

- [[project-handoff-current-state]]
- [[workspace-demo-ready-constraints]]
- [[wiki-capture-candidates]]
