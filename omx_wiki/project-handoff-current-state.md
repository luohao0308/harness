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
- Agent Knowledge Harness Eval Dimensions v2 is verified locally on 2026-05-28: Eval now supports optional deterministic `refusal_contract`, `safety_contract`, and `persona_contract` JSON sections, with aggregate metrics, regression gates, per-case UI badges/breakdowns, and preset templates. Validation passed backend Eval tests, Ruff, frontend contract test, lint/build under Node 24, docs validation, and whitespace checks. See [[session-2026-05-28-eval-dimensions-v2]].
- Agent Knowledge Harness P7 release and demo hardening is completed and pushed to `origin/p7-release-demo-hardening` through `c404603`: deterministic Knowledge/RAG demo seed uses public APIs only and includes an agent grounding support document for the backend `min_hits=2` threshold; service-level migration/restore smoke verifies Knowledge/RAG tables and selector continuity; release browser smoke covers Agent Studio, Workspace, Run Detail, Eval, and Observability demo projections; runbooks now distinguish local fixture evidence from optional credential-gated live provider validation.
- Console Chinese-first selector/terminology hardening is completed and pushed on the same branch through `a5d046b`: shared `MenuSelect` now covers model, knowledge, run, and settings dropdowns with keyboard/focus behavior, grouping, disabled-option skipping, and placement support; required English terms such as MCP, RAG, API, Trace, WarmPool, JSON, Markdown, Prompt, and Provider keep their original names with adjacent small Chinese explanations.
- Team Mode Team Mode alignment product surface is verified locally on 2026-05-25: Team Mode now has durable Team/TeamAgent/mailbox/task/event backend state, team CRUD/member/mailbox/task/wake/event APIs, Team frontend routes/list/create/rail/columns/composers, Agent Workspace team launch, and mocked browser smoke coverage.
- Capability product and console spine polish is verified locally on 2026-05-25: capability package validation/install/preflight/upload/attach/rollback/uninstall APIs are wired into Tool Registry, Agent Studio can create/clone Agents and attach capabilities, knowledge connector readiness is evidence-backed, same-origin API base fallback is deployment-safe, Run Detail includes token optimization evidence, and local runtime artifacts are ignored.
- Agent-level Token Optimizer and context cache evidence are verified locally on 2026-05-25: Agent Studio exposes built-in Token 省用方案 presets instead of requiring package install, context assembly records optimizer/cache evidence, `/token-savings` shows aggregate savings plus per-source cache hit rates, repeated `/context/compress` now persists and hits the server-side summary cache after request/session close, and live browser smoke shows `缓存命中率 2 / 11` with `摘要缓存 28.57%`.
- Workspace summary cache trust-boundary hardening is verified locally on 2026-05-25: `/context/compress` no longer trusts client-provided `existing_summary` as an accepted cache entry, DB-backed `workspace_context_caches` hits win even when the client hint is stale, and regression coverage confirms the server recomputes or reuses only server-owned summaries.
- Built-in multi-level context cache final verification is recorded locally on 2026-05-25: compression summary cache status now flows through chat payloads into ContextAssemblyManifest evidence, DB-backed `workspace_context_caches` covers `compression_summary`, `rag_retrieval`, and `long_term_memory`, `/token-savings` exposes total and per-source hit rates, and the live API returned total cache hits 5, misses 13, stale 0, with `摘要缓存` hit rate 41.67%.
- Built-in connector/model/layout polish is verified locally on 2026-05-26: Agent Studio Knowledge Management offers simple Dify, Coze, and RAGFlow external API presets without package installation; Tool Registry defaults to 常用预置能力 manual one-click built-in capability choices and hides package install/upload/lifecycle controls inside collapsed 高级包管理; Model Settings Add & Switch releases immediately after save success even if health/refetch calls are slow; Run History uses a compact toolbar with a short `工作台` action; browser smoke confirmed /tools default view hides 可信 URL 一键安装, 安装到 Agent, and 下载、安装并启用 while key pages have no horizontal overflow.
- Knowledge workbench local/API connector management is verified locally on 2026-05-26: `/knowledge` is a standalone console page with sidebar `知识库` navigation, Agent selection, local/API/preview filters, source statistics, and shared Knowledge Management detail/lifecycle controls. API presets cover runtime-capable Dify and Coze plus preview RAGFlow, Local Dify, and Local RAGFlow endpoint configuration; connector responses expose derived validation status/messages; endpoint, secret_ref, required dataset/space id for remote API providers, raw-secret redaction, endpoint-credential blocking, and crawler-style option rejection are covered; `source_type=connector` is excluded from local chunk grounding so connector configuration cannot become verified local evidence.
- Dify connector runtime retrieval is verified locally on 2026-05-26: configured Dify knowledge sources now call the Dify dataset retrieval endpoint at runtime after local Knowledge/RAG evidence is insufficient and before web research fallback. Retrieval creates `dify_connector` hits, `[D1]` citations, source-bound prompt manifest metadata, and connector policy audit evidence; raw secrets resolve from frontend-stored `secret://dify` values or environment fallback and are not persisted in source snapshots. RAGFlow/Local Dify/Local RAGFlow remain configuration/preflight-only in this slice, and connector config documents remain `connector_config_only` / `retrieval_eligible=false`.
- Coze connector runtime retrieval is verified locally on 2026-05-26: Coze now has usable release state, frontend-managed API key storage, runtime secret resolution for `secret://coze`, and a source-bound adapter path that runs after local insufficiency and before Dify/web fallback. Accepted results become `coze_connector` hits with `[C1]` citations, prompt-manifest snapshots, and connector policy audits; missing secrets or Coze provider errors are surfaced as runtime evidence without fabricating grounding. Live local API smoke proved Coze config readiness and backend secret storage, and a local Coze-compatible runtime smoke through Workspace chat returned `Local knowledge is insufficient; Coze connector grounded the answer` with `grounding_provider=coze_connector`, one `coze_connector` hit, and `[C1]` citation. External Coze provider retrieval was not run because no real Coze credential/dataset was available; the adapter defaults to `https://api.coze.cn/v1/datasets/{dataset_id}/retrieve` and remains endpoint-configurable.
- Dify connector secret-ref diagnostics are verified locally on 2026-05-26: live probing showed the configured Dify source was discovered and attempted at runtime, but the stored value in `secret_ref` was raw-secret-like and could not be resolved through the backend environment. The source was repaired to `secret://dify` with dataset id `e1c4cb28-2a23-42c4-b2ab-0736f12a9720`; backend creation/responses now reject or redact raw-secret-looking refs, runtime evidence now says when a Dify secret cannot be resolved or a provider call fails, and frontend forms warn users to use `secret://dify` or `env://DIFY_API_KEY`. A direct Dify probe with the old supplied-looking value returned HTTP 403, so real retrieval still requires a valid dataset-authorized Dify Knowledge API key configured in the API server environment.
- Dify connector frontend secret storage is verified locally on 2026-05-26: the `/knowledge` connector dialog now has separate `密钥引用` and `API Key 密钥值` fields. The backend accepts `connector_secret_value`, saves it in service-side connector secret settings keyed by `secret://dify`, and still keeps `KnowledgeSource.settings_json` / API responses / prompt manifests raw-secret-free. Runtime Dify retrieval resolves the saved frontend-provided key before environment fallback, and source responses expose only `connector_secret_configured`.
- Dify connector 403/1010 hardening is verified locally on 2026-05-26: Dify runtime retrieval now sends `Accept: application/json` plus `User-Agent: AgentHarness/0.1`, which moves Dify Cloud responses from pre-provider `HTTP 403 error code: 1010` to provider-layer diagnostics. Dify HTTP error bodies are included as short redacted connector failure messages. Live probing of saved source `7bca85fd-2c08-4cab-88de-8d33fb78baa6` confirmed `secret://dify` resolves and the current remaining failure is Dify-side `HTTP 400 invalid_param` with Collection/embedding/quota detail, not missing local connector invocation.
- Dify connector keyword-search runtime is verified locally on 2026-05-26: `DifyKnowledgeBaseAdapter` now uses `retrieval_model.search_method=keyword_search` instead of `hybrid_search`, avoiding Dify's vector collection path for datasets that return `Collection not found`. Live probing of source `7bca85fd-2c08-4cab-88de-8d33fb78baa6` with dataset `e1c4cb28-2a23-42c4-b2ab-0736f12a9720` and saved `secret://dify` returned HTTP 200 with 0 records instead of the previous `HTTP 400 invalid_param ... Collection not found`; remaining knowledge insufficiency means Dify returned no matching chunks for the query.
- Dify disabled-document empty-result diagnostics are verified locally on 2026-05-26: live Dify dataset probing showed source `7bca85fd-2c08-4cab-88de-8d33fb78baa6` has 4 documents, all `indexing_status=completed` but `enabled=false`. Runtime grounding now checks Dify document enabled status when retrieval succeeds with 0 records, records document counts in retrieval metadata, and reports that all indexed Dify documents are disabled instead of the generic `Dify connector returned no accepted results` message.
- Dify dataset-default retrieval is verified locally on 2026-05-26: after the user enabled documents in Dify, live probing showed the same query `公司的愿景与价值观是什么` returned 0 records only when Harness forced `keyword_search`; omitting `retrieval_model` let Dify apply its stored `retrieval_model_dict` and returned records, matching Dify Console test retrieval. `DifyKnowledgeBaseAdapter` now posts only the bounded query by default. After backend restart on `127.0.0.1:8000`, live `ground_query` returned 3 `dify_connector` hits and evidence message `Dify connector grounded the answer`.
- Coze official document-list ranking and Dify fallback are verified locally on 2026-05-26: Coze base endpoints such as `https://api.coze.cn` now use `/open_api/knowledge/document/list` with numeric dataset-id coercion, signed document-content fetch, bounded in-memory chunking, and stricter Chinese core-term ranking. Live probing of saved Coze dataset `7629341424630448134` returned 0 Coze results for `公司的愿景与价值观是什么` while preserving Coze hits for `厦门科技馆的主题是什么`; live `ground_query` now routes the science-museum query to `coze_connector` and falls through to Dify for the company vision query with 3 `dify_connector` hits.
- MCP/Skill/Tool modal configuration is verified locally on 2026-05-26: Tool Registry and Agent Studio no longer expose capability configuration forms inline by default. A shared `ConfigDialog` now hosts built-in preset Agent confirmation, trusted URL install, public URL preflight, Skill upload, package lifecycle, Agent-scoped test invoke, and Agent Studio capability attachment, with tests asserting inputs are hidden until the relevant dialog opens.
- Knowledge connector editable configuration UI is verified locally on 2026-05-26: the knowledge source edit dialog now clearly separates `基础信息` from `API 接入配置`, shows Provider/secret/retrieval status as read-only context, and lets connector users edit API Endpoint, Secret Ref, dataset/knowledge id, and optional replacement API Key. Backend PATCH now accepts connector settings for connector sources only and reuses the existing normalization safety gates for raw-secret rejection/redaction, endpoint credentials, required dataset ids, release-state derivation, and crawler-style option rejection. The local Coze source `5c3cfe97-9b9d-40ac-9021-d9da6bbaf859` was repaired from space id `7618108220116893732` to knowledge id `7629341424630448134`; response confirmed `connector_validation_status=ready` and `connector_secret_configured=true`.
- Knowledge workbench modal configuration UI is verified locally on 2026-05-26: `/knowledge` no longer renders long local/API configuration forms inline. Source creation, source editing, add-document, and reingest flows now open modal dialogs, while the page keeps overview metrics, source list, validation/status badges, lifecycle controls, and document-version summaries visible. External API connector creation now uses `保存配置` / `保存中` wording, adds a 12s connector-only frontend timeout that surfaces `请求超时` instead of leaving the modal indefinitely pending, and live API health plus temporary connector create/archive checks passed after restoring `127.0.0.1:8000`.
- Knowledge source hard delete and Chinese dialog copy are verified locally on 2026-05-26: `/knowledge` and Agent Studio now expose a dangerous `删除` action that calls `DELETE /api/agents/{agent_id}/knowledge/sources/{source_id}`. The backend deletes source/document/chunk/embedding rows, preserves historical retrieval/citation evidence through snapshots with live FKs nulled, marks RAG retrieval caches stale, and writes a `knowledge_source.deleted` audit event. Connector dialog/helper detail copy is Chinese-first, and the local API was restarted on `127.0.0.1:8000`; live create/delete smoke returned 204 and confirmed the deleted id disappeared from list responses, resolving the observed 405 from the stale backend process.
- Dify grounded answer evidence-use hardening is verified locally on 2026-05-26: live `ground_query` run `ecd15f37-7a3e-4752-a513-38aab367882e` for `公司的愿景与价值观是什么` returned `grounding_provider=dify_connector`, 3 hits, and the first two records `[D1] 企业愿景 > 成为客户最信赖的视觉创意伙伴，用设计创造商业价值` plus `[D2] 长期愿景` with international influence/design benchmark/world/social-good bullets. Workspace chat run `ec724c8b-c0ea-4918-8adf-1e3ba861443f` returned the Dify-backed answer with `[D1]`, `[D2]`, and `[D3]` instead of asking for a company name. Backend prompt evidence now tells the model to answer from retrieved evidence when direct evidence exists, and a deterministic fallback rewrites grounded-but-clarifying model output into cited retrieval snippets. The detector was expanded for the observed `没有指明具体是哪家公司 / 补充一下公司名称` wording; live Workspace chat run `8e428b6b-42e2-4686-b066-3fb99e837b16` returned the Dify-backed answer after API restart.
- Current multi-level context cache re-verification is recorded locally on 2026-05-26: targeted backend cache tests, frontend cache-status/token-savings tests, Ruff, frontend lint/build, and Alembic upgrade passed; live services in tmux session `harness-dev-cache` responded on `127.0.0.1:8000` and `127.0.0.1:5173`; `/api/observability/token-savings` returned actual total 160797, estimated saved 1882, cache hits 5, misses 13, stale 0, and source rows for `compression_summary`, `rag_retrieval`, and `long_term_memory`.
- Team Mode and Agent Workspace composer responsive polish is verified locally on 2026-05-25: Agent and Team share a 200px compact composer settings popover with 计划模式 and 追踪目标模式 switches, `View Steps · 0 条任务` remains visible in Team columns, the visible Team send-target pill has been removed from the composer, and Playwright layout checks found no document overflow.
- Agent Workspace and Team Mode composer commands/context polish is verified locally on 2026-05-25: `/compress` now works through the shared slash command registry, Team columns can manually or automatically compress branch-scoped context through the existing Agent compression endpoint, Team summaries use the same compact Agent Workspace-style header control, ContextRing shows an active pending compression state, and Team assistant replies can create Agent-like sibling branches with a branch switcher.
- Team Mode real-agent creation hardening is verified locally on 2026-05-25: the backend keeps the Team tool protocol in every model wake so follow-up confirmations still call `team_spawn_agent`, frontend SSE projection keeps `TEAM_AGENT_SPAWNED` as real chat columns, and target team `5b16955b-b4fb-49fe-9c9a-3b3f3e42ba82` now renders Default Agent plus real Writing Agent, Research Agent, and Review Agent windows.
- Composer plugin-row layout polish is verified locally on 2026-05-25: Agent Workspace and Team Mode now keep the `插件 / MCP` row aligned inside the 200px settings popover with fixed icon/chevron slots, middle-label truncation, and a tightened expanded MCP list; Playwright metrics show zero document overflow on both pages. The newer target team `04561550-0965-4b31-bf02-2deb2a8fc020` also verified tool-created visible teammate behavior with unknown `agent_type` falling back to `agent_id: default`.
- Team Mode message dedupe and latest-scroll polish is verified locally on 2026-05-25: Team chat now uses `mailbox_message_id` as the stable frontend dedupe key when present, preventing the temporary duplicate user turn during streaming, and chat records snap to the latest message when opened. Live Playwright on team `04561550-0965-4b31-bf02-2deb2a8fc020` confirmed sent-content counts stayed at 1 during and after send, with the scroller distance from bottom at 0.
- Team Mode assigned-task auto-wake hardening is verified locally on 2026-05-25: the non-streaming backend wake path now carries deferred follow-up owner wake IDs for `team_task_create` / `team_send_message`, tool-spawned teammates defer their welcome wake until the same tool round commits assignments, and target team `04561550-0965-4b31-bf02-2deb2a8fc020` recovered from all-pending symptoms to 8 `in_progress` tasks, empty unread counts, idle agents, and `wake.in_progress=false` across the team.
- Agent Workspace and Team Mode model picker popover layout is verified locally on 2026-05-25: the compact 200px model switch popover now uses provider labels as row titles, model ids as subtitles, selected-row highlighting instead of a right-side current badge, and 28px icon cells so `DeepSeek Flash`, `DeepSeek Pro`, and `openai-compatible` fit without the screenshot's text-column squeeze.
- Team Mode task-update alias/current-task hardening is verified locally on 2026-05-25: `team_task_update` now accepts `task_id` / `taskId` / `id` / `task`, can update the caller's unique open assigned task when no task id is provided, rejects ambiguous multi-task updates, and target team `6c03c9e9-7fd2-4316-a9e1-dd6958c0c2b5` recovered task `dfd23488-f9ef-41a3-983f-4421a9179f12` from `in_progress` to `completed`.
- Team/Agent stop-empty-placeholder hardening is verified locally on 2026-05-25: stopping before any assistant content removes the empty assistant placeholder instead of leaving a blank bubble, stopping after partial content preserves the paused partial answer, and the bottom-right shared composer no longer renders or accepts a continue-generation action after pause.
- Team/Agent composer stop-control and describe-assistant tool hardening is verified locally on 2026-05-25: Agent Workspace and Team Mode now keep stop generation only on the bottom-right composer primary action, Team column headers no longer render a separate stop button, and `team_describe_assistant` accepts omitted args plus `agent_id` / `agent_type` / `assistant` / `name` aliases instead of failing with `custom_agent_id is required`. Target team `04561550-0965-4b31-bf02-2deb2a8fc020` returned HTTP 200 for empty, `agent_id=default`, and `name="Default Agent"` describe-assistant calls after backend restart.
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

