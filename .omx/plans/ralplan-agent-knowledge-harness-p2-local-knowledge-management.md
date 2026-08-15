# RALPLAN: Agent Knowledge Harness P2 Local Knowledge Management

Path: `.omx/plans/ralplan-agent-knowledge-harness-p2-local-knowledge-management.md`

## Outcome

P2 交付一个 **本地知识源管理器**：支持 agent/org 作用域的纯文本和 Markdown 文档，具备生命周期控制、版本化重新导入、检索资格过滤，以及不破坏历史 Run 证据链的审计保留能力。

P2 不交付 real web research provider、PDF/DOCX/HTML parser、外部 vector DB、复杂 RBAC、长期 memory router 或观测 dashboard。这些分别留给 P3/P4/P5/P6。

## Hard Gate

P2 执行前必须先生成一个明确的 P1 gate result。不能只口头引用 P1 计划，也不能用模糊措辞替代。

Required artifact:

```text
.omx/reports/agent-knowledge-harness-p1/p1-gate-result-<timestamp>.md
```

The artifact must contain:

```yaml
status: verified_baseline | candidate_safe | blocked
candidate_commit: <git sha>
evidence:
  clean_alembic_upgrade: pass | fail | unavailable
  existing_data_upgrade: pass | fail | unavailable
  docker_compose_config: pass | fail | unavailable
  docker_private_smoke: pass | fail | unavailable
  agent_run_smoke: pass | fail | unavailable
  run_detail_exact_selector: pass | fail | unavailable
  eval_grounding_contract: pass | fail | unavailable
  append_only_audit_decision: pass | fail | unavailable
  backend_frontend_docs_browser_gate: pass | fail | unavailable
decision_owner: harness-agent
decision_time: <UTC timestamp>
blocking_reason: <required unless status=verified_baseline>
```

Gate semantics:

- `verified_baseline`: all required evidence is `pass`; normal P2 execution may proceed.
- `candidate_safe`: at least one P1 gate is `unavailable`, but no failed gate proves the baseline unsafe. P2 may proceed only as a non-promoting branch.
- `blocked`: any required gate is `fail`, or evidence is too ambiguous to isolate P1/P2 risk. Stop P2 and repair the failed P1 gate first.

If status is `candidate_safe`:

- every PR title, commit message body, report title, wiki update, and execution summary must include `candidate-safe`;
- `docs/ai/task-progress.yaml`, `docs/task-progress.md`, and `omx_wiki/agent-knowledge-harness-roadmap.md` must not mark P2 completed;
- private deployment verification must be written as deferred, not passed.

## RALPLAN-DR Summary

### Principles

1. **Hard gate before feature claim**: P1 state is a recorded artifact with an enumerated status, not a narrative.
2. **One closed slice at a time**: P2 is split into P2a/P2b/P2c so backend lifecycle and audit contracts close before UI and deployment polish.
3. **Historical evidence is immutable**: historical Run reconstruction must use persisted retrieval/citation/prompt snapshots, never current source/document/chunk active state.
4. **Lifecycle state is explicit**: source status, document version, chunk status, expiry, health, and retrieval eligibility must have truth tables and tests.
5. **Local-only boundary**: P2 manages local text/Markdown knowledge. Real web provider, rich parsers, and memory router remain follow-up lanes.

### Decision Drivers

1. Current UI only provides inline text ingestion and a shallow list; it cannot support source lifecycle, reingest, or operational diagnosis.
2. P1 created a grounding audit chain; P2 lifecycle mutations are only safe if they preserve exact historical evidence.
3. Private deployment remains the product path, so P2 migrations and data recovery must be verifiable, not only documented.

### Viable Options

| Option | Pros | Cons | Verdict |
| --- | --- | --- | --- |
| A. P2a/P2b/P2c staged delivery after hard P1 gate | Closes backend/audit before UI; prevents overclaiming; easiest to verify | Slower visible product progress | **Chosen** |
| B. Candidate-safe P2a only before P1 promotion | Allows narrow backend lifecycle work if Docker gate is unavailable | Requires strict non-promotion discipline | Allowed only with gate artifact |
| C. One large P2 bundle | Fewer planning artifacts | Too much surface at once; high partial-completion risk | Rejected |
| D. UI-first productization | Fast demo improvement | Does not prove lifecycle, audit, migration, or retrieval semantics | Rejected |
| E. Include real web/file parser expansion now | More capability | Crosses into P3/parser dependency decisions | Rejected |

