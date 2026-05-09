# Guardrail Policy Spec

## Policy Domains

- Input policy
- Output policy
- Tool policy
- Data policy
- Cost policy
- Permission policy

## Required Behaviors

- Dangerous shell commands are blocked.
- Sensitive values are removed from model context.
- High-risk tools require human approval.
- Side-effect tools require an explicit approve, reject, or modify decision before execution.
- Runs pause when budget limits are exceeded.
- Output is checked before final delivery.

## Policy Events

Policy checks write `POLICY_CHECKED`. Blocks write `POLICY_DENIED` and a tool or task failure event when they affect execution.

## Approval Statuses

```text
REQUESTED -> APPROVED -> SUCCESS
REQUESTED -> MODIFIED -> APPROVED -> SUCCESS
REQUESTED -> BLOCKED
REQUESTED -> FAILED
```

## Workspace Pro Controls

Workspace Pro exposes guardrails at the point of action:

- Tool approval cards render before side-effect execution.
- Approve clears the pending ToolCall error and marks the approval decision.
- Reject keeps the action blocked and records the reason.
- Modify updates the pending ToolCall input JSON, records the modified payload, then approves.
- All decisions write actor, reason, ToolCall id, ToolApproval id, and modification flag.

Client-side pause stops the active stream but does not approve, reject, or execute any
side-effect tool. Server-side execution state remains controlled by Agent Run, ToolCall,
ToolApproval, Event Store, and policy evaluation.