Team Mode Team Mode alignment and capability product spine:

```text
services/api-server/alembic/versions/20260523_0020_create_team_mode.py
services/api-server/app/api/teams.py
services/api-server/app/teams/
services/api-server/tests/test_teams.py
apps/agent-console/src/features/teams/
apps/agent-console/e2e/team-mode.smoke.spec.ts
apps/agent-console/src/features/tools/pages/ToolRegistryPage.tsx
services/api-server/app/api/tools.py
services/api-server/app/tools/capabilities.py
apps/agent-console/src/features/agents/pages/AgentListPage.tsx
apps/agent-console/src/features/tasks/api.ts
docs/architecture/team-mode-team-mode-alignment.md
docs/ai/task-progress.yaml
omx_wiki/project-handoff-current-state.md
omx_wiki/log.md
```

Team/capability verification summary:

```text
cd services/api-server && uv run pytest tests/test_teams.py -q -> passed
cd services/api-server && uv run pytest tests/test_tool_registry.py tests/test_agents.py tests/test_context_router.py tests/test_cors.py tests/test_knowledge_connectors.py tests/test_tool_runner.py -q -> passed
cd services/api-server && uv run ruff check app tests -> passed
cd apps/agent-console && npm test -- TeamPages.test.tsx AgentWorkspacePage.team-launch.test.tsx ToolRegistryPage.marketplace.test.tsx AgentListPage.studio.test.tsx api.test.ts ChatSurface.shell.test.tsx useChatStream.test.tsx -> passed
cd apps/agent-console && npm run lint -- --pretty false -> passed
cd apps/agent-console && npm run build -> passed
cd apps/agent-console && HARNESS_PLAYWRIGHT_BASE_URL=http://127.0.0.1:5173 npx playwright test --project=chromium e2e/team-mode.smoke.spec.ts -> 2 passed
python3 scripts/validate-docs.py -> passed
git diff --check -> passed
```

