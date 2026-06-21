# Workspace Pro Gap Register

This register tracks the difference between the completed AI Harness Platform vertical slice and the full canonical Workspace Pro specification.

## Status Rule

The focused six-stage vertical slice is complete. Workspace Pro full-spec completion is not claimed until every gap below has implementation evidence and verification evidence.

## Gaps

| Gap | Spec reference | Current code evidence | Target outcome | Recommended verification |
|---|---|---|---|---|
| `tool_call_result` stream handling | `docs/03-api-spec.md` Workspace Pro stream requires `tool_call_result`; `docs/08-console-ui-spec.md` requires Tool Cards with output/status/latency | Implemented in `services/api-server/app/api/agents.py` and `apps/agent-console/src/features/agents/pages/AgentWorkspacePage.tsx`; low-risk `ToolRunner` calls now emit stable `tool_call_id` request/result pairs, and the Workspace merges result cards by id | Closed in this pass | `services/api-server/.venv/bin/python -m pytest services/api-server/tests/test_agents.py services/api-server/tests/test_tool_approvals.py`; `cd apps/agent-console && npm run build` |
| Continue preserves Run and branch semantics | `docs/03-api-spec.md` says continue preserves original `run_id`, `active_branch_id`, and `continue_from_node_id`; `docs/08-console-ui-spec.md` describes paused assistant resume | Implemented in `AgentChatStreamRequest`, SSE `done` payloads, and stream tests; continue now preserves the supplied run id when valid and returns a recoverable error for missing/unauthorized runs | Closed in this pass | `services/api-server/.venv/bin/python -m pytest services/api-server/tests/test_agents.py services/api-server/tests/test_tool_approvals.py` |
| Artifact extraction beyond `plan.json` | `docs/08-console-ui-spec.md` requires code, JSON, diff, chart, and text preview from stream events, tool results, and subagent outputs | Implemented in `apps/agent-console/src/features/agents/workspaceArtifacts.ts` and rendered in the Workspace Artifacts panel for assistant/tool outputs | Closed in this pass | `cd apps/agent-console && npm run build` |
| Meaningful cost semantics | `docs/03-api-spec.md` usage event includes cost; `docs/08-console-ui-spec.md` displays cost in metadata | Implemented with `cost_usd: null` plus `cost_unavailable: true` on stream usage events, and the UI now renders `Unavailable` instead of fake `$0` | Closed in this pass | `services/api-server/.venv/bin/python -m pytest services/api-server/tests/test_agents.py`; `cd apps/agent-console && npm run build` |
| Conversation branch sibling navigation | `docs/08-console-ui-spec.md` requires tree-shaped conversation state and branch-preserving edits | Implemented in `apps/agent-console/src/stores/workspaceStore.ts` and `apps/agent-console/src/features/agents/pages/AgentWorkspacePage.tsx`; sibling branch switching is visible and preserves prior branches | Closed in this pass | `cd apps/agent-console && npm run build` |
| Approve, Reject, Modify tool approvals | `docs/03-api-spec.md` exposes approve/reject/modify approval endpoints; `docs/08-console-ui-spec.md` requires tool approvals with approve, reject, and modify actions for admins | Implemented in Run Detail approval cards and Workspace Inspector runtime cards; Modify opens a JSON editor, validates object JSON locally, calls `modifyToolApproval`, and refreshes approval state | 已实现 | Targeted TypeScript, production Vite build, and `tests/test_tool_approvals.py` pass |
| Frontend test infrastructure | `docs/qa/test-strategy.md` tracks frontend checks; `apps/agent-console/package.json` currently has no `test` script | Frontend verification currently relies on `npm run build` | Add component/e2e test tooling when the project is ready to own it, or keep test infra as an explicit deferred gap | `package.json` has real `test` script and CI/docs use it, or docs continue to mark it deferred |

## Required Before Closing This Register

- The first five product gaps above are closed and verified in this pass.
- Frontend test infrastructure remains the only deferred item.
- `docs/TECHNICAL-IMPLEMENTATION-PROGRESS.md`, `docs/task-progress.md`, and `docs/human/10-task-progress.md` reflect that split truthfully.
