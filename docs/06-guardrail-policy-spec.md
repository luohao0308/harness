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
- Runs pause when budget limits are exceeded.
- Output is checked before final delivery.

## Policy Events

Policy checks write `POLICY_CHECKED`. Blocks write `POLICY_DENIED` and a tool or task failure event when they affect execution.

## Approval Statuses

```text
REQUESTED -> APPROVED -> SUCCESS
REQUESTED -> BLOCKED
REQUESTED -> FAILED
```