Team/capability behavior:

```text
Team Mode is a durable team collaboration room, not a Run Detail variant.
Team API owns Team, TeamAgent, TeamMailboxMessage, TeamTask, and TeamEvent state plus wake/event streams.
Team UI exposes list/create, rail, horizontal agent columns, per-column composer, View Steps, message stream, and team launch from Agent Workspace.
Tool Registry exposes simple trusted URL install, public URL preflight, upload install, advanced lifecycle, attach/disable, rollback, uninstall, and dependency preflight.
Agent Studio supports create, clone, built-in capability attach, and knowledge connector readiness from indexed sources.
Frontend API resolution uses same-origin by default and falls back from configured absolute URLs to relative paths for deployed consoles.
```

Agent Workspace and Team Mode composer commands/context polish:

```text
apps/agent-console/src/features/agents/lib/slashCommands.ts
apps/agent-console/src/features/agents/components/ChatSurface.tsx
apps/agent-console/src/features/agents/components/ContextRing.tsx
apps/agent-console/src/features/agents/components/ContextSummaryManager.tsx
apps/agent-console/src/features/teams/pages/TeamPage.tsx
apps/agent-console/src/features/agents/__tests__/slashCommands.property.test.ts
apps/agent-console/src/features/agents/__tests__/ChatSurface.shell.test.tsx
apps/agent-console/src/features/teams/__tests__/TeamPages.test.tsx
docs/ai/task-progress.yaml
omx_wiki/project-handoff-current-state.md
omx_wiki/log.md
```

