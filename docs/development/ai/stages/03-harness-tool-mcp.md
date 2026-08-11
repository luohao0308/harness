# Stage 3: Harness Management And Tool MCP Runtime

## Goal

Expose the Harness runtime layer used by Agents: tools, MCP, permissions, sandbox policy, and orchestration controls.

## Input

- Tool Registry metadata.
- MCP-shaped tool metadata.
- Agent allowed tools.
- Sandbox policy settings.

## Output

- `/tools` displays API-backed built-in and MCP-shaped tools.
- Tool calls record status, input, output, risk, latency, sandbox, and trace.
- Agent assignments respect tool allowlists.

## Modules

- Tool Registry
- MCP Adapter
- Tool Runner
- Policy Engine
- Sandbox Runtime
- Multi-Agent Orchestrator

## API And Schema Changes

- Keep `GET /api/tools/registry`.
- Tool execution records use status values `REQUESTED`, `APPROVED`, `BLOCKED`, `SUCCESS`, `FAILED`, `TIMEOUT`, and compatibility values already in storage.
- Workspace projection includes `tool_calls`, `approvals`, `assignments`, and `handoffs`.

## Event Types

- `POLICY_CHECKED`
- `POLICY_DENIED`
- `TOOL_CALLED`
- `TOOL_RESULT_RECEIVED`
- `TOOL_FAILED`
- `TOOL_TIMEOUT`
- `TOOL_APPROVAL_REQUESTED`
- `AGENT_SELECTED`
- `AGENT_ASSIGNMENT_CREATED`
- `AGENT_ASSIGNMENT_STARTED`
- `AGENT_ASSIGNMENT_COMPLETED`
- `AGENT_ASSIGNMENT_FAILED`
- `AGENT_REDUCE_COMPLETED`

## Frontend Display

- `/tools` lists name, source, category, risk, sandbox requirement, roles, schema, and MCP method.
- Workspace and Run Detail show Tool Calls and Approvals.
- Harness management entries for DAG and triggers stay disabled until API-backed.

## Tests

- Backend tests cover registry, tool execution, MCP adapter, policy denial, and assignment allowlist.
- Frontend build covers `/tools` and Run projection rendering.

## Acceptance

- Tool data is API-backed.
- High-risk actions enter policy or approval path.
- Run detail shows tool trace and status.

## Not Doing

- No remote MCP transport beyond current adapter slice.
- No trigger execution engine.
- No visual DAG editor.

## Vertical Slice Demo

```text
Open /tools
-> inspect registry
-> create a Plan from Agent Workspace
-> open Run detail and confirm execution
-> inspect Tool Calls, policy events, approval state, and assignment statuses
```
