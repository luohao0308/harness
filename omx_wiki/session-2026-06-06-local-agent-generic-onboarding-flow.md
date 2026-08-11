# Local Agent Generic Onboarding Flow - 2026-06-06

Category: session-log
Tags: `agent-console`, `local-agent`, `hao-cli`, `codex`, `claude-code`, `pairing`, `frontend-state`

## Summary

Changed the Agent Studio "接入本地 Agent" flow from adapter-first command generation to a generic onboarding wizard:

1. generate one connection command;
2. run it locally;
3. choose and name the detected local Agents.

The default command no longer requires choosing an adapter before generation. Agent Studio now shows the Coze-style `npx -y /path/to/harness/services/api-server bridge pair ...` command in the private/dev stack, and `hao bridge pair` auto-detects the default real local adapters when `--adapter` is omitted. The published registry package form is reserved for deployments that set `LOCAL_AGENT_NPX_PACKAGE=@harness/hao@latest` after the package exists in npm.

## Delivered

- Agent Studio no longer renders the pre-command "本地 Agent 类型" selector.
- Frontend pairing creation sends scope `["hao", "codex", "claude_code"]` and excludes only `fake` from the default generic pairing scope.
- The detection panel now shows discovered real local Agents as selectable rows with display-name inputs and status/risk badges.
- Detected rows are stable-sorted by adapter/name/created/id, preserve typed names across polling, never auto-select discovered Agents, and remove disappeared or revoked rows.
- Revoking a detected row now immediately clears that connection from selected IDs, name drafts, the local query cache, and the subsequent display-name PATCH save set.
- User-facing local Agent readiness counts now ignore explicit `fake` bridge connections; fake remains an explicit test/smoke adapter only.
- Claude Code is part of the default generic command. The V6 SDK permission bridge remains an explicit advanced intent-capture path, but the default Claude Code connection now receives the same Harness-approved local tool capability surface as hao.
- Selected display names are saved through `PATCH /api/agents/local-agent/connections/{connection_id}`.
- `hao bridge pair` without `--adapter` registers detected `hao`, `codex`, and `claude_code` adapters.
- Codex CLI and Claude Code normalize to hao-parity Harness-approved local tool capability (`host_read`, `host_write`, `shell`, `git`, `network`), preserve stream tokens for pending-tool resume, and route side effects through Harness approval/audit rather than unmanaged native bypasses.
- Auto-paired adapters use separate state roots under `~/.hao/bridges/{adapter}` so daemon bridge state does not overwrite sibling adapters.
- The backend allows one connection per `(pairing_token_id, adapter_kind)` so a generic token can register multiple adapters while duplicate same-adapter replay is rejected.
- Explicit single-adapter pairing remains available for tests and advanced paths; single-adapter tokens still move to `consumed`.

## Files Changed

```text
apps/agent-console/src/features/agents/pages/AgentListPage.tsx
apps/agent-console/src/features/agents/__tests__/AgentListPage.studio.test.tsx
apps/agent-console/src/features/tasks/api.ts
services/api-server/app/api/agents/agent_local.py
services/api-server/app/api/agents/common.py
services/api-server/app/api/schemas.py
services/api-server/app/cli/hao/main.py
services/api-server/app/db/models.py
services/api-server/alembic/versions/20260613_0040_local_agent_multi_adapter_pairing.py
services/api-server/tests/test_local_agents.py
services/api-server/tests/test_hao_cli.py
docs/development/cli/hao.md
docs/test-suite-v1-v6-local-agent.md
docs/development/ai/task-progress.yaml
```

## Validation

