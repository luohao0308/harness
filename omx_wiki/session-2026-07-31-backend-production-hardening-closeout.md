# Backend Production Hardening Closeout

Category: `session-log`

Tags: `backend`, `saml`, `auth`, `onboarding`, `models`, `hao`, `team`, `knowledge`, `alembic`

## Summary

Closed the repository-controlled backend gaps found while reviewing the Desktop
production path. The result is one warning-free backend regression baseline
across enterprise identity, first-run setup, model routing, local-agent approval
resume, Team Runtime, Knowledge, task execution, and shared services.

## Production Contracts

- SAML certificate/metadata validation, SessionIndex logout, RelayState, Azure
  and Okta claims, role mapping, rate limiting, and hostile XML handling are
  covered by current integration tests.
- Session and onboarding state use UTC-safe behavior and authenticated,
  authorized step progression. Public registration remains closed by default in
  production.
- Platform provider settings are validated from server configuration at runtime.
  Reserved platform provider rows are rebuilt rather than trusted from persisted
  settings, model names are allowlisted, and custom providers retain independent
  credentials even when they use a historical provider name.
- Platform API keys are returned only for a fully canonical platform-managed
  provider identity. A client-supplied management flag alone cannot expose the
  server credential.
- HAO approval resume keeps model identity and non-sensitive progress in bridge
  state, while each stream token lives in a request-scoped `0600` file. The state
  stores only its reference and pending-request removal deletes the token file.
- Team Runtime resolves exact provider/model rows, validates platform model
  selections, preserves delegated wake evidence, and relies on the database
  invariant that only one active or paused Team Goal exists per Team.
- Executor queue tests are deterministic, task/model/tool audit ordering is
  stable, and Knowledge web research/RAG test doubles follow current scoped
  contracts.
- Alembic revision `20260628_0049` merges four branches into one current head.

## Key Files

- `services/api-server/app/config/saml_config.py`
- `services/api-server/app/services/saml_service.py`
- `services/api-server/app/services/session_service.py`
- `services/api-server/app/services/onboarding_service.py`
- `services/api-server/app/core/config.py`
- `services/api-server/app/agents/model_gateway.py`
- `services/api-server/app/cli/hao/main.py`
- `services/api-server/app/teams/model_runtime.py`
- `services/api-server/app/teams/service.py`
- `services/api-server/alembic/versions/20260628_0049_merge_current_heads.py`
- `services/api-server/tests/`

## Verification

- Model settings and gateway regression: `50 passed`.
- Validation/template/autofix/service regression: `94 passed`.
- Team and Team model runtime regression: `49 passed`.
- Session/Subagent warning-as-error regression: `43 passed`.
- Full backend regression: `1395 passed`, zero warnings.
- Repository-wide backend Ruff: passed.
- Alembic heads: `20260628_0049 (head)`.
- Documentation validation: passed.
- Git whitespace validation: passed.

## External Gates

- Real customer SAML IdP metadata/certificates and production claim mappings
  still require tenant-specific acceptance testing.
- Live model-provider latency, quota, billing, and failover require production
  credentials and provider-side observability.
- Apple Developer ID/notarization, Windows Authenticode, and production crash
  reporting credentials remain release-operator gates outside this backend
  closeout.
