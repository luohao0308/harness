# Agent Knowledge Harness Roadmap

Category: `decision`

Tags: `agent-knowledge-harness`, `memory`, `rag`, `mcp`, `skills`, `token-optimization`, `hallucination`, `task-progress`

## Decision

The final task target is **Agent Knowledge Harness**: make the Harness layer a configurable, auditable, and evaluable capability system that turns a base model into a useful Agent.

```text
Model + Harness = Agent
```

This target comes from the repository HTML report `docs/reports/release-gate-handoff-diff-2026-05-14.html`, which reframes the next work from "add memory/RAG" into a full Harness capability layer. Each capability must answer:

- what problem it solves;
- what mechanism implements it;
- where runtime evidence is recorded.

## Final Capability Map

The final product target is not a single RAG feature. It is the combined Harness capability stack:

- **Short-term memory**: Workspace/session/branch task state, preferences, unresolved decisions, and recent tool observations.
- **Long-term memory**: durable Agent/org knowledge, facts, preferences, decisions, provenance, deletion, and expiry.
- **RAG / document knowledge**: user or internal documents are chunked, indexed, retrieved, cited, and evaluated.
- **Local-insufficient evidence path and web research**: the Agent must say when local evidence is insufficient; real web research requires a policy-gated provider and must not be mocked as real evidence.
- **MCP creation and management**: external capabilities become registered, policy-controlled, sandboxed, auditable tools.
- **Skills / capability packs**: reusable instructions, allowed tools, examples, constraints, versions, and eval cases can be attached to Agents.
- **Context and token optimization**: select between chat history, pinned context, memory, RAG, tool observations, and compression summaries under a visible token budget.
- **Hallucination control**: prefer cited evidence, mark unsupported claims, and measure groundedness.
- **Eval / regression gate**: prove capability changes with groundedness, citation quality, retrieval precision, policy, cost, and latency checks.
- **Observability / audit**: connect model calls, tool calls, retrieval hits, citations, policy decisions, memory writes, and context compression through Run events and traces.
- **Policy / sandbox**: keep tools, network, files, MCP, and research behind existing policy and sandbox boundaries.
- **Agent orchestration**: Plan DAG, subagents, handoff edges, pause/resume/cancel, replay, and evidence per step.

## Existing Implemented Foundation

The repository already contains more than the original roadmap described:

- Stage 01-07 and private deployment handoff are completed in `docs/ai/task-progress.yaml`.
- Release validation is split into quick browser smoke, mocked browser release gate, and live backend validation.
- Workspace already has chat-first execution, Plan-Act approval, branch navigation, pinned messages, context compression, token budget controls, Run Detail links, and Eval Case capture.
- Agent Studio already exposes Model, Tools/MCP, Prompt, RAG, Templates, Orchestration, and a knowledge source management surface.
- Tools/MCP already share ToolRunner, Policy, ToolCall audit, sandbox, and event paths.
- Run Detail already shows Plan DAG, Tool Calls, Guardrails, Event Stream, Subagents, Model Calls, Replay, Eval Case save, and knowledge grounding evidence.
- Eval already has datasets, cases, Eval Runs, Regression Gate, Trace Grader state, and backend-backed history.
- Observability already links service health, metrics, traces, logs, and concrete Run routes.
- Sandboxes already expose WarmPool, tenant isolation, quota, and policy-backed resource settings.

Knowledge/RAG code now exists in the current worktree:

- `services/api-server/alembic/versions/20260514_0011_create_knowledge_rag.py` creates knowledge, document, chunk, embedding, retrieval, citation, and web-source records.
- `services/api-server/alembic/versions/20260516_0012_create_knowledge_audit_manifests.py` creates prompt assembly manifest and policy audit tables.
- `services/api-server/app/knowledge.py` implements ingestion, chunking, deterministic embeddings, vector capability state, lexical/CJK fallback, retrieval sessions, citations, prompt manifest persistence, policy/omission audit rows, and insufficient-local-evidence behavior.
- `services/api-server/app/api/agents.py` exposes `GET/POST /api/agents/{agent_id}/knowledge/sources`, uses knowledge grounding in normal Workspace chat, and returns manifest/audit evidence to Run Detail.
- `services/api-server/app/api/evals.py` includes a deterministic grounding contract grader for prompt manifest, policy decisions, sufficient retrieval, citation-hit inclusion, and forbidden-text leakage.
- `apps/agent-console/src/features/agents/pages/AgentListPage.tsx` includes a knowledge source add/list surface.
- `apps/agent-console/src/features/agents/components/ChatMessageBubble.tsx` renders assistant grounding metadata.
- `apps/agent-console/src/features/runs/pages/RunDetailPage.tsx` renders retrieval hits, citations, web sources, vector capability, local status, grounded status, prompt manifest counts/hash, and policy audit decisions.
- `services/api-server/tests/test_knowledge_rag.py` covers ingestion, versioning, lexical/CJK fallback, vector flag behavior, citation binding, prompt manifest persistence, policy audit rows, insufficient local evidence, tenant isolation, URL policy, API, and event behavior.

