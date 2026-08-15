# Desktop Local Runtime + SQLite Install-Ready Plan

## Status

- Workflow: `$plan --direct`
- Planning state: independently reviewed, approved, and implemented
- Product decision: Desktop is the primary operating surface; Web is a local extension of the running Desktop application.
- Runtime decision: one local `harnessd` process owns one canonical SQLite database.
- Required user configuration: model provider API key only.
- Implementation state: completed on 2026-08-07 with packaged native and Electron smoke evidence.

## Implementation Result

- Desktop starts and supervises one packaged `harnessd` on `127.0.0.1` and stores canonical application data in one profile-scoped SQLite runtime.
- Agent, Task, Team, Run/events, Terminal, Tools, Subagents, Eval, Observability, model settings, and the authenticated Web extension are present in the packaged route inventory.
- Redis, Dramatiq, `psycopg`, `psycopg2`, and `asyncpg` are excluded from and audited out of the native local-runtime archive; Docker remains optional.
- The normal Desktop workspace opens without a model key. The only clean-install secret input is under `Settings > 模型与密钥`, backed by Electron secure storage; missing credentials block only model execution.
- Desktop settings use an independent Codex-style two-column space, while the browser retains the advanced data and observability console.
- The optimized native runtime reaches its ready handshake in a clean-profile P95 of 2688 ms. Business routers hydrate on the first business API request before route matching, then remain resident for the process lifetime. The final packaged manifest contains 331 verified files, including the bundled model-pricing source document.

## Requirements Summary

Deliver an install-ready Harness application with this user contract:

```text
Install Harness Desktop
-> launch the application
-> use the local workspace, files, terminal, and settings immediately
-> enter the model API key under Settings > Model and API Key before the first model run
-> use Agent / Task / Team / Run from Desktop
-> optionally open the local Web extension
```

The default product runtime must not require the user to install or operate Python,
PostgreSQL, Redis, Docker, or a separate API process. Desktop and Web must share the
same local API, records, events, jobs, settings, and model configuration.

Docker remains optional and capability-scoped: it may be used for isolated code or
shell execution, but its absence must not block chat, Agent, Task, Team, Run,
approval, knowledge, or Web-extension workflows.

## Current-State Evidence

- Backend defaults still point at PostgreSQL, Redis, and the mock gateway
  (`services/api-server/app/core/config.py:40-54`).
- The SQLAlchemy engine already has a SQLite branch with WAL, NORMAL synchronous
  mode, and a 5-second busy timeout (`services/api-server/app/db/session.py:8-25`).
- Alembic reads the same configured database URL, but a full fresh-file SQLite
  upgrade is not yet a release gate (`services/api-server/alembic/env.py:17-46`).
- Models contain some dual-dialect partial indexes, proving partial SQLite intent,
  but historical migrations and lock behavior still need a complete compatibility
  audit (`services/api-server/app/db/models.py:551-565`,
  `services/api-server/app/db/models.py:903-925`).
- Electron currently registers native services and opens a window; it does not start
  or supervise the FastAPI backend (`apps/desktop-app/src/main.ts:56-85`).
- The packaged application currently contains only `dist/**/*` and `package.json`;
  no backend sidecar is included (`apps/desktop-app/electron-builder.yml:12-21`).
- Desktop main-process API calls default to an external
  `http://localhost:8000` (`apps/desktop-app/src/shared/api-client.ts:1-24`).
- The existing Electron SQLite file contains only offline task/sync state, not the
  canonical Harness schema (`apps/desktop-app/src/services/offline-sync-runtime.ts:372-393`).
- Redis is a hard dependency for Dramatiq broker creation
  (`services/api-server/app/workers/broker.py:1-10`) and is part of readiness
  (`services/api-server/app/api/health.py:30-55`).
- Team runtime uses a PostgreSQL advisory lock and only a process-local lock for
  SQLite (`services/api-server/app/workers/team_runtime_worker.py:496-522`).
- Terminal capability state uses an in-memory implementation in tests and as a
  development Redis failure fallback, but production selects Redis
  (`services/api-server/app/services/terminal_capability_store.py:408-445`).
- Missing/placeholder model credentials currently activate mock output
  (`services/api-server/app/agents/model_gateway.py:567-580`,
  `services/api-server/app/agents/model_gateway.py:812-813`).
- Electron already has a reusable `safeStorage` credential pattern
  (`apps/desktop-app/src/services/phase6-store.ts:278-305`).
- Desktop and browser already share the Agent Console codebase; the desktop build
  only changes router/API build inputs before copying the renderer
  (`apps/desktop-app/scripts/copy-renderer.mjs:14-51`).
- The current operating documentation explicitly requires separate API and Console
  processes before launching Electron (`docs/runbooks/local-development.md:159-169`).
- Current API startup validates JWT, secret-encryption, and production model credentials
  before serving traffic (`services/api-server/app/core/config.py:272-288`,
  `services/api-server/app/main.py:98-106`), while fresh admin bootstrap currently
  expects email/password-oriented configuration
  (`services/api-server/app/bootstrap/first_admin.py:17`).
- The shared browser API client currently reads bearer credentials from localStorage,
  which is not an acceptable local-runtime bootstrap boundary
  (`apps/agent-console/src/features/tasks/api.ts:54-79`).
- The existing execution contract says PostgreSQL is the production path; this plan
  intentionally replaces that rule for the new local-only product direction
  (`docs/ai/00-execution-protocol.md:35-44`).

## Architecture Decision

```text
Harness Desktop (Electron main process)
  |
  | starts, authenticates, monitors, and stops
  v
harnessd (one local backend process, loopback only)
  |-- FastAPI HTTP/SSE/WebSocket API
  |-- local owner/session bootstrap
  |-- model provider runtime
  |-- persistent job coordinator
  |-- Team/subagent scheduler
  |-- static Web-extension assets
  `-- one canonical harness.sqlite3

Electron renderer -------------------|
Local browser Web extension ---------|--> same API, same records, same events

