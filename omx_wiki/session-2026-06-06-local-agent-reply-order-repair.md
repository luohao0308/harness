# Local Agent Reply And Order Repair - 2026-06-06

Category: session-log
Tags: `agent-console`, `local-agent`, `codex`, `claude-code`, `bridge`, `frontend-state`, `review`

## Summary

Fixed the live Local Agent failure mode where Codex CLI and Claude Code connections appeared to never reply while `hao` still worked, and where the local Agent selector order could move around as bridge heartbeats updated `updated_at`.

The repair has two layers:

- make local bridge failures visible in Workspace instead of disappearing from the conversation;
- fix the adapter-specific runtime failures for Codex and Claude Code while keeping the local security boundary intact.

## Root Cause

- Codex CLI bridge tasks were failing with `Not inside a trusted directory and --skip-git-repo-check was not specified`.
- Claude Code bridge tasks were failing with `Not logged in`; the subprocess was intentionally isolated with temp `HOME` / `CLAUDE_CONFIG_DIR`, but no allowlisted Claude auth environment was carried into that isolated process.
- Failed local bridge tasks were not projected by the binding task API used by the Workspace conversation, so users only saw that the Agent did not answer.
- Local connection ordering came from API heartbeat `updated_at`, which can change every few seconds and make the selector appear to reorder.
- Generic error bubbles had to be guarded so local Agent failures could not retry through the cloud Agent chat-stream path.

## Delivered

- Binding task projection now includes `failed` and `cancelled` local bridge tasks.
- Failed/cancelled local task responses include a bounded `error_message` from bridge payload.
- `assistant_error` and `ack(status="failed")` both terminalize the bridge task and run with `completed_at`, `Task.status = FAILED`, and persisted `terminal_error_message`.
- Codex command generation adds `--skip-git-repo-check` before stdin `-` when the installed CLI advertises the flag, while preserving read-only sandboxing and dangerous-flag guards.
- Codex isolated subprocesses now copy only `auth.json` plus a filtered minimal `config.toml` into temp `CODEX_HOME`, preserving the selected model/provider runtime config without importing hooks, MCP servers, features, sandbox policy, plugins, or other host config.
- Codex provider names are written as quoted TOML key segments, so dotted provider names work and malicious provider names cannot inject filtered-out TOML tables.
- Claude Code subprocess execution still uses temp `HOME`, temp `CLAUDE_CONFIG_DIR`, private cwd, no unmanaged settings path, and no host tools, but now imports only allowlisted Claude auth/model env values from source `~/.claude/settings.json` or current env.
- Claude error redaction now literal-redacts the sensitive values actually injected into the subprocess, including `ANTHROPIC_AUTH_TOKEN` from settings and opt-in `ANTHROPIC_API_KEY`.
- Agent Workspace sorts usable local connections (`online` / `busy`) before offline or other states, then by stable adapter/name/workspace/created/id keys instead of heartbeat freshness.
- Failed local tasks render as visible assistant error bubbles, do not lock the composer, and do not expose the generic cloud Retry action.
- Local send API failures also disable the generic Retry action; manual resubmit remains the local binding path.

## Files Changed

```text
services/api-server/app/api/agents/agent_local.py
services/api-server/app/api/schemas.py
services/api-server/app/cli/hao/main.py
services/api-server/tests/test_local_agents.py
services/api-server/tests/test_hao_cli.py
apps/agent-console/src/features/tasks/api.ts
apps/agent-console/src/features/agents/pages/AgentWorkspacePage.tsx
apps/agent-console/src/features/agents/components/ChatErrorBubble.tsx
apps/agent-console/src/features/agents/components/ChatSurface.tsx
apps/agent-console/src/stores/workspaceStore.ts
apps/agent-console/src/features/agents/__tests__/AgentWorkspacePage.team-launch.test.tsx
```

## Review Notes

- Backend/CLI reviewer Socrates initially requested changes for failed bridge ack terminalization and Codex skip-flag regression coverage.
- Socrates then requested one security fix: Claude literal redaction for allowlisted auth values injected from settings/env.
- Socrates final follow-up requested quoting Codex provider names when writing the filtered TOML provider table; the fix and injection regression passed, then Socrates returned `PASS`.
- UI/state reviewer Lovelace initially requested changes for local failed-task error bubbles exposing generic cloud Retry.
- Lovelace then requested one follow-up fix for optimistic local send failures exposing a dead Retry button.
- Lovelace final follow-up requested treating `online` and `busy` as the same usable status rank before adapter tie-breaks; the fix passed the targeted Workspace regression, then Lovelace returned `PASS`.
- Final Socrates verdict: `PASS`.
- Final Lovelace verdict: `PASS`.

