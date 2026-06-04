# Local Agent Bridge Conversation V1

Category: `session-log`

Tags: `local-agent`, `hao`, `agent-studio`, `bridge`, `audit`, `workspace`

## Summary

Implemented the approved local Agent connection flow as an extension of the existing Harness `Run / Event / Tool / Policy / Session` model. Agent Studio now generates a local pairing command, discovers registered local bridges, shows adapter status, and revokes devices without adding a cloud-Agent creation path.

## Planning Documents

- `.omx/plans/prd-local-agent-bridge-conversation-v1.md`
- `.omx/plans/test-spec-local-agent-bridge-conversation-v1.md`

## Delivered

- Added local-Agent DB models and Alembic revision `20260611_0038` for pairing tokens, device connections, conversation bindings, bridge tasks, and bridge event receipts.
- Added local-Agent API routes for pairing create/revoke, bridge registration, connection list/status/revoke, heartbeat, conversation binding, owner-only message send, task pull/ack, and idempotent bridge event ingest.
- Kept API/DB as the source of truth: local Agent sends create/bind `AgentSession`, create Workspace `Task` Runs, queue bridge tasks, append `AgentEvent`, and write local tool evidence as `ToolCall`.
- Kept bridge untrusted: device token is required for heartbeat/task/event APIs, revoked devices are rejected, and bridge cannot write generic messages directly.
- Added secret/path redaction and bounded stdout/stderr payload handling for local bridge event/tool payloads.
- Added `hao bridge pair --daemon` and `hao bridge run`; pair stores `~/.hao/bridge.json`, can daemonize, and supports deterministic `--once` execution.
- Added fake bridge behavior for pair/register/heartbeat/pull/ack/delta/done without host command execution.
- Added hao bridge behavior that reuses existing `run_headless_once`; it reports success through `assistant_done` and failures through `assistant_error`.
- Updated Agent Studio UI to show `选择职业模板` plus `接入本地 Agent`, remove any `新建云端 Agent` path, expose the three-step pairing wizard, display fake/hao/Codex/Claude adapter states, and revoke local devices.
- Removed browser-side bridge registration from the UI; pair tokens are consumed only by a local bridge command.

## Boundary

- v1 enables fake and hao adapters. Codex CLI and Claude Code are visible as future disabled adapters.
- "Terminal closed can continue" means the bridge daemon remains alive after the foreground terminal exits. If the daemon or computer stops, Harness keeps readable history and can continue after reconnect.
- hao bridge requires a valid hao/Harness API token for real headless execution. Missing auth fails closed and reports `assistant_error`; it does not fake completion.
- Browser UI generates commands and reads connection projections only. It does not own business sessions or device registration.

## Code Review Closeout

- Code/security review initially requested changes for pair-token race resistance, send atomicity, repeated leased-task pull, terminal-event replay, lifecycle audit, daemon credential leakage, and hyphenated secret redaction. Those blockers are fixed and the final code/security复审 returned `APPROVE`.
- Architecture review initially blocked on binding-scoped idempotency, API-owned pending projection, and bridge task terminal-state safety. Those blockers are fixed and the final architecture复审 returned `WATCH` with no blockers.
- The remaining `WATCH` item is intentionally deferred to V3: bridge-reported `tool_result` is still an observation, not Harness policy authority.

## Verification

```text
cd services/api-server && .venv/bin/python -m pytest tests/test_local_agents.py -q -> 11 passed
cd services/api-server && .venv/bin/python -m pytest tests/test_hao_cli.py -q -k "bridge_pair_once or api_client_ignores or bridge_daemon" -> 3 passed
cd services/api-server && .venv/bin/python -m pytest tests/test_agents.py -q -k "agent_studio_create_clone" -> 2 passed
cd services/api-server && .venv/bin/python -m ruff check app/api/agents/agent_local.py app/api/agents/_workspace_chat_helpers.py app/api/schemas.py app/db/models.py app/events/event_types.py app/cli/hao/api_client.py app/cli/hao/main.py tests/test_local_agents.py tests/test_hao_cli.py alembic/versions/20260611_0038_create_local_agent_connections.py -> passed
cd services/api-server && .venv/bin/python -m py_compile app/api/agents/agent_local.py app/api/agents/_workspace_chat_helpers.py app/api/schemas.py app/db/models.py app/events/event_types.py app/cli/hao/api_client.py app/cli/hao/main.py tests/test_local_agents.py tests/test_hao_cli.py -> passed
cd services/api-server && DATABASE_URL=sqlite:////tmp/harness-local-agent-0038.sqlite AUTH_JWT_SECRET=test-harness-jwt-secret-32-characters-min HARNESS_SECRET_ENCRYPTION_KEY=test-harness-secret-encryption-key-32-min .venv/bin/alembic upgrade head -> upgraded through 20260611_0038
cd apps/agent-console && npm test -- AgentListPage.studio.test.tsx -> 3 passed
cd apps/agent-console && npm test -- AgentWorkspacePage.team-launch.test.tsx AgentListPage.studio.test.tsx ChatSurface.shell.test.tsx -> 22 passed
cd apps/agent-console && npm run lint -- --pretty false -> passed
python3 scripts/validate-docs.py -> passed
git diff --check -> passed
```
