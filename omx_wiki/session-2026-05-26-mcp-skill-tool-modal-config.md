# MCP Skill Tool Modal Configuration

Category: `session-log`

Tags: `agent-console`, `mcp`, `skills`, `tools`, `modal`, `capability-registry`, `chinese-first`

## Summary

Tool Registry and Agent Studio now keep MCP / Skill / Tool configuration behind click-open modal dialogs instead of exposing configuration forms inline on the default page.

Tool Registry also now has a searchable MCP / Skill marketplace panel. It aggregates Harness curated entries, the official MCP Registry, Smithery MCP servers, and Smithery prompt-based Skills through the backend, then routes selection into existing Harness-safe attach, upload-install, or metadata-only marketplace preflight flows.

The default surfaces now stay focused on scan state:

- Tool Registry metrics, compact marketplace summary, advanced-action buttons, harness tiles, and tool table.
- Agent Studio capability readiness, selected capability summary, and status checks.

## Delivered

- Added shared `ConfigDialog` with `role="dialog"` and `aria-modal="true"` for configuration flows.
- Added shared `FeedbackToastViewport`, success/error/info/warning toast helpers, and a reusable custom confirm dialog so button actions now return consistent in-product feedback instead of browser-native modal UI.
- Tool Registry preset capability cards now open a confirmation dialog with target Agent before enabling.
- Tool Registry advanced configuration opens dialogs for trusted URL install, public URL preflight, Skill upload, package lifecycle, and Agent-scoped test invoke.
- Capability package lifecycle APIs and test-invoke behavior remain unchanged; only the interaction shell moved from inline forms to dialogs.
- Agent Studio capability attachment now renders a compact summary and opens the attach form in a dialog.
- Tests assert configuration inputs are hidden by default and visible only inside the relevant dialog.
- Added `GET /api/tools/capabilities/marketplace` to normalize external marketplace entries into Harness `install_payload` records.
- Tool Registry now shows a compact marketplace summary on the default page and opens the full MCP / Skill market through a dialog.
- Marketplace sources:
  - Harness curated local entries for built-in attach/local install.
  - Official MCP Registry via `https://registry.modelcontextprotocol.io/v0/servers`.
  - Smithery MCP public server search via `https://api.smithery.ai/servers`.
  - Smithery prompt-based Skill search via `https://api.smithery.ai/skills`.