Optional Docker engine -----------------> sandbox-only capabilities
```

### Binding Decisions

1. SQLite is the only active database in the install-ready local runtime.
2. `harnessd` is the only process allowed to open the canonical SQLite database for
   application writes. Team/tool subprocesses communicate through the local API or
   an internal IPC channel; they do not open independent write connections.
3. The Web extension is served by `harnessd` and is available only while Harness is
   running, including close-to-tray background mode.
4. The first release binds only to `127.0.0.1`. LAN/public exposure, remote access,
   hosted sync, and multi-user server operation are separate product decisions.
5. The default local identity is created automatically. Users do not configure auth,
   database credentials, ports, or service accounts.
6. The model API key is stored through Electron `safeStorage`; it is never stored in
   plaintext in SQLite, renderer storage, command-line arguments, logs, or crash
   reports.
7. Missing or invalid model credentials produce a setup-required/error state. Mock
   output is restricted to explicit test/demo mode and must always carry a visible
   demo marker.
8. PostgreSQL/Redis/Dramatiq remain migration sources or legacy deployment code only
   during the transition. They are not started, probed, or required by the packaged
   local runtime.
9. Docker absence is represented as an unavailable sandbox capability, not as a
   failed application readiness state.
10. Electron holds the application single-instance lock, and `harnessd` holds a
    lifetime OS-level exclusive lock for the selected runtime directory before opening
    SQLite. A second runtime fails before acquiring a database connection.
11. The phrase "model API key is the only required configuration" applies to clean
    installs. A legacy PostgreSQL import may additionally require source credentials
    and an explicit local-owner mapping; it is an upgrade workflow, not first-run setup.
12. After runtime readiness, Electron loads the Desktop renderer from the exact signed
    loopback `harnessd` origin so API, SSE/WebSocket, and HttpOnly session cookies are
    same-origin. The existing `harness-app://renderer` bundle is retained only as a
    minimal startup/recovery screen. Preload APIs are exposed only to the verified
    loopback origin and navigation outside it is blocked.
13. If Electron `safeStorage` is unavailable, the local profile prohibits every
    persistent secret write, including `stored_secrets`. Model and integration secrets
    may exist only in the current authenticated process session, the UI marks them
    session-only, and restart leaves no undecryptable ciphertext.
14. Local-principal bootstrap has two exclusive modes: a clean install creates the
    default local owner; a legacy import builds an independent candidate, skips default
    owner creation, imports/maps one selected principal, validates its organization
    membership, records it in local runtime metadata, and only then switches the active
    database pointer.

## Data Ownership And Paths

Canonical user data lives outside the application bundle so upgrades cannot replace
it:

```text
<Electron userData>/
  runtime/
    harness.sqlite3
    backups/
    logs/
    runtime.json
  secrets.json              # encrypted safeStorage payloads only
  renderer-cache/
```

The exact OS path is resolved from Electron `app.getPath('userData')`; no code may
write mutable state under the signed `.app`, Windows installation directory, Linux
AppImage mount, or Electron ASAR.

SQLite requirements:

- WAL mode, foreign keys enabled, `busy_timeout`, and bounded checkpointing.
- Alembic is the only production schema migration mechanism; `Base.metadata.create_all`
  remains test/bootstrap support and cannot be used as release evidence.
- Startup runs `PRAGMA quick_check`; backup/restore uses the SQLite backup API rather
  than copying an open database file.
- Schema upgrades never mutate the active database in place. `harnessd` acquires the
  runtime ownership lock, stops writes, verifies free space and source integrity,
  creates a candidate with the SQLite backup API, migrates and validates only the
  candidate, closes all handles, then atomically switches a runtime manifest/pointer.
- Failure before pointer switch leaves the source active. Failure after pointer switch
  restores the previous pointer before accepting API traffic. The prior database and
  migration manifest remain available for rollback.

## Local Job And Concurrency Contract

Replace Redis/Dramatiq scheduling with a persistent SQLite-backed coordinator owned
by `harnessd`:

- Add a `runtime_jobs` table with `id`, `kind`, `payload`, `status`, `attempt`,
  `max_attempts`, `available_at`, `lease_until`, `lease_owner`, monotonic
  `lease_generation`, `heartbeat_at`, `dedupe_key`, `cancel_requested_at`,
  `finished_at`, `result_json`, `error`, and timestamps. A partial unique index owns
  active dedupe keys.
- One scheduler task atomically claims jobs inside a short transaction by changing the
  status, lease owner/generation, and deadline under a compare-and-set predicate, then
  dispatches bounded async/thread/subprocess work.
- The SQLite claim contract is `BEGIN IMMEDIATE` -> select the oldest eligible queued or
  expired job -> `UPDATE ... WHERE id=:id AND status=:expected_status AND
  lease_generation=:expected_generation` -> increment generation/set lease -> commit.
  Failure to update exactly one row retries selection. The active-dedupe invariant is a
  partial unique index on non-null `dedupe_key` for queued/running jobs.
- External worker subprocesses return results through API/IPC; only the coordinator
  changes durable job state.
- Delivery is explicitly at least once. On startup, expired `running` leases return to
  `queued` until the retry limit is reached. Durable state/event effects commit once
  through handler idempotency keys and lease-generation fencing; external side effects
  may be retried and every side-effecting handler must document an idempotency contract.
- Team/subagent wakeups are deduplicated by durable keys, not by process-local memory.
- Authoritative state change, event/audit row, and job/outbox transition occur in one
  SQLite transaction where the existing event contract requires atomicity.

Redis responsibilities map as follows:

| Current responsibility | Local replacement |
| --- | --- |
| Dramatiq broker and worker dispatch | SQLite `runtime_jobs` + one local coordinator |
| Team/recovery distributed lock | Single coordinator ownership + durable lease |
| Terminal one-time token/session cap | In-memory atomic store scoped to one `harnessd`; all tokens expire on restart |
| SAML rate limiting | SAML disabled in local-owner profile; no public login surface |
| Query cache | Bounded in-process TTL/LRU cache |
| Readiness Redis probe | Removed from local readiness |

