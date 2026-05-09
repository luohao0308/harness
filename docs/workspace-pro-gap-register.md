# Workspace Pro Gap Register

This register tracks the difference between the completed AI Harness Platform vertical slice and the full canonical Workspace Pro specification.

## Status Rule

The focused six-stage vertical slice is complete. Workspace Pro full-spec completion is not claimed until every gap below has implementation evidence and verification evidence.

## Gaps

| Gap | Spec reference | Current code evidence | Target outcome | Recommended verification |
|---|---|---|---|---|
| `tool_call_result` stream handling | `docs/03-api-spec.md` Workspace Pro stream requires `tool_call_result`; `docs/08-console-ui-spec.md` requires Tool Cards with output/status/latency | Backend stream in `services/api-server/app/api/agents.py` emits preview `tool_call_requested`, `artifact_created`, `usage`, and `done`; frontend parser in `apps/agent-console/src/features/tasks/api.ts` recognizes `tool_call_result`, but `AgentWorkspacePage` does not consume it | Backend emits `tool_call_result` for executed tools, and Workspace Tool Cards update with output summary, status, duration, and trace id | Add/extend backend stream test in `services/api-server/tests/test_agents.py`; add frontend handler/build verification |
| Continue preserves Run and branch semantics | `docs/03-api-spec.md` says continue preserves original `run_id`, `active_branch_id`, and `continue_from_node_id`; `docs/08-console-ui-spec.md` describes paused assistant resume | Frontend sends `continue_from_node_id` and partial content; backend request schema accepts these fields, but current stream creates a plan-oriented Run path without explicit branch persistence | Continue resumes a paused assistant node while preserving original Run and branch identity or explicitly documents P0 client-only semantics | Backend test proves run/branch linkage, or docs mark server persistence as deferred |
| Artifact extraction beyond `plan.json` | `docs/08-console-ui-spec.md` requires code, JSON, diff, chart, and text preview from stream events, tool results, and subagent outputs | Workspace collects stream artifacts and plan JSON; extraction from assistant code blocks, tool outputs, and subagent artifacts is not proven | Artifacts panel consistently renders code/json/diff/chart/text from supported sources | Add fixture-based frontend check or manual smoke checklist plus backend projection test |
| Meaningful cost semantics | `docs/03-api-spec.md` usage event includes cost; `docs/08-console-ui-spec.md` displays cost in metadata | Current stream reports `cost_usd: "0"` | Cost is computed from model settings/pricing or clearly marked unavailable when pricing is missing | Model-call usage test covers nonzero configured pricing or unavailable marker |
| Conversation branch sibling navigation | `docs/08-console-ui-spec.md` requires tree-shaped conversation state and branch-preserving edits | Store supports children, and edit/resend creates branchable nodes; visible sibling navigation is not explicit | User can see and switch between sibling branches without old branch loss | Frontend component/e2e test or manual smoke captures sibling branch navigation |
| Frontend test infrastructure | `docs/qa/test-strategy.md` tracks frontend checks; `apps/agent-console/package.json` currently has no `test` script | Frontend verification currently relies on `npm run build` | Add component/e2e test tooling when the project is ready to own it, or keep test infra as an explicit deferred gap | `package.json` has real `test` script and CI/docs use it, or docs continue to mark it deferred |

## Required Before Closing This Register

- Each gap has an implementation PR or commit reference.
- Each gap has fresh verification output.
- `docs/TECHNICAL-IMPLEMENTATION-PROGRESS.md`, `docs/task-progress.md`, and `docs/human/10-task-progress.md` are updated to remove the deferred status only after evidence exists.
