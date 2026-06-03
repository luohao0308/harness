# Harness Wiki

Persistent project knowledge for the AI Harness Platform.

## Start Here

- `docs/ai/agent-startup-context.md` - Low-token startup context for new agent sessions before implementation.
- `docs/ai/context-index.json` - Machine-readable task-to-context route index used by `scripts/agent-context-brief.py`.
- [[project-handoff-current-state]] - Canonical handoff page for new sessions and incoming agents.
- [[deep-interview-private-harness-chain]] - Accepted project-wide target from `$deep-interview`.
- [[agent-knowledge-harness-roadmap]] - Current final target and replanned progress for the Agent Knowledge Harness capability stack.

## Pages

- [[project-handoff-current-state]] - Current target, progress state, required reading order, and next work.
- [[deep-interview-private-harness-chain]] - The private deployable Harness chain and decision boundaries.
- [[agent-knowledge-harness-roadmap]] - Current final target and replanned progress for Memory/RAG, knowledge management, MCP, skills, memory, context/token routing, hallucination control, Eval, Observability, Policy/Sandbox, and orchestration.
- [[workspace-demo-ready-constraints]] - Workspace productization constraints after Stage 07.
- [[wiki-capture-candidates]] - What historical project knowledge is worth capturing in wiki.
- [[local-dev-backend-port-cors]] - Local backend startup and `8000`/CORS diagnosis.
- [[session-2026-05-13-workspace-browser-smoke]] - Workspace browser smoke, compact chrome hardening, local API port diagnosis, and push record.
- [[agent-workspace-execution-evidence-architecture]] - Context compression, Plan-Act, branching/search, Run Detail, and Eval Case architecture.
- [[local-dev-eval-dataset-migration]] - Local Eval Dataset migration trap and recovery for `baseline_run_id`.
- [[session-2026-05-14-workspace-execution-evidence]] - Session log for commit `e78f52a` and validation evidence.
- [[session-2026-05-16-agent-knowledge-p1-grounding-audit]] - P1 Knowledge/RAG grounding audit and blocker-repair record through `4475eef`: prompt manifests, policy audits, verified-vs-fixture grounding, denied/redacted isolation, v2 request hashes, exact selectors, Run Detail Eval contract propagation, validation evidence, and remaining private-deployment gate.
- [[session-2026-05-17-agent-knowledge-p3-web-research]] - P3 real policy-gated web research record through `76f11d5`: Tavily adapter, URL/DNS policy gates, attempt ledger, source-bound citations, fake-provider hardening, Run Detail evidence, reports, validation, live smoke, and push evidence.
- [[session-2026-05-17-agent-knowledge-p4-context-assembly]] - P4 memory/context router V2 record through `6c4a95d`: backend authoritative context assembly, scoped memory, token-budget pruning, pinned-message tagging, context manifests, Run Detail evidence, validation, and push evidence.
- [[session-2026-05-17-agent-knowledge-p5-capability-registry]] - P5 MCP/Skills productization record through `f05816e`: capability registry, Agent attachments, immutable capability versions, fail-closed ToolRunner, approval resume, console feedback, tests, report, and push evidence.
- [[session-2026-05-18-agent-knowledge-p6-groundedness-eval-observability]] - P6 groundedness Eval and Observability record through `83c8eee`: Eval-owned grounding traces, forbidden leak boundaries, Observability projection, Run Detail selector saves, tests, report, and push evidence.
- [[session-2026-05-18-agent-knowledge-p7-release-demo-hardening]] - P7 release/demo hardening record through `a5d046b` on `origin/p7-release-demo-hardening`: deterministic Knowledge seed, grounding support document, service-level migration/restore smoke, release browser smoke, runbooks, Chinese-first selector/terminology UI follow-up, validation evidence, service check, and push evidence.
- [[session-2026-05-23-agent-startup-context-loop]] - Low-token startup context, task-to-context index, brief script, progress write-back rule, validation evidence, and subagent acceptance record for new-session handoff.
- [[session-2026-05-25-agent-knowledge-context-optimizer]] - Agent-level declarative `context_optimizer` capability packages, backend context assembly overlays, manifest evidence, Run Detail and Observability projection, UI status, validation evidence, and safety boundaries.
- [[session-2026-05-26-knowledge-workbench-modal-ui]] - `/knowledge` workbench modal configuration UI: source creation, source editing, add-document, and reingest flows moved out of inline page forms, with frontend tests, lint/build, and Playwright zero-overflow evidence.
- [[session-2026-05-26-mcp-skill-tool-modal-config]] - Tool Registry and Agent Studio MCP/Skill/Tool configuration moved behind click-open modal dialogs, with frontend tests, lint, and build evidence.
- [[session-2026-05-27-agent-console-chinese-follow-up-pages]] - Agent Studio, Knowledge, and Team Chinese-first wording follow-up with status-label cleanup, refreshed browser fixtures, focused headed smoke, and repeated 53-case Chromium evidence.
- [[agent-knowledge-harness-roadmap]] - Agent Knowledge Harness phase roadmap from P1 grounding through P7 release/demo hardening.

## Categories

- `architecture`
- `decision`
- `debugging`
- `environment`
- `reference`
- `session-log`
- `convention`

## Tags

- `handoff`
- `deep-interview`
- `harness-chain`
- `workspace`
- `browser-smoke`
- `playwright`
- `agent-console`
- `context-compression`
- `plan-act`
- `branching`
- `run-detail`
- `eval-case`
- `local-dev`
- `postgres`
- `alembic`
- `cors`
- `git`
- `agent-knowledge-harness`
- `memory`
- `rag`
- `mcp`
- `skills`
- `token-optimization`
- `hallucination`
- `knowledge-grounding`
- `web-research`
- `context-assembly`
- `prompt-manifest`
- `policy-audit`
- `cjk-retrieval`
- `task-progress`
- `observability`
- `forbidden-leak`
- `release`
- `demo`
- `migration`
- `selector-ui`
- `chinese-first`
- `startup-context`
- `context-index`
