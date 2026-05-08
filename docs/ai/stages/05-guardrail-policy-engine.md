# Stage 5: Guardrail / Policy Engine

## Goal

Make the platform visibly controllable through input, output, tool, data, cost, and permission policies.

## Input

User task, model output, tool request, data payload, cost counters, and principal roles.

## Output

Policy decision, approval request, block event, sanitized context, or paused run.

## Modules

Policy Engine, Tool Runner, Model Gateway, Settings API, approval UI.

## API And Schema Changes

Policy settings expose risk levels, approvals, sandbox rules, budget rules, and data handling rules.

## Event Types

`POLICY_CHECKED`, `POLICY_DENIED`, `TOOL_DENIED_BY_POLICY`, `USER_ACTION`.

## Frontend Display

Run Detail shows guardrail blocks and pending approvals. Settings shows active policy.

## Tests

Dangerous shell commands are blocked. High-risk tool calls require approval. Sensitive fields are redacted.

## Acceptance

The demo can prove a dangerous action is prevented and audited.

## Not Doing

Enterprise SSO is outside this stage.

## Vertical Slice Demo

```text
Ask Agent to run dangerous shell command
-> policy blocks or requests approval
-> event appears in trace
```
