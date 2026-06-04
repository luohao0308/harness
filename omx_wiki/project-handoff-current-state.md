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
19. [[session-2026-05-29-auth-retention-cicd]] if the next work touches AuthN/AuthZ/RBAC, API keys, org membership, audit logs, data retention/export/delete, CI/CD workflows, production Dockerfiles, or release engineering.
20. [[session-2026-05-29-docs-help-performance-scale]] if the next work touches Help Center docs, troubleshooting, generated API docs, query caching, cursor pagination, lazy frontend routes, CDN/static assets, load tests, or performance runbooks.

## Current State

Evidence from `docs/ai/task-progress.yaml`:

- `current_stage`: `07-private-deployable-harness-chain`
- `current_status`: `completed`
- `product`: `AI Harness Platform`
- `formula`: `Model + Harness = Agent`
- Stage 01-07 are recorded as completed.
- Post-stage hardening `workspace-browser-e2e-smoke` is recorded as completed.
- Private deployment experience is the latest completed post-stage lane: Docker Compose is the canonical private handoff path, host-port overrides are documented, Docker smoke and Agent Run smoke pass, and cleanup evidence is recorded.
- Local Agent Bridge Conversation V1 and Workspace Chat V2 are verified locally on 2026-06-04 on branch `feature/local-agent-bridge-v1-v2`: `.omx/plans/prd-local-agent-bridge-conversation-v1.md`, `.omx/plans/test-spec-local-agent-bridge-conversation-v1.md`, `.omx/plans/prd-local-agent-workspace-chat-v2.md`, and `.omx/plans/test-spec-local-agent-workspace-chat-v2.md` are入库; Agent Studio pairs fake/hao local bridges without a cloud-Agent creation path; local connections bind/resume API-owned Workspace sessions inside the existing ChatSurface; pending/offline state is API-projected; terminal bridge event/ack state is immutable; final code/security review returned `APPROVE`; final architecture review returned `WATCH` with no blockers. The remaining WATCH is V3 scope: bridge-reported `tool_result` is observation only until host tool approval, policy, audit fail-closed, pending change, command lifecycle, cancel/retry, and safety tests are implemented.
- Model Settings manual status refresh is verified locally on 2026-06-03: Model Gateway now exposes a visible `刷新状态` action that manually calls Harness `/api/settings/models/health`, shows compact per-model Harness probe strips, and displays an adjacent official provider-status reference panel. OpenAI uses the official Statuspage JSON endpoint `https://status.openai.com/api/v2/status.json`; DeepSeek is represented as an official status-page reference through `https://status.deepseek.com/` because it does not expose the same `/api/v2/status.json` contract. Official status is displayed as external context only and does not replace Harness runtime probe evidence. Validation passed Model Settings Vitest (`13 passed`), backend settings tests (`8 passed`), targeted Ruff, frontend lint/build, docs validation, whitespace checks, local API/Console restart, `/health`, Console `/settings/models`, `/api/settings/models/official-status`, and `/api/settings/models/health` smoke checks.
- Model Settings supplier/link cleanup is verified locally on 2026-06-03: top model switch cards no longer display long endpoint URLs or provider/protocol subtitles, configured-model switching uses a two-way switch icon instead of the star icon, provider rows use text-first actions without delete, and visible endpoint/source URLs are clickable. The provider table now merges built-in presets with configured providers so Kimi and Z.AI appear as supplier rows even before keys are configured. Built-in pricing sources now keep only DeepSeek Flash/Pro, OpenAI `gpt-5.5`, Kimi `kimi-k2.6`, and Z.AI `glm-5.1`; Moonshot V1 8K and Z.AI GLM-5-Turbo were removed from frontend/backend source JSON and seed rows, with Alembic `20260610_0037` removing the deprecated rows from databases that had already run the older seed migration. Validation passed Model Settings Vitest, backend model pricing tests, clean SQLite Alembic upgrade to `20260610_0037`, migration-id lint, targeted Ruff, frontend lint/build, docs validation, and whitespace checks.
- Model Settings provider/model-kind polish is verified locally on 2026-06-03: `/settings/models` now groups configured rows by real provider, so DeepSeek appears as one supplier row while listing `deepseek-v4-flash` and `deepseek-v4-pro` as existing models. Model switch cards now use model ids as titles and display model-kind badges such as `文本模型` and `推理模型` without provider/protocol/base URL subtitles. The provider row preserves grouped secret and rate-limit state, hides `missing` secret-source noise, and limits row actions to configure/current/switch behavior. The Model Gateway configured-provider metric now counts grouped suppliers instead of raw model rows. Validation passed targeted Model Settings Vitest, frontend lint, frontend build, docs validation, whitespace checks, and independent reviewer PASS.
- Model Settings clean provider table / DeepSeek Pro pricing is verified locally on 2026-06-03: `/settings/models` now keeps top model switch cards to model id + model kind + action only, the provider table columns are reduced to `供应商 / 现有模型 / 密钥 / 限流 / 操作`, and each `现有模型` cell contains only model id plus model kind. Provider-row delete actions are hidden. DeepSeek Pro official-source metadata now uses the current official `deepseek-v4-pro` prices with `valid_until: null` and `token_tier: all`, so the row remains `已验证` instead of `已过期`. Validation passed targeted Model Settings Vitest (`12 passed`), backend model pricing tests (`6 passed`), targeted Ruff, frontend lint/build, docs validation, whitespace checks, and official DeepSeek pricing page spot-check.
- Model Settings UI / 24-hour time polish is verified locally on 2026-06-03: `/settings/models` now starts with the model-switching card, the Model Gateway summary is visually tighter with smaller metric tiles, built-in pricing rows show muted `不计入汇总` instead of the heavier `USD 汇总已阻塞` copy, and shared frontend timestamps render in 24-hour time. Additional non-shared timestamp formatters in chat run summaries, Team run links, and knowledge management now explicitly use `hour12: false`. Validation passed targeted Model Settings Vitest (`10 passed`), frontend lint, frontend build, docs validation, and whitespace checks.
- User Avatar DB Persistence is verified locally on 2026-06-03: registration/login account state remains database-backed through `users`, `organizations`, and `organization_members`, while JWT access/refresh tokens remain client-held session credentials rather than DB session rows. User avatars now persist on the `users` table through `avatar_mime_type`, `avatar_content`, `avatar_sha256`, and `avatar_updated_at`; `POST /api/auth/me/avatar` accepts PNG/JPEG/WEBP/GIF image content up to 2 MiB, preflights multipart bodies with a 2 MiB + 128 KiB request cap, validates magic bytes, rejects dev-token pseudo users, legacy dev user rows, and API key principals, and returns `avatar_data_url` through `/api/auth/me`. Agent Console shows "上传头像" in the JWT account menu only and prepares selected images as 512px JPEG uploads when browser canvas support is available. Validation passed backend auth tests (`25 passed` after the 413 repair), targeted Ruff, clean Alembic upgrade to `20260609_0036`, frontend auth/avatar tests (`19 passed` targeted after the 413 repair), frontend lint/build, docs validation, whitespace check, local service restart, and a live 600 KiB avatar upload smoke. See [[session-2026-06-03-user-avatar-db-persistence]].
- Frontend Login and Runtime Secret Generation is verified locally on 2026-06-03: Agent Console routes are protected by a login guard that redirects unauthenticated production users to `/login?next=...`, while `/login`, `/register`, and `/oauth/callback` remain public. `GET /api/auth/config` drives registration/OAuth visibility; public registration defaults to enabled in development/test and disabled in production via `AUTH_PUBLIC_REGISTRATION_ENABLED`, and closed registration returns 403 without creating users or organizations. The top-right Console auth entry is now an avatar menu showing name, email, organization, role, and dev-token state; JWT sessions show `退出登录`, while dev-token sessions show `开发令牌会话` and `使用账号登录`. The frontend API client prefers stored JWTs over dev bearer tokens for normal/admin/multipart/chat-stream paths, keeping dev tokens as a development-only fallback, and clears stored tokens when refresh fails after a 401. `scripts/generate-runtime-secrets.py` generates `AUTH_JWT_SECRET`, `HARNESS_SECRET_ENCRYPTION_KEY`, and `HARNESS_SECRET_ENCRYPTION_KEY_ID`; production startup rejects missing/placeholder/short/dev-only encryption keys. Env examples, production/private Compose, Helm Secret/Deployment/Job templates, README, and first-run/deployment runbooks are updated. Validation passed targeted frontend auth/API/menu tests (`22 passed`), backend auth/secret tests (`24 passed`), Ruff, frontend lint/build, env check, compose configs, Helm template, and docs validation. See [[session-2026-06-03-frontend-login-runtime-secret-generation]].
- User Scoped Encrypted Secret Vault V1 is verified locally on 2026-06-03: business integration secrets now persist in encrypted `stored_secrets` rows with user-private precedence, organization-shared fallback, and legacy env fallback only for compatibility. Model provider keys, Dify/Coze/RAGFlow connector secrets, MCP runtime secrets, Tavily/web research keys, and notification webhook/smtp/token fields now resolve through the vault without returning raw values. Agent Console exposes `/settings/secrets` for "my secrets" and "organization shared" views, with organization editing/env import visible only to admins. Validation passed affected backend regression (`102 passed`), Ruff, clean Alembic upgrade to `20260608_0035`, SecretVault/Model Settings Vitest (`10 passed`), frontend lint/build, and frontend/test/security review PASS after fixes. Local Postgres was upgraded to head, local dev services were restarted in tmux sessions `harness-api-langgraph` and `harness-console-langgraph`, API `/health` returned ok, Console root returned HTTP 200, and `GET /api/secrets` returned an empty redacted list for the dev engineer token. Follow-up: existing local DeepSeek env key and legacy Dify/Coze connector keys were imported into `makerhao` / `2429260713@qq.com` as 4 user-scoped active `StoredSecret` rows, with raw values never printed and legacy/env sources left in place for compatibility. See [[session-2026-06-03-user-scoped-encrypted-secret-vault-v1]].
- Product-reference cleanup and history hygiene is verified locally on 2026-06-03: project docs, plans, architecture notes, help copy, OpenAPI projections, tests, and planning-mode names now use Harness-owned language. Current planning mode is `markdown_plan`, legacy clients and historical Team metadata are normalized without publishing old mode strings, and the Team Mode architecture note now describes the Harness product surface directly. Validation passed strict body and filename scans, targeted backend planning/CLI/Team/Eval/Model/Settings regressions, Ruff, targeted frontend Workspace/Team/Eval tests, frontend lint/build, docs validation, and whitespace checks. Local SQLite runtime sidecar files remain untracked and are not part of the commit.
- hao Agent CLI v2 Step 1A is verified locally on 2026-05-31: `SessionStore` now persists an active-leaf tree model, `list_messages()` returns real `parent_id` / `children_ids`, `hao resume` loads only the active path, legacy `hao.db` files receive additive migration/backfill, and targeted v2 tests plus Ruff pass. See [[session-2026-05-31-hao-agent-cli-v2-step-1a]].
- hao Agent CLI v2 Step 1B is verified locally on 2026-06-01: `/chat` `/plan` `/act` now route distinctly through `cli_agent` and `markdown_plan`, `/act` carries explicit `act_intent`, workflow metadata is preserved in local messages and backend local-tool audit, pending-tool approvals freeze target/permission/workflow metadata, and targeted v2 tests plus Ruff pass. See [[session-2026-06-01-hao-agent-cli-v2-step-1b]].
- hao Agent CLI v2 Step 2 is verified locally on 2026-06-01: shell/test/git command execution now persists command lifecycle rows plus `commands.jsonl`, streams output, supports `/cancel` and `/retry`, rejects duplicate terminal transitions, and links local tool events back to command records. See [[session-2026-06-01-hao-agent-cli-v2-step-2]].
- hao Agent CLI v2 Step 3 is verified locally on 2026-06-01: host `write_file` and `apply_patch` now create diff-first pending changes with frozen approval metadata, `commit_*` gates on `change_id` plus hash validation, `/approve` and `/reject` arbitrate `tool-` versus `change-` ids, and targeted v2 tests plus Ruff/docs/diff checks pass. See [[session-2026-06-01-hao-agent-cli-v2-step-3]].
- hao Agent CLI v2 Step 4 is verified locally on 2026-06-01: the TUI workbench now surfaces active leaf/branch, pending approvals, command counts, plan/outputs views, workflow/session commands, sandbox host-safety coverage, and audit fail-closed behavior. See [[session-2026-06-01-hao-agent-cli-v2-step-4]].
- hao Agent CLI v2 Step 5 is verified locally on 2026-06-01: the backend protocol and local audit path now preserve workflow metadata across stream requests, local audit payloads, `ToolCall` snapshots, `AgentEvent` payloads, and local `tool` messages, while `markdown_plan` remains plan-only from the CLI side and host audit failure fails closed. See [[session-2026-06-01-hao-agent-cli-v2-step-5]].
- hao Agent CLI v3 local safety Step 4 is verified locally on 2026-06-01: `.omx/plans/hao-cli-v3-local-agent-safety.md` is marked completed; TUI/headless full-auto and explicit approval commits now apply already-audited pending changes without a second backend audit after workspace mutation; TUI stops the current stream on pending approvals or audit failure; write preview audit failure fails pending changes closed without model-visible tool messages. Validation passed Ruff, v3 subset (`30 passed`), full hao CLI suite (`107 passed`), and two independent subagent approvals.
- hao Agent CLI v4 本地 Agent CLI surface is verified locally on 2026-06-02: the TUI input now has a live slash-command hint menu, `/help` and `/commands` share a filtered command catalog, `/permissions` aliases `/mode`, direct view commands open the workbench, `/model` changes the model recorded on stream payloads, `/context` shows the local context card, `/usage` shows local run counts, `/resume <session_id>` reloads an existing session in-place, and transcript labels now use compact `>` / `hao` markers while preserving raw model-visible tool messages and existing audit/approval safety semantics. Validation passed py_compile, Ruff, full hao CLI regression (`120 passed`), `hao --help`, docs validation, and whitespace checks.
- hao Agent CLI v4.1 本地 Agent CLI follow-up follow-up is verified locally on 2026-06-02: the TUI command catalog now includes `/compact`, `/config` / `/settings`, `/cost` / `/stats`, `/allowed-tools`, `/output-style`, `/tasks` / `/bashes`, and `/todos`; `/compact [instructions]` replaces older active-path messages in the next stream payload with a deterministic local system summary while keeping the latest six messages; `/output-style` writes response-style hints into the local context card; status/config/usage expose compact and style state; output summaries render as terminal-like cards; `docs/cli/hao.md` and Help Center page `安装并使用 hao CLI` document the new command surface. Validation passed py_compile, Ruff, full hao CLI regression (`121 passed` with `.venv/bin` on PATH), `hao --help`, help content check, docs validation, whitespace checks, Agent Console Vite restart at `http://127.0.0.1:5173/` with root and Help markdown returning HTTP 200, and API server startup at `http://127.0.0.1:8000` with temporary local `AUTH_JWT_SECRET` and `/health` returning ok.
- hao Agent CLI v4.2 本地 Agent CLI page is verified locally on 2026-06-02: the default TUI now runs through a Rich terminal loop instead of a full-screen alternate-screen editor shape, no longer renders a default Textual Header/Footer or right-side split pane, and startup copies local Agent CLI's two-column welcome card structure with left `Welcome back!` plus icon/model/cwd and right Tips / What's new. `/tools`, `/diff`, `/files`, `/approvals`, `/outputs`, `/tasks`, `/bashes`, and `/view ...` open a bottom workbench drawer on demand, while tool/approval events remain visible inline when the drawer is closed. `HarnessApiClient` now uses `trust_env=False` so localhost Harness API calls ignore global proxy variables and avoid the missing-SOCKS failure path. Validation passed py_compile, Ruff, full hao CLI regression (`123 passed`), Textual headless smoke, direct `/quit` startup smoke, Help content check, docs validation, whitespace checks, Agent Console Vite restart at `http://127.0.0.1:5173/` with root and Help markdown returning expected content, and API server restart at `http://127.0.0.1:8000` with `/health` ok.
- hao Agent CLI v4.3 本地 Agent CLI footer and compact-ring follow-up is verified locally on 2026-06-02: the startup card and shell footer now show `provider/model · strength ...`, compact ring/percentage/message state, output style, approvals, and command counts; `/compress [instructions]` aliases the existing `/compact [instructions]` active-path summary flow. Model strength is a local display label derived from provider/model text and does not change routing or invent pricing. Validation passed py_compile, focused footer/compact/terminal tests (`12 passed`), full hao CLI regression (`129 passed`), combined hao/tracing regression (`135 passed`), Ruff, direct `/quit` startup smoke showing the footer, `/help compress` smoke, Help content check, docs validation, whitespace checks, and local API/frontend restart with `/health`, root, and Help markdown checks passing.
- hao Agent CLI v4.2 terminal-input follow-up is verified locally on 2026-06-02: the Rich terminal loop now reads stdin bytes directly, decodes UTF-8 with replacement for invalid boundaries, and no longer prints a second user transcript line after the terminal's own echo. The startup-card tips are now real commands: `/init` creates `HAO.md` without overwriting an existing file, and `/release-notes` / `/whats-new` shows hao v4 release notes. Synthetic local context and compact context messages now include backend-compatible `ConversationNode` fields, preventing `/runs/chat/stream` 422 validation failures. Observability tracing now avoids current-context span attach/detach in `traced_operation`, preventing streamed model responses from ending with a contextvars `stream error`. Stream 401/403 failures render concise hao login/permission hints instead of raw httpx/MDN text. Validation passed py_compile, v4.2 focused tests (`6 passed`), focused tracing regression (`2 passed`), full hao CLI regression (`127 passed`), Ruff, Chinese-input startup smoke, Help content check, docs validation, whitespace checks, local API/frontend restart, global `@harness/hao` reinstall, and a bare `hao` smoke from `/Users/luohao/Desktop/unimportant_files` returning assistant text.
- hao Agent CLI npm package is verified locally on 2026-06-01: `services/api-server` now publishes package metadata for `@harness/hao` with global bin `hao`; the launcher runs `uv run --project <package-root> hao ...`, preserves caller cwd, supports `HAO_UV_BIN` / `HAO_PYTHON_PROJECT`, reports `hao --version` from the shared Python package version, accepts documented `hao plan --cwd ...` style subcommand flags, returns non-zero for missing bundled project failures, and a real npm tarball installed into a temporary global prefix executed `<tmp>/bin/hao --help`. The local global npm conflict with `hao@0.2.9` has been removed; bare `hao` starts the installed TUI entrypoint, `hao -v`, `hao -V`, `hao version`, `hao login`, `hao status`, and `hao logout` now work from the global `@harness/hao` bin, and `logout` clears only the persisted token while keeping the persisted API URL. See [[session-2026-06-01-hao-npm-package]]. A Chinese-first Help Center tutorial, `安装并使用 hao CLI`, now lives at `apps/agent-console/public/help/getting-started/hao-cli.md` and documents install, version checks, login/status/logout, TUI launch, and old same-name npm package recovery.
- Agent Knowledge Harness is the current product direction after private deployment. Knowledge/RAG P1 is now a verified baseline in `.omx/reports/agent-knowledge-harness-p1/p1-gate-result-20260516T211017Z.md`, including Docker/private, existing-data migration, exact selector, Eval grounding, append-only audit, backend/frontend/docs/browser, and Agent Run smoke evidence.
- Agent Knowledge Harness P2 local knowledge management is completed and pushed: agent/org-scoped text and Markdown knowledge sources now have lifecycle controls, document-level versioning, stale chunk filtering, retrieval eligibility, lifecycle audit events, failure audit records, multipart `.txt` / `.md` import, Agent Studio management UI, restore smoke coverage, and compose/Postgres private smoke evidence.
- Agent Knowledge Harness P3 real policy-gated web research is completed and pushed through `76f11d5`: Tavily provider adapter, no backend second-hop URL fetch, pre-call and post-result policy gates, DNS/IP URL safety checks, per-run attempt ledger, source-bound web citations, fake-provider hardening, Run Detail evidence, runbook, HTML explanation report, and live Tavily smoke evidence are recorded.
- Agent Knowledge Harness P4 memory and context router V2 is completed and pushed through `6c4a95d`: backend context assembly manifests, long-term memory records, SQL-level scope filtering, token estimator/drop ordering, pinned-message tagging, compressed-summary schema/model/branch/path checks, model-call context binding, shadow/authoritative feature flag behavior, memory injection flags, and Run Detail context manifest projection are implemented and verified.
- Agent Knowledge Harness P5 MCP/Skills productization is completed and pushed through `f05816e`: runtime tool authority is now `CapabilityRegistry -> AgentCapabilityAttachment -> immutable CapabilityVersion -> ToolRunner metadata snapshot`, legacy `Agent.tools_json` is only deterministic migration/seed backfill input with no runtime lazy backfill, ToolRunner fails closed without Agent attachment scope, executing test invocation is agent-scoped, admin validation is non-executing, approval decisions resume or fail runs correctly, console tool cards refresh after approval, and Run/ModelCall/ToolCall/Eval artifacts carry capability snapshot refs/hashes.
- Agent Knowledge Harness P6 groundedness Eval and Observability is completed and pushed through `83c8eee`: Eval now owns `GroundingTraceV1`, forbidden evidence leak judgment, grounding metrics, regression deltas/gates, and failure reasons; Observability has a read-only grounding-quality projection; Run Detail saves objective evidence selectors without inferring required/forbidden snippets or unsupported markers; Eval API responses scrub forbidden snippet payloads.
- Agent Knowledge Harness Eval Dimensions v2 is verified locally on 2026-05-28: Eval now supports optional deterministic `refusal_contract`, `safety_contract`, and `persona_contract` JSON sections, with aggregate metrics, regression gates, per-case UI badges/breakdowns, and preset templates. Validation passed backend Eval tests, Ruff, frontend contract test, lint/build under Node 24, docs validation, and whitespace checks. See [[session-2026-05-28-eval-dimensions-v2]].
- Agent Knowledge Harness Subagent Specialists v1 is verified locally on 2026-05-28: subagents now bind optional specialist templates with role prompts, capability whitelists, structured output schemas, immutable `subagent_outputs`, per-specialist budget guards, deterministic planner/executor routing, and Agent Console `专家库` / Run Detail expert evidence. Validation passed full backend regression (`426 passed`), Ruff, Alembic upgrade/downgrade, frontend target tests/lint/build, docs validation, and whitespace checks. See [[session-2026-05-28-subagent-specialists-v1]].
- Agent Knowledge Harness Subagent Specialists v2 is verified locally on 2026-05-28: specialist plan steps now support bounded fanout metadata, `MAX_SPECIALIST_DEPTH=3` rejects over-nested spawns with audit events, specialist stats/ranking guide multi-candidate keyword selection, Eval can grade `specialist_contract`, and Agent Console surfaces fanout batches, sibling links, specialist performance, and Eval expert-contract metrics. Validation passed targeted backend tests (`55 passed`), full backend regression (`435 passed`), Ruff, frontend target tests, full frontend Vitest (`44 files / 214 tests`), lint/build, docs validation, and whitespace checks. See [[session-2026-05-28-subagent-specialists-v2]].
- Agent Knowledge Harness Subagent Specialists v3 is verified locally on 2026-05-29: specialist selection now has LLM confidence routing with keyword/success-rate fallback and calibration reports; a signed/admin-reviewed specialist marketplace creates org-local specialist copies; dynamic fanout extension is bounded, same-batch checked, and event-backed. Code review fixed verified-listing reapproval, marketplace uninstall historical FK preservation, and calibration task scoping before completion. Validation passed full backend regression (`497 passed`), Ruff, Alembic upgrade to `20260530_0025`, frontend target tests/lint/build, single-fork full frontend Vitest (`48 files / 223 tests`), docs validation, and whitespace checks. See [[session-2026-05-29-subagent-specialists-v3]].
- Agent Knowledge Harness Real Tool Adapters v1 is verified locally on 2026-05-28: ToolRunner/MCPAdapter now dispatch real registry-backed GitHub, Slack, and sandbox file adapters; adapter introspection/health endpoints feed Tool Registry and Tool Configuration schema/try-it UI; ToolCall snapshots carry adapter source and schema hashes. Validation passed targeted backend adapter tests (`73 passed`), full backend regression (`456 passed`), Ruff, targeted frontend adapter/page tests (`13 passed`), full frontend Vitest (`46 files / 219 tests`), lint/build, docs validation, and whitespace checks. No migration files, new tables, or new dependencies were added. See [[session-2026-05-28-real-tool-adapters-v1]].
- Large File Refactor v1 is verified locally on 2026-05-28: the oversized Agent API, Knowledge/RAG, Eval API, TeamPage, and ToolRegistryPage review surfaces were split in five independent pure-refactor commits while preserving public import paths and route/component exports. Validation passed backend target tests (`169 passed`), Ruff, frontend lint/build, TeamPage + ToolRegistryPage tests (`22 passed`), docs validation, whitespace checks, and the split-module line-count gate. See [[session-2026-05-28-large-file-refactor-v1]].
- Agent Knowledge Harness P7 release and demo hardening is completed and pushed to `origin/p7-release-demo-hardening` through `c404603`: deterministic Knowledge/RAG demo seed uses public APIs only and includes an agent grounding support document for the backend `min_hits=2` threshold; service-level migration/restore smoke verifies Knowledge/RAG tables and selector continuity; release browser smoke covers Agent Studio, Workspace, Run Detail, Eval, and Observability demo projections; runbooks now distinguish local fixture evidence from optional credential-gated live provider validation.
- Console Chinese-first selector/terminology hardening is completed and pushed on the same branch through `a5d046b`: shared `MenuSelect` now covers model, knowledge, run, and settings dropdowns with keyboard/focus behavior, grouping, disabled-option skipping, and placement support; required English terms such as MCP, RAG, API, Trace, WarmPool, JSON, Markdown, Prompt, and Provider keep their original names with adjacent small Chinese explanations.
- Dashboard Demo load state sync is verified locally on 2026-05-31: the screenshot mismatch where `一键加载 Demo` produced `Demo 数据已存在` while Dashboard still showed `Demo 数据未加载` was fixed. Dashboard now updates the onboarding query cache from successful Demo load responses, backend Demo loading recognizes existing organization-level Demo artifacts instead of relying only on the caller's user onboarding row, `/api/onboarding/state` reconciles current-user `demo_loaded` / `demo_task_id` from org Demo artifacts on refresh, and Demo reset clears the loaded flag for all org onboarding states. Validation passed backend Demo/onboarding tests, targeted Ruff, Dashboard Vitest, frontend typecheck, and production build. See [[session-2026-05-18-agent-knowledge-p7-release-demo-hardening]].
- P3/P6/P7 AuthN/AuthZ, data lifecycle, and CI/CD release engineering is verified locally on 2026-05-29: real JWT/API-key auth, org-scoped RBAC, user/API-key/audit settings, retention/export/delete management, GitHub Actions release gates, Dependabot, production Dockerfiles, CI compose smoke, release scripts, Helm canary values, and runbooks are implemented. Code review fixed stale JWT/API-key authorization after user or membership removal, export leakage of `password_hash` / `key_hash`, PR whitespace fetch depth, and API Docker healthcheck parsing. Validation passed full backend regression (`518 passed, 2 warnings`), Ruff, Alembic upgrade to `20260604_0031`, frontend lint, single-fork full frontend Vitest (`48 files / 223 tests`), production build plus bundle gate, docs validation, compose config, shell syntax checks, and whitespace checks. See [[session-2026-05-29-auth-retention-cicd]].
- P4/P8 Documentation Help Center and performance/scale foundations are verified locally on 2026-05-29: README, in-app Help Center, 25 help docs, 51 troubleshooting cases, OpenAPI generation, docs CI gate, Redis-first query cache, entity-version invalidation, HMAC-signed cursor pagination, list endpoint coverage, N+1 query instrumentation, lazy routes, cursor Run History, CDN/static asset config, k6 scripts, and performance runbook are implemented. Code review fixed unsigned cursors, stale Agent list cache snapshots after Token Optimizer/capability writes, backend test cache leakage, unsafe specialist calibration caching, and cost-rollup cache/rate-limit semantics. Validation passed full backend regression (`527 passed, 2 warnings`), Ruff, single-fork full frontend Vitest (`49 files / 224 tests`), frontend lint/build/bundle gate, docs/help/API generation, compose config, shell syntax, and whitespace checks. See [[session-2026-05-29-docs-help-performance-scale]].
- Production Critical Hardening v2 is verified locally on 2026-05-30: dev bearer tokens are gated to development/test, `AUTH_JWT_SECRET` is required and placeholder-checked, first-run admin bootstrap plus CLI fallback are implemented, the original legacy dev-admin/dev-engineer seed rows are removed by patch migration, migration id lint is in CI, and production console builds no longer embed dev tokens. Code review fixed frontend JWT/SSE auth gaps, a TypeScript header-name collision, test-mode CORS compatibility, Helm migration Job secret propagation, and legacy seed downgrade safety. Validation passed full backend regression (`538 passed, 2 warnings`), Ruff, Alembic upgrade and downgrade checks, frontend lint, single-fork full frontend Vitest (`49 files / 224 tests`), production build plus bundle gate, compose configs, Helm lint/template on Helm `v4.2.0`, docs validation, and whitespace checks. See [[session-2026-05-30-production-critical-hardening-v2]].
- Full Console interaction audit is verified locally on 2026-05-31: Playwright Chromium exercised the Agent Console shell controls plus visible controls across 37 static/dynamic route pages, including nested dialogs and popovers. The audit passed `38 passed (24.5m)`, with targeted shell and slow-route reruns green, frontend lint and production build passing, and deterministic fixtures covering Tool Registry dialogs, MCP discovery, adapter health/schema payloads, Team context compression, Eval created-dataset routes, and Observability controls while skipping raw operational hrefs that navigate outside the console UI. ChromeDevTools MCP tooling was not exposed in this runtime, so the repo's Playwright Chromium path is the browser automation evidence.
- Console page availability audit is verified locally on 2026-05-30: an isolated API/console stack on `127.0.0.1:18000` / `127.0.0.1:15173` uncovered and fixed a backend blocker where changed built-in capability metadata collided on version `1`; `CapabilityRegistry` now reuses matching hashes or assigns the next capability version number. Playwright Chromium checked 40 real routes with JWT auth and dynamic run/team/subagent/specialist/marketplace IDs, including `/subagents/:id`, and found zero console errors, page errors, request failures, API 5xx responses, route error boundaries, internal error pages, or blank-body states. Backend `test_tool_registry` passed (`34 passed`), Ruff passed, frontend lint and production build passed.
- Workspace viewport and subagent invocation hardening is verified locally on 2026-05-30: the live `127.0.0.1:15173/agents/default/workspace` page now has no document-level vertical or horizontal overflow at `1640x768`, with root/body scroll heights equal to the viewport, while internal chat scrolling remains available. Chinese subagent intent detection now handles `子 Agent` spacing, Chinese synonyms, and follow-up `你现在调用一下` after recent subagent context, routing those requests through auto orchestration instead of local-knowledge fallback. See [[session-2026-05-30-workspace-viewport-subagent-invocation]].
- Enterprise sidebar repair plans are verified locally on 2026-05-30: the three repair plans for sidebar coverage, official-source model pricing gates, Team Mode subagent evidence, and release-smoke regressions were executed. Built-in pricing source rows now cover DeepSeek, OpenAI `gpt-5.5` only, Kimi, Moonshot, and Z.AI with source URL/retrieval/unit/currency/hash metadata; stale OpenAI variants and removed provider-family target rows are absent from the current surface. Observability/Eval require exact source-bound pricing for official models; Team Mode task assignments project into subagent evidence and AdminAuditEvent records. Validation passed targeted backend tests (`23 passed`), Ruff, clean Alembic upgrade to `20260606_0033`, migration-id lint, frontend model/route inventory tests (`7 passed`), frontend lint/build, enterprise pricing/chains Playwright (`8 passed`), release smoke (`49 passed`), and sidebar enterprise smoke (`38 passed`). See [[session-2026-05-30-enterprise-sidebar-audit-repair-plans]].
- OpenAI 5.5-only model display and Chinese Help Center hardening are verified locally on 2026-05-30: Model Settings shows `OpenAI GPT-5.5` as the preset title instead of the internal provider key, the visible OpenAI target has one built-in preset, the model cost table renders pricing modes in Chinese user-facing copy, and Help Center UI/index plus all 25 Markdown documents and 51 troubleshooting cases are Chinese-first. Final review expanded the help gate to block old English help/product phrases such as `Run Detail`, `Prompt Manifest`, `Demo Task`, and `Team Mode` while preserving necessary technical identifiers. Validation passed `ModelSettingsPage.test.tsx` + `HelpCenter.test.tsx` (`5 passed`), targeted backend pricing/settings tests (`20 passed`), frontend lint/build, targeted Ruff, `scripts/check-help-content.py`, `scripts/validate-docs.py`, and `git diff --check`.
- Model Settings layout polish is verified locally on 2026-05-31: `/settings/models` now separates the current default model/provider from six key model-gateway metrics, keeps model switching and custom-provider configuration in responsive cards, contains pricing/fallback/provider tables in horizontal shells, and degrades pricing-source 404 into a Chinese `成本来源暂不可用` state instead of exposing raw `404: Not Found`. Validation passed targeted Model Settings Vitest (`5 passed`), frontend TypeScript lint, production build, Playwright Chromium screenshot checks at `1440x1200` and `390x844`, and the enterprise model-pricing Playwright spec (`3 passed`).
- Model Settings pricing fallback is verified locally on 2026-05-31: when `/api/settings/models/pricing-sources` returns 404 from a stale local backend, `getModelPricingSources()` now falls back to bundled `/model_pricing_sources.json` from the backend official-source dataset, computes stale/blocking status on the client, and renders the built-in pricing table instead of the `成本来源暂不可用` warning. Live Playwright smoke against `127.0.0.1:5177/settings/models` observed pricing API `404`, bundled JSON `200`, visible DeepSeek/OpenAI/Kimi/Z.AI rows, no raw 404 copy, and no document overflow. Validation passed Model Settings Vitest, frontend TypeScript lint, production build, `git diff --check`, and the enterprise model-pricing Chromium spec (`4 passed`).
- Model Settings key-gated switching is verified locally on 2026-05-31: unconfigured built-in providers now show `需配置密钥` / `未配置` and open the shared configuration dialog instead of switching directly, including the edge case where the current default provider itself lacks a usable key; configured providers still support direct `切换`. Custom model configuration is no longer inline on `/settings/models`; the bottom-right quick action exposes `添加自定义模型` and opens the dialog. Validation passed Model Settings Vitest (`7 passed`), frontend lint/build, enterprise model-pricing Chromium spec (`4 passed`), live Playwright smoke on `127.0.0.1:5177/settings/models` with no inline custom form and no horizontal overflow, docs validation, and `git diff --check`.
- Team Mode product surface is verified locally on 2026-05-25: Team Mode now has durable Team/TeamAgent/mailbox/task/event backend state, team CRUD/member/mailbox/task/wake/event APIs, Team frontend routes/list/create/rail/columns/composers, Agent Workspace team launch, and mocked browser smoke coverage.
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

