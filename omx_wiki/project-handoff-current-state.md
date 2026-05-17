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

The current final task target is **Agent Knowledge Harness**. Based on the repository HTML report `docs/reports/release-gate-handoff-diff-2026-05-14.html`, the target is not merely "add memory" or "add RAG"; it is to make Harness a configurable, auditable, and evaluable capability layer across memory, knowledge retrieval, MCP, skills, context/token routing, hallucination control, Eval, Observability, Policy/Sandbox, and Agent orchestration.

## Authoritative Reading Order

Read these first:

1. [[deep-interview-private-harness-chain]]
2. [[agent-knowledge-harness-roadmap]]
3. `.omx/specs/deep-interview-agent-knowledge-harness-memory-rag.md`
4. `.omx/specs/deep-interview-project-positioning-orchestration.md`
5. `.omx/plans/prd-private-deployable-harness-chain.md`
6. `.omx/plans/test-spec-private-deployable-harness-chain.md`
7. `docs/ai/task-progress.yaml`
8. `docs/task-progress.md`
9. Latest relevant `.omx/context/*.md`
10. [[workspace-demo-ready-constraints]] if the next work touches Agent Workspace
11. [[local-dev-backend-port-cors]] if the frontend cannot reach the backend
12. [[agent-workspace-execution-evidence-architecture]] if the work touches Workspace context, Plan-Act, branching, Run Detail, or Eval Case capture
13. [[local-dev-eval-dataset-migration]] if Run Detail cannot list or save Eval Datasets
14. [[session-2026-05-16-agent-knowledge-p1-grounding-audit]] if the next work touches Knowledge/RAG grounding, prompt manifests, policy audit, Run Detail evidence, Eval grounding contracts, or Chinese knowledge retrieval.
15. `.omx/plans/prd-private-deployment-experience.md` and `.omx/plans/test-spec-private-deployment-experience.md` if the next work touches private deployment handoff.

## Current State

Evidence from `docs/ai/task-progress.yaml`:

- `current_stage`: `07-private-deployable-harness-chain`
- `current_status`: `completed`
- `product`: `AI Harness Platform`
- `formula`: `Model + Harness = Agent`
- Stage 01-07 are recorded as completed.
- Post-stage hardening `workspace-browser-e2e-smoke` is recorded as completed.
- Private deployment experience is the latest completed post-stage lane: Docker Compose is the canonical private handoff path, host-port overrides are documented, Docker smoke and Agent Run smoke pass, and cleanup evidence is recorded.
- Agent Knowledge Harness is the current product direction after private deployment. Knowledge/RAG P1 is now a verified baseline in `.omx/reports/agent-knowledge-harness-p1/p1-gate-result-20260516T211017Z.md`, including Docker/private, existing-data migration, exact selector, Eval grounding, append-only audit, backend/frontend/docs/browser, and Agent Run smoke evidence.
- Agent Knowledge Harness P2 local knowledge management is completed in the current worktree: agent/org-scoped text and Markdown knowledge sources now have lifecycle controls, document-level versioning, stale chunk filtering, retrieval eligibility, lifecycle audit events, failure audit records, multipart `.txt` / `.md` import, Agent Studio management UI, restore smoke coverage, and compose/Postgres private smoke evidence.
- Git persistence status on 2026-05-17: P2 was split into five local Lore commits on `main`, but push to `origin/main` failed because the environment could not connect to `github.com:443`. The branch is ahead of `origin/main` until network access is restored and `git push origin main` succeeds.
- Frontend acceptance HTML is saved in the tracked report path `docs/reports/agent-knowledge-p2-code-review-frontend-acceptance-2026-05-17.html`; the runtime copy remains at `.omx/reports/html-archive/agent-knowledge-p2-code-review-frontend-acceptance-2026-05-17.html`.

Evidence from `docs/task-progress.md`:

- Stage 07 canonical Agent Run smoke is part of the regular release gate.
- Workspace browser smoke and compact chrome hardening were added after Stage 07.
- Broader browser smoke now has an explicit release-gate entrypoint through `cd apps/agent-console && npm run e2e:smoke:release`.
- Private deployment handoff now has a canonical Docker Compose path in `docs/runbooks/deployment.md`; static checks, compose config, compose startup, Docker smoke, Agent Run smoke, and compose cleanup have passed using intentional host-port overrides.

Evidence from the current codebase:

- `services/api-server/app/knowledge.py`, `services/api-server/alembic/versions/20260514_0011_create_knowledge_rag.py`, `services/api-server/alembic/versions/20260516_0012_create_knowledge_audit_manifests.py`, `services/api-server/alembic/versions/20260516_0013_add_grounding_model_call_binding.py`, `services/api-server/alembic/versions/20260517_0015_add_knowledge_lifecycle_contract.py`, and `services/api-server/tests/test_knowledge_rag.py` define a Knowledge/RAG foundation with prompt assembly manifests, policy audits, citation snapshots, insufficient-evidence controls, CJK fallback retrieval, attempt-level model-call audit binding, request hashing, exact selector behavior, lifecycle/versioning, restore/migration smoke, and org/agent scope isolation.
- `services/api-server/app/api/agents.py` exposes knowledge source lifecycle APIs, document APIs, scope APIs, and Workspace grounding behavior.
- `apps/agent-console/src/features/agents/components/KnowledgeManagementPanel.tsx` exposes Agent Studio knowledge source management.
- `apps/agent-console/src/features/agents/components/ChatMessageBubble.tsx` and `apps/agent-console/src/features/runs/pages/RunDetailPage.tsx` expose grounding evidence in Workspace and Run Detail.

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

Recent local P2 commits pending push on `main`:

```text
8eed571 Record P2 knowledge management evidence
3877433 Productize Agent Studio knowledge management
a95eb3f Cover knowledge lifecycle regressions
fdc04df Manage knowledge lifecycle and document versions
19802ab Add knowledge lifecycle schema contract
```

Push evidence:

```text
git push origin main
fatal: unable to access 'https://github.com/luohao0308/harness.git/':
Failed to connect to github.com port 443 after 75005 ms: Couldn't connect to server
```

Previously pushed P1 commits on `main`:

```text
7524df0 Cover grounding gate readiness paths
f087d45 Expose exact grounding selectors
4034f9b Bind grounded prompts to model attempts
7881cab Persist grounded prompt assembly evidence
30e972b Add grounding audit binding fields
4475eef Cover grounding contract blocker regressions
6d51898 Preserve grounding contracts in Run Detail
baa0b4a Enforce exact grounding contracts through APIs
52fbc3d Bind model calls to recomputable request hashes
d8a681f Persist safe grounding policy outcomes
801e710 Add grounding audit contract storage
1415bf6 Document P1 grounding audit status
eefa906 Cover grounding audit gate regressions
f199069 Show grounding audit evidence in Run Detail
247beec Expose grounding audit contracts through APIs
aef447c Persist auditable knowledge grounding evidence
9bee19e Add knowledge audit persistence tables
```

Captured in wiki:

- [[project-handoff-current-state]]
- [[session-2026-05-16-agent-knowledge-p1-grounding-audit]]
- [[session-2026-05-14-workspace-execution-evidence]]
- [[agent-workspace-execution-evidence-architecture]]
- [[local-dev-eval-dataset-migration]]
- [[session-2026-05-13-workspace-browser-smoke]]

## Next Known Work

The latest completed Agent Knowledge Harness lane is **P2 local knowledge management**. The next planned lane is **P3 real policy-gated web research**, and it should not be mocked as user-facing real evidence.

Follow the replanned progress in [[agent-knowledge-harness-roadmap]]:

- add real policy-gated web research only after provider configuration and safety policy exist;
- connect short-term memory, long-term memory, RAG, pinned context, context compression, and token budget into a prompt assembly router;
- productize MCP creation/management and Skills/capability packs;
- add groundedness/citation/unsupported-claim Eval and Observability surfaces;
- keep Docker Compose release and demo validation current.

Useful follow-up rules:

- Keep using host-port overrides when default local development ports are occupied.
- Preserve the Private Deployment report at `.omx/reports/private-deployment-experience/report-20260514T074949Z.md` as the runtime evidence pointer.
- If deployment handoff expands later, keep it bounded to documented private handoff improvements unless a new plan explicitly authorizes installer, Kubernetes, cloud matrix, or full operations work.
- For Agent Knowledge Harness changes, start from `.omx/specs/deep-interview-agent-knowledge-harness-memory-rag.md`, `.omx/plans/prd-agent-knowledge-harness-memory-rag.md`, `.omx/plans/test-spec-agent-knowledge-harness-memory-rag.md`, and this wiki page.

## Stop Rules For Future Agents

Do not claim product completion from UI polish alone. Stage claims must map to evidence in `docs/ai/task-progress.yaml`, `docs/task-progress.md`, test output, and the relevant `.omx/plans/test-spec-*.md`.

Do not change the product target away from `Model + Harness = Agent` without a new explicit user decision.

Do not treat legacy `/api/tasks/*` as the primary product proof. Agent Run is the product execution object; task APIs are compatibility plumbing.

## Related Pages

- [[deep-interview-private-harness-chain]]
- [[agent-knowledge-harness-roadmap]]
- [[workspace-demo-ready-constraints]]
- [[wiki-capture-candidates]]
- [[local-dev-backend-port-cors]]
- [[session-2026-05-13-workspace-browser-smoke]]
- [[agent-workspace-execution-evidence-architecture]]
- [[local-dev-eval-dataset-migration]]
- [[session-2026-05-14-workspace-execution-evidence]]