Composer command/context verification summary:

```text
cd apps/agent-console && npm test -- TeamPages.test.tsx ChatSurface.shell.test.tsx slashCommands.property.test.ts -> 50 passed
cd apps/agent-console && npm test -- TeamPages.test.tsx ChatSurface.shell.test.tsx -> 35 passed
cd apps/agent-console && npm run lint -- --pretty false -> passed
python3 scripts/validate-docs.py -> passed
git diff --check -> passed
curl --noproxy '*' -sS -m 5 http://127.0.0.1:5173/ -> HTTP 200
curl --noproxy '*' -sS -m 5 http://127.0.0.1:8000/health -> HTTP 200
```

Composer command/context behavior:

```text
/compress, /compact, and /context resolve to the shared compress command.
Agent Workspace dispatches /compress through the existing manual context compression path.
Team Mode /plan switches the active column into markdown planning mode and sends the next message with mode=markdown_plan.
Legacy /Harness Agent remains a compatibility alias for /plan, but the visible command menu now uses /plan.
/run, /act, and /execute switch the active column into executable Plan-Act mode and send the next message with mode=plan.
Team Mode reuses POST /api/agents/{agent_id}/context/compress per Team column with team/slot/leaf scoped branch keys.
Agent Workspace and Team Mode now import the same `ContextSummaryManager` component for generated compression summaries: inline coverage count plus recompress/clear actions, with preview text and token compression details available on hover/focus.
Team ContextRing supports manual compression, pending animation, effective-token display, and threshold-based background compression after completed assistant turns.
Team assistant messages can branch from the previous user prompt and switch sibling assistant replies with the Agent branch switcher.
```