- External entries do not install directly into runtime. They enter metadata-only marketplace preflight or package lifecycle before approval, immutable version creation, Agent attachment, and ToolRunner policy execution.
- Marketplace dialog provides search, MCP/Skill filters, source health badges, a left-side entry list, risk notes, target Agent input, direct attach for built-ins, and a right-side install workbench for external entries.
- The marketplace shell is now Chinese-first for the operator path: heading, search, source labels, install actions, `当前下一步`, quick-test guidance, suggested validation cases, and the visible install-state labels all render in Chinese.
- The install workbench now exposes explicit status chips for `未安装`, `待审批`, `待安装`, and `已安装`, so users can see both current state and next-step intent without reading raw package status codes.
- Marketplace install no longer opens a second install dialog. Users select an item, then complete `登记预检 -> 审批版本 -> 安装到智能体` beside the market list.
- Added `POST /api/tools/capabilities/preflight/marketplace` for registry metadata registration. It does not download, execute, or DNS-resolve the listed homepage/remote URL; approval still creates an immutable capability version and Agent attachment remains the runtime gate.
- The previous 400 `public source resolver returned private, loopback, link-local, or metadata address` is avoided for market entries because homepage/remote URLs are no longer treated as downloadable public package sources. Strict public URL download validation remains unchanged for `/preflight/public-url` and `/packages/public`.
- Repeating the same marketplace preflight is idempotent. The registry reuses the existing `(organization_id, package_key, source_sha256)` package, records `idempotent_preflight`, and avoids duplicate-key 500s.
- Approved marketplace `mcp_server` packages now synthesize executable MCP `tool_metadata` from the manifest when the external registry entry does not include an explicit tool definition.
- Generic marketplace MCP test invoke now returns deterministic Harness smoke output through `mcp-marketplace-adapter`, proving Agent attachment, policy, ToolRunner, ToolCall, event, and snapshot wiring without pretending to call the external provider.
- The market dialog install workbench now includes a direct MCP quick-test section after enable/attach. It derives the tool name from the selected entry or manifest, accepts a query, calls Agent-scoped `test-invoke`, and renders the top result rows inline.
- Tool Registry, Knowledge Management, Agent Workspace, and Team flows no longer use `window.confirm`; confirm-style actions now use the shared custom dialog surface, and button actions provide toast feedback for success/failure.
- The follow-up polish pass extended the same feedback contract to Agent Studio create/clone/capability attach/token plan actions, Team create/member actions, Run Detail replay/approval/eval-save/orchestration actions, Eval dataset/case/run/baseline actions, Sandboxes benchmark start, and Subagents bulk/single cancel actions.
- The next follow-up closed the remaining drift risk around Agent Workspace and Knowledge Management: creating a Team from the current conversation now shows explicit success/failure feedback, knowledge source create/edit/add-document/reingest actions now show explicit success/failure feedback, and Team send failures now surface a toast instead of only implicit stalled UI.
- Browser-native `confirm/alert/prompt` calls are no longer used under `apps/agent-console/src`; the remaining `confirm(...)` callsites now route through the shared custom confirm dialog helper.
- Added browser smoke coverage for the cross-page feedback pass: `agent-workspace`, `agent-studio-feedback`, `run-detail`, `sandboxes-page`, `eval-page`, and `subagents-feedback`, alongside the existing Tools and Team smoke cases.
- Agent Workspace `SearchOverlay` and `ShortcutOverlay` now use the same backdrop/close affordance language as the shared dialog system, and the workspace tool popover now stays inside the mobile viewport by anchoring to the right edge.
- Workspace Chat now recognizes model-emitted XML-style tool-call blocks such as `<function_calls><invoke name="brave_web_search">...` in normal chat responses. The backend strips the raw block from visible assistant output, resolves aliases such as `brave_web_search` through the current Agent's enabled MCP registry, executes the installed MCP through `CapabilityRegistry -> ToolRunner`, and then asks the model for a final Chinese answer grounded in the tool result.
- XML-triggered MCP execution stays scoped to already attached Agent capabilities. Unknown or unattached tool names still use the existing failed-tool feedback path, and markdown planning mode does not gain a new direct MCP execution bypass.
- Follow-up hardening now prevents the observed bad answer shape where the MCP request succeeds but the final assistant says it cannot view the returned search results. Successful MCP `items` are summarized by the backend and forced into the visible Workspace answer when the follow-up model answer omits them or uses evasive `无法直接查看...` wording.
- The later pending-search hardening handles the screenshot case where the model only says `正在搜索“MCP教程”，请稍等。` and emits no XML function-call block. In that case the backend selects the current Agent's installed low-risk idempotent search MCP, emits `tool_call_requested` and `tool_call_result`, and does not send final `done` until the MCP result summary has been rendered.
- Runtime restart verification on 2026-05-27 moved the API to tmux session `harness-api-mcp-restart`, confirmed `GET /health` on `127.0.0.1:8000`, confirmed `GET /api/tools/registry?agent_id=default` contains installed `brave`, and ran live Workspace Chat Brave smoke `ddb08a1d-9748-4222-a325-f17cdcc9ebb8` with event order `run_created -> tool_call_requested(running) -> tool_call_result(success) -> delta -> done`.
- Installed MCP runtime configuration is now a first-class page at `/tools/config`, linked from the sidebar as `工具配置` and from `/tools` as `运行配置`.
- The configuration page lists Agent-scoped installed MCPs and shows clear Chinese status badges for `已配置 / 未配置 / 缺少密钥`, registry visibility, and saved-secret state.
- Runtime config supports HTTP, SSE, and stdio fields. Brave Search defaults to `https://api.search.brave.com/res/v1/web/search` and exposes a one-time `替换 API Key` input that is saved through backend secret storage and never echoed.
- Backend runtime config saves by creating a new immutable `CapabilityVersion`, repointing the active Agent attachment, and keeping raw secret material out of `config_json` and API responses.
- `ToolRunner` now passes active capability `config_json` plus resolved server-side secret to `MCPAdapter`; configured Brave calls the live Brave Search API with `X-Subscription-Token`, while unconfigured marketplace MCPs return explicit Harness smoke output.
- `/tools/config` includes a visible `运行案例测试` path; successful Brave live-provider output renders result rows and a `真实 Brave API` badge instead of a vague completed status.
- Runtime configuration listing deduplicates same-name MCP attachments by priority/order and the React selection state uses `attachment_id`, so repeated Brave installs no longer create unstable duplicate rows in the config list.

## Validation

