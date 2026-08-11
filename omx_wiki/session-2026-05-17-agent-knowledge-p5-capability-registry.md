# Session 2026-05-17 Agent Knowledge P5 Capability Registry

Category: `session-log`

Tags: `agent-knowledge-harness`, `p5`, `capability-registry`, `mcp`, `skills`, `tool-approval`, `workspace`, `run-detail`

## Summary

Agent Knowledge Harness P5 MCP/Skills productization is implemented, reviewed, split into atomic commits, and pushed to `origin/main` through `f05816e`.

The delivered slice replaces runtime `Agent.tools_json` authority with persisted capability attachments. `Agent.tools_json` remains only as legacy preset metadata and deterministic migration/seed backfill input; runtime execution resolves through `CapabilityRegistry -> AgentCapabilityAttachment -> immutable CapabilityVersion -> ToolRunner metadata snapshot`.

## Pushed Commits

```text
67b7a5c Add capability registry storage contract
237c403 Resolve tool execution through capability attachments
b0fbbd2 Expose capability-bound tool feedback in console
152d070 Cover capability and approval regressions
f05816e Record P5 capability registry handoff
```

Push evidence:

```text
git push origin main
6c4a95d..f05816e  main -> main
git rev-list --left-right --count origin/main...HEAD
0 0
```

## Key Implementation Points

- `Capability`, `CapabilityVersion`, `AgentCapabilityAttachment`, and `CapabilitySnapshot` persist capability authority and immutable hash evidence.
- Runtime tool execution fails closed when no Agent capability attachment scope is supplied.
- Workspace chat, Agent Run, assignment, subagent, compatibility, approval, and test invocation paths resolve tools through capability attachments.
- Admin capability validation is non-executing and redacts secrets before hashing.
- Agent-scoped test invocation executes through `ToolRunner`, `ToolCall`, and `EventStore`.
- Approval decisions now execute approved calls or fail rejected calls, then update Run state and tool events.
- Workspace and Run Detail surface live tool status, output summaries, capability hashes, and refreshed approval state.

## Verification

Latest validation before commit/push:

```text
cd services/api-server && .venv/bin/python -m pytest tests/test_tool_approvals.py -> 3 passed
cd services/api-server && .venv/bin/python -m ruff check app tests -> passed
cd apps/agent-console && npm run lint -> passed
cd apps/agent-console && npm run test -- --run src/features/agents/__tests__/WorkspaceShellBar.render.test.tsx src/features/agents/__tests__/applyChatEvents.property.test.ts src/features/runs/pages/__tests__/RunDetailPage.helpers.test.ts -> 11 passed
git diff --check HEAD~5..HEAD -> passed
```

Broader P5 verification recorded before the final approval-sync fix:

```text
cd services/api-server && uv run pytest -q -> 272 passed
cd services/api-server && DATABASE_URL=sqlite:////tmp/harness-p5-alembic.sqlite uv run alembic upgrade head -> reached 20260517_0018
```

## Manual Test Report

Tracked report:

```text
docs/工作日志/reports/p5-mcp-skills-code-review-and-manual-test-2026-05-17.html
```

The report explains the new capability boundary and lists only user-facing frontend manual test operations.

## Remaining Local Untracked Files

These were intentionally not committed or pushed during the Git Master pass:

```text
.omc/
.vscode/settings.json
apps/agent-console/src/features/agents/lib/_probe.ts
services/api-server/uv.lock
```

They appear to be local runtime, IDE, probe, or untracked lockfile state outside the committed product slice.

## Next Work

The next planned Agent Knowledge Harness lane is P6 Groundedness Eval and Observability.

Start from [[agent-knowledge-harness-roadmap]] and [[project-handoff-current-state]] before beginning P6.
