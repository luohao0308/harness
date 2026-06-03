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
15. [[session-2026-05-17-agent-knowledge-p3-web-research]] if the next work touches real web research, Tavily, source-bound web citations, URL policy, fake-provider hardening, or web research Run Detail evidence.
16. [[session-2026-05-17-agent-knowledge-p4-context-assembly]] and `.omx/plans/ralplan-agent-knowledge-harness-p4-memory-context-router-v2.md` if the next work touches backend context assembly, long-term memory records, context manifests, token budgeting, pinned context, or model-call context binding.
17. `.omx/plans/prd-private-deployment-experience.md` and `.omx/plans/test-spec-private-deployment-experience.md` if the next work touches private deployment handoff.
18. [[session-2026-05-18-agent-knowledge-p7-release-demo-hardening]] if the next work touches deterministic demo seeds, Knowledge/RAG migration/restore smoke, release browser smoke, local fixture versus live provider evidence boundaries, Chinese-first console wording, or shared selector UI.

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
- Agent Knowledge Harness P2 local knowledge management is completed and pushed: agent/org-scoped text and Markdown knowledge sources now have lifecycle controls, document-level versioning, stale chunk filtering, retrieval eligibility, lifecycle audit events, failure audit records, multipart `.txt` / `.md` import, Agent Studio management UI, restore smoke coverage, and compose/Postgres private smoke evidence.
- Agent Knowledge Harness P3 real policy-gated web research is completed and pushed through `76f11d5`: Tavily provider adapter, no backend second-hop URL fetch, pre-call and post-result policy gates, DNS/IP URL safety checks, per-run attempt ledger, source-bound web citations, fake-provider hardening, Run Detail evidence, runbook, HTML explanation report, and live Tavily smoke evidence are recorded.
- Agent Knowledge Harness P4 memory and context router V2 is completed and pushed through `6c4a95d`: backend context assembly manifests, long-term memory records, SQL-level scope filtering, token estimator/drop ordering, pinned-message tagging, compressed-summary schema/model/branch/path checks, model-call context binding, shadow/authoritative feature flag behavior, memory injection flags, and Run Detail context manifest projection are implemented and verified.
- Agent Knowledge Harness P5 MCP/Skills productization is completed and pushed through `f05816e`: runtime tool authority is now `CapabilityRegistry -> AgentCapabilityAttachment -> immutable CapabilityVersion -> ToolRunner metadata snapshot`, legacy `Agent.tools_json` is only deterministic migration/seed backfill input with no runtime lazy backfill, ToolRunner fails closed without Agent attachment scope, executing test invocation is agent-scoped, admin validation is non-executing, approval decisions resume or fail runs correctly, console tool cards refresh after approval, and Run/ModelCall/ToolCall/Eval artifacts carry capability snapshot refs/hashes.
- Agent Knowledge Harness P6 groundedness Eval and Observability is completed and pushed through `83c8eee`: Eval now owns `GroundingTraceV1`, forbidden evidence leak judgment, grounding metrics, regression deltas/gates, and failure reasons; Observability has a read-only grounding-quality projection; Run Detail saves objective evidence selectors without inferring required/forbidden snippets or unsupported markers; Eval API responses scrub forbidden snippet payloads.
- Agent Knowledge Harness P7 release and demo hardening is completed and pushed to `origin/p7-release-demo-hardening` through `c404603`: deterministic Knowledge/RAG demo seed uses public APIs only and includes an agent grounding support document for the backend `min_hits=2` threshold; service-level migration/restore smoke verifies Knowledge/RAG tables and selector continuity; release browser smoke covers Agent Studio, Workspace, Run Detail, Eval, and Observability demo projections; runbooks now distinguish local fixture evidence from optional credential-gated live provider validation.
- Console Chinese-first selector/terminology hardening is completed and pushed on the same branch through `a5d046b`: shared `MenuSelect` now covers model, knowledge, run, and settings dropdowns with keyboard/focus behavior, grouping, disabled-option skipping, and placement support; required English terms such as MCP, RAG, API, Trace, WarmPool, JSON, Markdown, Prompt, and Provider keep their original names with adjacent small Chinese explanations.
- Frontend acceptance HTML is saved in the tracked report path `docs/reports/agent-knowledge-p2-code-review-frontend-acceptance-2026-05-17.html`; the runtime copy remains at `.omx/reports/html-archive/agent-knowledge-p2-code-review-frontend-acceptance-2026-05-17.html`.
- P3 HTML explanation report is saved in the tracked report path `docs/reports/p3-web-research-implementation-2026-05-17.html`.

Evidence from `docs/task-progress.md`:

- Stage 07 canonical Agent Run smoke is part of the regular release gate.
- Workspace browser smoke and compact chrome hardening were added after Stage 07.
- Broader browser smoke now has an explicit release-gate entrypoint through `cd apps/agent-console && npm run e2e:smoke:release`.
- Private deployment handoff now has a canonical Docker Compose path in `docs/runbooks/deployment.md`; static checks, compose config, compose startup, Docker smoke, Agent Run smoke, and compose cleanup have passed using intentional host-port overrides.
- P3 real policy-gated web research is recorded as completed with `96 passed` backend target tests, ruff, Alembic clean upgrade, frontend lint/build/targeted tests, and a live Tavily smoke.
- P4 memory/context router V2 is recorded as completed with backend context assembly tests, model-call binding tests, ruff, frontend build/lint/test evidence, docs validation, and final pushed commits through `6c4a95d`.
- P5 MCP/Skills productization is recorded as completed with capability registry storage, attachment-only runtime authority, approval resume fixes, console feedback, targeted backend/frontend tests, ruff, lint, and final pushed commits through `f05816e`.
- P7 release/demo hardening is recorded as completed and pushed with seed-plan py_compile/print-plan checks, non-default local API seed/readback/idempotency, chat-stream demo grounding proof, service-level migration/restore smoke, backend ruff/targeted tests, frontend lint/build/unit tests, release browser smoke, compose config, docs validation, whitespace checks, and branch push evidence through `c404603`.
- The latest console UI follow-up is recorded with frontend lint, full Vitest, production build, whitespace check, non-default frontend service check on `18082`, and push evidence through `a5d046b`.

Evidence from the current codebase:

- `services/api-server/app/knowledge.py`, `services/api-server/alembic/versions/20260514_0011_create_knowledge_rag.py`, `services/api-server/alembic/versions/20260516_0012_create_knowledge_audit_manifests.py`, `services/api-server/alembic/versions/20260516_0013_add_grounding_model_call_binding.py`, `services/api-server/alembic/versions/20260517_0015_add_knowledge_lifecycle_contract.py`, and `services/api-server/tests/test_knowledge_rag.py` define a Knowledge/RAG foundation with prompt assembly manifests, policy audits, citation snapshots, insufficient-evidence controls, CJK fallback retrieval, attempt-level model-call audit binding, request hashing, exact selector behavior, lifecycle/versioning, restore/migration smoke, and org/agent scope isolation.
- `services/api-server/app/api/agents.py` exposes knowledge source lifecycle APIs, document APIs, scope APIs, and Workspace grounding behavior.
- `services/api-server/app/knowledge_web.py`, `services/api-server/app/sandbox/policies.py`, `services/api-server/app/knowledge.py`, and `services/api-server/alembic/versions/20260517_0016_create_web_research_attempts.py` implement P3 Tavily-backed source-bound web research with policy gates and attempt reservations.
- `services/api-server/app/agents/context_router.py`, `services/api-server/alembic/versions/20260517_0017_create_context_assembly.py`, and `services/api-server/tests/test_context_router.py` implement P4 backend context assembly, memory eligibility, token pruning, append-only context manifests, and model-call context binding.
- `apps/agent-console/src/features/agents/components/KnowledgeManagementPanel.tsx` exposes Agent Studio knowledge source management.
- `apps/agent-console/src/features/agents/components/ChatMessageBubble.tsx` and `apps/agent-console/src/features/runs/pages/RunDetailPage.tsx` expose grounding evidence in Workspace and Run Detail, including P3 source-bound web evidence.

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

Console Chinese-first selector/terminology follow-up:

```text
apps/agent-console/src/components/ui/menu-select.tsx
apps/agent-console/src/components/ui/term.tsx
apps/agent-console/src/components/ui/__tests__/menu-select.test.tsx
apps/agent-console/src/features/agents/components/ModelPicker.tsx
apps/agent-console/src/features/agents/components/KnowledgeManagementPanel.tsx
apps/agent-console/src/features/agents/pages/AgentListPage.tsx
apps/agent-console/src/features/runs/pages/RunDetailPage.tsx
apps/agent-console/src/features/settings/pages/ModelSettingsPage.tsx
apps/agent-console/src/features/observability/pages/ObservabilityPage.tsx
apps/agent-console/src/features/tools/pages/ToolRegistryPage.tsx
docs/ai/task-progress.yaml
docs/task-progress.md
docs/human/10-task-progress.md
```

Console UI verification summary:

```text
cd apps/agent-console && npm run lint -> passed
cd apps/agent-console && npm test -> 30 files / 148 tests passed
cd apps/agent-console && npm run build -> passed
git diff --check -> passed
frontend http://127.0.0.1:18082/ -> ok
API http://127.0.0.1:8000/health -> ok
```

Console UI commit pushed to `origin/p7-release-demo-hardening`:

```text
a5d046b Make console selectors and terms usable for Chinese-first UI
```

P7 pushed branch work:

```text
scripts/seed-knowledge-demo.py
scripts/smoke-test-knowledge-migration-restore.py
apps/agent-console/e2e/eval-page.smoke.spec.ts
apps/agent-console/e2e/knowledge-demo.smoke.spec.ts
apps/agent-console/package.json
docs/runbooks/deployment.md
docs/runbooks/troubleshooting.md
docs/runbooks/web-research.md
docs/ai/task-progress.yaml
docs/task-progress.md
omx_wiki/agent-knowledge-harness-roadmap.md
omx_wiki/index.md
omx_wiki/project-handoff-current-state.md
omx_wiki/session-2026-05-18-agent-knowledge-p7-release-demo-hardening.md
```