Previous Agent Workspace and Team Mode model picker popover layout:

```text
apps/agent-console/src/components/ui/menu-select.tsx
apps/agent-console/src/features/agents/components/ModelPicker.tsx
apps/agent-console/src/features/agents/components/ChatSurface.tsx
apps/agent-console/src/features/teams/pages/TeamPage.tsx
docs/ai/task-progress.yaml
omx_wiki/project-handoff-current-state.md
omx_wiki/log.md
```

Model picker popover verification summary:

```text
cd apps/agent-console && npm test -- ChatSurface.shell.test.tsx TeamPages.test.tsx WorkspaceShellBar.render.test.tsx -> 37 passed
cd apps/agent-console && npm run lint -- --pretty false -> passed
Playwright 390x844 /agents/default/workspace model popover -> width 200, document overflow 0, row width 186, text column width 128
Playwright 390x844 /teams/04561550-0965-4b31-bf02-2deb2a8fc020 model popover -> width 200, document overflow 0, row width 186, text column width 128
```

Model picker popover behavior:

```text
Rows show the readable provider label as the title and the concrete model id as the subtitle.
The selected row is indicated by row highlighting, not a trailing "当前" badge that consumes width.
Agent Workspace, shared MenuSelect, and Team Mode use the same compact 28px icon cell and reduced horizontal padding.
```

Previous Team Mode task-update alias/current-task hardening remains recorded in `docs/ai/task-progress.yaml` and the session log.

Previous Team/Agent stop-empty-placeholder and no-composer-resume hardening remains recorded in `docs/ai/task-progress.yaml` and the session log.

Previous Team/Agent composer stop-control and describe-assistant tool hardening remains recorded in `docs/ai/task-progress.yaml` and the session log.

Previous Team Mode assigned-task auto-wake hardening remains recorded in `docs/ai/task-progress.yaml` and the session log.

Previous Team Mode message dedupe and latest-scroll polish remains recorded in `docs/ai/task-progress.yaml` and the session log.

Previous console Chinese-first selector/terminology follow-up remains recorded below as pushed through `a5d046b`.

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
