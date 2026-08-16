# Deep Interview Spec: Agent Knowledge Harness Memory/RAG

## Metadata

- Profile: standard
- Context type: brownfield
- Rounds: 6
- Final ambiguity: 0.12
- Threshold: 0.20
- Context snapshot: `.omx/context/next-product-lane-from-final-goal-20260514T121413Z.md`
- Transcript: `.omx/interviews/agent-knowledge-harness-memory-rag-20260514T123351Z.md`

## Clarity Breakdown

| Dimension | Score | Notes |
| --- | ---: | --- |
| Intent | 0.95 | User wants Harness capabilities that make models more useful, grounded, and token-efficient. |
| Outcome | 0.90 | First proof is a Memory/RAG grounding loop with citations and anti-fabrication behavior. |
| Scope | 0.84 | Unified Agent Knowledge Harness is the product direction; v1 is Memory/RAG first. |
| Constraints | 0.84 | Complex RBAC is out; migrations/vector/embedding/web research are authorized. |
| Success Criteria | 0.86 | User-facing proof is document/knowledge ingestion -> retrieval -> cited answer -> fallback research. |
| Context | 0.90 | Existing MCP/context-router surfaces were inspected; missing RAG infrastructure is known. |

## Intent

Move the platform toward an **Agent Knowledge Harness**: the Harness layer should not only execute plans and tools, but also make the model more useful by managing knowledge, retrieval, memory, evidence, hallucination policy, and token/context pressure.

This fits the final product thesis:

```text
Model + Harness = Agent
```

The Harness should give the model the right context, callable capabilities, durable memory, source evidence, and verifiable behavior.

## Desired Outcome

Implement the first thin slice of Agent Knowledge Harness as a **Memory/RAG Grounding Loop**:

1. A user adds long-term knowledge or a document to an Agent or organization knowledge space.
2. The platform chunks/indexes it for retrieval.
3. A later Agent Workspace question retrieves relevant knowledge.
4. The Agent answer cites retrieved sources.
5. If local knowledge is insufficient, the Agent states that clearly, runs controlled web research automatically, and answers from the newly gathered sources.
6. Run Detail, observability, or Eval surfaces show retrieval/citation evidence so the behavior is auditable.

## Broader New Product Goal

This spec establishes **Agent Knowledge Harness** as the next product direction after the completed private-deployable Harness chain. Memory/RAG grounding is only v1, not the whole goal.

Future engineers should preserve these follow-up goals as first-class next targets:

1. **MCP creation and management**
   - Users can create/register MCP servers or MCP-shaped tools.
   - Agent Studio can attach those capabilities to an Agent.
   - Agent Runs can invoke them through policy, sandbox/audit, and Run Detail evidence.

2. **Skill creation and management**
   - Users can define reusable skills or capability packs for Agents.
   - Skills can carry instructions, tool bindings, constraints, examples, and tests.
   - Skills should be versioned, attachable to Agents, and visible in Run evidence when they affect behavior.

3. **Short-term memory**
   - Workspace/session/branch-scoped memory captures active task state, preferences, facts, and unresolved decisions.
   - Short-term memory must be editable, inspectable, and excluded or compressed under token pressure.

4. **Long-term memory**
   - Agent/org-scoped durable memory stores stable facts, preferences, decisions, and reusable context.
   - Long-term memory must have provenance, update rules, deletion/expiry behavior, and retrieval evidence.

5. **Token and context optimization**
   - Context compression, memory selection, RAG selection, and prompt assembly should work together.
   - Users and engineers should be able to see why context was included or omitted.
   - Token savings, retrieval cost, and grounding quality should become observable signals.

6. **Hallucination reduction as a Harness contract**
   - The Agent should prefer cited knowledge over unsupported generation.
   - Missing or weak evidence should trigger the resolved v1 fallback policy: disclose local insufficiency, run controlled web research, and cite new sources.
   - Eval/regression should measure groundedness, citation quality, and unsupported-claim behavior.

These follow-up goals should not be collapsed into v1 unless a later plan explicitly widens scope. They are the intended roadmap after the Memory/RAG grounding loop proves the foundation.

## In Scope

- Productized knowledge sources for Agent/organization scope.
- Lightweight knowledge/document management sufficient for the v1 loop.
- Alembic migrations for knowledge sources, documents, chunks, embeddings, retrieval hits, citations, or equivalent records.
- Postgres/pgvector or equivalent vector retrieval.
- Embedding provider configuration.
- Controlled web research/crawl tooling for fallback when local evidence is insufficient.
- Prompt/context assembly changes so retrieved evidence is injected explicitly and separated from chat history.
- Hallucination policy behavior: do not silently invent when evidence is missing.
- Run Detail / audit evidence for retrieval hits, source citations, and fallback web research.
- Tests that prove grounded answer behavior, insufficient-local-knowledge fallback, and source evidence recording.