Consensus state: no remaining blocking backend, CLI, security, UI, state, or test findings.

## Validation

```text
cd services/api-server && .venv/bin/python -m pytest tests/test_local_agents.py -q -k 'pending_task_is_api_projected or failed_task_is_projected or failed_ack'
3 passed

cd services/api-server && .venv/bin/python -m pytest tests/test_hao_cli.py -q -k 'codex_command_builder or run_codex_cli_success or claude_command_builder or run_claude_cli_success or run_claude_cli_rejects_workspace'
5 passed before Codex minimal config follow-up

cd services/api-server && .venv/bin/python -m pytest tests/test_hao_cli.py -q -k 'codex_command_builder or codex_minimal_toml or run_codex_cli_success or run_codex_cli_reports_timeout or claude_command_builder or run_claude_cli_success or run_claude_cli_rejects_workspace'
7 passed

cd services/api-server && .venv/bin/python -m pytest tests/test_hao_cli.py -q
51 passed

cd services/api-server && .venv/bin/python -m ruff check app/cli/hao/main.py app/api/agents/agent_local.py app/api/schemas.py tests/test_local_agents.py tests/test_hao_cli.py
passed

cd apps/agent-console && PATH="/Users/luohao/.nvm/versions/node/v20.9.0/bin:/usr/local/bin:$PATH" npm test -- AgentWorkspacePage.team-launch.test.tsx
10 passed

cd apps/agent-console && PATH="/Users/luohao/.nvm/versions/node/v20.9.0/bin:/usr/local/bin:$PATH" npm run lint -- --pretty false
passed

git diff --check
passed

Live API health on `127.0.0.1:8000`
passed

Live Codex CLI local Agent smoke through connection `7f204050-3240-48b6-9269-a9ffdbefe1e3`
message `只回复 OK` -> assistant `OK`; run `330cbe0e-7e25-4db2-a279-563351157b32` completed; binding task list empty

Live Claude Code local Agent smoke through connection `8c008bc7-31b7-4028-958a-49f1ec9641a4`
message `只回复 OK` -> assistant `OKOK`; run `a6c49629-0321-44c8-9ef2-ddcd632b0a76` completed; binding task list empty
```

## Runtime Note

The local API server on `127.0.0.1:8000` is running from the current source. The live bridge set after repair is:

- `hao`: `99597a75-0325-4014-aebd-1a7f48028b1c`
- `codex`: `7f204050-3240-48b6-9269-a9ffdbefe1e3`
- `claude_code`: `8c008bc7-31b7-4028-958a-49f1ec9641a4`

The previous Codex bridge `e3403d6a-86fe-4ce5-9017-26954dba7487` was stopped and revoked after the new Codex bridge was paired with isolated state under `/Users/luohao/.hao-codex-live`.

## Boundaries

- Codex still receives only a temp `HOME` and temp `CODEX_HOME`; the temp `CODEX_HOME` contains only copied `auth.json` plus filtered scalar model settings and the selected provider block. Hooks, MCP servers, features, sandbox policy, plugins, and other host config are not copied.
- Claude Code still does not load unmanaged `~/.claude` runtime settings, hooks, MCP, plugins, subagents, browser, or remote-control surfaces.
- `ANTHROPIC_API_KEY` is still passed only when `HAO_CLAUDE_CODE_ALLOW_ANTHROPIC_API_KEY=1`.
- The generic cloud Retry action remains available for normal cloud chat-stream errors; only local Agent error nodes disable it.

## Follow-Up: Streaming, Token Scope, And History Stability

Closed the remaining local Agent Workspace stability issues after the UI follow-up:

- Local Agent task-event SSE deltas now project into the active assistant bubble, and `LOCAL_AGENT_MESSAGE_COMPLETED` clears the browser pending id so the composer does not remain locked after a successful streamed reply.
- The derived local conversation hydration no longer preserves a streamed temporary pending bubble after the backend has returned a final assistant message with the same `bridge_task_id`.
- Local message polling upserts non-current local conversation summaries instead of forcing the current conversation back to the local Agent binding.
- Conversation history groups sessions by Agent, including local Agent-backed sessions, so one Agent's histories stay together instead of splitting by local connection display name.
- Agent Studio local discovery polling no longer drives the manual refresh overlay/badge, preventing the realtime local Agent area from flashing on background refresh.
- Saving the local Agent wizard revokes unchecked detected local connections, including unchecked Claude Code, instead of silently leaving them attached.
- Local connection model capabilities can auto-sync the Workspace composer model; local send payloads preserve model provider/name, workspace request, tool mentions, attachments, compressed context, and active-path context.
- Plan mode now maps to backend `markdown_plan` for local bridge tasks and to hao CLI `plan` for the local execution command.
- hao bridge payloads include a `harness_stream_token` plus the stream request now sends `local_bridge_task_id`.
- `harness_stream_token` is no longer a normal engineer token. It is a 30-minute scoped JWT bound to `scope=local_agent_bridge_stream`, `agent_id`, `run_id`, and `bridge_task_id`, matching the local tool approval window.
- Normal API auth rejects scoped stream tokens; the chat stream endpoint accepts them only when the request path/body and `LocalAgentBridgeTask` row match the token claims.

### Follow-Up Validation

```text
cd services/api-server && .venv/bin/python -m pytest tests/test_local_agents.py::test_hao_local_agent_plan_mode_queues_markdown_plan_run_with_stream_token tests/test_hao_cli.py::test_hao_bridge_task_uses_plan_command_and_stream_token -q
2 passed

cd services/api-server && .venv/bin/python -m pytest tests/test_local_agents.py tests/test_hao_cli.py -q
106 passed

cd services/api-server && .venv/bin/python -m ruff check app/security/auth.py app/api/agents/agent_chat/streaming.py app/api/agents/agent_local.py app/api/schemas.py app/cli/hao/main.py tests/test_local_agents.py tests/test_hao_cli.py
passed

cd services/api-server && .venv/bin/python -m py_compile app/security/auth.py app/api/agents/agent_chat/streaming.py app/api/agents/agent_local.py app/api/agents/common.py app/api/schemas.py app/cli/hao/main.py
passed

cd apps/agent-console && PATH="/Users/luohao/.nvm/versions/node/v20.9.0/bin:/usr/local/bin:$PATH" npm test -- AgentWorkspacePage.team-launch.test.tsx AgentListPage.studio.test.tsx
19 passed

cd apps/agent-console && PATH="/Users/luohao/.nvm/versions/node/v20.9.0/bin:/usr/local/bin:$PATH" npm run lint -- --pretty false
passed

cd apps/agent-console && PATH="/Users/luohao/.nvm/versions/node/v20.9.0/bin:/usr/local/bin:$PATH" npm run build
passed

Restarted local dev services in tmux sessions harness-api-langgraph and harness-console-langgraph
API http://127.0.0.1:8000/health -> {"status":"ok","service":"api-server"}
Console http://127.0.0.1:5173/ -> HTTP 200
OpenAPI contains /api/agents/{agent_id}/runs/chat/stream, /api/agents/local-agent/pairing-tokens, and /api/agents/local-agent/connections/{connection_id}

git diff --check for touched local-agent/frontend/backend files
passed
```

### Follow-Up Reviews

- Frontend/UI reviewer Raman initially found a blocking SSE completion lifecycle bug; after the pending-id and duplicate-bubble fix, final verdict `PASS`.
- Backend/local-agent reviewer Harvey initially found that `harness_stream_token` was a normal bearer token with ignored scope; after scoped JWT and stream-only dependency fix, final verdict `PASS`.

Consensus state: no remaining blocking streaming, token-scope, model passthrough, plan-mode, local discovery, history grouping, or local Agent polling findings.

## Follow-Up: Realtime SSE, ModelCall Reuse, And Manual Model Choice

Closed the final code-review findings from the local Agent stability pass:

- hao headless bridge now mirrors each platform chat-stream `delta` into a local bridge `assistant_delta` event while the run is still streaming. Workspace already listens to task-event SSE for `LOCAL_AGENT_DELTA_RECEIVED`, so hao local Agent output now appears incrementally instead of only after final message hydration.
- hao headless result captures the platform stream `usage.model_call_id` and includes it in `assistant_done` metadata.
- Backend local bridge `assistant_done` reuses an existing same-task `ModelCall` when `metadata.model_call_id` is present, and only creates a local bridge `ModelCall` when no existing platform model call exists. This keeps Codex/Claude/direct local outputs observable while avoiding hao double-counting in Run Detail and token rollups.
- hao pending-tool resume now preserves the scoped `harness_stream_token`, uses it for the approved local-tool follow-up chat stream, and uses the same delta/done sequence plus `model_call_id` / `usage` handoff as the primary bridge path, so approved local-tool follow-up runs stream reliably and avoid duplicate model-call accounting.
- The scoped `harness_stream_token` lifetime now uses the same 30-minute TTL constant as local tool approval decisions, preventing a valid approval from outliving its follow-up stream credential.
- Local bridge `ModelCall` rows now store bounded request/response snapshots, model provider/name, token/duration estimates, safe attachment/tool/context metadata, and source/capability metadata marked as `local_agent_bridge`.
- Agent Workspace local connection polling no longer overwrites a user-manual composer model selection after the local connection has auto-synced once. Switching local connections still auto-syncs the new connection model.
- Follow-up review hardening keeps resumed pending-tool SSE delta event IDs monotonic after pre-approval deltas, removes heartbeat-updated `updated_at` from backend connection-list ordering, removes status from frontend connection display sorting, closes active local EventSource handles when local mode is disabled, clears pending local-focus intent when the user manually changes history, and removes Claude Code from default generic pairing scope so it is only connected through explicit `--adapter claude_code`.

### Follow-Up Validation

```text
cd services/api-server && .venv/bin/python -m pytest tests/test_hao_cli.py::test_hao_headless_forwards_bridge_deltas_and_model_call_usage tests/test_local_agents.py::test_local_agent_assistant_done_reuses_existing_model_call -q
2 passed

cd services/api-server && .venv/bin/python -m pytest tests/test_hao_cli.py::test_hao_bridge_pending_tool_preserves_selected_model_for_resume -q
1 passed

cd services/api-server && .venv/bin/python -m pytest tests/test_local_agents.py::test_hao_local_agent_plan_mode_queues_markdown_plan_run_with_stream_token tests/test_hao_cli.py::test_hao_bridge_pending_tool_preserves_selected_model_for_resume -q
2 passed

cd services/api-server && .venv/bin/python -m pytest tests/test_local_agents.py tests/test_hao_cli.py -q
108 passed

cd services/api-server && .venv/bin/python -m ruff check app/api/agents/agent_local.py app/cli/hao/main.py tests/test_local_agents.py tests/test_hao_cli.py
passed

cd services/api-server && .venv/bin/python -m py_compile app/api/agents/agent_local.py app/cli/hao/main.py
passed

cd apps/agent-console && PATH="/Users/luohao/.nvm/versions/node/v20.9.0/bin:/usr/local/bin:$PATH" npm test -- AgentWorkspacePage.team-launch.test.tsx AgentListPage.studio.test.tsx
20 passed

cd apps/agent-console && PATH="/Users/luohao/.nvm/versions/node/v20.9.0/bin:/usr/local/bin:$PATH" npm run lint -- --pretty false
passed

cd apps/agent-console && PATH="/Users/luohao/.nvm/versions/node/v20.9.0/bin:/usr/local/bin:$PATH" npm run build
passed

cd services/api-server && .venv/bin/python -m pytest tests/test_local_agents.py tests/test_hao_cli.py -q
109 passed

cd apps/agent-console && npm test -- AgentWorkspacePage.team-launch.test.tsx AgentListPage.studio.test.tsx
21 passed
```

## Follow-Up: Scoped Stream Token Replay Hardening

Closed the final backend review finding from the scoped local Agent stream-token pass:

- Scoped local bridge stream tokens are now one-time per JWT `jti`, not one-time per bridge task.
- `_consume_local_bridge_stream_token` rejects missing `jti`, reads the legacy `harness_stream_token_consumed_jti`, tracks consumed values in `harness_stream_token_consumed_jtis`, and rejects only duplicate incoming `jti` values.
- Fresh scoped tokens for the same active bridge task can still be used for pending-tool resume or other follow-up streaming paths.
- Legacy metadata remains compatible: the latest consumed token is mirrored to `harness_stream_token_consumed_jti`, while the full list preserves the replay evidence.
- The regression test now proves: first token succeeds, replaying that token returns 401, a freshly issued scoped token for the same active bridge task succeeds, and replaying the fresh token also returns 401.

