# Agent Knowledge Harness Roadmap

Category: `decision`

Tags: `agent-knowledge-harness`, `memory`, `rag`, `mcp`, `skills`, `token-optimization`, `hallucination`

## Decision

The next product direction after the completed private-deployable Harness chain is **Agent Knowledge Harness**.

The goal is to make the Harness layer responsible for giving the model better usable capability:

```text
Model + Harness = Agent
```

For this lane, the Harness means knowledge, memory, retrieval, MCP/skills, context selection, token control, citation evidence, and hallucination reduction.

## V1 Thin Slice

The first implementation target is **Memory/RAG Grounding Loop**:

1. User adds long-term knowledge or a document.
2. The platform chunks/indexes it.
3. A later Workspace question retrieves relevant knowledge.
4. The Agent cites retrieved sources.
5. If local evidence is insufficient, the Agent states that local knowledge is insufficient; web research stays disabled until a real policy-gated provider is configured.
6. Run Detail, observability, or Eval shows retrieval/citation evidence.

Source spec:

- `.omx/specs/deep-interview-agent-knowledge-harness-memory-rag.md`

## Follow-Up Goals For Future Engineers

These are not discarded because v1 focuses on Memory/RAG. They are the intended follow-up product targets:

- **MCP creation and management**: create/register MCP servers or MCP-shaped tools, attach them to Agents, invoke them through policy/sandbox/audit, and show evidence in Run Detail.
- **Skill creation and management**: define reusable skills/capability packs with instructions, tool bindings, constraints, examples, and tests; version them and attach them to Agents.
- **Short-term memory**: workspace/session/branch memory for active task state, preferences, facts, and unresolved decisions.
- **Long-term memory**: durable Agent/org memory with provenance, update rules, deletion/expiry behavior, and retrieval evidence.
- **Token and context optimization**: coordinate context compression, memory selection, RAG selection, prompt assembly, token savings, and visible inclusion/omission reasons.
- **Hallucination reduction**: prefer cited knowledge, handle missing evidence explicitly, use policy-gated web research only when a real provider exists, and validate groundedness with Eval/regression.

## Boundaries

V1 may add Alembic migrations, vector retrieval, embedding provider configuration, and policy-gated web research tooling. Mock web research must remain opt-in development behavior and must not be presented as real evidence.

V1 should not add complex RBAC or a full permission redesign. Use existing agent/org isolation unless a later explicit plan changes that boundary.

Do not reopen Stage 07 as active work. This is a new post-Stage-07 product direction.

## Related Pages

- [[project-handoff-current-state]]
- [[deep-interview-private-harness-chain]]
- [[agent-workspace-execution-evidence-architecture]]