## Local Authentication And Web Bootstrap

- On first clean launch, Electron creates a stable secret-vault encryption key and stores
  it through `safeStorage`. It creates a fresh JWT/session signing secret on every
  `harnessd` launch. Both are transferred over an inherited pipe before the FastAPI app
  imports runtime settings; neither appears in argv, environment files, stdout,
  `runtime.json`, or renderer state.
- If `safeStorage` is unavailable, Electron does not create a persistable vault key.
  `harnessd` selects a session-only secret backend and rejects every request that would
  write persistent secret ciphertext with a typed `SECRET_STORAGE_UNAVAILABLE` result.
  Non-secret application data remains persistent.
- Local settings construction is an explicit bootstrap path, not a mutation of process
  environment variables. The local profile still validates JWT and vault secrets, but
  bypasses only the model-key production startup requirement so the setup screen can
  load.
- An empty database creates one stable local organization, user, and membership without
  asking for email/password. This local principal is selected only by the local runtime
  profile; enterprise first-admin/SAML paths remain unreachable in that profile.
- Import mode disables that empty-database bootstrap. The importer must write and verify
  exactly one selected local principal in local runtime metadata before pointer switch;
  post-switch authentication reads that metadata and no extra automatic owner may exist.
- Electron receives the endpoint through a machine-readable handshake, installs an
  HttpOnly runtime-origin Desktop session cookie, and then loads the signed Desktop
  renderer from that exact origin. The packaged renderer must not persist the runtime
  bearer/session token in localStorage.
- `Open Web Extension` asks `harnessd` for a one-time browser bootstrap token and places
  it in the URL fragment. Browser bootstrap clears the fragment with
  `history.replaceState` before exchanging the token for an HttpOnly, Secure-when-
  applicable, SameSite=Strict cookie. The server stores only a hash, expiry, intended
  origin, and consumed state for the token.
- CORS accepts only the packaged renderer origin and the exact loopback runtime origin.
- Requests with unexpected `Host`/`Origin` values fail closed to reduce DNS-rebinding
  risk on HTTP, SSE, and WebSocket upgrade paths.
- The local API never listens on `0.0.0.0` in this release.
- The Web Model Settings surface can read provider/model/health metadata but cannot
  submit or replace the model key. Secret writes are available only through Electron
  IPC to `safeStorage`.

## Model Configuration Contract

- First launch reaches the normal Desktop workspace even when no model key exists; API
  process readiness and non-model local features must not depend on a configured model.
- The normal key surface lives under the Codex-style Desktop settings center and asks
  only for the API key while validating the shipped default provider/base URL/model.
  Provider/model overrides stay under advanced model settings. The legacy setup route
  redirects to this settings category instead of acting as a global application gate.
- Electron encrypts the key with `safeStorage`. If OS-backed encryption is unavailable,
  the key is session-only and the UI states that it must be entered again after restart.
- Electron transfers the decrypted key to `harnessd` through an inherited pipe or
  authenticated local IPC handshake, never through argv or a persisted plaintext env
  file.
- The backend exposes `setup_required`, `configured`, `healthy`, and `error` model
  states without returning the secret.
- Normal inference endpoints reject missing/invalid credentials with a typed error;
  `_uses_local_mock()` cannot be reached outside explicit test/demo configuration.

## Scope

### In Scope

- Canonical SQLite schema and full Alembic-on-SQLite gate.
- One local backend runtime with persistent job scheduling.
- Redis-free Agent, Task, Team, Run, terminal token, cache, health, and recovery paths.
- Electron sidecar lifecycle, crash recovery, logs, dynamic endpoint discovery, and
  package inclusion.
- First-run model API key setup using `safeStorage`.
- Shared local Web extension served from the same runtime.
- Existing PostgreSQL and Electron offline SQLite data import with non-destructive
  verification.
- Optional Docker capability detection and sandbox-only gating.
- macOS, Windows, and Linux package/build/smoke coverage.
- Documentation and support-contract replacement for install-ready local operation.

### Out Of Scope

- Public Internet or LAN hosting.
- Multi-user accounts, SAML, OAuth, enterprise RBAC, or multiple API replicas.
- Cloud synchronization or access while the desktop runtime is stopped.
- PostgreSQL/Redis compatibility as a release-blocking runtime after the transition.
- Bundling PostgreSQL or Redis binaries.
- Reimplementing unsafe Docker sandboxes directly on the host.
- Rewriting FastAPI or the shared Agent Console in another framework.

## Testable Acceptance Criteria

1. On clean supported release hosts with no Python, PostgreSQL, Redis, or Docker, the
   signed/packaged application reaches the normal Desktop workspace and can open the
   model-key settings category. Initial supported native
   sidecars are macOS x64/arm64, Windows x64, and Linux x64; Windows/Linux arm64 artifacts
   are removed from release claims until native builders exist.
2. First launch creates exactly one canonical `harness.sqlite3` under Electron
   `userData`; no PostgreSQL or Redis connection attempt appears in logs.
3. A fresh SQLite file reaches the single Alembic head with `alembic upgrade head` and
   passes `PRAGMA foreign_key_check` plus `PRAGMA quick_check`.
4. Missing model credentials never produce assistant mock text. The API returns a typed
   setup-required response; the attempted model action displays an inline explanation
   and a direct action to open the model-key settings category without blocking the rest
   of the application.
5. Saving a valid key, restarting Harness, and sending a prompt produces a non-empty
   real-provider response with provider/model/usage evidence and no `raw_response.mode=mock`.
6. A test injects a unique canary model secret and scans SQLite plus WAL/SHM, JSON state,
   renderer storage, process arguments, inherited environment, application logs, crash
   envelopes, and unpacked packaged assets; the scan finds zero plaintext occurrences.
   Plaintext exists only transiently in Electron/sidecar memory and the authenticated
   secret channel, while the persisted `safeStorage` payload is ciphertext.
