# Terminal Capability Shared State

Category: `session-log`

Tags: `terminal`, `redis`, `websocket`, `security`, `multi-replica`

## Summary

Closed the remaining multi-replica Terminal capability gap.

- Production token and session state now uses Redis instead of process-local
  dictionaries.
- Token issuance, one-time consumption, terminal binding, expired-session
  cleanup, and per-principal session reservation execute atomically through Lua.
- Redis Cluster hash tags keep each token and its principal session set in the
  same slot.
- Active WebSockets renew a 90-second lease every 30 seconds. API instance
  failure therefore releases capacity after the lease expires.
- Production fails closed with HTTP 503 or WebSocket 1013 when the shared store
  is unavailable. Only development and test environments may use the in-memory
  fallback.
- Redis keys contain SHA-256 token/principal digests rather than raw identity
  values; the one-time token secret is not stored directly.

## Changed Files

- `services/api-server/app/services/terminal_capability_store.py`
- `services/api-server/app/api/terminal.py`
- `services/api-server/app/db/models.py`
- `services/api-server/tests/test_terminal_capability_store.py`
- `services/api-server/tests/test_terminal_websocket.py`
- `docs/development/desktop/README.md`
- `omx_wiki/session-2026-07-12-authenticated-terminal-sessions.md`

## Verification

- Backend Terminal/CORS/update regression: `22 passed`.
- Backend Session/Auth/Terminal regression: `42 passed`.
- Real temporary Redis tests prove cross-instance one-time consumption, atomic
  concurrent session caps, lease expiry reclamation, expiry rejection, and
  terminal mismatch invalidation.
- Backend Ruff and py_compile passed.
- Agent Console Terminal/API regression: `5 files / 32 tests passed`.
- Desktop full Vitest: `31 files / 278 tests passed`.
- Desktop main-process build and Agent Console production build passed.

## Verification Boundary

- The full backend suite now advances past the historical
  `Session = UserSession` collection blocker, but the existing Okta SLO
  integration file still has nine unrelated failures around SAML certificate
  fixture paths, stale `validate_session` expectations, and endpoint 500s.
  This task does not claim the repository-wide backend suite is green.

## Remaining External Gates

- Apple Developer ID signing and notarization.
- Windows Authenticode signing.
- Production Sentry credentials and sourcemap upload evidence.