```text
cd services/api-server && .venv/bin/python -m pytest tests/test_local_agents.py -q -k 'pairing or connection_display_name or adapter_scope'
8 passed

cd services/api-server && .venv/bin/python -m pytest tests/test_hao_cli.py -q -k 'bridge_pair_without_adapter or bridge_pair_once_registers or bridge_daemon_uses_protected_state or codex_state_uses_workspace_sidecar or claude_state_uses_workspace_sidecar or codex_pair_fails_before_register or claude_pair_fails_before_register'
8 passed

cd services/api-server && .venv/bin/python -m pytest tests/test_local_agents.py tests/test_hao_cli.py -q -k 'pairing or connection_display_name or adapter_scope or bridge_pair_without_adapter or bridge_pair_once_registers or bridge_daemon_uses_protected_state or codex_state_uses_workspace_sidecar or claude_state_uses_workspace_sidecar or codex_pair_fails_before_register or claude_pair_fails_before_register'
16 passed

cd services/api-server && .venv/bin/python -m ruff check app/api/agents/agent_local.py app/api/schemas.py app/cli/hao/main.py app/db/models.py tests/test_local_agents.py tests/test_hao_cli.py
passed

cd services/api-server && .venv/bin/python -m py_compile app/api/agents/agent_local.py app/api/schemas.py app/cli/hao/main.py app/db/models.py
passed

cd apps/agent-console && PATH="/Users/luohao/.nvm/versions/node/v20.9.0/bin:/usr/local/bin:$PATH" npm test -- AgentListPage.studio.test.tsx
7 passed

cd apps/agent-console && PATH="/Users/luohao/.nvm/versions/node/v20.9.0/bin:/usr/local/bin:$PATH" npm run lint -- --pretty false
passed

cd apps/agent-console && PATH="/Users/luohao/.nvm/versions/node/v20.9.0/bin:/usr/local/bin:$PATH" npm run build
passed

cd services/api-server && .venv/bin/alembic upgrade head && .venv/bin/alembic current
20260613_0040 (head)

Restarted harness-api-langgraph API tmux session on 127.0.0.1:8000
/health returned ok and OpenAPI exposed PATCH /api/agents/local-agent/connections/{connection_id}

Live generic pairing on 127.0.0.1:8000 started hao and codex daemons; explicit follow-up --adapter claude_code with local PATH started Claude Code
Authenticated connection list showed hao, codex, and claude_code online

python3 scripts/validate-docs.py
passed

git diff --check
passed

Restarted harness-api-langgraph and harness-console-langgraph
API /health ok; Console / HTTP 200

Live temporary Codex registration smoke
onboarding_confirmed=false
direct binding returned HTTP 409 Local Agent connection has not been confirmed
temporary connection and pairing token revoked
```

## 2026-06-07 Parity Closeout

- Agent Studio's default user-facing pairing response now generates the npx command form:

Historical note: this 2026-06-07 registry-package command was superseded by the 2026-06-08 npm 404 repair below. Current private/dev command generation uses the local `services/api-server` package path.

```bash
npx -y --registry=https://registry.npmmirror.com @harness/hao@latest bridge pair --api http://127.0.0.1:8000 --pair-token <token> --pair-code <code> --daemon
```

- The generated default user-facing command no longer appends `--adapter` or `--permission-bridge`; adapter choice happens after local discovery, matching the Coze-style onboarding requested by the user. Explicit advanced API/CLI paths may still append adapter flags for scoped tests and Claude SDK permission-bridge smoke coverage.
- Codex CLI and Claude Code display `本机工具链可用` in Agent Studio and advertise the same risk capability set as hao.
- Current parity keeps Harness as the approval/audit boundary: local tool requests become `LocalAgentToolRequest`, `ToolApproval`, `ToolCall`, and bridge command/event records before host side effects run. Codex CLI and Claude Code still reject legacy `tool_result` bypasses and force context replay when a binding asks for native resume.

Latest validation:

```text
cd services/api-server && .venv/bin/python -m pytest tests/test_local_agents.py tests/test_hao_cli.py -q
115 passed

cd services/api-server && .venv/bin/python -m ruff check app/api/agents/agent_local.py app/cli/hao/main.py tests/test_local_agents.py tests/test_hao_cli.py
passed

cd services/api-server && .venv/bin/python -m py_compile app/api/agents/agent_local.py app/cli/hao/main.py
passed

cd apps/agent-console && PATH="/Users/luohao/.nvm/versions/node/v20.9.0/bin:/usr/local/bin:$PATH" npm test -- AgentListPage.studio.test.tsx
8 passed

cd apps/agent-console && PATH="/Users/luohao/.nvm/versions/node/v20.9.0/bin:/usr/local/bin:$PATH" npm run lint -- --pretty false
passed

cd apps/agent-console && PATH="/Users/luohao/.nvm/versions/node/v20.9.0/bin:/usr/local/bin:$PATH" npm run build
passed

python3 scripts/validate-docs.py
passed

git diff --check
passed

cd services/api-server && APP_ENV=development AUTH_JWT_SECRET=<local-dev-64-hex> .venv/bin/alembic upgrade head && APP_ENV=development AUTH_JWT_SECRET=<local-dev-64-hex> .venv/bin/alembic current
20260613_0040 (head)

Restarted harness-api-langgraph and harness-console-langgraph from current source
API /health returned {"status":"ok","service":"api-server"}
Console / returned HTTP 200

Historical pre-404-repair live POST /api/agents/local-agent/pairing-tokens generated the redacted npx command:
npx -y --registry=https://registry.npmmirror.com @harness/hao@latest bridge pair --api http://127.0.0.1:8000 --pair-token <redacted> --pair-code <redacted> --daemon

Live command checks:
command_prefix_ok=yes
has_adapter_flag=no
has_permission_bridge=no

Live temporary registration smoke using that generic token:
hao risk=["host_read","host_write","shell","git","network"], supports_cancel=true
codex risk=["host_read","host_write","shell","git","network"], host_tools_authorized=true, tool_execution_authority=harness_approved_local_bridge, permission_defer_supported=true, resume_mode=context_replay_new_session
claude_code risk=["host_read","host_write","shell","git","network"], host_tools_authorized=true, tool_execution_authority=harness_approved_local_bridge, permission_defer_supported=true, execution_mode=headless_harness_tool_bridge, resume_mode=context_replay_new_session
temporary_connections_revoked=yes
temporary_pairing_token_revoked=yes
```

## Boundaries

- `fake` remains supported for explicit tests and smoke paths, but is not part of the default generic user-facing onboarding command.
- Claude Code SDK permission bridge remains an explicit advanced path for SDK intent capture; normal local tool execution is still available through the Harness-approved local bridge.
- Running the local `npx` command itself was not performed in this pass to avoid disrupting the user's current live bridge daemons; the API-level live smoke generated, registered, verified, and revoked temporary records only.

## 2026-06-08 Review Hardening

- Historical note: Agent Studio briefly default-selected every real user-facing detected local Agent (`hao`, `codex`, `claude_code`) instead of only `hao`; the strict-checkbox follow-up below supersedes this behavior.
- Saving the detected list treats unchecked rows as "do not connect": selected rows receive display-name PATCH requests, unchecked detected rows are revoked, and the 0-selected state can be confirmed to disconnect every detected local Agent.
- The generated pairing command now uses configured `API_BASE_URL` / `get_settings().api_base_url` instead of hardcoded `http://127.0.0.1:8000`.
- Host-tool protocol access is now gated by server-owned `metadata_json.local_tool_policy=harness_approved_local_bridge`, and registration strips client-supplied `local_tool_policy` plus `server_permission_bridge_entitlement` before writing server values.
- The fake bypass regression now forges both `capabilities.host_tools_authorized=true` and `metadata.local_tool_policy=harness_approved_local_bridge`; the stored row drops the spoofed policy and the host-tool request remains rejected.
- Alembic downgrade for `20260613_0040` is explicitly blocked as unsafe instead of silently restoring the old single-token unique constraint.

Validation:

```text
cd services/api-server && .venv/bin/python -m pytest tests/test_local_agents.py::test_local_agent_host_tool_protocol_requires_server_policy tests/test_local_agents.py::test_local_agent_pairing_registers_with_hashed_token_and_multi_adapter_default tests/test_local_agents.py::test_local_agent_v4_codex_host_tool_protocol_uses_harness_approval -q
3 passed

cd services/api-server && .venv/bin/python -m pytest tests/test_local_agents.py tests/test_hao_cli.py -q
116 passed

cd services/api-server && .venv/bin/python -m ruff check app/api/agents/agent_local.py app/cli/hao/main.py tests/test_local_agents.py tests/test_hao_cli.py
passed

cd services/api-server && .venv/bin/python -m py_compile app/api/agents/agent_local.py app/cli/hao/main.py alembic/versions/20260613_0040_local_agent_multi_adapter_pairing.py
passed

cd apps/agent-console && PATH="/Users/luohao/.nvm/versions/node/v20.9.0/bin:/usr/local/bin:$PATH" npm test -- AgentListPage.studio.test.tsx
10 passed

cd apps/agent-console && PATH="/Users/luohao/.nvm/versions/node/v20.9.0/bin:/usr/local/bin:$PATH" npm run lint -- --pretty false
passed

cd apps/agent-console && PATH="/Users/luohao/.nvm/versions/node/v20.9.0/bin:/usr/local/bin:$PATH" npm run build
passed

python3 scripts/validate-docs.py
passed

git diff --check
passed
```

