# Local Agent Offline Bridge Run Recovery

Category: `session-log`

Tags: `local-agent`, `agent-workspace`, `recovery`, `bridge`, `validation`

## Summary

Agent Workspace `恢复` no longer stops at a frontend refresh when a local Agent bridge is still offline. It now generates an inline `hao bridge run` recovery command for the existing confirmed connection, so the user can restart the same bridge from Workspace and keep queued messages attached to the current connection.

Follow-up: HAO/Codex local tool approvals are now surfaced explicitly in Workspace. A pending local approval no longer looks like an indefinitely running local Agent turn.

Follow-up: approving from Run Detail no longer fails when HAO requests another local tool with the same model `tool_call_id` after an approved tool result.

Follow-up: HAO local Agent chat no longer treats bridge instructions and workspace context as the user goal, and backend local mock model output is rejected before it can appear as an assistant reply.

## Evidence

- `services/api-server/app/api/agents/agent_local.py` exposes `GET /api/agents/local-agent/connections/{connection_id}/recovery-command` for confirmed owner/admin connections.
- The recovery command uses the same npx package and registry resolution as pairing, but runs `bridge run --connection-id ... --adapter ... --daemon` instead of creating a new pairing token.
- The command does not include the stored local Agent device token.
- Multi-adapter default Agent Studio connections default `HAO_HOME` to adapter-scoped state such as `$HOME/.hao/bridges/hao`, so recovery reuses the saved local bridge state.
- `hao bridge run --daemon` is now supported by the CLI; it starts from the Python project root, keeps the device token out of argv, and writes daemon output to `HAO_HOME/bridge-daemon.log` instead of silently discarding startup failures.
- The bridge now accepts `adapter_heartbeat` events. The CLI emits best-effort task heartbeats while an adapter handler is blocked in local execution, so the backend 180-second idle fallback does not fail a task that is still actively owned by a live bridge.
- The hao adapter now emits `adapter_started` before entering headless execution, matching Codex/Claude observability and proving the adapter picked up the task before model/tool execution begins.
- Live follow-up root cause: the visible 404 came from a stale running `api-server` process whose OpenAPI did not include `/recovery-command`. After restarting the local `harness_api` service, the endpoint returned 200 for connection `c465ba35-3782-44d9-a66c-0edfdf7933b2`.
- Claude Code permission-bridge connections include `--permission-bridge sdk` in the generated command when applicable.
- `apps/agent-console/src/features/agents/pages/AgentWorkspacePage.tsx` keeps `恢复` as the first action, refreshes local connection/binding/session/task/Run state, and only shows the command panel if the refreshed connection is still offline.
- The Workspace panel includes the generated command, state home, `复制命令`, and `我已执行，刷新`; it clears after the bridge reports `online` or `busy`.
- Offline pending assistant copy now points users to click `恢复` to generate the restart command instead of only waiting for the bridge to come back later.
- Final browser repro root cause: binding `aee0f1fb-ce2d-4f8c-a987-41b36bbba47b` still returned old failed bridge task `0999f316-a559-44ab-b087-e40da01f89a4` from `/tasks`; the frontend reattached that historical failure under its old user message and incorrectly made it the conversation `activeLeafId`.
- `localAgentConversationFromMessages` now tracks the active leaf separately from historical task branches. A terminal historical task is still added under its original user message, but it only becomes active when that parent had no newer children.
- On the user URL `http://127.0.0.1:5173/agents/default/workspace?conversation_id=conv-chart-artifact-demo&run_id=demo-tool-approval-run`, selecting `hao Local Agent` now keeps the newer HAO reply on the visible path instead of jumping back to the old 180-second timeout branch.
- Latest 7-minute repro root cause: HAO task `af97a48e-6ccf-4de3-93d0-46c16b8dce28` was legitimately waiting on Run approval `ed23eaf5-596d-465d-b46d-575937cbd5c6` for local `run_shell`, but the Workspace only had Claude-specific pending-approval copy and was still showing the generic processing fallback for non-Claude local agents.
- `AgentWorkspacePage.tsx` now restores `activeRunId` from the active local conversation leaf and from local message/task hydration, so `getAgentRunWorkspace` loads pending approvals after polling or refresh.
- Non-Claude local agents now render `等待本地工具审批。可在运行详情处理审批。` when a pending approval exists. Claude Code permission bridge keeps `等待 Claude Code 本地工具审批。可在运行详情处理审批。`.
- The local Agent header approval hint is no longer Claude-only. HAO and Codex pending local tool approvals now expose a Run Detail link that targets `#approvals`.
- The original HAO approval later expired and uncovered a second daemon failure: pending-tool resume reported `assistant_error` with an `event_id` containing the full `tool_request_id`, which exceeded the backend 160-character schema limit and returned 422.
- `services/api-server/app/cli/hao/main.py` now uses bounded assistant error event ids in the form `{bridge_task_id}:error:{uuid}`, so expired/rejected/execution-failed pending tools can fail closed without taking the bridge daemon down.
- Fresh HAO proof after the CLI fix uses bridge task `09f538e0-6b92-49a6-9bb7-948906dd63ee`, Run `63c8955e-7207-4a93-a9ec-138a236c0823`, and approval `8c88b084-c45e-4594-a097-75a9c27600c0`; API and browser both show explicit `run_shell` pending approval instead of a silent processing state.
- Latest approval-after-click root cause: HAO Run `ce448e37-f33c-488f-8d36-29a7bec8b3d8` failed after Run Detail approval because the model requested `list_files` again with the same `tool_call_id` after the first approved `list_files` result.
- The bridge had reused the same `tool_request_id`, so the backend returned the already-terminal local tool request with `status=succeeded` and reason `Approved from Agent Run Detail`; the CLI interpreted that reason as a denied tool result and failed the assistant turn.
- `services/api-server/app/cli/hao/main.py` now derives a per-session persisted tool-result count and passes it into `_bridge_tool_request_id(...)`; the first request keeps the original id, while repeated requests after tool results append `:1`, `:2`, etc.
- `_resume_bridge_pending_tools(...)` now removes local pending-tool state when the server decision is already `succeeded`, avoiding a stale local `assistant_error` for an approval that has already completed.
- Live HAO proof used Run `a05bf4c8-580c-4a80-97a9-dba3f52f8826` and bridge task `01703ac6-a4e6-44b9-9120-c7c5ff0d4aa9`. First approval `80111ca7-11a2-4f13-83ec-0da432fd7a36` used request id `01703ac6-a4e6-44b9-9120-c7c5ff0d4aa9:hao-local-a05bf4c8-580c-4a80-97a9-dba3f52f8826-0`; second approval `fc1f0d63-d4ed-46be-bf43-28341049e27b` used `01703ac6-a4e6-44b9-9120-c7c5ff0d4aa9:hao-local-a05bf4c8-580c-4a80-97a9-dba3f52f8826-0:1`.
- Both live HAO approvals used reason `Approved from Agent Run Detail`; the Run reached `COMPLETED`, both `list_files` tool calls were `SUCCESS`, and `failed_events=[]`.
- Live Codex proof used Run `7683a15b-d5b8-4439-b931-efe54940db38` and bridge task `a357ffab-75b0-4755-b380-3c994f5a79a8`; the Run reached `COMPLETED` with `failed_events=[]`.
- After daemon cleanup and restart, HAO bridge pid `96210` and Codex bridge pid `96212` were active, and both connections remained `online` after a 35-second recheck.
- Latest messy-context root cause: HAO built one combined prompt containing bridge role instructions, resume mode, Harness workspace context, prior conversation snippets, attachments, and the user message. `run_headless_once(...)` persisted that combined prompt as the `user` message and stream `goal`, so the backend local mock model could echo internal bridge context back into the UI.
- `_hao_prompt_for_task(...)` now returns only the redacted user message. `_hao_system_prompt_for_task(...)` carries the bridge/system/request context separately, and `run_headless_once(...)` stores it as a `system` message before the clean `user` message.
- The HAO bridge now detects the backend Docker-private-delivery local mock response prefix before appending assistant content or sending bridge `assistant_delta` events. If that prefix appears, the bridge fails closed with a real-model/API-key configuration error instead of presenting mock text as the assistant answer.
- Live HAO proof after this fix used binding `aee0f1fb-ce2d-4f8c-a987-41b36bbba47b`, bridge task `1efdb336-5b76-4898-b388-0537388c922e`, and Run `03a8b04e-5aff-4a52-8007-ba17e83be885`. The model call was `deepseek-flash` / `deepseek-v4-flash`; the Run reached `COMPLETED`, assistant deltas were `你好！有什么我可以帮你的吗？`, no local mock text was emitted, and both HAO/Codex connections stayed online.