### Replay Hardening Validation

```text
cd services/api-server && .venv/bin/python -m pytest tests/test_local_agents.py::test_local_agent_scoped_stream_token_is_single_use_before_terminal_state tests/test_local_agents.py::test_local_agent_scoped_stream_token_rejects_terminal_bridge_task_replay tests/test_local_agents.py::test_hao_local_agent_plan_mode_queues_markdown_plan_run_with_stream_token tests/test_local_agents.py::test_normal_token_cannot_mark_local_bridge_stream_model_call_metadata -q
4 passed

cd services/api-server && .venv/bin/python -m pytest tests/test_local_agents.py tests/test_hao_cli.py tests/test_model_gateway.py -q
131 passed

cd services/api-server && .venv/bin/python -m ruff check app/security/auth.py app/api/agents/agent_chat/streaming.py app/api/agents/agent_local.py app/api/schemas.py app/cli/hao/main.py tests/test_local_agents.py tests/test_hao_cli.py tests/test_model_gateway.py
passed

cd services/api-server && .venv/bin/python -m py_compile app/security/auth.py app/api/agents/agent_chat/streaming.py app/api/agents/agent_local.py app/api/agents/common.py app/api/schemas.py app/cli/hao/main.py
passed

cd apps/agent-console && PATH="/Users/luohao/.nvm/versions/node/v20.9.0/bin:/usr/local/bin:$PATH" npm test -- AgentListPage.studio.test.tsx AgentWorkspacePage.team-launch.test.tsx
22 passed

cd apps/agent-console && PATH="/Users/luohao/.nvm/versions/node/v20.9.0/bin:/usr/local/bin:$PATH" npm run lint -- --pretty false
passed

cd apps/agent-console && PATH="/Users/luohao/.nvm/versions/node/v20.9.0/bin:/usr/local/bin:$PATH" npm run build
passed

python3 scripts/validate-docs.py
passed

git diff --check
passed

Restarted current-source runtime:
- `harness-api-langgraph` on `127.0.0.1:8000`; `/health` returned ok.
- `harness-console-langgraph` on `127.0.0.1:5173`; `/` returned HTTP 200.
- `harness-bridge-hao`, `harness-bridge-codex`, and `harness-bridge-claude-code` tmux sessions are running.
- Authenticated local connection list showed `hao`, `Codex CLI`, and `Claude Code` all `online`.
```

### Replay Hardening Reviews

- Backend/security reviewer Popper final verdict: `PASS`. The prior HIGH finding is resolved because replay is rejected per incoming `jti` while fresh scoped same-task tokens continue to work.
- UI/experience reviewer Dewey final verdict: `PASS`. The Coze-like local Agent onboarding, explicit Claude Code flow, recovery/status visibility, local Agent labels, stable history/model behavior, and targeted frontend tests have no remaining blocking findings.

Consensus state: no remaining blocking backend/security, replay, pending-tool resume, UI/experience, or test findings.

## Follow-Up: Codex/Claude Stdout Streaming And Approval Hydration

Closed the user-visible stuck state where Codex CLI / Claude Code local Agents could sit on the placeholder while their subprocess was still running, and where local-tool approval state could be lost after polling.