Team Mode product surface and capability product spine:

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
docs/architecture/team-mode-product-surface.md
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
Legacy /plan-md remains a compatibility alias for /plan, but the visible command menu now uses /plan.
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

The latest completed post-stage lane is **Production Critical Hardening v2**, with review fixes and validation recorded in [[session-2026-05-30-production-critical-hardening-v2]].

Follow the replanned progress in [[agent-knowledge-harness-roadmap]]:

- keep groundedness/citation/unsupported-claim Eval and Observability surfaces regression-tested;
- keep Docker Compose release and demo validation current.
- keep deterministic local P7 seed separate from optional credential-gated Tavily/live provider validation.
- keep the shared `MenuSelect` keyboard/focus contract and adjacent small Chinese explanations when adding new selectors or required English terms.
- keep JWT/API-key principal resolution tied to current active users and accepted memberships; do not rely on stale token claims for org authorization.
- keep organization exports redacting credential verifier fields such as `password_hash` and `key_hash`.
- keep cursor tokens signed, query-cache keys organization-scoped and entity-versioned, and Help Center/API docs regenerated when public API surfaces change.
- keep production auth smoke tests on real JWTs and avoid reintroducing production build defaults for dev bearer tokens.

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
- [[session-2026-05-29-auth-retention-cicd]]
- [[session-2026-05-29-docs-help-performance-scale]]
