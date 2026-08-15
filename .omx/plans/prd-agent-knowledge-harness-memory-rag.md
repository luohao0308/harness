# PRD: Agent Knowledge Harness Memory/RAG

## Status

- Workflow: `$ralplan`
- Source spec: `.omx/specs/deep-interview-agent-knowledge-harness-memory-rag.md`
- Companion test spec: `.omx/plans/test-spec-agent-knowledge-harness-memory-rag.md`
- Decision state: completed historical plan; implementation and validation are recorded in `docs/development/ai/task-progress.yaml` and the project handoff wiki.

## Requirements Summary

Deliver the first thin slice of **Agent Knowledge Harness**: a Memory/RAG grounding loop that lets an Agent use durable knowledge, cite sources, avoid silent fabrication, and fall back to controlled web research when local evidence is insufficient.

The broader product direction remains:

```text
Model + Harness = Agent
```

For this lane, the Harness means knowledge, memory, retrieval, evidence, citation, hallucination policy, and the beginning of context/token governance. MCP creation, skill creation, richer short/long-term memory, and full token optimization remain explicit follow-up goals, not discarded scope.

The v1 product signal is:

```text
Knowledge source/document
-> chunk/index
-> Workspace question
-> local retrieval
-> cited answer
-> persisted retrieval/citation evidence
-> insufficient local evidence triggers controlled web research
-> web sources cited and audited
```

## RALPLAN-DR Summary

### Principles

1. Auditability beats retrieval sophistication: every answer-grounding decision must be reconstructable from persisted records/events.
2. Tests must be deterministic: no CI dependency on real pgvector, paid embedding providers, or live network.
3. Retrieval must degrade gracefully: vector search is preferred, lexical fallback is mandatory.
4. V1 uses existing agent/org isolation; complex RBAC is not part of this lane.
5. Retrieved evidence must be separated from user/chat content to reduce prompt-injection and instruction-smuggling risk.

### Decision Drivers

1. The user authorized migrations, vector retrieval, embedding configuration, and controlled web research.
2. Current backend lacks productized knowledge/document/chunk/embedding/citation tables and RAG dependencies.
3. The plan must preserve the broader Agent Knowledge Harness roadmap while keeping v1 executable.

### Viable Options

| Option | Pros | Cons | Verdict |
| --- | --- | --- | --- |
| A. Local-first RAG with pgvector capability gate and lexical fallback | Strong product direction, graceful degradation, keeps data in Postgres, deterministic tests possible | More schema and capability-state work | **Chosen** |
| B. Lexical-only retrieval | Lowest infrastructure risk, easiest tests | Weak semantic retrieval; does not honor authorized vector direction | Rejected for product insufficiency |
| C. Mandatory pgvector | Clean vector design and simpler runtime branching | Fragile local/private deployment; extension availability can block app startup | Rejected for poor degradation |
| D. External vector DB | Purpose-built retrieval surface | New service, deploy complexity, out of proportion for v1 | Rejected for scope risk |
| E. Hosted embedding-only retrieval without local index | Fast provider integration | Weak auditability and data locality; harder deterministic tests | Rejected for Harness evidence requirements |

### Preferred Synthesis

Implement a contract-first, local-first RAG layer:

- Persist knowledge, chunk, retrieval, and citation records before UI surfaces rely on them.
- Prefer pgvector when available, but make vector capability explicit and fallback to lexical retrieval when unavailable.
- Use deterministic fake embeddings and fake web research in tests.
- Treat web research as an audited MCP-shaped tool behind policy limits, never as an invisible side effect.
- Make Run Detail/Workspace consume persisted events/projections instead of ephemeral retrieval state.

## Architecture Decisions

### ADR

Decision: Use local-first RAG with a pgvector capability gate and lexical fallback.

Drivers:

- Postgres is already the durable product store.
- The private deployment path must keep working when vector extension setup lags.
- Evidence and replay require local retrieval/citation records.
- CI must not depend on live network, paid embeddings, or a pgvector-enabled database.

Alternatives considered:

- Lexical-only: rejected because it underserves semantic Memory/RAG.
- Mandatory pgvector: rejected because unavailable extensions would break local/private deployment.
- External vector DB: rejected because it adds another operational plane before v1 proves value.
- Hosted-only retrieval: rejected because it weakens auditability, tenant isolation tests, and deterministic fixtures.