```text
cd services/api-server && uv run pytest tests/test_tool_registry.py -q
28 passed

cd services/api-server && uv run pytest tests/test_tool_registry.py::test_capability_marketplace_aggregates_mcp_and_skill_sources tests/test_tool_registry.py::test_marketplace_preflight_registers_metadata_without_public_source_resolution -q
2 passed

cd services/api-server && uv run ruff check app tests
passed

cd services/api-server && uv run ruff check app/tools/marketplace.py app/api/tools.py tests/test_tool_registry.py
passed

cd services/api-server && uv run ruff check app/tools/capabilities.py app/tools/marketplace.py app/api/tools.py tests/test_tool_registry.py
passed

cd services/api-server && uv run pytest tests/test_tool_registry.py::test_marketplace_mcp_package_can_be_attached_and_test_invoked -q
1 passed

cd services/api-server && uv run pytest tests/test_tool_registry.py -q
29 passed

cd services/api-server && uv run ruff check app/tools/capabilities.py app/tools/mcp_adapter.py tests/test_tool_registry.py
passed

cd apps/agent-console && npm test -- ToolRegistryPage.marketplace.test.tsx
2 tests passed

cd apps/agent-console && npm run lint -- --pretty false
passed

cd apps/agent-console && npm run build
passed, with existing Vite chunk-size warning

cd apps/agent-console && npm test -- src/features/tools/__tests__/ToolRegistryPage.marketplace.test.tsx src/features/agents/__tests__/KnowledgeManagementPanel.render.test.tsx src/features/agents/__tests__/ChatSurface.shell.test.tsx
3 files / 31 tests passed

cd services/api-server && uv run pytest tests/test_tool_registry.py -q
29 passed

cd apps/agent-console && npm run lint -- --pretty false
passed

cd apps/agent-console && npm run build
passed, with existing Vite chunk-size warning

HARNESS_PLAYWRIGHT_EXTERNAL_SERVER=1 npx playwright test --project=chromium e2e/tools-page.smoke.spec.ts
6 passed against local Vite server `http://127.0.0.1:5177`

cd apps/agent-console && npm test -- ToolRegistryPage.marketplace.test.tsx
2 tests passed

cd apps/agent-console && npm test -- AgentListPage.studio.test.tsx
2 tests passed

cd apps/agent-console && npm test -- ToolRegistryPage AgentListPage
2 files / 4 tests passed

cd apps/agent-console && npm run lint -- --pretty false
passed

cd apps/agent-console && npm run build
passed, with existing Vite chunk-size warning

HARNESS_PLAYWRIGHT_BASE_URL=http://127.0.0.1:5174 HARNESS_PLAYWRIGHT_EXTERNAL_SERVER=1 npx playwright test --project=chromium e2e/tools-page.smoke.spec.ts
4 passed

cd apps/agent-console && npm test -- src/features/agents/__tests__/AgentListPage.studio.test.tsx src/features/teams/__tests__/TeamPages.test.tsx src/features/settings/pages/__tests__/ModelSettingsPage.test.tsx src/features/runs/pages/__tests__/RunDetailPage.optimizer.test.tsx
4 files / 23 tests passed

cd apps/agent-console && npm test -- src/features/agents/__tests__/KnowledgeManagementPanel.render.test.tsx src/features/agents/__tests__/ChatSurface.shell.test.tsx src/features/agents/__tests__/AgentListPage.studio.test.tsx src/features/teams/__tests__/TeamPages.test.tsx src/features/settings/pages/__tests__/ModelSettingsPage.test.tsx src/features/runs/pages/__tests__/RunDetailPage.optimizer.test.tsx
6 files / 52 tests passed

cd apps/agent-console && HARNESS_PLAYWRIGHT_EXTERNAL_SERVER=1 npx playwright test --project=chromium e2e/agent-workspace.smoke.spec.ts e2e/agent-studio-feedback.smoke.spec.ts
7 passed against local Vite server `http://127.0.0.1:5177`

cd apps/agent-console && HARNESS_PLAYWRIGHT_EXTERNAL_SERVER=1 npx playwright test --project=chromium e2e/tools-page.smoke.spec.ts e2e/team-mode.smoke.spec.ts e2e/agent-studio-feedback.smoke.spec.ts e2e/run-detail.smoke.spec.ts e2e/sandboxes-page.smoke.spec.ts e2e/eval-page.smoke.spec.ts e2e/subagents-feedback.smoke.spec.ts
33 passed against local Vite server `http://127.0.0.1:5177`

cd apps/agent-console && HARNESS_PLAYWRIGHT_EXTERNAL_SERVER=1 npx playwright test --project=chromium e2e/agent-workspace.smoke.spec.ts e2e/agent-studio-feedback.smoke.spec.ts e2e/team-mode.smoke.spec.ts e2e/tools-page.smoke.spec.ts e2e/run-detail.smoke.spec.ts e2e/sandboxes-page.smoke.spec.ts e2e/eval-page.smoke.spec.ts e2e/subagents-feedback.smoke.spec.ts
38 passed against local Vite server `http://127.0.0.1:5177`

rg -n "window\\.(alert|confirm|prompt)|\\b(alert|confirm|prompt)\\(" apps/agent-console/src
only shared custom confirm helper callsites remained; no browser-native modal calls