## Validation

- `services/api-server/.venv/bin/python -m pytest services/api-server/tests/test_local_agents.py::test_local_agent_recovery_command_restarts_confirmed_connection -q` passed.
- `services/api-server/.venv/bin/python -m pytest services/api-server/tests/test_local_agents.py::test_local_agent_recovery_command_restarts_confirmed_connection services/api-server/tests/test_local_agents.py::test_local_agent_pairing_command_can_use_published_npm_package_override services/api-server/tests/test_local_agents.py::test_local_agent_pairing_command_does_not_add_registry_for_git_package_override -q` passed with `3 passed`.
- `services/api-server/.venv/bin/python -m ruff check services/api-server/app/api/agents/agent_local.py services/api-server/app/api/agents/common.py services/api-server/app/api/schemas.py services/api-server/tests/test_local_agents.py` passed.
- `services/api-server/.venv/bin/python -m py_compile services/api-server/app/api/agents/agent_local.py services/api-server/app/api/agents/common.py services/api-server/app/api/schemas.py services/api-server/tests/test_local_agents.py` passed.
- `cd apps/agent-console && PATH="/Users/luohao/.nvm/versions/node/v20.9.0/bin:/usr/local/bin:$PATH" npx vitest run src/features/agents/__tests__/AgentWorkspacePage.team-launch.test.tsx -t "bridge run command"` passed.
- `cd apps/agent-console && PATH="/Users/luohao/.nvm/versions/node/v20.9.0/bin:/usr/local/bin:$PATH" npx vitest run src/features/agents/__tests__/AgentWorkspacePage.team-launch.test.tsx` passed with `27 passed`.
- `cd apps/agent-console && PATH="/Users/luohao/.nvm/versions/node/v20.9.0/bin:/usr/local/bin:$PATH" npx tsc --noEmit --pretty false --types vite/client --skipLibCheck --jsx react-jsx --lib DOM,DOM.Iterable,ES2022 --module ESNext --moduleResolution Bundler --target ES2020 --esModuleInterop --allowSyntheticDefaultImports src/features/agents/pages/AgentWorkspacePage.tsx src/features/tasks/api.ts` passed.
- `services/api-server/.venv/bin/python -m pytest services/api-server/tests/test_hao_cli.py::test_hao_bridge_run_daemon_uses_project_cwd_and_log_file services/api-server/tests/test_hao_cli.py::test_hao_bridge_daemon_uses_protected_state_without_device_token_argv -q` passed with `2 passed`.
- `services/api-server/.venv/bin/python -m ruff check services/api-server/app/cli/hao/main.py services/api-server/app/api/agents/agent_local.py services/api-server/tests/test_hao_cli.py services/api-server/tests/test_local_agents.py && services/api-server/.venv/bin/python -m py_compile services/api-server/app/cli/hao/main.py services/api-server/app/api/agents/agent_local.py services/api-server/tests/test_hao_cli.py services/api-server/tests/test_local_agents.py` passed.
- `services/api-server/.venv/bin/python -m pytest services/api-server/tests/test_local_agents.py::test_local_agent_recovery_command_restarts_confirmed_connection services/api-server/tests/test_local_agents.py::test_local_agent_adapter_heartbeat_keeps_active_task_alive services/api-server/tests/test_local_agents.py::test_local_agent_stale_active_task_auto_fails_on_binding_poll services/api-server/tests/test_local_agents.py::test_local_agent_stale_task_waiting_on_local_tool_does_not_timeout services/api-server/tests/test_hao_cli.py::test_hao_bridge_run_daemon_uses_project_cwd_and_log_file services/api-server/tests/test_hao_cli.py::test_hao_bridge_daemon_uses_protected_state_without_device_token_argv services/api-server/tests/test_hao_cli.py::test_bridge_task_reports_heartbeat_while_adapter_is_running -q` passed with `7 passed`.
- `services/api-server/.venv/bin/python -m ruff check services/api-server/app/cli/hao/main.py services/api-server/app/api/agents/agent_local.py services/api-server/app/api/schemas.py services/api-server/tests/test_hao_cli.py services/api-server/tests/test_local_agents.py` passed.
- `services/api-server/.venv/bin/python -m py_compile services/api-server/app/cli/hao/main.py services/api-server/app/api/agents/agent_local.py services/api-server/app/api/schemas.py services/api-server/tests/test_hao_cli.py services/api-server/tests/test_local_agents.py` passed.
- Live recovery command for connection `c465ba35-3782-44d9-a66c-0edfdf7933b2` returned `daemon_started`, created `/Users/luohao/.hao/bridges/hao/bridge-daemon.log`, left a running `app.cli.hao.main bridge run` process, and `GET /api/agents/local-agent/connections` returned `online` for the hao connection.
- Live recovery command for connection `fd9aed0d-a5ef-458a-92c6-5b8254ef9b14` returned `daemon_started`, created `/Users/luohao/.hao/bridges/codex/bridge-daemon.log`, left a running `app.cli.hao.main bridge run` process, and `GET /api/agents/local-agent/connections` returned `online` for the Codex connection.
- Live e2e HAO send used binding `aee0f1fb-ce2d-4f8c-a987-41b36bbba47b`, bridge task `f2c52b3f-ab42-4d30-8529-86753648910f`, and run `f3fb1581-c5d7-4195-8a99-b548d798b347`; the assistant reply contained `HAO_LIVE_OK`, Run workspace status was `COMPLETED`, and the connection remained `online` after waiting beyond the 30-second offline threshold.
- Live e2e Codex send used binding `f4ceb0ed-3294-42e8-ba6e-a8bf8a705df8`, bridge task `bf35e4f2-9b8c-4fe3-a227-1105a2a46da0`, and run `0c9e8ce3-2ab9-4377-b0ad-83f98f283854`; the assistant reply was `CODEX_LIVE_OK`, Run workspace status was `COMPLETED`, and the connection remained `online` after waiting beyond the 30-second offline threshold.
- Run workspace events for both live runs include `LOCAL_AGENT_MESSAGE_QUEUED`, `LOCAL_AGENT_TASK_LEASED`, `LOCAL_AGENT_TASK_ACKED`, `LOCAL_AGENT_ADAPTER_STARTED`, `MODEL_CALLED`, `MODEL_RESPONSE_RECEIVED`, and `LOCAL_AGENT_MESSAGE_COMPLETED`.
- `cd apps/agent-console && PATH="/Users/luohao/.nvm/versions/node/v20.9.0/bin:/usr/local/bin:$PATH" npx vitest run src/features/agents/__tests__/AgentWorkspacePage.team-launch.test.tsx -t "old failed local Agent task"` passed with `1 passed`.
- `cd apps/agent-console && PATH="/Users/luohao/.nvm/versions/node/v20.9.0/bin:/usr/local/bin:$PATH" npx vitest run src/features/agents/__tests__/AgentWorkspacePage.team-launch.test.tsx` passed with `28 passed`.
- Browser verification on the user URL with `hao Local Agent` selected showed `hasTimeoutError=false`, `hasBackendError=false`, and the newer HAO mock reply visible.
- `cd apps/agent-console && PATH="/Users/luohao/.nvm/versions/node/v20.9.0/bin:/usr/local/bin:$PATH" npx vitest run src/features/agents/__tests__/AgentWorkspacePage.team-launch.test.tsx -t "non-Claude local tool approvals"` passed.
- `cd apps/agent-console && PATH="/Users/luohao/.nvm/versions/node/v20.9.0/bin:/usr/local/bin:$PATH" npx vitest run src/features/agents/__tests__/AgentWorkspacePage.team-launch.test.tsx -t "Claude Code permission bridge"` passed.
- `cd apps/agent-console && PATH="/Users/luohao/.nvm/versions/node/v20.9.0/bin:/usr/local/bin:$PATH" npx vitest run src/features/agents/__tests__/AgentWorkspacePage.team-launch.test.tsx` passed with `29 passed`.
- Browser verification on the user URL with `hao Local Agent` selected showed `hasProcessing=false`, `hasSpecificPendingApproval=true`, HAO status `online`, a `运行详情` link pointing to Run `d8ee702e-30c8-48f3-9d2c-6b3d188f44ad#approvals`, and no old generic processing copy.
- Run Detail browser verification for Run `d8ee702e-30c8-48f3-9d2c-6b3d188f44ad#approvals` showed the approval section, `run_shell`, wait state, reason `local host side-effect tools require Harness approval`, and visible `批准` / `拒绝` buttons.
- After restarting local API during verification, both bridge daemons were restarted through recovery commands; `GET /api/agents/local-agent/connections` returned HAO `c465ba35-3782-44d9-a66c-0edfdf7933b2` and Codex `fd9aed0d-a5ef-458a-92c6-5b8254ef9b14` as `online`.
- Live post-restart Codex send used binding `f4ceb0ed-3294-42e8-ba6e-a8bf8a705df8`, bridge task `18f2a94b-ddcc-4c71-ab27-5faaed1f554b`, and Run `077ecdb0-de4f-48b6-ac45-bec8071191a2`; the assistant reply was `CODEX_LIVE_OK` and Run workspace status was `COMPLETED`.
- `services/api-server/.venv/bin/python -m pytest services/api-server/tests/test_hao_cli.py::test_hao_bridge_pending_tool_expiry_uses_bounded_error_event_id -q` passed with `1 passed`.
- `services/api-server/.venv/bin/python -m ruff check services/api-server/app/cli/hao/main.py services/api-server/tests/test_hao_cli.py` passed.
- `services/api-server/.venv/bin/python -m py_compile services/api-server/app/cli/hao/main.py services/api-server/tests/test_hao_cli.py` passed.
- API verification for Run `63c8955e-7207-4a93-a9ec-138a236c0823` showed status `WAITING_APPROVAL`, approval `8c88b084-c45e-4594-a097-75a9c27600c0` as `PENDING`, and tool `run_shell` as `PENDING_APPROVAL`.
- Browser verification on `http://127.0.0.1:5173/agents/default/workspace?conversation_id=local-agent%3Aaee0f1fb-ce2d-4f8c-a987-41b36bbba47b&run_id=63c8955e-7207-4a93-a9ec-138a236c0823` showed `等待本地工具审批。可在运行详情处理审批。`, no generic processing copy, HAO online, and a Run Detail link targeting Run `63c8955e-7207-4a93-a9ec-138a236c0823#approvals`.
- Run Detail browser verification for Run `63c8955e-7207-4a93-a9ec-138a236c0823#approvals` showed `run_shell`, wait state, reason `local host side-effect tools require Harness approval`, and visible `批准` / `拒绝` buttons.
- `services/api-server/.venv/bin/python -m pytest services/api-server/tests/test_hao_cli.py::test_hao_bridge_repeated_tool_call_id_uses_tool_result_sequence services/api-server/tests/test_hao_cli.py::test_hao_bridge_stale_succeeded_pending_tool_does_not_fail_task services/api-server/tests/test_hao_cli.py::test_hao_bridge_pending_tool_expiry_uses_bounded_error_event_id -q` passed with `3 passed`.
- `services/api-server/.venv/bin/python -m pytest services/api-server/tests/test_hao_cli.py -q` passed with `65 passed`.
- `services/api-server/.venv/bin/python -m py_compile services/api-server/app/cli/hao/main.py services/api-server/tests/test_hao_cli.py` passed.
- `services/api-server/.venv/bin/python -m ruff check services/api-server/app/cli/hao/main.py services/api-server/tests/test_hao_cli.py` passed.
- Live HAO Run `a05bf4c8-580c-4a80-97a9-dba3f52f8826` completed after two approved `list_files` requests with distinct request ids, both tool calls `SUCCESS`, and `failed_events=[]`.
- Live Codex Run `7683a15b-d5b8-4439-b931-efe54940db38` completed with `failed_events=[]`.
- HAO and Codex local Agent connections remained `online` after 35 seconds.
- `services/api-server/.venv/bin/python -m pytest services/api-server/tests/test_hao_cli.py::test_hao_bridge_task_passes_harness_context_to_headless services/api-server/tests/test_hao_cli.py::test_hao_headless_keeps_user_goal_separate_from_system_context services/api-server/tests/test_hao_cli.py::test_hao_headless_rejects_local_bridge_mock_model_response -q` passed with `3 passed`.
- `services/api-server/.venv/bin/python -m pytest services/api-server/tests/test_hao_cli.py -q` passed with `67 passed`.
- `services/api-server/.venv/bin/python -m ruff check services/api-server/app/cli/hao/main.py services/api-server/tests/test_hao_cli.py` passed.
- `services/api-server/.venv/bin/python -m py_compile services/api-server/app/cli/hao/main.py services/api-server/tests/test_hao_cli.py` passed.
- Live HAO Run `03a8b04e-5aff-4a52-8007-ba17e83be885` completed with real DeepSeek Flash output `你好！有什么我可以帮你的吗？`, no local mock response text, no bridge prompt leakage in assistant deltas, and no `LOCAL_AGENT_MESSAGE_FAILED`.
- `python3 scripts/validate-docs.py` passed.
- `git diff --check` passed.

## Boundaries

- Recovery intentionally does not mint a new pairing token, because that would create a `pending_confirmation` connection and still require Agent Studio confirmation.
- Recovery intentionally does not auto-run shell commands from the browser; the Workspace produces a copyable command and verifies recovery by refreshing bridge status.
- Historical failed local-agent task branches remain available for inspection; the fix only prevents them from overriding the newer visible reply path.
- Pending local host-tool approvals still require an explicit human approval/reject decision in Run Detail. The Workspace fix makes that state visible and linked instead of approving the command automatically.
- Repeated model `tool_call_id` values are treated as new local tool requests only after persisted local tool results exist in the local session; this preserves the original request id for first-time approval compatibility.
- System bridge context may still be visible in developer/debug evidence surfaces where system messages are intentionally inspectable. It is no longer stored as the user goal and is no longer emitted as assistant reply content.