## Replanned Progress

### P0: Completed Baseline

Status: completed / keep closed.

- Private deployable Harness chain.
- Docker Compose private handoff.
- Release gate and handoff hygiene.
- Workspace execution evidence: context compression, Plan-Act, branching/search, Run Detail evidence, Eval Case capture.

### P1: Formalize Agent Knowledge Harness V1

Status: direction complete / gate-ready not proven.

Goal: turn the existing Knowledge/RAG implementation into the official recorded progress state.

Completed in the current P1 candidate:

- prompt manifest persistence;
- policy/omission audit persistence;
- citation snapshot metadata;
- Run Detail manifest/audit display;
- grounding Eval contract checks;
- CJK lexical fallback for small Chinese handbook content;
- regression coverage for sufficient evidence, insufficient evidence, tenant isolation, policy audit, and CJK single-chunk grounding.

Fresh validation evidence is captured in [[session-2026-05-16-agent-knowledge-p1-grounding-audit]].

Remaining gate blockers:

- bind prompt manifest to the exact `ModelCall` request/message hash;
- make Eval and Run Detail target exact evidence IDs for multi-query runs;
- prove denied/redacted content omission and isolation, not only selected/omitted retrieval candidates;
- verify Docker/private deployment migration compatibility for the new audit tables;
- run broader backend/frontend/docs/build/browser validation before marking P1 gate-ready or verified baseline.

### P2: Productize Local Knowledge Management

Status: planned.

Goal: make local knowledge usable beyond an inline demo form.

Scope:

- source lifecycle: edit, reingest, disable/delete, status, versions, provenance, expiry;
- document/file ingestion beyond inline text when safe;
- org-scoped versus agent-scoped source visibility;
- source health and indexing errors in Agent Studio;
- migration and backup notes for private deployment.

### P3: Add Real Policy-Gated Web Research

Status: planned / blocked on provider choice.

Goal: support external research only when a real provider and policy boundary exist.

Scope:

- provider adapter and configuration;
- URL allow/deny policy, private-network blocking, approval behavior, and audit;
- source snapshots and citation binding;
- explicit "local evidence insufficient" behavior when provider is disabled;
- no mock research presented as real evidence.

### P4: Build Memory And Context Router V2

Status: planned.

Goal: connect short-term memory, long-term memory, RAG, pinned context, compression, and prompt assembly.

Scope:

- session/branch memory projection from conversation tree and Run events;
- durable long-term memory records with provenance and deletion rules;
- prompt assembly manifest with included/omitted reasons;
- Workspace Context panel for memory/RAG/compression/token evidence;
- Run Detail snapshot of memory and prompt assembly.

### P5: Productize MCP And Skills

Status: planned.

Goal: make tools and skills manageable Harness capabilities, not hidden implementation details.

Scope:

- MCP server/method registry, health checks, schema, secret binding, and test invocation;
- skill manifest with instructions, allowed tools, examples, constraints, versions, and eval cases;
- attach/detach skills to Agents;
- Run metadata and Eval regression by active skill version.

### P6: Groundedness Eval And Observability

Status: planned.

Goal: make quality and hallucination control measurable.

Scope:

- groundedness, citation coverage, unsupported-claim, retrieval precision, fallback correctness graders;
- Observability filters for retrieval sessions, citations, insufficient-evidence, fallback, and unsupported claims;
- dashboards for token savings, retrieval cost, grounding quality, latency, and policy decisions.

### P7: Release And Demo Hardening

Status: planned.

Goal: preserve the private handoff quality while new capability layers grow.

Scope:

- Docker Compose migration smoke for knowledge tables;
- one-command seeded demo data for Knowledge/RAG;
- browser release smoke covering Agent Studio knowledge, Workspace grounding, and Run Detail knowledge evidence;
- updated runbooks for backup/restore, provider configuration, and failure diagnosis.

## Boundaries

- Do not reopen Stage 07. It is a completed foundation.
- Do not claim Agent Knowledge Harness completion from UI surfaces alone; each capability needs persisted records, runtime evidence, and tests.
- Do not add complex RBAC unless a later plan explicitly changes that boundary. Use existing agent/org isolation.
- Mock or deterministic retrieval helpers are acceptable for tests, but user-facing web research must require a real provider and policy gate.

## Related Pages

- [[project-handoff-current-state]]
- [[deep-interview-private-harness-chain]]
- [[agent-workspace-execution-evidence-architecture]]
- [[session-2026-05-14-workspace-execution-evidence]]
