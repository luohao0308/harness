# Agent Workspace Execution Evidence Architecture

Category: `architecture`

Tags: `workspace`, `agent-console`, `context-compression`, `plan-act`, `branching`, `run-detail`, `eval-case`

## Purpose

This page captures the durable architecture decisions from commit `e78f52a`.

The change makes Agent Workspace preserve raw conversation state while adding executable evidence flows:

- branch-aware context compression,
- Plan-Act approval without approval loops,
- search/branch navigation that does not hide current history,
- Run Detail evidence surfaces,
- completed/failed Run capture into Eval Cases.

## Core Principle

Raw Workspace history is never deleted to save context. Compression changes the future prompt payload only.

The effective prompt context is:

1. system prompt,
2. attachment context,
3. validated compressed summary,
4. pinned raw messages,
5. uncovered recent raw messages,
6. current user goal.

The UI context ring must show the effective next prompt estimate after compression, not the raw transcript size alone. Hover can still expose the raw estimate.

## Frontend State

Workspace compression state is branch/path scoped and persisted with conversation history.

Key files:

- `apps/agent-console/src/features/agents/lib/contextCompression.ts`
- `apps/agent-console/src/stores/workspaceStore.ts`
- `apps/agent-console/src/features/agents/hooks/useChatStream.ts`
- `apps/agent-console/src/features/agents/components/ContextRing.tsx`
- `apps/agent-console/src/features/agents/components/ChatSurface.tsx`

Important state fields:

- `contextMaxTokens`: default `258_000`
- `autoCompressionRatio`: default `0.8`
- `contextCompressions`: branch-keyed summary cache

Summaries include provenance:

- `coverageNodeIds`
- `coveragePathHash`
- `lastCoveredNodeId`
- schema/prompt versions
- compressor provider/model
- estimated original/summary/uncovered tokens
- cache/status/error metadata

## Backend Compression Contract

Backend endpoint:

```text
POST /api/agents/{agent_id}/context/compress
```

Implemented in:

- `services/api-server/app/api/agents.py`
- `services/api-server/app/api/schemas.py`
- `services/api-server/tests/test_agents.py`

The backend treats prior client summaries as untrusted cache hints. It validates submitted raw active-path messages, coverage ids, coverage hash, prompt/schema versions, and normalized provider/model before accepting or extending a summary.

Provider failures return typed `provider_error` responses instead of silently mutating context state.

## Plan-Act Approval

`markdown_plan` is markdown planning output that can show the approval panel.

`plan` is already a Plan-Act Run output and must not show approval again.

This prevents:

```text
approve -> plan run result -> approve panel -> plan run result -> ...
```

Key files:

- `apps/agent-console/src/features/agents/lib/planApprovalGate.ts`
- `apps/agent-console/src/features/agents/components/PlanApprovalPanel.tsx`
- `apps/agent-console/src/features/agents/__tests__/planApprovalGate.test.ts`

Approval runs from the original user goal, not from the model-produced plan text.

## Search And Branching

Conversation search should reveal a message without truncating the visible path.

If a search hit is already in the current active path, the UI scrolls and highlights it only. It does not call `setActiveLeafId`, because that would resolve a new branch leaf and can hide later messages.

Only hits outside the current active path switch the active branch.

Key files:

- `apps/agent-console/src/features/agents/pages/AgentWorkspacePage.tsx`
- `apps/agent-console/src/features/agents/components/ChatMessageList.tsx`
- `apps/agent-console/src/features/agents/pages/agentWorkspaceDerive.ts`
- `apps/agent-console/src/features/agents/__tests__/agentWorkspaceDerive.test.ts`

Assistant branch creation reuses the previous user message as the new branch goal and shows branch switchers for sibling assistant nodes.

## Slash Command Selection

Slash command menu selection uses pointer-down with click fallback so mouse/touch selection fires before textarea blur can reclassify the command.

Key file:

- `apps/agent-console/src/features/agents/components/SlashCommandMenu.tsx`

Regression coverage:

- `apps/agent-console/src/features/agents/__tests__/ChatSurface.shell.test.tsx`

## Run Detail Evidence

Run Detail is the product proof surface for execution evidence.

Covered evidence:

- Plan DAG steps,
- `depends_on`,
- `sync` / `async`,
- `Sandbox` / `Subagent` labels,
- Tool Calls,
- Guardrails,
- Event Stream,
- Model Calls,
- Replay,
- Save as Eval Case.

Key files:

- `apps/agent-console/src/features/runs/pages/RunDetailPage.tsx`
- `apps/agent-console/e2e/run-detail.smoke.spec.ts`
- `apps/agent-console/src/features/tasks/api.ts`
- `services/api-server/app/api/tasks.py`
- `services/api-server/app/api/schemas.py`

## Eval Case Capture

COMPLETED and FAILED Runs show `Save as Eval Case`.

If a dataset exists, the user can choose it. If no dataset exists, Run Detail exposes a recoverable default path: selecting the default option creates `Saved Runs` and then saves the case.

This avoids the previous failure mode where an empty dataset list disabled the save button.

## Related Pages

- [[project-handoff-current-state]]
- [[session-2026-05-14-workspace-execution-evidence]]
- [[local-dev-eval-dataset-migration]]
- [[workspace-demo-ready-constraints]]
