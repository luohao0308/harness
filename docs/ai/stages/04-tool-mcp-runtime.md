# Stage 4: Tool / MCP Runtime

## Goal

Unify built-in tools and MCP tools under one registry, policy, execution, and trace contract.

## Input

Tool request from Executor or Subagent.

## Output

ToolCall audit row, tool event, normalized output, and console-visible trace.

## Modules

Tool Registry, Tool Runner, MCP Adapter, Sandbox Manager, Policy Engine.

## API And Schema Changes

Extend `/api/tasks/{task_id}/tools/execute` and tool registry metadata to support MCP-shaped tools.

## Event Types

`TOOL_CALLED`, `TOOL_RESULT_RECEIVED`, `TOOL_FAILED`, `TOOL_TIMEOUT`, `TOOL_DENIED_BY_POLICY`.

## Frontend Display

Run Detail shows tool name, input, output, status, latency, risk, sandbox, and trace ID.

## Tests

Tool policy tests, tool execution tests, MCP adapter contract tests.

## Acceptance

Built-in and MCP tools share one audit and policy path.

## Not Doing

Vendor-specific MCP UI configuration is outside this stage.

## Vertical Slice Demo

```text
Run tool from Agent step
-> policy checks it
-> execution writes ToolCall
-> console displays trace
```