## ADR

Decision: Deliver P2 as three gated slices:

- **P2a: Backend Lifecycle And Audit Contract**
- **P2b: Agent Studio Management Surface**
- **P2c: Text/Markdown File Import And Private Deployment Recovery**

Drivers:

- Backend lifecycle and immutable historical reconstruction are the foundation; UI should not outrun those contracts.
- File upload and private deployment recovery are meaningful but should not block P2a/P2b from closing.
- Current code already has typed tables for source/document/chunk/retrieval/citation/manifest; P2 should extend that model, not hide critical state in JSON.

Alternatives considered:

- Keep one monolithic P2 plan: rejected because it makes every area half-done.
- Put lifecycle in UI only: rejected because retrieval eligibility and audit semantics are backend product contracts.
- Build a job system first: rejected for P2a unless synchronous indexing cannot meet the strict limits below.

Consequences:

- P2a must finish before P2b begins.
- P2c may be deferred without invalidating P2a/P2b, but then the product claim is "local text/Markdown document management", not "file import complete".
- No hard delete or purge API is exposed in P2. Purge/compliance deletion requires a separate plan because it conflicts with audit retention.

## Scope By Slice

### P2a: Backend Lifecycle And Audit Contract

Goal: make local knowledge lifecycle safe and testable before UI expansion.

Includes:

- hard P1 gate artifact;
- typed lifecycle columns and migrations;
- source status transitions;
- document version/reingest semantics;
- chunk stale semantics;
- retrieval eligibility join through `KnowledgeSource`;
- immutable historical reconstruction contract;
- lifecycle audit events committed atomically with lifecycle mutations;
- org-scoped vs agent-scoped write/read isolation.

P2a completion claim: backend contract complete, UI may still be thin.

### P2b: Agent Studio Management Surface

Goal: expose P2a safely in Agent Studio.

Includes:

- source list/detail;
- document list and version history;
- add/reingest document;
- disable/enable/archive actions;
- health/error/scope badges;
- confirmation for archive, scope change, and reingest;
- 390px and desktop usability.

P2b completion claim: local knowledge can be managed from the console without relying on the old demo-only textarea.

### P2c: Text/Markdown File Import And Private Deployment Recovery

Goal: add conservative file import and prove private deployment recovery.

Includes:

- `.txt` / `.md` upload;
- `text/plain` and `text/markdown` only;
- small synchronous import limits;
- backup/restore runbook plus restore verification;
- Docker/private smoke after P2 migrations if Docker is available.

P2c completion claim: text/Markdown file import and deployment recovery path are verified. If this slice is deferred, P2 must not claim file upload support.

## Product Boundaries

Required for P2a/P2b:

- local text/Markdown knowledge source manager;
- agent-scoped and org-scoped sources;
- lifecycle controls;
- versioned reingestion;
- retrieval eligibility filtering;
- historical evidence preservation.

Required only for P2c:

- actual multipart `.txt` / `.md` file upload;
- backup/restore verification.

Out of scope:

- PDF/DOCX/HTML parsing;
- rich background indexing jobs;
- real web provider;
- hard purge;
- complex RBAC beyond existing role checks plus explicit org-scope permissions.

## Historical Reconstruction Contract

Historical grounding reconstruction **must** use immutable retrieval/citation/prompt snapshots. It **must not** depend on current `KnowledgeSource`, `KnowledgeDocument`, or `KnowledgeChunk` active status.

Every historical Run Detail and Eval exact-selector path must be reconstructable from persisted records containing at least:

- `retrieval_session_id`;
- `prompt_manifest_id`;
- `source_id`;
- `source_name_snapshot`;
- `source_version`;
- `document_id`;
- `document_version`;
- `document_title_snapshot`;
- `chunk_id`;
- `chunk_text_snapshot` or `citation_text_snapshot`;
- `content_sha256` / `chunk_text_sha256`;
- `chunk_span` with start/end offsets;
- retrieval `score`;
- `retrieved_at`;
- embedding provider/model/version where available;
- `policy_decision_snapshot`;
- rendered citation key/text;
- prompt evidence hash.