## Review Consensus

- Backend/CLI reviewer Archimedes returned PASS after checking default multi-adapter scope, token+adapter replay rejection, single-adapter consumption, DB uniqueness migration, `hao bridge pair` auto-detection, and full local-agent/hao CLI regression evidence.
- UI/state reviewer Lorentz returned PASS after the follow-up fixes for revoke cache cleanup, save-set filtering, fake readiness exclusion, and polling stability; current parity closeout supersedes the earlier Claude no-tools wording.
- Frontend/docs reviewer Linnaeus returned PASS after the advanced adapter example wording was clarified.
- Final independent closeout reviewer Descartes returned `PASS - no blockers` for the default npx command, default real adapter scope, Codex/Claude hao-parity capability normalization, legacy bypass rejection, and advanced-path documentation boundary.
- Frontend reviewer Socrates returned PASS for default-select-all real adapters, explicit-only revoke, non-destructive unchecked save, updated helper copy, and polling preservation coverage; this was superseded by the unchecked-row revoke repair below.
- Backend/security reviewer Curie initially found the spoofed `metadata.local_tool_policy` blocker, then cleared it after server-owned metadata stripping and fake metadata-spoof regression coverage.

## 2026-06-08 npm 404 Repair

- The generated private/dev pairing command now defaults to the local npm package path derived from `services/api-server` instead of the unpublished `@harness/hao@latest` registry package.
- `LOCAL_AGENT_NPX_PACKAGE` and `LOCAL_AGENT_NPX_REGISTRY` are available for published deployments; registry flags are added only for registry package specs, not local paths, URLs, file specs, git/GitHub/GitLab/Bitbucket specs, ssh specs, or slash-containing non-scoped specs.
- The pairing-command regression now asserts the local-path default includes `--pair-token`, `--pair-code`, and `--daemon`, excludes `@harness/hao@latest`, and excludes `--registry`; override coverage proves the published package path can still generate `npx -y --registry=... @harness/hao@latest ...`.
- Docs now show `npx -y /path/to/harness/services/api-server bridge pair ...` as the current private/dev command and describe `@harness/hao@latest` only as a publish-time override.

Validation:

```text
cd services/api-server && .venv/bin/python -m pytest tests/test_local_agents.py::test_local_agent_pairing_registers_with_hashed_token_and_multi_adapter_default tests/test_local_agents.py::test_local_agent_pairing_command_can_use_published_npm_package_override tests/test_local_agents.py::test_local_agent_pairing_command_does_not_add_registry_for_git_package_override tests/test_local_agents.py::test_local_agent_v4_pairing_command_is_adapter_scoped tests/test_local_agents.py::test_local_agent_v6_claude_pairing_command_includes_permission_bridge -q
5 passed

cd services/api-server && .venv/bin/python -m pytest tests/test_local_agents.py tests/test_hao_cli.py -q
118 passed

cd services/api-server && .venv/bin/python -m ruff check app/api/agents/agent_local.py app/core/config.py tests/test_local_agents.py
passed

cd services/api-server && .venv/bin/python -m py_compile app/api/agents/agent_local.py app/core/config.py
passed

python3 scripts/validate-docs.py
passed

targeted git diff --check for touched command/docs files
passed

npx -y /Users/luohao/Desktop/agent_workspace/harness/services/api-server --version
hao 0.1.0

npx -y /Users/luohao/Desktop/agent_workspace/harness/services/api-server bridge pair --help
displayed `hao bridge pair` options including --pair-token, --pair-code, --daemon, --adapter, and --permission-bridge

Live POST /api/agents/local-agent/pairing-tokens on 127.0.0.1:8000 generated:
npx -y /Users/luohao/Desktop/agent_workspace/harness/services/api-server bridge pair --api http://localhost:8000 --pair-token <redacted> --pair-code <redacted> --daemon
uses_local_package=true
has_pair_code=true
has_daemon=true
uses_unpublished_package=false
uses_registry=false
temporary_pairing_token_revoked=yes
```