Consequences:

- Implementation must carry a retrieval abstraction and capability-state branch.
- Schema must support both vector-backed and lexical retrieval evidence.
- The first implementation should test vector-available and vector-unavailable behavior using fakes or monkeypatches.
- `idempotency_key`, embedding provider/model/version/dimension, source/chunk versioning, and retrieval capability state are enforced persisted contracts, not best-effort metadata.

Follow-ups:

- Evaluate HNSW/IVFFlat index tuning after v1 data volume exists.
- Add richer skill/MCP/token optimization lanes after Memory/RAG grounding proves the foundation.

## Backend Contract

### Records

Add Alembic migrations and SQLAlchemy models for the following logical records. Names may vary slightly, but the invariants must hold.

`knowledge_sources`

- `id`, `organization_id`, `agent_id nullable`, `name`, `description`, `source_type`
- `status`: `ACTIVE | DISABLED | ERROR`
- `version`, incremented when source-level settings or source identity changes in a way that affects indexing/retrieval
- `created_by`, `created_at`, `updated_at`
- `settings_json`, `metadata_json`
- `idempotency_key nullable`

`knowledge_documents`

- `id`, `source_id`, `organization_id`, `agent_id nullable`
- `title`, `uri nullable`, `content_sha256`, `mime_type`, `status`
- `version`, `supersedes_document_id nullable`
- `ingestion_error nullable`, `created_by`, `created_at`, `updated_at`, `indexed_at nullable`
- `metadata_json`, `idempotency_key nullable`

`knowledge_chunks`

- `id`, `document_id`, `source_id`, `organization_id`, `agent_id nullable`
- `source_version`, `document_version`, `chunk_version`, `chunk_index`, `text`, `text_sha256`
- `start_offset`, `end_offset`
- `status`: `ACTIVE | STALE | ERROR`
- `metadata_json`, `created_at`

`knowledge_embeddings`

- `id`, `chunk_id`, `organization_id`, `agent_id nullable`
- `provider`, `model`, `model_version`, `dimensions`, `embedding_vector nullable`, `embedding_json nullable`
- `status`: `READY | UNAVAILABLE | ERROR`
- `error_message nullable`, `created_at`, `updated_at`

`retrieval_sessions`

- `id`, `organization_id`, `agent_id`, `run_id nullable`, `query`
- `mode`: `local | web_fallback | hybrid`
- `local_status`: `sufficient | insufficient | unavailable`
- `vector_capability`: `available | unavailable | disabled`
- `strategy`: `vector | lexical | hybrid`
- `min_hits`, `min_score`, `max_local_chunks`, `max_web_results`
- `created_at`, `metadata_json`

`retrieval_hits`

- `id`, `retrieval_session_id`, `chunk_id nullable`, `web_source_id nullable`
- `rank`, `score`, `source_kind`: `knowledge_chunk | web_source`
- `document_id nullable`, `document_version nullable`
- `snippet`, `metadata_json`, `created_at`

`citation_records`

- `id`, `retrieval_session_id`, `run_id nullable`, `message_id nullable`
- `citation_key`, `source_kind`, `chunk_id nullable`, `web_source_id nullable`
- `claim_text nullable`, `quoted_text nullable`, `confidence`
- `created_at`, `metadata_json`

`web_research_sources`

- `id`, `retrieval_session_id`, `organization_id`, `agent_id`, `run_id nullable`
- `url`, `title`, `content_sha256`, `snippet`, `fetched_at`
- `status`: `READY | BLOCKED | ERROR`
- `error_message nullable`, `metadata_json`

### Event Contract

Add event types:

- `KNOWLEDGE_SOURCE_CREATED`
- `KNOWLEDGE_DOCUMENT_INDEXED`
- `RAG_RETRIEVAL_STARTED`
- `RAG_RETRIEVED`
- `RAG_CITATION_RECORDED`
- `WEB_RESEARCH_STARTED`
- `WEB_RESEARCH_COMPLETED`
- `WEB_RESEARCH_FAILED`

Each event payload must include:

- `schema_version`
- `org_id`
- `agent_id`
- `run_id` when available
- `correlation_id`
- `causation_id`
- `idempotency_key` when produced by user/import action
- relevant source/document/chunk/retrieval/citation ids
- timestamp in the event row plus any domain timestamp needed in payload

