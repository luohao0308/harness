# Tool MCP Runtime Spec

## Tool Runtime

The Tool Runtime centralizes tool registration, permission checks, execution, sandbox binding, tracing, and output normalization.

## Tool Types

- Shell
- Filesystem
- Browser
- HTTP
- GitHub
- Database
- MCP Tools

## Runtime Contract

```text
Tool request
-> registry lookup
-> permission policy
-> sandbox policy
-> approval policy
-> execute or block
-> persist ToolCall
-> append task event
```

## MCP Adapter

MCP tools are exposed through the same ToolCall schema and policy flow as built-in tools. MCP transport details do not leak into Agent plans.

## Workspace Tool Tray

Workspace Pro exposes registry-backed tools in the left Tool Tray.

Tool Tray entries include:

- tool name
- source
- category
- risk level
- sandbox requirement
- MCP server and method for MCP-shaped tools

The Chat Console supports structured tool mentions such as `@mcp_context_search` and
`@read_file`. Mentions are sent as structured request fields and are not treated as
untrusted plain-text commands.

## Tool Calling Cards

Each visible tool call renders as a Tool Calling Card with:

- tool name
- status
- risk level
- sandbox id
- input JSON
- output JSON
- output summary
- duration
- trace id

Pending side-effect calls render an approval card before execution.

## Approval Modify Flow

High-risk side-effect tools use the approval flow:

```text
PENDING_APPROVAL -> APPROVED
PENDING_APPROVAL -> REJECTED
PENDING_APPROVAL -> MODIFIED_APPROVED
```

`MODIFIED_APPROVED` means the approver changed tool input JSON before approval. The
ToolCall input, ToolApproval request JSON, decision JSON, and approval event record the
modified input.

## Artifact Extraction

Tool results and subagent outputs with code, JSON, diff, chart, file, or report content
are eligible for the Workspace Pro Artifacts panel. Artifact rendering never bypasses the
Tool Runtime, policy engine, audit trail, or sandbox boundary.