7. Creating an Agent task in Desktop makes the same task ID and events visible in the
   Web extension with no reload, exactly one ID/event sequence, and projection latency
   P95 <= 2 seconds over 50 local samples.
8. Updating/cancelling a task in the Web extension is immediately reflected in Desktop
   through the existing SSE/WebSocket projection with no reload, exactly one terminal
   event, and projection latency P95 <= 2 seconds over 50 local samples.
9. Agent, Task, Team, Run, approvals, knowledge, and model settings pass with Redis
   unavailable and `REDIS_URL` unset.
10. A queued/running Team job survives termination and is reclaimed at least once after
    lease expiry. Durable state transitions and authoritative events commit once through
    idempotency keys and lease-generation fencing; crash tests cover failure before
    external work, after external work but before commit, and after commit but before
    acknowledgement.
11. Two simultaneous Team wake requests with the same dedupe key create one durable
    job and one corresponding authoritative event sequence.
12. Terminal one-time tokens cannot be reused or bound to another terminal; restart
    invalidates all outstanding tokens and releases active-session reservations.
13. Readiness reports database/runtime readiness independently from model setup and
    optional Docker capability status.
14. With Docker absent, core workflows remain healthy and Docker-backed tools render a
    clear unavailable capability state instead of failing the Run generically.
15. With Docker present, existing sandbox policy/audit behavior remains covered by its
    current tests and smoke path.
16. `Open Web Extension` opens an authenticated loopback page without prompting for a
    database, Redis, API port, or login credential.
17. Hostile bootstrap tests cover HTTP, SSE, WebSocket, malformed Host, missing/foreign
    Origin, sibling loopback ports, expired/reused tokens, and static-content CSP; each
    unauthorized path fails with 4xx/closed upgrade and creates no session.
18. Upgrade tests name exact old/new signed artifacts, compare a canonical
    Agent/Team/Run/event checksum before and after update, then exercise rollback to the
    old artifact while preserving the pre-upgrade runtime pointer and database.
19. PostgreSQL import and legacy `offline-sync.sqlite` import are repeatable, record row
    counts/content checksums, do not delete their sources, do not duplicate rows on
    rerun, and emit explicit reports for local-owner mapping, ID collisions, undecryptable
    legacy secrets, external artifacts, JSON/timezone normalization, pending queues, and
    the exactly-one imported local principal with no extra bootstrap owner.
20. Cold first-launch and warm-launch packaged startup each use five isolated samples and
    meet the existing phase budgets and total P95 <= 6000 ms, including candidate
    migration, runtime handshake, and health time.
21. Structured runtime evidence records database busy/locked counts, job lease recovery,
    migration stage/failure, sidecar restart count, Web bootstrap rejection reasons, and
    secret-redaction gate failures without including user content or secrets.

## Implementation Plan

### Phase 0: Lock The New Product Contract With Failing Tests

Goal: make the requested runtime boundary executable and prove the sidecar can ship
before changing the full schema or worker system.

1. Update architecture/product contracts to define Desktop + local Web extension as one
   product runtime and replace the PostgreSQL production invariant for this profile.
2. Add contract tests asserting that local runtime defaults resolve to SQLite, do not
   require Redis, do not use the mock gateway, and bind to loopback.
3. Specify failing tests for the local principal, stable vault key, per-launch session
   secret, pipe bootstrap, cookie-only Desktop auth, Web one-time token exchange, and
   Host/Origin checks across HTTP/SSE/WebSocket.
4. Inventory every background actor and enqueue call with `rg` coverage, including
   assignment, orchestration, subagent, recovery, Team, and alert evaluation. Record the
   required idempotency key and external-side-effect contract for every handler.
5. Add Electron lifecycle tests describing sidecar start -> health -> renderer and
   renderer close/tray -> runtime remains -> app quit -> runtime exits.
6. Add Electron single-instance and `harnessd` lifetime runtime-directory lock tests;
   the loser must fail before opening SQLite.
7. Run a Phase 0B native packaging spike that bundles a minimal FastAPI health endpoint,
   Alembic assets, and one SQLite migration without host Python. Build natively for
   macOS x64/arm64, Windows x64, and Linux x64; remove Windows/Linux arm64 from release
   targets until native builders exist.
8. Verify executable permissions, sanitized-`PATH` startup, runtime manifest/version
   compatibility, artifact checksum before spawn, nested signing/notarization, native
   imports, and process cleanup. Only then select/add the self-contained Python packager.

Primary files:

- `docs/00-product-spec.md`
- `docs/01-system-architecture.md`
- `docs/02-data-model-and-event-spec.md`
- `docs/03-api-spec.md`
- `docs/ai/00-execution-protocol.md`
- `services/api-server/tests/test_health_probes.py`
- `services/api-server/tests/test_model_gateway.py`
- `services/api-server/app/main.py`
- `services/api-server/app/bootstrap/first_admin.py`
- `services/api-server/app/agents/orchestrator.py`
- `services/api-server/app/agents/subagent_manager.py`
- `apps/agent-console/src/features/tasks/api.ts`
- `apps/desktop-app/src/__tests__/main.test.ts`
- `apps/desktop-app/src/__tests__/lifecycle.test.ts`
- `apps/desktop-app/electron-builder.yml`
- `.github/workflows/release.yml`
- new minimal sidecar build/smoke scripts

Exit gate: the new contract tests fail only on missing local-runtime behavior, and a
minimal signed/native sidecar starts without host Python on every declared release
target. No schema/worker implementation begins until both gates pass.

### Phase 1: Make The Canonical Schema Fully SQLite-Compatible

Goal: prove that the complete production schema and migrations work on a persistent
SQLite file.

1. Introduce an explicit local runtime profile and resolve its database URL from the
   Electron-provided data directory rather than a repository `.env` file.
2. Enable SQLite foreign keys and define checkpoint/connection behavior in the single
   engine entry point.