Review consensus:

- Backend/security reviewer Mencius returned PASS, with no blocking findings after the npm-spec registry follow-up.
- Docs/test reviewer Nash initially found the missing `--pair-code` / `--daemon` regression assertions, then returned PASS after those tests were added.

## 2026-06-08 Unchecked Codex Repair

- Root cause: Agent Studio's generic onboarding command correctly auto-detected and registered available local Agents, but the dialog save step treated unchecked detected rows as "skip display-name PATCH" rather than "do not connect". That left an unchecked Codex connection online, so it still appeared later in the Workspace local Agent switcher.
- The save mutation now receives both `detectedConnections` and `selectedConnections`; it PATCHes selected rows and calls `POST /api/agents/local-agent/connections/{connection_id}/revoke` for every unchecked user-facing detected row.
- The local query cache is updated immediately to mark revoked rows as `revoked`, selected/seen/name draft state is cleaned, and the connections query is invalidated so the top-left Workspace switcher keeps filtering revoked rows out.
- The 0-selected state is now a valid confirmation path with the button label `不接入，断开全部` / `Disconnect all`; it revokes every detected local Agent and shows a non-misleading "未接入本地 Agent" success toast.
- Tests now cover the original Codex-shaped failure directly: hao, Codex, and Claude all detected; Codex unchecked; hao/Claude selected; save PATCHes hao/Claude and revokes only Codex. They also cover partial unchecked revocation, Codex-only 0-selected disconnect-all, and polling preservation of an unchecked Codex row.
- Follow-up hardening made `onboarding_confirmed` a backend execution boundary, not only a frontend projection flag. New local-agent registrations are discoverable but unconfirmed; `PATCH /api/agents/local-agent/connections/{connection_id}` confirms selected rows. Unconfirmed connections may heartbeat/list for discovery, but they cannot create bindings, send messages, pull or ack bridge tasks, emit bridge events, create/poll/result local tool requests, report command events, cancel commands, or retry commands.
- Initial pending-change previews are normalized with `change_id`, `target_paths`, and `diff_sha256`, so write-file/apply-patch approval/result flows can validate the same diff evidence even when the bridge supplied only a diff body.

Validation:

```text
cd apps/agent-console && PATH="/Users/luohao/.nvm/versions/node/v20.9.0/bin:/usr/local/bin:$PATH" npm test -- AgentListPage.studio.test.tsx
10 passed

cd apps/agent-console && PATH="/Users/luohao/.nvm/versions/node/v20.9.0/bin:/usr/local/bin:$PATH" npm test -- AgentWorkspacePage.team-launch.test.tsx
15 passed

cd apps/agent-console && PATH="/Users/luohao/.nvm/versions/node/v20.9.0/bin:/usr/local/bin:$PATH" npm run lint -- --pretty false
passed

cd apps/agent-console && PATH="/Users/luohao/.nvm/versions/node/v20.9.0/bin:/usr/local/bin:$PATH" npm run build
passed

cd services/api-server && .venv/bin/python -m pytest tests/test_local_agents.py::test_local_agent_unconfirmed_connection_cannot_execute_until_confirmed -q
1 passed

cd services/api-server && .venv/bin/python -m pytest tests/test_local_agents.py::test_local_agent_v3_retry_creates_fresh_request_and_command tests/test_local_agents.py::test_local_agent_v3_retry_rejects_non_retryable_commands -q
2 passed

cd services/api-server && .venv/bin/python -m pytest tests/test_local_agents.py tests/test_hao_cli.py -q
120 passed

cd services/api-server && .venv/bin/python -m ruff check app/api/agents/agent_local.py app/api/schemas.py tests/test_local_agents.py
passed

cd services/api-server && .venv/bin/python -m py_compile app/api/agents/agent_local.py app/api/schemas.py
passed

cd apps/agent-console && PATH="/Users/luohao/.nvm/versions/node/v20.9.0/bin:/usr/local/bin:$PATH" npm test -- AgentListPage.studio.test.tsx AgentWorkspacePage.team-launch.test.tsx
25 passed

python3 scripts/validate-docs.py
passed

git diff --check
passed
```