If current P1 tables are missing any required snapshot field, P2a must either:

- add the snapshot at future retrieval/citation/manifest creation time and mark older rows as `legacy_snapshot_partial`; or
- stop as `blocked` if exact historical evidence would be misleading.

Exact selector rule:

```text
If retrieval_session_id or prompt_manifest_id is provided,
the system MUST render persisted historical evidence for that selector.
It MUST NOT recompute retrieval from current knowledge state.
```

## Lifecycle State Model

Source lifecycle state and operational health are separate:

- `status`: lifecycle control state, one of `ACTIVE`, `DISABLED`, `ARCHIVED`.
- `health`: derived or stored operational state, one of `HEALTHY`, `DEGRADED`, `ERROR`, `INDEXING`.

`ERROR` is not a source lifecycle status in P2. Import/reingest errors affect `health`, `last_ingestion_error`, and document version state. This avoids mixing "user disabled it" with "system failed to index it".

Allowed source transitions:

| From | To | Allowed | Notes |
| --- | --- | --- | --- |
| ACTIVE | DISABLED | yes | Temporary stop; may be enabled later. |
| DISABLED | ACTIVE | yes | Retrieval resumes if not expired and latest document is indexed. |
| ACTIVE | ARCHIVED | yes | Long-term removal from retrieval. |
| DISABLED | ARCHIVED | yes | Allowed. |
| ARCHIVED | ACTIVE | no in P2 | Restore from archive is a later explicit plan. |
| any | hard delete | no in P2 | No purge API or Agent Studio action. |
| ACTIVE | EXPIRED | derived | Expiry is computed from `expires_at`, not a stored status. |

Version truth table:

| Operation | Source status | Document v1 | Chunk v1 | Document v2 | Chunk v2 | Retrieval |
| --- | --- | --- | --- | --- | --- | --- |
| initial import success | ACTIVE | INDEXED, current | ACTIVE | - | - | use v1 |
| same content/idempotency retry | ACTIVE | INDEXED, current | ACTIVE | - | - | use v1; no duplicate |
| reingest success | ACTIVE | SUPERSEDED | STALE | INDEXED, current | ACTIVE | use v2 only |
| reingest failure | ACTIVE | INDEXED, current | ACTIVE | FAILED | none active | continue using v1; health=DEGRADED or ERROR |
| disable source | DISABLED | unchanged | unchanged | unchanged | unchanged | no retrieval |
| archive source | ARCHIVED | unchanged | unchanged | unchanged | unchanged | no retrieval |
| source expired | ACTIVE + expired | unchanged | unchanged | unchanged | unchanged | no retrieval |

Current successful version rule:

```text
Only the latest successful INDEXED document version for a logical document is retrievable.
Older versions are retained for audit only.
```

P2a must define whether the logical document identity is represented by an existing `supersedes_document_id` chain or a new typed `logical_document_id`. The chosen representation must be tested.

## Retrieval Eligibility Contract

A chunk is retrievable if and only if all conditions are true:

- `source.organization_id == request.organization_id`;
- `source.agent_id == request.agent_id OR source.agent_id IS NULL`;
- `source.status == ACTIVE`;
- `source.expires_at IS NULL OR source.expires_at > now`;
- `document.status == INDEXED`;
- `document` is the latest successful version for its logical document;
- `chunk.status == ACTIVE`.

`ground_query` must join/filter `KnowledgeSource`, `KnowledgeDocument`, and `KnowledgeChunk`. Filtering only document/chunk status is insufficient.

History exception:

- historical Run Detail/Eval exact selectors may show stale/superseded/disabled/archived evidence, but only as historical evidence;
- those records must not be reintroduced into live retrieval.

## Scope And Permission Contract

Org-scoped source means `agent_id = null`. This is allowed only with explicit checks.

Creation routes:

- agent-scoped create may use:
  - `POST /api/agents/{agent_id}/knowledge/sources`
- org-scoped create should use a dedicated route if the API already has org routes:
  - `POST /api/orgs/{org_id}/knowledge/sources`
- if P2 keeps org-scoped create on the agent route, request body must include `scope: "org"` and the handler must enforce org-level permission.

Rules:

- source, document, chunk, and embedding rows must all use the same scope:
  - agent scope: `agent_id = <path agent_id>`;
  - org scope: `agent_id = null`.