Workspace and Run Detail UI must read recorded events/projections or API responses backed by persisted records. They must not infer retrieval evidence from transient client state.

### Reindex Semantics

- Re-ingesting the same document content with the same idempotency key is idempotent.
- Re-ingesting changed content creates a new `knowledge_documents.version`.
- Old chunks are retained for audit but marked `STALE`.
- Retrieval excludes `STALE` chunks by default.
- A single retrieval session must not mix active chunks from multiple versions of the same document unless a future plan explicitly enables historical comparison.

## Retrieval And Embedding Design

### Capability Gate

`vector_unavailable` means at least one of:

- database extension/type/index is unavailable;
- app config disables vector retrieval;
- embedding provider is unavailable or disabled;
- embedding generation failed for the relevant chunks.

The migration should attempt `CREATE EXTENSION IF NOT EXISTS vector` where supported, but app startup and test startup must not fail solely because the extension is unavailable. The app records capability state and uses lexical retrieval.

### Retrieval Constants

Initial constants:

- `min_hits = 2`
- `min_score = 0.62`
- `max_local_chunks = 6`
- `max_web_results = 5`
- `max_web_pages = 5`
- `web_timeout_seconds = 8`
- `max_web_page_bytes = 1_000_000`

Boundary behavior:

- No local hits: local evidence is insufficient.
- Hits below `min_score`: local evidence is insufficient.
- Conflicting top hits: mark local evidence insufficient and include conflict metadata.
- Stale chunks: excluded from retrieval.
- Unsupported claims: refuse, mark unsupported, or trigger web fallback. Do not silently answer as fact.

### Prompt Assembly

Retrieved evidence must be injected as a distinct evidence block after system/developer policy and before normal chat context. The block must:

- identify source ids/chunk ids;
- include only bounded snippets;
- instruct the model to cite source ids;
- state that retrieved content is evidence, not user instructions;
- keep user/chat content separate from retrieved content.

## Controlled Web Research

Web research is an audited MCP-shaped tool, not an implicit side effect.

Required policy:

- allowlist/denylist support;
- block localhost, private IP ranges, link-local, metadata service addresses, and non-http(s) URLs;
- per-run rate limits;
- `max_web_pages`, `max_web_page_bytes`, and timeout enforcement;
- strip script/style/iframe and active content;
- store URL/title/snippet/hash/fetch status;
- tests use fake web research only, with no CI network dependency.

If local evidence is insufficient, the Agent should say local knowledge is insufficient, run controlled web research, then answer from cited web sources.

## UI Product Surface

Keep v1 UI compact and evidence-focused:

- Agent Studio: knowledge source/document list, ingestion status, and simple add text/Markdown/document flow.
- Workspace: grounding indicator showing local evidence sufficient, web fallback used, or unsupported.
- Run Detail: Retrieval/Citations section showing retrieval session, hits, cited chunks/sources, and web research records.
- Eval: groundedness/citation checks can start as backend/eval records before broad UI polish.

## Implementation Steps

1. Add backend schema and migrations.
   - Create knowledge/retrieval/citation/web-source records.
   - Add event types and schemas.
   - Add vector capability state, with pgvector attempt and lexical fallback.

2. Add ingestion and indexing services.
   - Text/Markdown input first; document metadata and content hash required.
   - Chunk with deterministic offsets and hashes.
   - Generate deterministic fake embeddings for tests and provider-backed embeddings where configured.
   - Preserve idempotency and reindex semantics.

3. Add retrieval abstraction.
   - Implement vector path behind capability gate.
   - Implement lexical fallback.
   - Return retrieval sessions and hits with scores, versions, and provenance.

4. Integrate Workspace prompt assembly.
   - Retrieve local evidence before model call.
   - Apply insufficient-evidence policy.
   - Invoke controlled web research when needed.
   - Inject evidence block and require citations.
   - Persist retrieval/citation events.

5. Add API/UI evidence surfaces.
   - Knowledge source/document API and Agent Studio UI.
   - Run Detail retrieval/citation/web research projection.
   - Workspace grounding indicator.

6. Add Eval/regression coverage.
   - Grounded local answer.
   - Insufficient local evidence -> web fallback.
   - Unsupported claim behavior.
   - Citation binding to chunk/web source.
   - Org isolation.