- Codex and Claude Code bridge runners now support live stdout streaming through an `on_delta` callback. When the bridge handler passes that callback, the subprocess is launched with `Popen`, stdout JSONL is parsed line-by-line, and bridge `assistant_delta` events are reported before process exit.
- Codex streaming reuses the existing assistant-text extractor plus Codex redaction, preserving chunk whitespace instead of trimming `Hello ` into `Hello`.
- Claude Code V5 buffers assistant text until the empty-tool `system/init` proof appears, then streams redacted chunks. Unsafe Claude stream events remain fail-closed, and final `assistant_done` still carries API-checked safety metadata.
- Codex/Claude bridge handlers now emit dynamic monotonic event sequences after `adapter_started`; if real stdout deltas were emitted, the handler skips the old synthesized full-content delta and sends only `assistant_done` after the last real chunk.
- Claude `result` records are treated as final result text rather than another delta, preventing partial-plus-result duplication such as the earlier live `OKOK` symptom.
- Subprocess stdin writing runs on a background thread, so a stuck stdin pipe cannot prevent the stdout/timeout loop from terminating a hung adapter process.
- Workspace now treats `waiting_approval` and `awaiting_message_hydration` as active task-event SSE states. A polling refresh can no longer replace a concrete "请求本地工具 read_file，等待审批" bubble with the generic "正在处理" placeholder.
- If `LOCAL_AGENT_MESSAGE_COMPLETED` arrives with no streamed content and before final message hydration, the optimistic assistant stays streaming with `awaiting_message_hydration` instead of being frozen as a completed placeholder.

### Stdout Streaming Validation

```text
cd services/api-server && .venv/bin/python -m pytest tests/test_hao_cli.py -q -k 'run_codex_cli_success or run_codex_cli_streams_stdout_deltas or run_claude_cli_success or run_claude_cli_streams_after_safety_init or terminal_event_ids_are_stable or claude_jsonl_parser_requires_empty_tool_safety_proof or claude_jsonl_parser_ignores_generic'
8 passed, 50 deselected

cd services/api-server && .venv/bin/python -m pytest tests/test_hao_cli.py -q
58 passed

cd services/api-server && .venv/bin/python -m pytest tests/test_local_agents.py tests/test_hao_cli.py -q
115 passed

cd services/api-server && .venv/bin/python -m ruff check app/cli/hao/main.py app/api/agents/agent_local.py app/api/schemas.py tests/test_local_agents.py tests/test_hao_cli.py
passed

python3 -m py_compile services/api-server/app/cli/hao/main.py
passed

cd apps/agent-console && PATH="/Users/luohao/.nvm/versions/node/v20.9.0/bin:/usr/local/bin:$PATH" npm test -- AgentWorkspacePage.team-launch.test.tsx
15 passed

cd apps/agent-console && PATH="/Users/luohao/.nvm/versions/node/v20.9.0/bin:/usr/local/bin:$PATH" npm test -- AgentWorkspacePage.team-launch.test.tsx AgentListPage.studio.test.tsx
23 passed

cd apps/agent-console && PATH="/Users/luohao/.nvm/versions/node/v20.9.0/bin:/usr/local/bin:$PATH" npm run lint -- --pretty false
passed

cd apps/agent-console && PATH="/Users/luohao/.nvm/versions/node/v20.9.0/bin:/usr/local/bin:$PATH" npm run build
passed

python3 scripts/validate-docs.py
passed

git diff --check
passed
```

### Stdout Streaming Reviews

- Frontend reviewer Boole final verdict: `PASS`. Prior approval hydration and no-delta completion blockers are resolved and covered by tests.
- Backend/CLI reviewer Wegener final verdict: `PASS`. Prior buffered subprocess, dynamic sequence, duplicate final-delta, Claude safety-gating, and partial/result dedupe requirements are resolved and covered by tests.

Consensus state: no remaining blocking frontend approval-hydration or backend stdout-streaming findings.

## Follow-Up: Local Agent Conversation Isolation, Cloud Return, And Pending Binding Guard

Closed the user-visible cross-talk where Claude Code and hao local Agent conversations could appear to share context after switching targets: the page could keep showing the prior local conversation, switching back could look like a new conversation, and a later send could still continue the older binding's context.