Review:

- Frontend state/interaction reviewer Confucius returned PASS for unchecked revoke, 0-selected disconnect-all, cache/invalidate behavior, and Workspace revoked filtering.
- Test/regression reviewer Newton returned PASS after the direct Codex-unchecked mixed scenario was added.
- Code/security reviewer Dewey initially requested backend confirmation gating, then returned PASS after binding/send/bridge/tool execution paths rejected unconfirmed connections.
- Architecture reviewer Kepler initially kept a narrow WATCH for command cancel/retry, then returned CLEAR/PASS after those user command paths also required confirmed onboarding.

## 2026-06-08 Strict Checkbox Follow-up

- Root cause of the second repro: after the backend confirmation gate landed, the Agent Studio wizard still had an older frontend convenience path that could auto-select an already confirmed, non-current-pairing local Agent during dialog open/regenerate/polling. That meant a user could intend to connect only hao while an older confirmed Codex row was silently kept in the selected set.
- The wizard now clears selected IDs, seen IDs, and name drafts when opened or when a pairing command is generated/regenerated.
- Discovery polling now only prunes selected IDs that disappeared; it never adds newly seen rows or previously confirmed rows to the selected set.
- The detection copy now states that all discovered Agents are not connected by default, and the checkbox state is the only source of truth for the save mutation.
- The new direct regression covers an old `onboarding_confirmed=true` Codex row plus a newly discovered hao row. Selecting only hao PATCHes hao, revokes Codex, and asserts there is no Codex PATCH.

Validation:

```text
cd apps/agent-console && PATH="/Users/luohao/.nvm/versions/node/v20.9.0/bin:/usr/local/bin:$PATH" npm test -- AgentListPage.studio.test.tsx
11 passed

cd apps/agent-console && PATH="/Users/luohao/.nvm/versions/node/v20.9.0/bin:/usr/local/bin:$PATH" npm test -- AgentListPage.studio.test.tsx AgentWorkspacePage.team-launch.test.tsx
26 passed

cd apps/agent-console && PATH="/Users/luohao/.nvm/versions/node/v20.9.0/bin:/usr/local/bin:$PATH" npm run lint -- --pretty false
passed

cd apps/agent-console && PATH="/Users/luohao/.nvm/versions/node/v20.9.0/bin:/usr/local/bin:$PATH" npm run build
passed

cd services/api-server && .venv/bin/python -m pytest tests/test_local_agents.py::test_local_agent_unconfirmed_connection_cannot_execute_until_confirmed -q
1 passed
```

Review:

- Arendt returned PASS for no default selection, polling not re-checking, selected-only PATCH, unchecked revoke, and old confirmed Codex not being silently retained.
- Avicenna returned PASS for the frontend/backend boundary: unconfirmed execution remains gated, Workspace filters confirmed connections, and the old confirmed Codex plus selected hao test covers the observed failure.

## 2026-06-08 Late Codex Token Closeout