python3 scripts/validate-docs.py
docs validation passed

cd services/api-server && uv run pytest tests/test_tool_registry.py::test_mcp_runtime_config_creates_new_version_and_live_brave_test -q
1 passed

cd services/api-server && uv run pytest tests/test_tool_registry.py -q
32 passed

cd services/api-server && uv run ruff check app/api/tools.py app/api/schemas.py app/tools/capabilities.py app/tools/mcp_adapter.py app/tools/runner.py tests/test_tool_registry.py
passed

cd apps/agent-console && npm test -- src/features/tools/__tests__/ToolRegistryPage.marketplace.test.tsx src/features/tools/__tests__/ToolConfigurationPage.test.tsx
2 files / 4 tests passed

cd apps/agent-console && npm run lint -- --pretty false
passed

cd apps/agent-console && npm run build
passed, with existing Vite chunk-size warning

cd apps/agent-console && npx playwright test --project=chromium e2e/tools-page.smoke.spec.ts
7 passed, including runtime configuration page save/test case

python3 scripts/validate-docs.py
docs validation passed

git diff --check
passed

cd services/api-server && uv run pytest tests/test_agents.py::test_agent_workspace_chat_executes_xml_function_call_for_installed_mcp -q
1 passed

cd services/api-server && uv run pytest tests/test_agents.py::test_agent_workspace_pro_chat_mode_executes_list_files_tool_mention tests/test_agents.py::test_agent_workspace_chat_executes_xml_function_call_for_installed_mcp tests/test_agents.py::test_agent_workspace_pro_chat_mode_keeps_side_effect_tool_pending_approval tests/test_tool_registry.py::test_marketplace_mcp_package_can_be_attached_and_test_invoked -q
4 passed

cd services/api-server && uv run ruff check app/api/agents.py tests/test_agents.py app/tools/mcp_adapter.py tests/test_tool_registry.py
passed

python3 -m py_compile services/api-server/app/api/agents.py services/api-server/tests/test_agents.py
passed

cd services/api-server && uv run pytest tests/test_agents.py::test_agent_workspace_chat_infers_installed_mcp_from_pending_search_text -q
1 passed; regression verifies pending text `正在搜索“MCP教程”，请稍等。` triggers installed `brave`, and event order is `tool_call_requested -> tool_call_result -> delta -> done`.

cd services/api-server && uv run pytest tests/test_agents.py::test_agent_workspace_chat_executes_xml_function_call_for_installed_mcp tests/test_agents.py::test_agent_workspace_chat_infers_installed_mcp_from_pending_search_text -q
2 passed

cd services/api-server && uv run pytest tests/test_agents.py::test_agent_workspace_pro_chat_mode_executes_list_files_tool_mention tests/test_agents.py::test_agent_workspace_chat_executes_xml_function_call_for_installed_mcp tests/test_agents.py::test_agent_workspace_chat_infers_installed_mcp_from_pending_search_text tests/test_agents.py::test_agent_workspace_pro_chat_mode_keeps_side_effect_tool_pending_approval tests/test_tool_registry.py::test_marketplace_mcp_package_can_be_attached_and_test_invoked -q
5 passed

cd services/api-server && uv run ruff check app/api/agents.py tests/test_agents.py app/tools/mcp_adapter.py tests/test_tool_registry.py
passed

python3 -m py_compile services/api-server/app/api/agents.py services/api-server/tests/test_agents.py
passed

cd services/api-server && uv run pytest tests/test_agents.py::test_agent_workspace_chat_executes_xml_function_call_for_installed_mcp -q
1 passed; regression now simulates the model saying it cannot directly view Brave results and verifies the final SSE contains `brave MCP result 1` instead of that failure wording.

cd services/api-server && uv run pytest tests/test_agents.py::test_agent_workspace_pro_chat_mode_executes_list_files_tool_mention tests/test_agents.py::test_agent_workspace_chat_executes_xml_function_call_for_installed_mcp tests/test_agents.py::test_agent_workspace_pro_chat_mode_keeps_side_effect_tool_pending_approval tests/test_tool_registry.py::test_marketplace_mcp_package_can_be_attached_and_test_invoked -q
4 passed

cd services/api-server && uv run ruff check app/api/agents.py tests/test_agents.py app/tools/mcp_adapter.py tests/test_tool_registry.py
passed

python3 -m py_compile services/api-server/app/api/agents.py services/api-server/tests/test_agents.py
passed

git diff --check
passed

curl --noproxy '*' -i -sS -m 20 'http://127.0.0.1:8000/api/tools/capabilities/marketplace?kind=all&limit=2' -H 'Authorization: Bearer dev-engineer-token'
HTTP 200