3. Run every historical Alembic migration against a fresh SQLite file; repair dialect
   branches for indexes, constraints, DDL, server defaults, and batch table changes.
4. Add `runtime_jobs` and any local runtime metadata tables through Alembic.
5. Implement candidate-database upgrades: runtime lock, source quick check, free-space
   check, backup-API candidate creation, candidate-only migration, FK/quick/replay
   validation, closed-handle pointer switch, and previous-pointer retention.
6. Add fault injection at backup, every migration boundary, integrity validation, pointer
   switch, and post-switch pre-serve recovery on macOS, Windows, and Linux.

Primary files:

- `services/api-server/app/core/config.py`
- `services/api-server/app/db/session.py`
- `services/api-server/app/db/models.py`
- `services/api-server/alembic/env.py`
- `services/api-server/alembic/versions/*.py`
- `services/api-server/tests/conftest.py`
- new SQLite migration/integrity tests under `services/api-server/tests/`

Exit gate: a temporary on-disk SQLite database upgrades from empty to head, restarts,
passes integrity checks, and executes representative Agent/Team/Run/Event CRUD; every
fault-injection point leaves either the old or candidate database selected and valid.

### Phase 2: Establish Local Identity, Authentication, And Secret Bootstrap

Goal: allow a clean install to reach model setup without weakening secret or browser
boundaries.

1. Add a local-runtime settings bootstrap that reads stable vault and per-launch session
   secrets from an inherited pipe before importing/constructing the FastAPI application.
2. Keep JWT and secret-vault validation enabled; bypass only the model-key production
   check until setup completes.
3. Add idempotent creation of one stable local organization, user, and membership without
   email/password, separate from enterprise first-admin bootstrap.
4. Add Electron write-only secure storage for the stable vault key and model key; emit a
   session-only warning when OS encryption is unavailable, reject persistent
   `stored_secrets` writes, and prove restart leaves no undecryptable ciphertext.
5. Replace packaged-renderer localStorage bearer auth with an HttpOnly runtime-origin
   Desktop cookie installed through the authenticated main-process bootstrap; local
   fetch/EventSource/WebSocket clients use the same runtime origin and cookie credentials.
6. Implement hashed, expiring, intended-origin, single-use Web bootstrap tokens plus
   HTTP/SSE/WebSocket Host/Origin enforcement and static CSP.

Primary files:

- `services/api-server/app/core/config.py`
- `services/api-server/app/main.py`
- `services/api-server/app/bootstrap/first_admin.py`
- `services/api-server/app/security/auth.py`
- new local bootstrap/auth API modules and tests
- `apps/desktop-app/src/main.ts`
- `apps/desktop-app/src/services/phase6-store.ts` or a focused secret store
- `apps/desktop-app/src/preload.ts`
- `apps/desktop-app/src/preload-api.ts`
- `apps/agent-console/src/features/tasks/api.ts`

Exit gate: a clean SQLite database opens the setup UI without email/password or model
key; exact canary scanning finds zero plaintext persistence while the stored payload is
encrypted; no-safeStorage restart tests leave no persistent secret ciphertext; hostile
bootstrap tests pass; a real Electron window completes authenticated GET, SSE, and
WebSocket traffic with no bearer/session value in localStorage.

### Phase 3: Replace Redis And Distributed Worker Semantics

Goal: make one `harnessd` process sufficient for all non-sandbox product capabilities.

1. Add a persistent local job repository/coordinator with atomic claim, lease owner,
   monotonic fencing generation, heartbeat, max attempts, retry, cancellation, partial
   unique dedupe, result, and crash-recovery behavior.
2. Route Team runtime, subagent recovery, assignment, orchestration, subagent manager,
   alert evaluation, and every inventoried Dramatiq actor/enqueue call through a backend
   interface with a local coordinator implementation.
3. Replace local Team/recovery lock assumptions with coordinator ownership and durable
   job leases; prohibit multiple local schedulers for the same database.
4. Select the in-memory terminal capability store explicitly for the local profile and
   retain one-time token/session-cap tests.
5. Disable SAML/public-login runtime in the local profile and select the bounded
   in-process query cache.
6. Remove Redis from local readiness and expose each optional capability separately.
7. Commit authoritative state, event/audit, and job/outbox transitions atomically; add
   handler-level idempotency for all external side effects.

Primary files:

- `services/api-server/app/workers/broker.py`
- `services/api-server/app/workers/team_runtime_worker.py`
- `services/api-server/app/workers/subagent_recovery_worker.py`
- `services/api-server/app/agents/orchestrator.py`
- `services/api-server/app/agents/subagent_manager.py`
- `services/api-server/app/services/terminal_capability_store.py`
- `services/api-server/app/security/saml_rate_limit.py`
- `services/api-server/app/cache/query_cache.py`
- `services/api-server/app/api/health.py`
- new local runtime job/coordinator modules and tests

Exit gate: the targeted backend suite passes with no Redis process or `REDIS_URL`;
crash-window tests before work, after external work/before commit, and after commit/
before acknowledgement prove at-least-once delivery with once-only durable effects.

### Phase 4: Consolidate To One Canonical SQLite Database

Goal: remove the split between backend business data and Electron offline-task data.

1. Make the local API authoritative for all task, sync, metadata, and runtime records.
2. Add an idempotent importer for existing `offline-sync.sqlite` tasks/operations.
3. Add an optional PostgreSQL-to-SQLite importer for existing installations; preserve
   IDs, timestamps, organization/user ownership, events, hashes, and foreign keys.
4. Require an empty/fresh target or abort on ID collisions. Ask for explicit local-owner
   mapping when the source contains multiple users/organizations; never silently merge
   tenants.
5. Mark legacy encrypted secrets as `requires_reconfiguration` instead of importing
   undecryptable ciphertext; copy external knowledge/file artifacts with hashes; define
   JSON/timezone canonicalization and pending offline-operation ordering/dedupe.
6. Produce source/target row-count and content-checksum evidence and leave source
   databases untouched.