- Final root cause for the repeated repro: the generic command can register adapters at slightly different times. If the user selected only hao and clicked save while Codex registered just after the current UI list snapshot, the earlier strict-checkbox save could miss that late Codex row. The row was still unconfirmed and non-executable, but it remained visible as a discovered connection and looked like Codex had been connected.
- Saving the wizard now first revokes the current pairing token, then refreshes `listLocalAgentConnections`, then PATCH-confirms only checked rows and revokes unchecked rows from both the original visible list and the same-token late-registration snapshot.
- The latest snapshot is deliberately scoped: it includes rows the user already saw/selected plus rows whose `pairing_token_id` is the current wizard token. A new regression proves a different-token late Codex row is not revoked or PATCHed by the current wizard.
- Backend pairing-token revoke now locks the token row with `SELECT ... FOR UPDATE`, matching the register path and narrowing revoke/register races.
- Backend reviewer Banach found a separate revoked-connection blocker: retrying an old failed command after connection revoke could create a new approved local-tool request and pending command. `_owned_connection(..., executable=True)` now rejects revoked connections, and the regression proves no new `LocalAgentToolRequest` or `LocalAgentCommand` rows are created after a revoked retry attempt.
- The full-flow parity regression is API-level deterministic coverage, not a real generated `npx ... bridge pair --daemon` daemon end-to-end run. It covers the complete backend objective through pairing-token creation, local bridge registration, pre-confirm execution rejection, PATCH confirmation, message send, bridge pull/ack, scoped local bridge SSE, direct platform SSE comparison with the same model/provider, all seven local tool categories, pending-change committed hash evidence for `write_file`, assistant completion, `ModelCall` reuse, task events, event-stream replay, model-calls API, and observability summary. The separate live `npx` smoke only proved local-path command/help generation plus temporary API registration/capability cleanup.

## 2026-06-08 Pending Confirmation Semantics

- Root cause of the latest UX repro: the generic command intentionally discovers every installed default adapter, including Codex, and `--daemon` could start each adapter loop before the user confirmed selection. Execution was still gated, but the API/UI projected unconfirmed rows as online discovery rows, so an unchecked Codex looked like it had been connected.
- Unconfirmed local connections now project `status="pending_confirmation"` in register, heartbeat, and list responses until the user confirms them through the onboarding PATCH. Backend executable gates require explicit `onboarding_confirmed=true` and non-`pending_confirmation`; heartbeat cannot promote pending rows to online; PATCH confirm can recover dirty pending rows. The Agent Studio dialog shows those rows as `待确认` / `未接入`, and the copy says discovered Agents need checkbox selection plus save before they are connected.
- `hao bridge run` now treats unconfirmed heartbeat or bridge-task pull rejection as a wait state. A daemon for a discovered-but-unconfirmed adapter keeps heartbeat alive for discovery, but it does not pull bridge tasks, resume pending tools, or exit before the user confirms the row.
- `AgentWorkspacePage` and `WorkspaceShellBar` now defensively filter unconfirmed, `pending_confirmation`, and revoked local connections, preventing future reuse regressions in Workspace target resolution and the top-left Agent/local-Agent target picker. The regression also covers stale-cache dirty data where `onboarding_confirmed=true` but the projected status remains `pending_confirmation`.

Validation:

```text
cd services/api-server && .venv/bin/python -m pytest tests/test_hao_cli.py::test_hao_bridge_run_waits_for_onboarding_confirmation_before_pulling_tasks tests/test_hao_cli.py::test_hao_bridge_run_treats_unconfirmed_pull_rejection_as_wait_state tests/test_hao_cli.py::test_hao_bridge_pair_without_adapter_auto_registers_detected_local_agents tests/test_local_agents.py::test_local_agent_pairing_registers_with_hashed_token_and_multi_adapter_default tests/test_local_agents.py::test_local_agent_unconfirmed_connection_cannot_execute_until_confirmed -q
5 passed

cd apps/agent-console && PATH="/Users/luohao/.nvm/versions/node/v20.9.0/bin:/usr/local/bin:$PATH" npm test -- AgentListPage.studio.test.tsx WorkspaceShellBar.render.test.tsx
18 passed

cd apps/agent-console && PATH="/Users/luohao/.nvm/versions/node/v20.9.0/bin:/usr/local/bin:$PATH" npm test -- AgentListPage.studio.test.tsx
13 passed

cd apps/agent-console && PATH="/Users/luohao/.nvm/versions/node/v20.9.0/bin:/usr/local/bin:$PATH" npm test -- AgentListPage.studio.test.tsx AgentWorkspacePage.team-launch.test.tsx
28 passed

cd services/api-server && .venv/bin/python -m pytest tests/test_local_agents.py::test_local_agent_full_flow_streams_tools_and_observability_like_platform_model -q
1 passed

cd services/api-server && .venv/bin/python -m pytest tests/test_local_agents.py::test_local_agent_revoked_pairing_token_blocks_late_codex_registration tests/test_local_agents.py::test_local_agent_unconfirmed_connection_cannot_execute_until_confirmed -q
2 passed

cd services/api-server && .venv/bin/python -m pytest tests/test_local_agents.py::test_local_agent_v3_retry_creates_fresh_request_and_command tests/test_local_agents.py::test_local_agent_v3_retry_rejects_revoked_connection tests/test_local_agents.py::test_local_agent_v3_retry_rejects_non_retryable_commands tests/test_local_agents.py::test_local_agent_revoke_blocks_bridge_pull -q
4 passed

cd services/api-server && .venv/bin/python -m pytest tests/test_local_agents.py tests/test_hao_cli.py -q
124 passed

cd services/api-server && .venv/bin/python -m ruff check app/api/agents/agent_local.py app/cli/hao/main.py tests/test_local_agents.py tests/test_hao_cli.py
passed

cd services/api-server && .venv/bin/python -m py_compile app/api/agents/agent_local.py app/cli/hao/main.py tests/test_local_agents.py tests/test_hao_cli.py
passed

cd apps/agent-console && PATH="/Users/luohao/.nvm/versions/node/v20.9.0/bin:/usr/local/bin:$PATH" npm run lint -- --pretty false
passed

cd apps/agent-console && PATH="/Users/luohao/.nvm/versions/node/v20.9.0/bin:/usr/local/bin:$PATH" npm run build
passed

python3 scripts/validate-docs.py
passed

targeted git diff --check for touched local-agent files and docs
passed
```

