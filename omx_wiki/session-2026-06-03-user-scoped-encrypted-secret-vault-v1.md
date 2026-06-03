# User Scoped Encrypted Secret Vault V1

Category: `session-log`

Tags: `secrets`, `security`, `settings`, `model-gateway`, `connectors`, `mcp`, `notifications`

## Summary

Implemented the user/org scoped encrypted secret vault for business integration keys. Startup-level secrets remain environment variables, and platform API keys remain hash-only.

## Delivered

- Added `stored_secrets` with encrypted values, key id, scope, provider, purpose, owner user, active/disabled status, last-used metadata, and active uniqueness indexes.
- Added secret service helpers for encrypt/decrypt, upsert, list, disable, and resolution.
- Added `/api/secrets` list/upsert/delete plus admin-only `/api/secrets/import-env`.
- Resolution order is current user active secret, organization active secret, then legacy env fallback when enabled.
- Model Settings writes raw provider keys into `StoredSecret`, persists no raw `providers[*].api_key`, and returns configured/source/id metadata.
- Knowledge connector, MCP runtime, Tavily/web research, and notification-channel secret paths now resolve through the secret vault while keeping legacy fallback compatibility.
- Agent Console adds `/settings/secrets`, navigation, API helpers, user/org secret views, admin-only env import/org editing, delete/disable, and one-time password inputs that clear after save.
- Model Settings displays key configured/source state and treats stored keys as usable without echoing raw values.

## Security Boundaries

- Business integration secrets are in DB; startup secrets such as database URL, JWT secret, Redis, and `HARNESS_SECRET_ENCRYPTION_KEY` stay in env.
- Production secret read/write fails closed without usable encryption configuration.
- API responses and audit payloads never include raw secret material.
- User-scoped secrets are visible and manageable only by their owner; org secrets are admin-managed.
- Legacy env fallback remains compatibility-only and is visible as a source, not a new write path.

## Verification

```text
services/api-server/.venv/bin/python -m pytest services/api-server/tests/test_secrets.py services/api-server/tests/test_settings.py services/api-server/tests/test_knowledge_connectors.py services/api-server/tests/test_tool_registry.py services/api-server/tests/test_observability.py -q -> 102 passed
services/api-server/.venv/bin/python -m ruff check services/api-server/app services/api-server/tests -> passed
cd services/api-server && rm -f /tmp/harness-secret-vault.sqlite && DATABASE_URL=sqlite:////tmp/harness-secret-vault.sqlite .venv/bin/alembic upgrade head -> reached 20260608_0035
cd apps/agent-console && npm test -- SecretVaultPage.test.tsx ModelSettingsPage.test.tsx -> 10 passed
cd apps/agent-console && npm run lint -- --pretty false -> passed
cd apps/agent-console && npm run build -> passed
cd services/api-server && .venv/bin/alembic upgrade head -> local Postgres reached 20260608_0035
curl --noproxy '*' -sS http://127.0.0.1:8000/health -> {"status":"ok","service":"api-server"}
curl --noproxy '*' -sS -I http://127.0.0.1:5173/ -> HTTP 200
curl --noproxy '*' -sS -H 'Authorization: Bearer dev-engineer-token' http://127.0.0.1:8000/api/secrets -> {"items":[],"next_cursor":null}
```

## Review

- Frontend review: PASS.
- Test coverage review: initial FINDINGS for list/delete/import-env/model scope coverage; fixed and re-reviewed PASS.
- Security review: initial FINDING for helper-level cross-user disable risk; fixed with owner check and regression test, then re-reviewed PASS.

## Notes

- `/api/tools/capabilities/test-invoke` now passes the backend app workspace root to `ToolRunner`, matching other ToolRunner entrypoints and restoring existing read-file test-invoke behavior.
- Local dev services were restarted in tmux sessions `harness-api-langgraph` and `harness-console-langgraph`. API uses a local development `AUTH_JWT_SECRET`; startup-level secrets still remain env-managed and are not part of the stored-secret vault.
- Local follow-up imported existing business keys into `makerhao` / `2429260713@qq.com` as user-scoped active `StoredSecret` rows without printing raw values: `deepseek-flash` and `deepseek-pro` from the local `DEEPSEEK_API_KEY`, plus `dify` and `coze` from legacy `system_settings` connector secrets. A temporary local JWT-backed `/api/secrets` check returned 4 redacted `stored_secret_user` items. Legacy env/system settings were left in place for compatibility.
