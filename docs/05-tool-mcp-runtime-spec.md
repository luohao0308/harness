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
