# PRD: Agent Knowledge Harness P7 Release Demo Hardening

## Objective

Make the completed Agent Knowledge Harness capabilities deterministic to demo and safe to hand off for private release without adding new core Knowledge/RAG, Eval, Observability, or Workspace semantics.

## Scope

- Add a one-command deterministic Knowledge/RAG demo seed that uses public API endpoints only.
- Add a service-level migration/restore smoke path for private Docker Compose handoff evidence.
- Extend the existing browser release smoke with a focused Knowledge demo projection spec.
- Update deployment, troubleshooting, web research, task-progress, and wiki handoff docs after verification.

## Constraints

- P7 starts only after P6 baseline verification proves P6 is completed, pushed, and independently traceable.
- Demo seed data must be local-safe, no-secret, idempotent, and clearly marked as fixture evidence.
- Seed implementation must not write database rows directly.
- Browser smoke remains mocked and must not require Tavily or other external provider credentials.
- P7 must not reintroduce raw `forbidden_evidence_snippets` in fixtures, reports, runbooks, Eval, Observability, or Run Detail assertions.
- Eval remains the owner of grounding quality; UI and Observability only project backend-owned results.

## Deliverables

- Public-API seed script under `scripts/`.
- Service-level migration/restore smoke script under `scripts/`.
- `apps/agent-console/e2e/knowledge-demo.smoke.spec.ts` wired into `npm run e2e:smoke:release`.
- Runbook updates for deterministic demo, migration/restore smoke, optional live provider validation, and failure diagnosis.
- Progress/wiki updates marking P7 complete only after verification passes.

## Acceptance Criteria

- P7-0 baseline gate is recorded with current git status, branch alignment, P6 evidence, and clean tracked worktree.
- Seed command creates or verifies deterministic agent-scoped and org-scoped demo knowledge through public APIs and readback.
- Migration/restore smoke proves knowledge-related tables/selectors survive the service-level private handoff path.
- Browser release smoke covers Agent Studio knowledge, Workspace grounding projection, Run Detail evidence, Eval grounding quality, and Observability grounding quality without forbidden snippet payloads.
- Verification commands pass and are recorded in task progress and wiki.