## Out Of Scope / Non-goals

- Complex permissions or full RBAC redesign.
- Kubernetes, SaaS commercialization, cloud deployment matrix, or product repositioning.
- Reopening Stage 07 as active work.
- Building every Agent Knowledge Harness capability in v1. MCP/skill creation and full token optimization remain part of the broader direction, but v1 anchors on Memory/RAG grounding.
- Model-internal KV cache, token merging, or provider-private context mechanisms that are not available through the current model gateway.

## Decision Boundaries

OMX may autonomously decide:

- Exact schema names and API shape for knowledge sources, documents, chunks, embeddings, retrieval hits, and citations.
- Whether the first vector implementation uses pgvector or an equivalent local retrieval approach, as long as the choice is justified in `$ralplan`.
- The smallest UI surfaces needed in Agent Studio, Agent Workspace, and Run Detail for v1 proof.
- Test fixture design and fake embedding/search adapters needed for deterministic tests.
- Documentation and progress/wiki updates required for handoff.

OMX is authorized to:

- Add Alembic migrations.
- Add dependencies required for vector retrieval, embedding, document parsing, or controlled web research.
- Add embedding provider configuration.
- Add controlled web research tools.

OMX must pause before:

- Complex RBAC/permission redesign.
- Destructive database migrations.
- Broad remote browsing/crawling without policy limits.
- Repositioning the product away from `Model + Harness = Agent`.
- Turning v1 into a full MCP/skill marketplace or full token-optimization platform.

## Constraints

- Preserve existing Agent Run and Tool/MCP audit contracts where possible.
- Keep Stage 07 closed historical context.
- Use existing agent/org isolation for v1.
- Web research must be controlled, auditable, and source-cited.
- RAG evidence must be visible enough to debug hallucination and retrieval failure.
- Tests should not require external network or paid embedding providers; use deterministic fakes where needed.

## Testable Acceptance Criteria

1. A knowledge source or document can be created for an Agent or organization scope.
2. The source is chunked and indexed for retrieval.
3. A Workspace question retrieves relevant local knowledge and injects it into the model prompt/context.
4. The answer includes source citations or source references.
5. Retrieval hits and citations are recorded with the Agent Run or related audit trail.
6. When local retrieval confidence is insufficient, the Agent response path states local knowledge is insufficient and automatically runs controlled web research.
7. Web research results are recorded as sources and used in the answer with citations.
8. Run Detail or an equivalent evidence surface shows local retrieval hits, web-research fallback, and citations.
9. Eval/regression coverage can assert that answers are grounded in retrieved evidence and do not fabricate unsupported claims.
10. Existing quick smoke/build/backend regression gates still pass, or any validation gap is explicitly recorded.

## Assumptions Exposed And Resolved

- Assumption: the next lane should be deployment/adoption hardening.
  - Resolution: user wants model-enhancing Harness capabilities instead.
- Assumption: the unified Agent Knowledge Harness might implement MCP, skill, memory, RAG, and token optimization together.
  - Resolution: plan the unified direction, but v1 proof is Memory/RAG.
- Assumption: v1 should avoid new infrastructure.
  - Resolution: user authorized migrations, vector retrieval, embedding config, and controlled web research.
- Assumption: evidence gaps might lead to refusal only.
  - Resolution: local-insufficient answers should trigger controlled web research and cite new sources.

## Brownfield Evidence Vs Inference

- Evidence: `services/api-server/app/tools/registry.py` contains MCP-shaped tools today.
- Evidence: `services/api-server/app/tools/mcp_adapter.py` is local/deterministic and preserves the audit contract.
- Evidence: `services/api-server/app/agents/context_router.py` already emits memory/RAG-shaped sections, but from task traces rather than productized knowledge storage.
- Evidence: `services/api-server/pyproject.toml` has no pgvector/embedding/RAG/crawler dependencies.
- Evidence: current DB models lack knowledge/document/chunk/embedding/citation/memory tables.
- Inference: the highest-leverage next lane is a Memory/RAG grounding layer that converts existing context-router/MCP concepts into durable product behavior.

## Recommended Handoff

Use `$ralplan` before execution because this lane includes schema design, dependencies, retrieval architecture, model prompt behavior, UI evidence, and test strategy:

```text
$plan --consensus --direct .omx/specs/deep-interview-agent-knowledge-harness-memory-rag.md
```

After `$ralplan`, use `$autopilot` or `$ralph` for implementation. Use `$team` only if the approved plan splits cleanly into independent backend retrieval, frontend evidence, and verification lanes.

`$ultragoal` is also suitable after planning if this should become a durable multi-step product goal.