7. Run import mode with automatic local-owner bootstrap disabled. Persist the chosen
   imported user/org/membership in local runtime metadata, verify it is unique and
   active, then switch the runtime pointer; post-switch auth must resolve that principal.
8. Remove the Electron `better-sqlite3` stores and offline promotion path only after
   importer and canonical API tests pass.

Primary files:

- `apps/desktop-app/src/services/offline-sync-runtime.ts`
- `apps/desktop-app/src/stores/sqlite-task-store.ts`
- `apps/desktop-app/src/stores/sqlite-offline-queue.ts`
- `apps/desktop-app/src/services/sqlite-sync-metadata.ts`
- `apps/desktop-app/package.json`
- `services/api-server/app/api/desktop_sync.py`
- new non-destructive migration/import tooling and tests

Exit gate: Desktop and Web read/write the same records through the API; import reports
cover owner mapping, collisions, secret reconfiguration, artifacts, normalized content,
pending operations, and exactly one imported local principal with no bootstrap owner;
Electron no longer opens a second application database.

### Phase 5: Make Real Model Setup The Only User Configuration

Goal: remove silent mock behavior and provide secure first-run setup.

1. Add local runtime model-state/bootstrap APIs that never return secret values.
2. Extend the current Electron secure credential store for the model provider key.
3. Add a main-process IPC boundary for write-only save, status, delete, and connection
   test operations.
4. Transfer the decrypted key to `harnessd` through a non-persisted secret channel.
5. Route first launch to the compact API-key setup state; keep provider/base/model under
   Advanced settings.
6. Restrict mock model construction to explicit test/demo configuration and show a
   persistent demo marker whenever enabled.
7. Keep the Web settings surface read-only for secret state; model key replacement is
   available only from the Desktop IPC-backed setup/settings surface.

Primary files:

- `services/api-server/app/agents/model_gateway.py`
- `services/api-server/app/core/config.py`
- `services/api-server/app/api/settings.py`
- `apps/desktop-app/src/services/phase6-store.ts` or a focused secret-store module
- `apps/desktop-app/src/preload.ts`
- `apps/desktop-app/src/preload-api.ts`
- `apps/agent-console/src/features/settings/pages/ModelSettingsPage.tsx`
- onboarding/model/settings regression tests

Exit gate: a clean first launch needs only the API key, restart retains secure access,
and mock text is impossible in normal packaged mode.

### Phase 6: Integrate And Supervise The Production `harnessd`

Goal: make the existing FastAPI backend a self-contained platform-specific sidecar.

1. Expand the Phase 0B-selected native packager from the minimal spike to the complete
   backend, migrations, runtime manifest, and required assets on each supported target.
2. Add `harnessd` startup arguments for data directory, loopback port `0`, log path,
   and local-runtime profile; secrets must not use argv.
3. Emit a single machine-readable ready handshake after migration, bootstrap, and bind.
4. Add an Electron runtime manager for spawn, timeout, health polling, crash restart,
   log routing, graceful shutdown, forced bounded cleanup, and update coordination.
5. Verify the runtime checksum/version before spawn; include it with `electron-builder`
   `extraResources` and sign/notarize the nested binary with the parent application.
6. Package both the minimal recovery renderer and signed runtime-served Desktop renderer.
   After readiness, set the HttpOnly Desktop cookie and load the exact loopback runtime
   origin; keep API/SSE/WebSocket relative and same-origin.
7. Restrict preload exposure and navigation to the verified runtime origin; checksum/
   version mismatch keeps Electron on the recovery screen and never opens API traffic.

Primary files:

- new `services/api-server/app/local_runtime.py` or equivalent entry point
- new desktop runtime build script(s)
- `apps/desktop-app/electron-builder.yml`
- `apps/desktop-app/package.json`
- new `apps/desktop-app/src/services/local-runtime.ts`
- `apps/desktop-app/src/main.ts`
- `apps/desktop-app/src/shared/api-client.ts`
- `apps/desktop-app/src/services/phase6-store.ts`
- `.github/workflows/release.yml`

Exit gate: a packaged application on every supported target starts the bundled runtime on a
free loopback port, opens the renderer only after runtime readiness, survives one forced
sidecar crash, and leaves no child process after full quit.

### Phase 7: Serve The Local Web Extension

Goal: expose the existing shared Agent Console as a browser extension of the same local
runtime without creating a second application or database.

1. Build a browser-target Agent Console artifact from the same source tree and include
   it in the local runtime package.
2. Serve the web artifact and history fallback from `harnessd` at the runtime origin.
3. Add the one-time browser bootstrap token exchange and secure cookie session.
4. Add an `Open Web Extension` desktop command and show the active local URL in Desktop
   settings without exposing reusable credentials.
5. Preserve Desktop-specific capability guards through `window.desktopApi`; the browser
   remains a data/inspection extension and does not imitate native file/window actions.

Primary files:

- `apps/agent-console/src/main.tsx`
- `apps/agent-console/src/app/routes.tsx`
- `apps/agent-console/src/features/tasks/api.ts`
- `apps/desktop-app/scripts/copy-renderer.mjs`
- `apps/desktop-app/src/services/system-integration.ts`
- `services/api-server/app/main.py`
- new local Web bootstrap/auth endpoints and tests

Exit gate: Desktop-created Agent/Team/Run data appears in an authenticated local browser
session with identical IDs/events, and no second API/database process is created.

### Phase 8: Make Docker Optional And Cut Over The Release Contract

Goal: preserve safe tool execution without making Docker an installation prerequisite.

1. Classify tools as local-safe, host-native with approval, or Docker-sandbox-required.
2. Detect Docker asynchronously after core readiness and publish capability state.
3. Disable only Docker-required tool actions when unavailable; preserve clear policy and
   audit evidence for the unavailable decision.
4. Keep current Docker sandbox/WarmPool tests as an optional capability lane.
5. Do not add an unrestricted host-execution fallback for tools that currently depend on
   container isolation.