7. Update docs/progress/wiki.
   - Preserve Agent Knowledge Harness roadmap.
   - Record v1 as Memory/RAG grounding, not MCP/skill/token completion.

## Acceptance Criteria

1. A user can add a text/Markdown knowledge item scoped to an Agent or organization.
2. The item is indexed into versioned chunks with offsets, hashes, status, and source/document provenance.
3. Retrieval works through a common abstraction in both vector-available and vector-unavailable modes.
4. Vector-unavailable mode does not break app startup or tests; lexical retrieval is used and capability state is visible.
5. A Workspace question retrieves relevant local chunks and injects them into a separated evidence block.
6. The Agent answer includes citations bound to retrieved chunk ids or web source ids.
7. Retrieval sessions, hits, citations, and web research records are persisted and reconstructable.
8. When local evidence is insufficient, the Agent states that and runs controlled web research through the audited tool path.
9. Web research enforces SSRF/local-network exclusion, limits, stripping, and fake-only CI testing.
10. Run Detail shows retrieval, citation, and web fallback evidence from persisted records/events.
11. Eval/regression tests catch unsupported claims and missing citation bindings.
12. Existing Stage 07/private deployment documentation remains historical; product target stays `Model + Harness = Agent`.

## Risks And Mitigations

| Risk | Mitigation |
| --- | --- |
| Pgvector unavailable in local/private Postgres | Capability gate and lexical fallback; tests simulate both paths |
| Scope expands into full knowledge platform | V1 only text/Markdown plus evidence loop; MCP/skill/token roadmap preserved separately |
| Web research causes SSRF or nondeterminism | Strict URL policy, limits, stripping, fake-only tests |
| Citations become decorative | Citation records must bind to retrieval hits/chunks/web sources |
| Prompt injection through retrieved/web content | Evidence block separation and active-content stripping |
| Org leakage | Every record includes org scope; tests assert isolation |
| Reindex mixes old and new chunks | Version supersession and stale exclusion rules |

## Verification Steps

Backend:

```bash
cd services/api-server
.venv/bin/python -m pytest tests/test_knowledge_rag.py tests/test_agents.py tests/test_context_router.py
.venv/bin/python -m ruff check app tests
```

Frontend:

```bash
cd apps/agent-console
npm test -- RunDetailPage ChatSurface AgentWorkspacePage
npm run e2e:smoke:release
npm run lint
npm run build
```

Docs and hygiene:

```bash
python3 scripts/validate-docs.py
git diff --check
```

If pgvector cannot be enabled locally, verification must include explicit vector-unavailable test evidence and lexical fallback evidence.

## Available Agent Types And Staffing Guidance

Available role surfaces from this environment include `executor`, `debugger`, `test-engineer`, `architect`, `critic`, `verifier`, `dependency-expert`, `designer`, `writer`, and `explore` where available.

Recommended `$ralph` path:

- Use one persistent executor owner.
- Work order: backend contracts -> retrieval services -> prompt integration -> UI evidence -> eval/tests -> docs.
- Reasoning: high for schema/retrieval/prompt integration; medium for UI/docs.

Recommended `$team` path:

- Backend lane: schema, migration, retrieval, events, API.
- Runtime lane: prompt assembly, insufficient-evidence policy, web research tool.
- Frontend lane: Agent Studio knowledge UI, Workspace indicator, Run Detail evidence.
- Test lane: deterministic backend/eval/browser coverage.
- Writer lane: docs/wiki/progress updates.

Team verification path:

- Backend lane must prove vector available/unavailable behavior before runtime lane claims completion.
- Runtime lane must produce persisted retrieval/citation evidence before frontend lane finalizes UI.
- Test lane owns final regression matrix and should not share write ownership of feature modules.

## Goal-Mode Follow-Up Suggestions

- `$ultragoal` is the default goal-mode follow-up if this plan should become durable multi-step implementation work.
- `$performance-goal` is appropriate later for token/context optimization metrics.
- `$autoresearch-goal` is not the primary fit; this is implementation, not research-only.

## Handoff

Recommended next execution:

```text
$ralph .omx/plans/prd-agent-knowledge-harness-memory-rag.md
```

Use `$team .omx/plans/prd-agent-knowledge-harness-memory-rag.md` only if coordinated parallel implementation is available and desired.