Review:

- Frontend reviewer Nietzsche returned PASS for the save ordering, same-token late Codex cleanup, selected hao/Claude preservation, different-token non-interference, and regression coverage.
- Backend reviewer Banach initially found the revoked retry gate blocker, then returned PASS after the shared executable-owner revoke gate and no-new-command regression were added.

## 2026-06-08 Final Subagent Review Closeout

- Follow-up reviewers Erdos and Harvey rechecked the pending-confirmation/onboarding hardening. Erdos returned PASS for backend executable gates, dirty pending regression coverage, Workspace target filtering, and API-level full-flow wording.
- Harvey initially raised two WATCH items: `WorkspaceShellBar` accepted rows where `onboarding_confirmed` was missing, and an older task-progress line could be read as current proof of a generated `npx ... --daemon` e2e. Both were fixed.
- `WorkspaceShellBar` now matches `AgentWorkspacePage` by requiring `onboarding_confirmed === true`; `WorkspaceShellBar.render.test.tsx` includes a malformed missing-confirmation local connection and asserts it is hidden from the target picker.
- The historical live pairing record now says the daemon start was a historical observation, while the current 2026-06-08 `npx` evidence is limited to command/help generation plus temporary API registration/capability cleanup. The full-flow parity test remains explicitly API-level deterministic coverage.

Validation:

```text
cd services/api-server && .venv/bin/python -m pytest tests/test_local_agents.py tests/test_hao_cli.py -q
125 passed

cd services/api-server && .venv/bin/python -m ruff check app/api/agents/agent_local.py app/cli/hao/main.py tests/test_local_agents.py tests/test_hao_cli.py
passed

cd services/api-server && .venv/bin/python -m py_compile app/api/agents/agent_local.py app/cli/hao/main.py tests/test_local_agents.py tests/test_hao_cli.py
passed

cd apps/agent-console && PATH="/Users/luohao/.nvm/versions/node/v20.9.0/bin:/usr/local/bin:$PATH" npm test -- WorkspaceShellBar.render.test.tsx AgentWorkspacePage.team-launch.test.tsx AgentListPage.studio.test.tsx
34 passed

cd apps/agent-console && PATH="/Users/luohao/.nvm/versions/node/v20.9.0/bin:/usr/local/bin:$PATH" npm run lint -- --pretty false
passed

cd apps/agent-console && PATH="/Users/luohao/.nvm/versions/node/v20.9.0/bin:/usr/local/bin:$PATH" npm run build
passed

python3 scripts/validate-docs.py
passed

targeted git diff --check for touched local-agent files and docs
passed
```
