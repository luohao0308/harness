# Local Agent Tool Safety V3

Category: `session-log`

Tags: `local-agent`, `tool-safety`, `approval`, `hao`, `bridge`, `audit`

## Summary

Local Agent Tool Safety V3 is planned, documented, and independently reviewed as the next implementation baseline after V1/V2.

V3 closes the V1/V2 architecture watch item: bridge-reported `tool_result` stays observation-only until local host execution is governed by Harness-owned tool request, policy, approval, authorized result, command lifecycle, pending change, cancel/retry, privacy, and audit fail-closed contracts.

## Planning Documents

- `.omx/plans/prd-local-agent-tool-safety-v3.md`
- `.omx/plans/test-spec-local-agent-tool-safety-v3.md`

## Planned Scope

- Add local tool request, decision, result, command lifecycle, cancel, retry, and pending-change APIs under the existing local-Agent bridge boundary.
- Keep API/DB as the only authority for `ToolCall`, `ToolApproval`, `AgentEvent`, Run/Task, `AgentSession`, local tool request state, and audit evidence.
- Treat bridge risk fields as advisory telemetry only; server-side classification remains deny-by-default.
- Split local host approval from generic server ToolRunner approval. Local approval unlocks bridge polling, not server-side execution.
- Reject side-effect results that lack an authorized `tool_request_id` / `tool_call_id`.
- Preserve fake bridge and hao as the V3 acceptance adapters; Codex CLI and Claude Code remain disabled future adapters.

## Review Gate

Two independent plan reviewers reached PASS after revisions:

- Aristotle architecture review: `PASS`. Watch items are local `ToolCall(APPROVED)` semantics, event/OpenAPI/UI projection coverage, avoiding unnecessary new statuses, and tightly keying the local approval branch by provenance plus `LocalAgentToolRequest.tool_call_id`.
- Parfit security/test review: `PASS`. Watch items are strict separation from generic `ToolApproval -> ToolRunner`, deny-by-default server classification, service guards for SQLite cross-table invariants, exactly-once smoke side effects in a temp workspace, and a fixed redaction corpus.

No plan blockers remain before V3 implementation.

## Branch And Delivery Policy

- V3 planning branch: `feature/local-agent-tool-safety-v3`.
- V1/V2 reviewed implementation branch: `feature/local-agent-bridge-v1-v2`.
- New functionality must stay off `main` until review, verification, commit, and push are complete.
- Each future version plan must be入库 first, then pass two independent agent reviews before execution.
- After each implementation slice, run code review, fix blockers, verify, commit, and push.

## Implementation Baseline

Start V3 implementation from these gates:

1. Protocol and migration for local tool request, command, and pending-change projection.
2. Backend policy/approval path that writes `ToolCall`, `ToolApproval`, `AgentEvent`, and Run state transactionally.
3. hao bridge pre-execution authorization, decision polling, lifecycle reporting, cancel/retry, and pending-change hash guards.
4. Workspace/Run Detail/Agent Studio projection using existing surfaces.
5. Security negative tests, deterministic smoke, docs validation, and code review before commit.

## Validation For This Planning Closeout

```text
python3 scripts/validate-docs.py
git diff --check
```

This page records the planning closeout only. V3 implementation evidence belongs in a later session update after code lands and review passes.