- `organization_id` must always equal the principal organization.
- ordinary users must not promote an agent-scoped source to org-scoped.
- scope mutation is not part of ordinary `PATCH`; it uses a separate endpoint or strict discriminated action with higher permission.
- foreign org reads/writes/actions must fail even for org-scoped sources.

Required tests:

- agent A sees its own agent source;
- agent B in same org does not see agent A's agent-scoped source;
- agent A and B in same org both see org-scoped source;
- foreign org never sees or mutates the source;
- ordinary user cannot create org-scoped source or change scope;
- admin/engineer scope change writes consistent `agent_id = null` rows for source/document/chunk/embedding.

## Lifecycle Audit Contract

Lifecycle mutation and lifecycle event insert must be committed atomically in one DB transaction.

```text
If the audit event cannot be written, the lifecycle mutation MUST fail.
If the lifecycle mutation rolls back, the audit event MUST roll back.
```

Minimum event payload for P2a:

- `event_type`;
- `schema_version`;
- `organization_id`;
- `agent_id` when scoped;
- `actor_user_id`;
- `source_id`;
- `document_id` and version where applicable;
- `request_id` or correlation id if available;
- `idempotency_key` when applicable;
- `before_json`;
- `after_json`;
- `created_at`.

Do not invent a large event platform if current infrastructure is not ready. P2a may use the existing event/audit table that best fits product audit, but it must document the choice before adding routes. The storage path cannot be ambiguous.

Required lifecycle event types:

- source created;
- source updated;
- source disabled;
- source enabled;
- source archived;
- source scope changed;
- document version created;
- document reingest failed;
- document import failed.

## API Contract

Avoid vague source-level `reingest` and loose `actions` strings.

Preferred endpoints:

```text
PATCH /api/agents/{agent_id}/knowledge/sources/{source_id}
POST  /api/agents/{agent_id}/knowledge/sources/{source_id}/disable
POST  /api/agents/{agent_id}/knowledge/sources/{source_id}/enable
POST  /api/agents/{agent_id}/knowledge/sources/{source_id}/archive
POST  /api/agents/{agent_id}/knowledge/sources/{source_id}/scope
GET   /api/agents/{agent_id}/knowledge/sources/{source_id}/documents
POST  /api/agents/{agent_id}/knowledge/sources/{source_id}/documents
POST  /api/agents/{agent_id}/knowledge/sources/{source_id}/documents/{document_id}/versions
POST  /api/agents/{agent_id}/knowledge/sources/{source_id}/documents/{document_id}/reindex
```

Rules:

- ordinary `PATCH` may update name, description, settings, and `expires_at`.
- scope mutation must not be hidden in ordinary `PATCH`.
- document version endpoint means new content for a specific logical document.
- reindex endpoint means same content, rerun indexing/embedding only.
- if an action endpoint is consolidated, the schema must be a strict discriminated union, not arbitrary strings.

File upload:

- P2a/P2b do not require multipart upload.
- P2c requires `.txt` / `.md` upload support.
- If P2c is deferred, all output must say "text/Markdown document management"; it must not claim file upload support.

## Data Model And Migration Contract

Core filtering and lifecycle fields must be typed columns, not hidden in JSON.

Required typed columns or already-existing equivalents:

- `KnowledgeSource.status`;
- `KnowledgeSource.expires_at`;
- `KnowledgeSource.disabled_at`;
- `KnowledgeSource.archived_at`;
- `KnowledgeSource.last_indexed_at`;
- `KnowledgeSource.last_ingestion_error`;
- `KnowledgeSource.health_status` or documented derived health function;
- `KnowledgeDocument.status`;
- `KnowledgeDocument.version`;
- `KnowledgeDocument.content_sha256`;
- `KnowledgeDocument.indexed_at`;
- `KnowledgeDocument.superseded_at` or equivalent;
- `KnowledgeDocument.logical_document_id` or tested `supersedes_document_id` chain;
- `KnowledgeChunk.status`;
- `KnowledgeChunk.document_version`.

JSON may store optional metadata only. It must not hold fields required for live retrieval eligibility or migration safety.

Existing-data migration fixture must prove:

- P1 source rows default to `ACTIVE`;
- P1 document rows default to `INDEXED`, version `1`, current;
- P1 chunks default to `ACTIVE`;
- P1 retrieval/citation/manifest rows remain queryable;
- old Run Detail exact selectors still open;
- row counts for source/document/chunk/retrieval/citation/manifest/audit tables are preserved;
- SQLite clean upgrade passes;
- Postgres/Docker upgrade is verified when Docker is available.

If Docker is unavailable, record `private_deployment_verification: deferred` and keep the branch non-promoting.

## Indexing Mode

P2a/P2b use **strict synchronous indexing** only.

Limits:

- small text/Markdown content only;
- max bytes no larger than current `KnowledgeSourceCreateRequest.content` limit unless a migration/test explicitly changes it;
- max chunks enforced before active chunks are committed;
- one request uses one DB transaction for document/chunk/embedding/event writes;
- no persistent progress UI is required.

`INDEXING` health may be used internally during the request, but P2a/P2b must not promise background progress. If real async indexing is needed, create a later `KnowledgeIngestionJob` plan with polling, retry, and failure events.

Failure rule:

- import/reingest failure must not leave active partial chunks;
- old successful version remains active unless the source is explicitly disabled or archived;
- the failure is visible via `health`, `last_ingestion_error`, document `FAILED`, and lifecycle event.

## Frontend Contract

Do not keep P2 UI as one large `AgentListPage.tsx` block.

Expected component split:

- `KnowledgeSourceList`;
- `KnowledgeSourceDetail`;
- `KnowledgeDocumentList`;
- `KnowledgeDocumentVersionHistory`;
- `KnowledgeSourceActions`;
- `KnowledgeCreateDialog`;
- `KnowledgeDocumentIngestDialog`;
- `KnowledgeHealthBadge`;
- `KnowledgeScopeBadge`.

API types should be moved to a knowledge-specific frontend API module when practical; do not keep growing unrelated task API surface without a boundary.

Dangerous action UX:

- archive requires confirmation;
- scope change requires confirmation and explains visibility expansion;
- reingest explains it creates a new effective version if successful;
- reingest failure shows whether the old version remains in use;
- disabled/archived state explicitly says the source will not be used for retrieval.

Frontend acceptance:

- source list/detail, documents, versions, health, errors, and scope render at desktop and 390px;
- no UI card nesting beyond existing design system norms;
- dangerous actions are not single-click ambiguous;
- old demo textarea is no longer the only path to manage knowledge.

## Deployment And Recovery Contract

P2 must not blur P1 and P2 private-deployment evidence.

Before P2 starts, record:

```yaml
p1_docker_baseline: pass | fail | unavailable
```

If `p1_docker_baseline != pass`, P2 reports must say:

```text
Private deployment verification deferred.
P2 cannot be promoted to completed baseline.
```

P2c backup/restore verification must prove:

- backup database;
- restore database;
- run migrations if needed;
- current retrieval works;
- disabled/archived source is not retrieved;
- historical Run evidence renders by exact selector;
- lifecycle events exist after restore;
- org isolation still holds.

Runbook-only backup notes are not enough for P2c completion.

## Execution Plan

### Phase 0: Hard P1 Gate

1. Create the required P1 gate result artifact.
2. Set status to `verified_baseline`, `candidate_safe`, or `blocked`.
3. Stop if `blocked`.
4. If `candidate_safe`, label all downstream artifacts and disable all progress promotion.

Acceptance:

- Gate artifact exists with the required YAML fields.
- No implementation starts without a gate status.

### P2a Phase 1: Backend Contracts And Migration

1. Add typed columns/migrations for required lifecycle/filter fields.
2. Define logical document version representation.
3. Implement source lifecycle transitions.
4. Implement document version creation and reindex semantics.
5. Implement atomic lifecycle audit event writes.
6. Implement retrieval eligibility with explicit source join.
7. Implement historical reconstruction snapshot gap handling.
8. Implement org-scope write/read permission checks.

Acceptance:

- Version truth table is enforced by tests.
- Retrieval eligibility contract is enforced by tests.
- Historical exact selector does not recompute from current state.
- Audit event write failure rolls back lifecycle mutation.
- Existing P1 data migrates with safe defaults.

### P2a Phase 2: Backend Tests

Required high-value tests:

- same idempotency key duplicate create;
- same content hash reingest;
- reingest success supersedes v1 and retrieves v2 only;
- reingest failure keeps v1 active and writes failure event;
- disable/archive/expiry excludes retrieval;
- exact historical Run still renders v1 after v2 reingest;
- concurrent reingest conflict is rejected or serialized;
- disable + reingest race is deterministic;
- lifecycle event failure rolls back mutation;
- embedding/chunk failure leaves no active partial chunks;
- ordinary user cannot create org source or change scope;
- foreign org cannot read or mutate;
- API error shape and response schema are stable.

### P2b Phase 3: Agent Studio UI

1. Split knowledge UI into dedicated components.
2. Add source list/detail and document version history.
3. Add lifecycle actions with confirmations.
4. Add add/reingest document flows.
5. Show health, errors, scope, status, and current version.

Acceptance:

- UI does not rely on the old inline demo form as the only management path.
- Dangerous actions have confirmation and clear effect text.
- 390px and desktop layouts fit.

### P2c Phase 4: File Import And Recovery

1. Add `.txt` / `.md` upload only.
2. Enforce MIME, extension, byte, and chunk limits.
3. Reject binary/oversized/unknown files safely.
4. Add backup/restore verification and runbook updates.
5. Run Docker/private smoke only if Docker baseline is available.

Acceptance:

- If file import is implemented, it has frontend and backend tests.
- If file import is deferred, reports do not claim file support.
- Restore verification proves retrieval, history, lifecycle events, and org isolation.

## Verification Commands

Backend:

```bash
cd services/api-server
uv run pytest tests/test_knowledge_rag.py tests/test_agents.py tests/test_evals.py -q
uv run ruff check app tests alembic/versions
DATABASE_URL=sqlite:///$TMPDIR/harness-p2-clean.db uv run alembic upgrade head
```

Frontend:

```bash
cd apps/agent-console
npm test -- AgentListPage Knowledge
npm run lint
npm run build
```

Browser:

```bash
cd apps/agent-console
npm run e2e:smoke:release
```

Docs and hygiene:

```bash
python3 scripts/validate-docs.py
git diff --check
```

Private deployment when available:

```bash
docker compose --env-file deploy/docker-compose/.env.example -f deploy/docker-compose/docker-compose.yml config
python3 scripts/smoke-test-docker.py
python3 scripts/smoke-test-agent-run.py
```

## Promotion Rules

P2a may be marked complete only when backend lifecycle/audit/retrieval contracts pass.

P2b may be marked complete only when P2a is complete and Agent Studio management tests pass.

P2c may be marked complete only when file import and restore/private deployment checks pass or the scope explicitly excludes file import.

Full P2 may be promoted in `docs/ai/task-progress.yaml`, `docs/task-progress.md`, and wiki only when:

- P1 gate status is `verified_baseline`;
- P2a, P2b, and any claimed P2c scope pass;
- no private deployment verification is deferred for claimed migration/file/recovery behavior.

## Available Agent Types

- `explore`: repo lookup and current API/model/test mapping.
- `architect`: lifecycle/audit/data model design review.
- `executor`: backend/frontend/doc implementation.
- `test-engineer`: concurrency, transaction, permission, API, e2e tests.
- `verifier`: gate evidence and exact-selector validation.
- `code-reviewer`: final risk review before promotion.
- `writer`: runbooks, wiki, and progress docs after gates pass.

## Execution Handoff

Recommended first execution lane:

```text
$ralph implement P2a backend lifecycle and audit contract from .omx/plans/ralplan-agent-knowledge-harness-p2-local-knowledge-management.md
```

Use `$team` only after P2a contracts are stable or when lanes are explicitly separated:

```text
$team implement P2a/P2b/P2c from .omx/plans/ralplan-agent-knowledge-harness-p2-local-knowledge-management.md
```

Recommended team lanes:

1. Backend lifecycle/migration lane.
2. Audit/event/transaction test lane.
3. Frontend Agent Studio lane, after backend schemas stabilize.
4. Deployment/recovery docs lane, after migrations stabilize.
5. Verification/code-review lane.

Goal-mode follow-up:

- `$ultragoal` is the default if this plan should become a durable goal ledger.
- `$ultragoal` + `$team` is appropriate only after P2a contracts are no longer moving.