6. Replace external API/PostgreSQL/Redis desktop startup instructions with installation,
   first-run key setup, data location, backup, reset, and recovery guidance.
7. Add release jobs for self-contained runtime build, artifact inclusion, fresh-install,
   cold/warm startup budgets, signed upgrade/rollback, data import, sidecar crash, secret
   canary scanning, and runtime evidence assertions.
8. Remove Redis/Dramatiq/PostgreSQL client runtime dependencies from the packaged artifact
   after the legacy import window closes; keep migration tooling separate if required.
9. Remove stale mock-model defaults and Docker-private-delivery wording from normal
   configuration examples.
10. Update progress/wiki/design/API documentation with the final runtime contract and
    explicit unsupported remote/multi-user boundary.

Primary files:

- `services/api-server/app/agents/executor.py`
- `services/api-server/app/sandbox/`
- `services/api-server/app/tools/`
- `apps/agent-console/src/features/sandboxes/`
- `docs/runbooks/local-development.md`
- `docs/desktop/README.md`
- `docs/runbooks/deployment.md`
- `docs/runbooks/troubleshooting.md`
- `services/api-server/.env.example`
- `apps/agent-console/.env.example`
- `.github/workflows/release.yml`
- `services/api-server/pyproject.toml`
- release/smoke scripts
- capability/readiness/smoke tests

Exit gate: clean no-Docker packaged smoke passes core workflows; Docker-enabled smoke
continues to prove sandbox allocation, policy, audit, and cleanup; signed fresh-install
and upgrade/rollback evidence passes; the user-facing install guide contains no required
PostgreSQL, Redis, Docker, Python, port, bearer-token, or database configuration step.

## Data Migration And Rollback

### SQLite Schema Upgrade

1. Acquire the Electron single-instance and `harnessd` runtime-directory locks before
   opening the active database.
2. Stop API writes, run `PRAGMA quick_check`, and verify free space for source + candidate
   + retained rollback copy.
3. Create a candidate with the SQLite backup API and migrate only the candidate.
4. Validate Alembic head, foreign keys, quick check, representative replay, and canonical
   Agent/Team/Run/event checksum against the candidate.
5. Close every source/candidate handle, fsync the candidate/manifest directory where the
   platform permits, and atomically switch the runtime manifest pointer.
6. A fault before switch keeps the source selected. A fault after switch restores the
   previous pointer before API traffic. Fault injection covers every numbered boundary
   on macOS, Windows, and Linux.

### Legacy PostgreSQL And Offline-SQLite Import

1. Treat the model-key-only promise as a clean-install contract. Legacy PostgreSQL import
   may request source connection credentials and a local-owner mapping.
2. Quiesce source writes through a maintenance window or consistent export transaction;
   create the target schema fresh through Alembic and abort if the target is not empty.
3. If multiple organizations/users exist, require an explicit selected owner/org or a
   separately reviewed mapping file. Never silently merge tenants or rewrite IDs.
4. Import tables in foreign-key order while preserving stable IDs/timestamps. Abort on
   collisions; canonicalize timezone/JSON representations before hashing.
5. Do not copy legacy encrypted `stored_secrets` ciphertext into the new vault. Import
   metadata as `requires_reconfiguration` and list affected integrations without values.
6. Copy external knowledge/file artifacts into the runtime data directory with path
   containment and content-hash verification.
7. Import pending offline operations after authoritative entities, preserving dedupe keys
   and ordering; conflicts remain pending for explicit reconciliation rather than being
   silently applied.
8. Compare row counts and stable content checksums for users/orgs, agents, tasks, runs,
   events, model calls, Team records, knowledge, approvals, evals, and settings; run FK,
   quick-check, and representative read/replay queries.
9. Keep clean-install local-owner bootstrap disabled throughout import. Write the chosen
   user/org/membership into local runtime metadata, validate uniqueness/active status,
   and switch the pointer only after an authentication probe resolves that principal.
10. Keep source PostgreSQL and legacy offline SQLite files untouched until the documented
   retention window expires. Rerunning the importer produces no duplicate target rows.

## Verification Matrix

### Backend

```bash
cd services/api-server
DATABASE_URL=sqlite+pysqlite:////tmp/harness-local-runtime.sqlite .venv/bin/alembic upgrade head
DATABASE_URL=sqlite+pysqlite:////tmp/harness-local-runtime.sqlite .venv/bin/alembic current
.venv/bin/python -m pytest tests -q
.venv/bin/python -m ruff check app tests alembic
```

Add focused suites for:

- fresh SQLite migration, candidate/pointer fault injection, restart, backup, restore,
  free-space failure, and integrity;
- complete actor/enqueue inventory; runtime job atomic claim, lease generation,
  at-least-once retry, durable-effect idempotency, outbox, dedupe, cancel, and all three
  crash windows;
- local principal/bootstrap, stable vault key, per-launch session key, Desktop cookie,
  no-safeStorage persistent-write rejection/restart, Web token hashing/expiry/consumption,
  real Electron authenticated GET/SSE/WebSocket, Host/Origin, and CSP;
- Redis-free health, Team, subagent, terminal, cache, and rate-limit profile;
- model setup-required, secure configuration, real provider, and mock rejection;
- PostgreSQL/offline-SQLite owner mapping, collision abort, secret reconfiguration,
  import-mode bootstrap suppression, exactly-one principal auth probe, external-artifact
  hashing, pending-operation handling, idempotency, and checksums.

### Agent Console

```bash
cd apps/agent-console
npm test
npm run lint -- --pretty false
npm run build
npm run e2e:smoke
```

Add focused browser/Desktop parity coverage for task IDs, Team events, Run detail,
settings status, optional sandbox state, and no document-level overflow.

### Desktop And Packaging

```bash
cd apps/desktop-app
npm test
npm run build:main
npm run build:renderer
npm run package
npm run test:startup-budget
```