- Agent Workspace now ensures the active local binding has its own `local-agent:<bindingId>` conversation before submit or message hydration, and focuses that binding-specific conversation when the user selects the local Agent target.
- Local message hydration filters messages and bridge tasks by the selected binding, connection, and session before deriving the active path, so one local Agent's history cannot replace another local Agent's visible conversation.
- Local submit context is rebuilt from the selected binding's own conversation; messages, active leaf, pinned ids, turns, and compressed context are filtered by binding/connection/session metadata before sending to the bridge.
- Backend binding and send paths now enforce the same isolation boundary: one active `AgentSession` can belong to only one local Agent connection. New cross-connection binds return 409, conflict bindings cannot send, and Alembic `20260614_0041` marks older duplicate active bindings as `conflict` before adding the active-session unique index.
- Server-side fallback context replay now filters persisted `AgentMessage` rows by `source=local_agent`, `binding_id`, `connection_id`, and `agent_session_id`, so source-only or other-binding rows in the same session cannot be replayed into the selected local Agent bridge payload.
- Pending optimistic assistant `input_tokens` estimation now includes the selected binding's history, metadata, tool mentions, attachments, attachment names, and compressed summary rather than only the current user input.
- Late local send responses are ignored if the user has switched local connection or conversation before the response returns. The stale response can invalidate only its original binding/session queries and cannot set the current run, mutate the visible assistant node, or start an SSE stream.
- Active local task-event SSE streams now use an ownership token and verify selected connection, current local conversation, run id, binding id, session id, bridge task id, and assistant node ownership before any event can mutate UI state, clear pending state, invalidate active queries, or close the stream.
- Switching from a local Agent target back to the same cloud Agent now explicitly restores the latest non-local conversation or creates a fresh cloud conversation, so cloud chat payloads cannot keep using the visible local binding's history after the header label changes.
- Starting a new local Agent conversation clears the previous active binding immediately and blocks submit while the new binding is pending, preventing fast typing/sending from enqueueing the new message on the old binding/session.

### Conversation Isolation Validation

```text
cd apps/agent-console && PATH="/Users/luohao/.nvm/versions/node/v20.9.0/bin:/usr/local/bin:$PATH" npm test -- AgentWorkspacePage.team-launch.test.tsx
20 passed

cd apps/agent-console && PATH="/Users/luohao/.nvm/versions/node/v20.9.0/bin:/usr/local/bin:$PATH" npm test -- AgentWorkspacePage.team-launch.test.tsx
21 passed after the final Claude Code -> hao -> Claude Code -> send both ways DOM/POST/token regression was added

cd apps/agent-console && PATH="/Users/luohao/.nvm/versions/node/v20.9.0/bin:/usr/local/bin:$PATH" npm test -- AgentWorkspacePage.team-launch.test.tsx -t "isolates local Agent history|stale local Agent pending state|previous local binding"
3 passed

cd apps/agent-console && PATH="/Users/luohao/.nvm/versions/node/v20.9.0/bin:/usr/local/bin:$PATH" npm run lint -- --pretty false
passed

cd apps/agent-console && PATH="/Users/luohao/.nvm/versions/node/v20.9.0/bin:/usr/local/bin:$PATH" npm run build
passed

cd services/api-server && .venv/bin/python -m pytest tests/test_local_agents.py::test_local_agent_explicit_empty_workspace_context_does_not_replay_session -q
1 passed

cd services/api-server && .venv/bin/python -m pytest tests/test_local_agents.py tests/test_hao_cli.py -q
126 passed

cd services/api-server && .venv/bin/python -m pytest tests/test_local_agents.py::test_local_agent_v4_codex_second_turn_replays_redacted_harness_context tests/test_local_agents.py::test_local_agent_session_cannot_be_rebound_to_another_connection tests/test_local_agents.py::test_local_agent_conflict_session_binding_cannot_send tests/test_local_agents.py::test_local_agent_owner_can_send_and_bridge_events_are_idempotent -q
4 passed

cd services/api-server && .venv/bin/python -m pytest tests/test_local_agents.py tests/test_hao_cli.py -q
128 passed

cd services/api-server && .venv/bin/python -m ruff check app/api/agents/agent_local.py app/api/schemas.py tests/test_local_agents.py
passed

cd services/api-server && .venv/bin/python -m ruff check app/api/agents/agent_local.py app/db/models.py tests/test_local_agents.py alembic/versions/20260614_0041_local_agent_active_session_guard.py
passed

cd services/api-server && .venv/bin/python -m py_compile app/api/agents/agent_local.py app/db/models.py alembic/versions/20260614_0041_local_agent_active_session_guard.py
passed

python3 scripts/validate-docs.py
passed

cd apps/agent-console && /usr/local/bin/npm test -- AgentWorkspacePage.team-launch.test.tsx ChatMessageList.render.test.tsx
28 passed

cd apps/agent-console && /usr/local/bin/npm run lint -- --pretty false
passed

cd apps/agent-console && /usr/local/bin/npm run build
passed

git diff --check
passed
```

### Conversation Isolation Reviews