curl --noproxy '*' -i -sS -m 20 'http://127.0.0.1:5174/api/tools/capabilities/marketplace?kind=all&limit=2' -H 'Authorization: Bearer dev-engineer-token'
HTTP 200

Repeated live Brave Search marketplace preflight against `http://127.0.0.1:8000/api/tools/capabilities/preflight/public-url`
HTTP 201 twice, both responses reused staged package `eb7766ea-806c-45ef-b591-e1c39c480d75`

Live marketplace metadata preflight against `http://127.0.0.1:8000/api/tools/capabilities/preflight/marketplace`
with `source_uri=https://localhost/internal-mcp`
HTTP 201, `source_kind=marketplace_preflight`, `source_resolution=registry_metadata_only_no_url_fetch`, `no_source_download=true`; the smoke package was uninstalled afterward.

Live Brave Search installed-tool smoke against `http://127.0.0.1:8000/api/tools/capabilities/test-invoke`
with `agent_id=default`, `tool_name=brave`, and `{"query":"OpenAI latest news","limit":3}`
HTTP 202, `tool_call.status=SUCCESS`, `capability_version_id=brave-9693b089e19e2135-3e429fc2`, `mcp_server=brave`, `mcp_method=search`, and result source `mcp-marketplace-adapter`.

cd apps/agent-console && npm test -- ToolRegistryPage.marketplace.test.tsx
3 tests passed

cd apps/agent-console && npm test -- TeamPages.test.tsx
19 tests passed

cd apps/agent-console && npm run lint -- --pretty false
passed

cd apps/agent-console && npm run build
passed, with existing Vite chunk-size warning

cd services/api-server && uv run pytest tests/test_tool_registry.py -q
29 passed

cd services/api-server && uv run ruff check app/tools/capabilities.py app/tools/mcp_adapter.py app/tools/marketplace.py app/api/tools.py app/api/schemas.py tests/test_tool_registry.py
passed

cd apps/agent-console && HARNESS_PLAYWRIGHT_BASE_URL=http://127.0.0.1:5177 HARNESS_PLAYWRIGHT_EXTERNAL_SERVER=1 npx playwright test --project=chromium e2e/tools-page.smoke.spec.ts
6 passed

cd apps/agent-console && HARNESS_PLAYWRIGHT_BASE_URL=http://127.0.0.1:5177 HARNESS_PLAYWRIGHT_EXTERNAL_SERVER=1 npx playwright test --project=chromium e2e/agent-studio-feedback.smoke.spec.ts e2e/subagents-feedback.smoke.spec.ts
7 passed

cd apps/agent-console && HARNESS_PLAYWRIGHT_BASE_URL=http://127.0.0.1:5177 HARNESS_PLAYWRIGHT_EXTERNAL_SERVER=1 npx playwright test --project=chromium e2e/tools-live-marketplace.spec.ts
2 passed

Live `mcp_context_search` case through `POST /api/tools/capabilities/test-invoke`
`tool_call.status=SUCCESS` with query `发布准备情况`, limit 2, and 2 `Context match` rows.

Live installed Brave case through `POST /api/tools/capabilities/test-invoke`
`tool_call.status=SUCCESS` with query `OpenAI 最新动态`, limit 3, and 3 `brave MCP result` rows.

Live `conservative-token-saver` Skill runtime case through Workspace Chat
Run `85a1227c-cbc5-47c6-ac08-6269d5774460`, context manifest `a4ca6f42-ef41-4101-b505-fa97b01e107a`, `optimizer_applied` for `conservative-token-saver-c43094e1d97c9126-2ec8d5c3`, `pruning_applied=true`, and `estimated_saved_tokens=1382`.

cd apps/agent-console && HARNESS_PLAYWRIGHT_BASE_URL=http://127.0.0.1:5177 HARNESS_PLAYWRIGHT_EXTERNAL_SERVER=1 npx playwright test --project=chromium e2e/tools-live-marketplace.spec.ts e2e/tools-page.smoke.spec.ts e2e/agent-studio-feedback.smoke.spec.ts e2e/subagents-feedback.smoke.spec.ts e2e/team-mode.smoke.spec.ts e2e/run-detail.smoke.spec.ts e2e/sandboxes-page.smoke.spec.ts e2e/eval-page.smoke.spec.ts e2e/observability.smoke.spec.ts e2e/knowledge-demo.smoke.spec.ts
45 passed

cd apps/agent-console && npm test -- ToolRegistryPage.marketplace.test.tsx TeamPages.test.tsx
2 files / 22 tests passed

cd apps/agent-console && npm run lint -- --pretty false
passed

cd apps/agent-console && npm run build
passed, with existing Vite chunk-size warning