P7 verification summary:

```text
HARNESS_API_BASE_URL=http://127.0.0.1:18007 python3 scripts/seed-knowledge-demo.py --verify-readback --check-idempotent -> passed against temporary local API server
HARNESS_API_BASE_URL=http://127.0.0.1:18008 python3 scripts/seed-knowledge-demo.py --verify-readback --check-idempotent -> passed on non-default local API, with agent_grounding-evidence_document_id c56df7d0-d084-4014-9119-12f8100e5dc6
POST /api/agents/default/runs/chat/stream on http://127.0.0.1:18008 with the demo question -> returned knowledge_grounding: Local knowledge grounded the answer.
python3 scripts/smoke-test-knowledge-migration-restore.py -> passed
cd apps/agent-console && npm run e2e:smoke:release -> passed
python3 scripts/validate-docs.py -> passed
git diff --check -> passed
```

P7 commits pushed to `origin/p7-release-demo-hardening`:

```text
a5d046b Make console selectors and terms usable for Chinese-first UI
c404603 Record P7 release demo handoff
40026b3 Add P7 release demo review report
f8ba7cf Document P7 release demo runbooks
a561d4e Add P7 browser release smoke
7a15f1e Guard P7 service smoke scripts
d6478b7 Add P7 Knowledge demo seed
```

P7 pull request URL:

```text
https://github.com/luohao0308/harness/pull/new/p7-release-demo-hardening
```

Recent P5 commits pushed on `main`:

```text
f05816e Record P5 capability registry handoff
152d070 Cover capability and approval regressions
b0fbbd2 Expose capability-bound tool feedback in console
237c403 Resolve tool execution through capability attachments
67b7a5c Add capability registry storage contract
```

Push evidence:

```text
git push origin main
6c4a95d..f05816e  main -> main
git rev-list --left-right --count origin/main...HEAD
0 0
```

Previous P4 commits pushed on `main`:

```text
6c4a95d Record P4 context assembly handoff
c97a333 Cover context assembly regressions
dc0f916 Expose backend context assembly in Workspace
d2b6e50 Assemble authoritative workspace context
45da62f Add context assembly storage contract
```

P4 push evidence:

```text
git push origin main
76f11d5..6c4a95d  main -> main
git rev-list --left-right --count origin/main...HEAD
0 0
```

Previous P3 commits pushed on `main`:

```text
76f11d5 Document P3 web research handoff
50f6d33 Show source-bound web evidence in Run Detail
03f4814 Bind web research fallback evidence
39ec034 Enforce web research policy gates
7cb3e9a Persist web research attempt reservations
d3e8d24 Add Tavily web research adapter
```

P3 push evidence:

```text
git push origin main
11a4906..76f11d5  main -> main
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
- [[session-2026-05-17-agent-knowledge-p3-web-research]]
- [[session-2026-05-17-agent-knowledge-p4-context-assembly]]
- [[session-2026-05-18-agent-knowledge-p7-release-demo-hardening]]
- [[session-2026-05-17-agent-knowledge-p5-capability-registry]]
- [[session-2026-05-18-agent-knowledge-p6-groundedness-eval-observability]]

## Next Known Work

The latest completed Agent Knowledge Harness lane is **P7 Release And Demo Hardening**, with a follow-up console Chinese-first selector/terminology hardening commit pushed to `origin/p7-release-demo-hardening` through `a5d046b`.

Follow the replanned progress in [[agent-knowledge-harness-roadmap]]:

- keep groundedness/citation/unsupported-claim Eval and Observability surfaces regression-tested;
- keep Docker Compose release and demo validation current.
- keep deterministic local P7 seed separate from optional credential-gated Tavily/live provider validation.
- keep the shared `MenuSelect` keyboard/focus contract and adjacent small Chinese explanations when adding new selectors or required English terms.

Useful follow-up rules:

- Keep using host-port overrides when default local development ports are occupied.
- Preserve the Private Deployment report at `.omx/reports/private-deployment-experience/report-20260514T074949Z.md` as the runtime evidence pointer.
- If deployment handoff expands later, keep it bounded to documented private handoff improvements unless a new plan explicitly authorizes installer, Kubernetes, cloud matrix, or full operations work.
- For Agent Knowledge Harness changes, start from `.omx/specs/deep-interview-agent-knowledge-harness-memory-rag.md`, `.omx/plans/prd-agent-knowledge-harness-memory-rag.md`, `.omx/plans/test-spec-agent-knowledge-harness-memory-rag.md`, and this wiki page.
- If future web work fetches webpage bodies from returned URLs, treat it as a new crawler/fetcher security design rather than an implicit P3 extension.

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
- [[session-2026-05-17-agent-knowledge-p3-web-research]]