- State/race reviewer Mencius initially found a remaining medium late-SSE risk where an old already-open stream could close a newer local Agent stream after target switching. After the stream-token ownership guard and stale-SSE regression were added, final verdict `PASS`.
- Test coverage reviewer Planck final verdict `PASS`: the Workspace local Agent suite covers Claude Code -> hao -> Claude Code isolation, payload context filtering in both directions, server token metadata preservation, richer optimistic input-token estimates, late send response discard, and late SSE event discard; the final suite now has 21 cases after adding the full DOM/POST/token repro in both local-Agent directions.
- Frontend reviewer Darwin final verdict `PASS` after the follow-up cloud-return conversation guard and pending-new-binding submit block were added.
- Backend/local-agent reviewer Zeno final verdict `PASS` for the explicit empty workspace-context boundary and local input/output replay behavior.
- Final frontend reviewer Kant verdict `PASS` for target switching, binding/message polling, submit payload filtering, stale send/SSE guards, and DOM/POST/token regression coverage.
- Final backend reviewer Nietzsche verdict `PASS` for local Agent I/O recording and binding/session isolation.

Consensus state: no remaining blocking local Agent conversation isolation, cloud-return payload, pending-new-binding, local input/output metadata, binding/session isolation, stale send response, or late SSE stream ownership findings.

## Follow-Up: Exact Binding Restore And Compressed Context Gate

Closed the final reproduction edges after the Claude Code / hao cross-talk review pass:

- The top `启用本地 Agent` path now restores the most recent exact persisted binding hint for the selected connection instead of blindly choosing the latest active binding on that connection.
- Cold-cache local target switching keeps a pending restore state until the exact `binding_id`, `connection_id`, and `agent_session_id` binding is confirmed by the API cache; it no longer fabricates a binding from stale conversation metadata.
- Local sends are blocked while binding messages or binding tasks are still switching, so a fast send cannot land on the previous local Agent's bridge task/session.
- Local message hydration, optimistic user/assistant nodes, active-path filtering, submit context, and task-event SSE ownership all require `source=local_agent` plus exact binding, connection, and agent-session ids.
- The local Agent I/O panel now shows richer bounded input/context/output details on assistant bubbles only; user bubbles do not expand the large I/O context inline.
- Backend compressed context is accepted only when `coverage_node_ids` are non-empty and all covered nodes belong to the current binding/session. Source-only or other-binding compressed summaries are dropped from the bridge payload, workspace request, persisted I/O, and server fallback context replay.
- Duplicate local tool-request decisions now recheck active binding ownership, the exact bridge task, and matching binding/task ids before returning an existing decision.
- Alembic `20260614_0041` marks conflict-binding pending changes as `denied` and fills `denied_at`, matching runtime terminal semantics.

### Exact Binding Validation

```text
cd apps/agent-console && /usr/local/bin/npm test -- AgentWorkspacePage.team-launch.test.tsx ChatMessageList.render.test.tsx --reporter=dot
30 passed

cd services/api-server && .venv/bin/python -m pytest tests/test_local_agents.py tests/test_hao_cli.py -q
133 passed

cd apps/agent-console && npm run lint -- --pretty false
passed

cd apps/agent-console && npm run build
passed

cd services/api-server && .venv/bin/python -m ruff check app/api/agents/agent_local.py app/api/agents/common.py app/db/models.py tests/test_local_agents.py
passed

cd services/api-server && .venv/bin/python -m py_compile app/api/agents/agent_local.py app/api/agents/common.py app/db/models.py alembic/versions/20260614_0041_local_agent_active_session_guard.py
passed

git diff --check
passed

python3 scripts/validate-docs.py
passed
```

### Exact Binding Reviews

- Frontend reviewer Raman returned `PASS`: the top-enable restore path, cold-cache exact binding, Claude Code -> hao -> Claude Code switching, source/binding/connection/session filters, and assistant-only I/O rendering have no remaining blocker.
- Backend reviewer Gauss returned `PASS`: compressed-context coverage gating, duplicate tool-request active-binding revalidation, bridge-task ownership guards, and migration pending-change denial semantics have no remaining blocker.

Consensus state: no remaining blocking frontend or backend findings for the user's Claude Code/hao cross-talk repro, local Agent I/O detail, compressed summary replay, duplicate local tool decisions, or conflict migration cleanup.
