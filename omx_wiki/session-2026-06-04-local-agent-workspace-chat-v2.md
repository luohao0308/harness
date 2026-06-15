# Local Agent Workspace Chat V2

Category: `session-log`

Tags: `local-agent`, `workspace`, `chat-surface`, `hao`, `bridge`, `session`

## Summary

Implemented the next local Agent version by integrating local bridge-backed conversations into the existing Agent Workspace chat surface. V2 keeps Harness as the source of truth for connections, bindings, `AgentSession`, `AgentMessage`, Run, events, and tool audit, while the browser only selects a registered local connection and sends messages through the local-Agent API.

## Planning Documents

- `.omx/plans/prd-local-agent-workspace-chat-v2.md`
- `.omx/plans/test-spec-local-agent-workspace-chat-v2.md`

## Delivered

- Added Workspace-level local Agent controls that list registered local connections for the current Agent, show online/offline/revoked projection, display workspace root, and link back to Agent Studio when no local bridge is connected.
- Added local Agent mode inside the existing `ChatSurface` instead of a separate chat UI. The same message list, composer, history rail, Run detail link, and inspector surfaces remain in use.
- Added connection selection, binding creation/resume, and server-backed `AgentSession` message loading in `AgentWorkspacePage`.
- Projected local `AgentMessage` history into the existing `ConversationNode` tree under deterministic `local-agent:<binding_id>` / `local-msg:<message_id>` identifiers, so refresh/reconnect can recover readable history from the API.
- Added optimistic pending user/assistant nodes while the bridge task is queued. If a bridge is offline, the UI keeps the message pending and explains that bridge recovery will continue processing.
- Added local send path through `POST /api/agents/local-agent/bindings/{binding_id}/messages`; browser still cannot register devices or consume pair tokens.
- Added API-owned pending task projection through `GET /api/agents/local-agent/bindings/{binding_id}/tasks`, so reload/offline state can recover queued local assistant nodes without trusting browser memory.
- Added stale-heartbeat offline projection and binding-list API coverage for owner/admin/operator boundaries.

## Boundary

- V2 does not enable Codex CLI or Claude Code executable adapters.
- V2 does not make the browser a bridge. Pairing, device credential registration, heartbeat, task pull, ack, and event reporting remain bridge-only.
- V2 serializes local sends per active binding in the UI by holding the composer while one pending local response is outstanding.
- Pending local messages are visible in the Workspace projection; authoritative completion still comes from bridge-reported `assistant_done` writing `AgentMessage`.

## Code Review Closeout

- Code/security复审 returned `APPROVE` after fixes for pair-token replay/race resistance, atomic local sends, leased-task pull behavior, terminal bridge events, lifecycle audit, daemon credential handling, and redaction.
- Architecture复审 returned `WATCH` with no blockers after binding-scoped idempotency, API-owned pending projection, and terminal ack immutability were fixed.
- The remaining `WATCH` item is V3 scope: bridge `tool_result` evidence is currently stored as observation only and must become policy/approval/audit-governed before local tools are treated as Harness-authorized execution.

## Verification

```text
cd services/api-server && .venv/bin/python -m pytest tests/test_local_agents.py -q -> 11 passed
cd services/api-server && .venv/bin/python -m pytest tests/test_hao_cli.py -q -k "bridge_pair_once or api_client_ignores or bridge_daemon" -> 3 passed
cd services/api-server && .venv/bin/python -m ruff check app/api/agents/agent_local.py app/api/agents/_workspace_chat_helpers.py app/api/schemas.py app/db/models.py app/events/event_types.py app/cli/hao/api_client.py app/cli/hao/main.py tests/test_local_agents.py tests/test_hao_cli.py alembic/versions/20260611_0038_create_local_agent_connections.py -> passed
cd services/api-server && .venv/bin/python -m py_compile app/api/agents/agent_local.py app/api/agents/_workspace_chat_helpers.py app/api/schemas.py app/db/models.py app/events/event_types.py app/cli/hao/api_client.py app/cli/hao/main.py tests/test_local_agents.py tests/test_hao_cli.py -> passed
cd apps/agent-console && npm test -- AgentWorkspacePage.team-launch.test.tsx -> 2 passed
cd apps/agent-console && npm test -- AgentListPage.studio.test.tsx ChatSurface.shell.test.tsx AgentWorkspacePage.team-launch.test.tsx -> 22 passed
cd apps/agent-console && npm run lint -- --pretty false -> passed
python3 scripts/validate-docs.py -> passed
git diff --check -> passed
```