Packaged smoke must run natively on macOS x64/arm64, Windows x64, and Linux x64. The
release configuration must stop claiming Windows/Linux arm64 until native sidecar
builders and the same gates exist. Smoke verifies no host Python/PostgreSQL/Redis/Docker
prerequisite, executable permission, nested signature/notarization, runtime checksum and
version compatibility, sanitized-`PATH` startup, dynamic port collision handling,
single-instance/runtime locks, process cleanup, Web open, signed upgrade/rollback,
cold/warm startup budgets, structured evidence, and exact canary secret redaction.

### Repository Gates

```bash
python3 scripts/validate-docs.py
git diff --check
```

## Risks And Mitigations

| Risk | Mitigation |
| --- | --- |
| Full Alembic history is not SQLite-compatible | Establish the fresh-file migration gate before runtime integration; use dialect branches and batch migrations where required. |
| Team concurrency causes SQLite lock storms | Enforce one DB-owning coordinator, short transactions, WAL, bounded worker concurrency, and API/IPC result submission. |
| Replacing Redis weakens terminal or job atomicity | Preserve terminal one-time/session-cap contract in one process; use at-least-once jobs, monotonic lease fencing, transactional job/outbox/event writes, handler idempotency, and crash-window tests. |
| Electron auto-update replaces or corrupts data | Store all data outside the bundle; migrate a backup-API candidate, validate it, close handles before pointer switch, retain the old pointer, and fault-test rollback. |
| Packaged Python runtime is large, misses native modules, or cannot cross-compile | Complete the minimal native Phase 0B spike before schema/worker work; build each supported OS/arch on a native runner and remove unsupported architecture claims. |
| Dynamic local endpoint breaks compiled renderer URLs | Add a runtime endpoint discovery contract; keep Web same-origin and test HTTP/SSE/WebSocket clients. |
| Loopback Web access is vulnerable to token theft or DNS rebinding | Use one-time bootstrap exchange, HttpOnly SameSite cookie, exact Host/Origin validation, loopback bind, and no tokens in URLs/logs. |
| Model key leaks between Electron and Python | Keep ciphertext in `safeStorage`, transfer over inherited pipe/authenticated IPC, redact every logging/crash boundary, and add secret-scanning tests. |
| Existing PostgreSQL/offline data is lost, cross-tenant, or duplicated | Import into an empty target, require owner/org mapping, abort collisions, verify content checksums/artifacts/pending operations, make import idempotent, and never delete sources automatically. |
| Docker removal encourages unsafe host execution | Disable sandbox-required tools when Docker is absent; do not silently substitute unrestricted host execution. |
| Existing enterprise features conflict with local-owner mode | Gate SAML/multi-user/distributed-only surfaces by runtime profile and remove them from the local navigation/readiness contract. |

## Delivery Sequence And Stop Conditions

The phases are intentionally ordered. Phase 0B proves only the minimal native packaging
contract; do not expand it into the full sidecar until SQLite, local auth, and Redis-free
runtime gates pass. Do not remove legacy stores/dependencies until import evidence passes.
Do not expose the Web extension beyond loopback in this plan.

Stop and replan if any of these becomes required:

- public/LAN remote access;
- more than one backend process writing the same database;
- multi-user/SAML production auth;
- cloud sync while Desktop is offline;
- a tool capability that cannot remain safe without Docker;
- an existing production dataset whose verified migration cannot fit the bounded
  maintenance/rollback process.

## Independent Review Result

The first independent review rejected the draft because local identity/bootstrap,
job-delivery semantics, staged migration rollback, and native sidecar packaging were not
fully executable. The revised plan added:

- same-origin Desktop authentication, stable/local secret bootstrap, no-`safeStorage`
  persistent-write rejection, and exactly-one imported principal selection;
- at-least-once jobs with atomic claims, monotonic fencing, transactional event/outbox
  effects, handler idempotency, and crash-window tests;
- candidate-database migrations with fault-injected pointer switch/rollback;
- a Phase 0B native packaging gate and an explicit initial supported architecture matrix;
- measurable projection, security, upgrade, startup, and structured-evidence criteria.

The follow-up independent review returned `APPROVE` with no remaining blockers.

## ADR

### Decision

Adopt a single-process local runtime using one canonical SQLite database. Package and
supervise the existing FastAPI backend as `harnessd`; serve Desktop and the local Web
extension from the same API/data/event authority. Remove PostgreSQL and Redis from the
default installed runtime, and keep Docker optional for sandbox-only capabilities.

### Drivers

- The user should configure only a model API key.
- Web is an extension of Desktop, not an independent hosted or multi-user product.
- The current FastAPI and shared Agent Console contain the required product behavior and
  should be reused rather than rewritten.

### Alternatives Considered

1. Bundle PostgreSQL and Redis with Electron.
   - Rejected: background services, ports, credentials, upgrades, platform packaging,
     repair, and process ownership undermine install-ready desktop behavior.
2. Keep external PostgreSQL/Redis and add a setup wizard.
   - Rejected: automating configuration still leaves external runtime and operational
     failure modes on the user's machine.
3. Rewrite the backend in Electron/Node and use the existing `better-sqlite3` stores.
   - Rejected: duplicates the mature FastAPI Harness contracts and creates a long,
     high-regression rewrite.
4. Use SQLite through one packaged FastAPI runtime.
   - Chosen: reuses the current API/models/migrations/UI, removes external services, and
     matches a local single-user/Web-extension workload.

### Consequences

- Distributed/multi-replica semantics are intentionally removed from the local product.
- Team/background work needs a real persistent local coordinator rather than a simple
  in-memory queue.
- SQLite migration and process ownership become release-critical infrastructure.
- The Web extension is unavailable when Harness is fully stopped.
- A future cloud/multi-user product would require a separate ADR and may reintroduce
  PostgreSQL/Redis behind the same API contracts.

### Follow-Ups

- After the plan is accepted for implementation, execute it as staged vertical slices;
  each phase must land with its own rollback and verification evidence.
- Re-evaluate the self-contained Python packager only after the cross-platform spike.
- Revisit LAN/public Web access only after local loopback security and lifecycle gates
  are complete.