cd services/api-server && uv run pytest tests/test_tool_registry.py -q
29 passed

cd services/api-server && uv run ruff check app/tools/capabilities.py app/tools/mcp_adapter.py app/tools/marketplace.py app/api/tools.py app/api/schemas.py tests/test_tool_registry.py
passed

GET http://127.0.0.1:8000/api/tools/capabilities/marketplace?kind=all&limit=5
returned ready sources: `平台推荐`, `官方 MCP 注册表`, `Smithery MCP 服务库`, `Smithery 技能库`

Live `mcp_context_search` case through `POST /api/tools/capabilities/test-invoke`
with `input_json={"query":"发布准备情况","limit":2}` returned `tool_call.status=SUCCESS`, 2 rows, and snippets containing `发布准备情况`.

Live installed `brave` case through `POST /api/tools/capabilities/test-invoke`
with `input_json={"query":"OpenAI 最新动态","limit":3}` returned `tool_call.status=SUCCESS`, 3 `brave MCP result` rows, and snippets containing `OpenAI 最新动态`.

rg -n "window\\.(alert|confirm|prompt)|\\b(alert|confirm|prompt)\\(" apps/agent-console/src apps/agent-console/e2e
only shared custom confirm helper callsites remained; no browser-native modal calls.
```

## Notes

- Runtime capability authority remains `CapabilityRegistry -> AgentCapabilityAttachment -> CapabilityVersion -> ToolRunner`.
- The latest browser smoke intentionally exercises hand-written operator cases instead of only static render checks: trusted/public/upload install flows, direct built-in MCP enable, external MCP `登记预检 -> 审批版本 -> 安装到智能体 -> 一键测试`, and external Skill `登记预检 -> 审批版本 -> 安装到智能体`.
- The official MCP Registry and Smithery market sources were checked on 2026-05-26. MCP has a direct public REST registry shape; Smithery has public `/servers` and `/skills` APIs. Both are treated as discovery sources, not trusted runtime authority.
- A live 404 on the marketplace API was caused by the old local API process still running on `127.0.0.1:8000`; restarting the API loaded the route.
- A follow-up 500 was caused by local SOCKS proxy environment variables and missing `socksio`; marketplace outbound HTTP now uses `trust_env=False`, so the endpoint returns local curated entries and source health instead of crashing.
- A later preflight 500 was caused by repeated inserts for the same external package. `_stage_package` now checks the org/package/source hash first and returns the existing package for repeat preflight.
- A later preflight 400 was caused by sending marketplace homepage/remote URLs through the public source resolver. Market entries now use `marketplace_preflight`, which registers source metadata only and avoids private/loopback resolver checks unless the user explicitly chooses public URL download preflight.
- A Brave test-invoke failure was caused by approved marketplace `mcp_server` packages lacking `tool_metadata`; `CapabilityRegistry` now synthesizes metadata from `package_manifest` for both new versions and existing approved rows, so installed Brave resolves as `tool_name=brave`.
- The current Brave smoke validates Harness capability wiring only. Real Brave Search API results still require a configured external MCP/Smithery runtime and credentials.
- For a more visual operator path, use Tools -> `打开市场` -> select Brave/Search -> complete enable/install -> use the right-side `快速测试` query box and `一键测试`. The older `高级包管理` -> `测试调用` dialog remains available for arbitrary tool names and raw JSON payloads.
- Chat/workspace tool pickers were already popover/dialog based and were not changed.
- The broader 2026-05-27 follow-up intentionally used browser-level mocked smoke instead of only component tests so each feedback path could be exercised through real clicks, visible dialogs, and visible success toasts.
- The anti-drift 2026-05-27 follow-up specifically rechecked Agent Workspace and Knowledge Management so the task did not narrow to `/tools` alone; the browser suite now exercises Chinese-first feedback through store, workspace, studio, team, run detail, eval, sandbox, and subagent routes.
- The final 2026-05-27 viewport fix moved the shared Agent Workspace bottom popover to column-bounded inset sizing on narrow screens, so `输入设置` and `切换模型` stay fully inside the visible viewport even when the collapsed shell and history rail remain on screen.
- The final Team smoke follow-up also aligned the created-team leader column assertion to the live Chinese-first naming path (`队长 队长 列`), while the default fixture still verifies the mixed `Leader 队长 列` path on mobile.
- A later 2026-05-27 sweep localized more high-visibility labels outside `/tools`: Agent Studio now shows `智能体 ID`, `创建智能体`, and `克隆当前智能体`; the Team rail header now shows `团队`; and Knowledge Management now renders `已启用 / 健康 / 智能体或组织 / N 个分块` instead of raw `ACTIVE / HEALTHY / agent|org / chunks`.
- The same sweep refreshed older browser smoke to the current product contract: knowledge-management cases now open dialogs before asserting form fields, Workspace success/nav/demo cases now mock same-origin SSE routes on `127.0.0.1:5177`, and run-detail link assertions now target the shell-bar `aria-label="运行详情"` link instead of ambiguously matching both visible run-detail links.
- Fresh browser evidence after that update: `HARNESS_PLAYWRIGHT_EXTERNAL_SERVER=1 npx playwright test --project=chromium e2e/agent-workspace.smoke.spec.ts e2e/agent-workspace-success.smoke.spec.ts e2e/agent-studio.smoke.spec.ts e2e/agent-studio-feedback.smoke.spec.ts e2e/team-mode.smoke.spec.ts e2e/tools-page.smoke.spec.ts e2e/run-detail.smoke.spec.ts e2e/sandboxes-page.smoke.spec.ts e2e/eval-page.smoke.spec.ts e2e/subagents-feedback.smoke.spec.ts e2e/observability.smoke.spec.ts e2e/knowledge-demo.smoke.spec.ts e2e/nav-resilience.spec.ts` passed with 53/53 Chromium cases on `http://127.0.0.1:5177`.
- A later 2026-05-27 follow-up finished the remaining Chinese-first gaps in the store and audit surfaces: Tool Registry now uses `目标智能体 / 安装到智能体 / 已启用到目标智能体 / 已安装到目标智能体`, Run Detail now localizes the grounding/context/token/model-call audit labels such as `依据来源 / 上下文优化器 / 已省标记 / 哈希审计`, and Observability now shows `依据质量 / 已省标记 / 实际标记 / 低成本路由 / 后备不一致率 / 不支持标记率`.
- Fresh focused browser evidence after that follow-up: `HARNESS_PLAYWRIGHT_EXTERNAL_SERVER=1 npx playwright test --project=chromium e2e/tools-page.smoke.spec.ts e2e/run-detail.smoke.spec.ts e2e/observability.smoke.spec.ts e2e/knowledge-demo.smoke.spec.ts` passed with 26/26 Chromium cases on `http://127.0.0.1:5177`, and the broader 53-case non-live Chromium suite was rerun afterward with 53/53 passing again.
- The latest 2026-05-27 follow-up finished the remaining raw enum exposure inside Run Detail and the global shell chrome: Run Detail now maps `COMPLETED / PLAN_CREATED / TOOL_CALL / local_knowledge / local_evidence_sufficient / seed_fixture_local_evidence / knowledge_chunk / selected_for_prompt / recomputable_v2 / authoritative / available / sufficient / chars_div_4` into Chinese-first display values such as `已完成 / 计划已创建 / 工具调用 / 本地知识库 / 本地证据充足 / 演示夹具本地证据 / 知识分块 / 已纳入提示词 / 可复算 v2 / 权威组装 / 可用 / 证据充足 / 字符数/4`.
- The same follow-up also converted remaining high-visibility shell wording from mixed English to Chinese-first: Console Shell brand text now shows `运行平台`, the `/token-savings` navigation and page title now show `标记节省`, and Run History replaces the `Harness` table header with `运行平台`.
- Fresh validation after that follow-up: `npm test -- src/features/runs/pages/__tests__/RunDetailPage.helpers.test.ts src/features/runs/pages/__tests__/RunDetailPage.optimizer.test.tsx` passed with 4/4 tests, `npm test -- src/features/observability/pages/__tests__/TokenSavingsPage.test.tsx` passed with 1/1 test, `HARNESS_PLAYWRIGHT_EXTERNAL_SERVER=1 npx playwright test --project=chromium --headed e2e/run-detail.smoke.spec.ts` passed with 13/13 Chromium cases, and the full 53-case Chromium regression suite passed again afterward.
- The latest 2026-05-27 store-label cleanup finished the remaining mixed English source labels and novice-facing store copy: marketplace sources now display `平台推荐 / 官方 MCP 注册表 / Smithery MCP 服务库 / Smithery 技能库`, Smithery risk notes now say `平台预检` instead of `Harness 预检`, and the built-in recommendation cards now use `智能体 / 技能` Chinese wording in their descriptions and risk notes instead of `Agent / Skill`.
- Fresh validation after that store-label cleanup: `cd services/api-server && uv run pytest tests/test_tool_registry.py -q` passed with 29/29 tests, `cd apps/agent-console && npm test -- src/features/tools/__tests__/ToolRegistryPage.marketplace.test.tsx` passed with 2/2 tests, `HARNESS_PLAYWRIGHT_EXTERNAL_SERVER=1 npx playwright test --project=chromium --headed e2e/tools-page.smoke.spec.ts` passed with 6/6 Chromium cases, and the full 53-case Chromium regression suite passed again afterward.
- The latest completion pass made marketplace install-state detection null-safe for legacy or partial Agent attachments. The observed failure was a mocked direct-enable attachment with `capability_version_id: null`; the UI now guards string-prefix checks so successful attachment writes cannot crash the route before the success toast renders.
- Live marketplace browser evidence now covers both desktop and mobile: the real-backend spec opens `MCP / 技能商店`, verifies the custom dialog path, runs `上下文搜索` with `发布准备情况`, runs Brave with `OpenAI 最新动态`, installs `保守上下文优化`, sees success feedback, and checks the 390px mobile dialog has no horizontal overflow.
- Concrete MCP validation now includes two direct API cases: `mcp_context_search` returned 2 context rows for `发布准备情况`, and installed `brave` returned 3 deterministic MCP smoke rows for `OpenAI 最新动态`.
- Concrete Skill validation now uses runtime context assembly evidence instead of only an installed badge: Workspace Chat run `85a1227c-cbc5-47c6-ac08-6269d5774460` applied `conservative-token-saver-c43094e1d97c9126-2ec8d5c3`, omitted 4 refs for `optimizer_budget`, and reported 1382 estimated saved tokens.
- The final completion audit reran the real-backend Tools live marketplace spec plus the cross-page feedback browser suite with 45/45 Chromium cases passing on `http://127.0.0.1:5177`.
- The final direct MCP API audit used the correct `input_json` request field, so the recorded context-search and Brave cases prove query/limit propagation rather than only default empty-input behavior.
- The final test maintenance pass fixed two stale test assertions without changing product UI: Eval now uses a unique `选择评测智能体：默认智能体` role selector, Run Detail now asserts the current `计划 / 依赖图` wording, and Team branch switching waits for the accessible `分支 N/2` label after async updates.
- The latest registry follow-up fixes the installed-MCP visibility gap. `GET /api/tools/registry?agent_id=default` now uses `CapabilityRegistry.tool_registry_for_agent`, so the unified registry reflects the selected target agent's enabled attachments instead of the static default registry.
- The Tool Registry page now queries `["tool-registry", simpleAgentId]`, refreshes the registry after install/attach success, and labels the table as the current target agent's enabled tools.
- Capability attachment listing now filters attachment and capability organization before runtime resolution, so org-scoped marketplace MCP attached to a global default agent is visible to its org and hidden from a different org.
- Fresh evidence after API restart on `127.0.0.1:8000`: `GET /api/tools/registry?agent_id=default` returned installed `brave` and `gmail` rows for `dev-engineer-token`; the same request with `dev-other-org-token` did not return those org-scoped MCP rows.
- Fresh validation: `cd services/api-server && uv run pytest tests/test_tool_registry.py -q` passed with 31/31 tests, `cd services/api-server && uv run ruff check app tests` passed, `cd apps/agent-console && npm test -- ToolRegistryPage.marketplace.test.tsx` passed with 3/3 tests, `cd apps/agent-console && npm run lint -- --pretty false` passed, `HARNESS_PLAYWRIGHT_BASE_URL=http://127.0.0.1:5177 HARNESS_PLAYWRIGHT_EXTERNAL_SERVER=1 npx playwright test --project=chromium e2e/tools-page.smoke.spec.ts` passed with 6/6 cases, and the live marketplace spec passed with 2/2 cases.
- The slash command follow-up adds `/mcp` with alias `plugins` to the shared command registry. Agent Workspace opens the `可用 MCP` popover from `/mcp`, auto-expands `插件 / MCP`, shows success/empty-state toast feedback, and inserts `@工具名` when a listed MCP tool is clicked.
- Agent Workspace now fetches `GET /api/tools/registry?agent_id=<agentId>` for the chat tool list, and Team Mode fetches the registry per member `agent_id`, so installed MCP attachments are visible in the current Agent or column instead of depending on the global registry.
- Browser smoke fixtures now fail fast when `/api/tools/registry` is requested without `agent_id=default`; fresh Chromium evidence passed for Agent Workspace `/mcp` menu -> `可用 MCP` -> `@github_search` insertion and for Team Mode desktop/mobile smoke.
- Fresh slash-command validation: local Vitest binary ran `slashCommands.property.test.ts` plus `ChatSurface.shell.test.tsx` with 33/33 tests passing; `pnpm --filter agent-console lint`, `pnpm --filter agent-console build`, `./node_modules/.bin/playwright test --project=chromium e2e/agent-workspace.smoke.spec.ts`, `./node_modules/.bin/playwright test --project=chromium e2e/team-mode.smoke.spec.ts`, and `git diff --check` all passed.
